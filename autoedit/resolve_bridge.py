"""Build an EditPlan as a real timeline inside DaVinci Resolve.

Works in two ways:
  * inside Resolve (Workspace > Scripts > AutoEdit) - Free and Studio;
  * from an external Python/terminal - Resolve Studio only (Resolve must be
    running and "External scripting using: Local" enabled in Preferences).
"""

from __future__ import annotations

import os
import sys
from typing import Callable, Dict, Iterable, List, Optional

from .planner import ClipEvent, EditPlan

Log = Callable[[str], None]


class ResolveError(RuntimeError):
    pass


def _module_dirs() -> List[str]:
    if sys.platform.startswith("win"):
        base = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        return [os.path.join(base, "Blackmagic Design", "DaVinci Resolve",
                             "Support", "Developer", "Scripting", "Modules")]
    if sys.platform == "darwin":
        return ["/Library/Application Support/Blackmagic Design/DaVinci Resolve/"
                "Developer/Scripting/Modules"]
    return ["/opt/resolve/Developer/Scripting/Modules",
            "/home/resolve/Developer/Scripting/Modules"]


def _script_lib() -> Optional[str]:
    if sys.platform.startswith("win"):
        base = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        path = os.path.join(base, "Blackmagic Design", "DaVinci Resolve",
                            "fusionscript.dll")
    elif sys.platform == "darwin":
        path = ("/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/"
                "Libraries/Fusion/fusionscript.so")
    else:
        path = "/opt/resolve/libs/Fusion/fusionscript.so"
    return path if os.path.exists(path) else None


def get_resolve(hint: Optional[dict] = None):
    """Return the Resolve scripting object.

    `hint` is the globals() of a script launched from Resolve's Scripts menu,
    where Resolve injects `resolve`, `app` or `bmd`.
    """
    hint = hint or {}
    if hint.get("resolve") is not None:
        return hint["resolve"]
    for key in ("app", "fusion"):
        obj = hint.get(key)
        if obj is not None and hasattr(obj, "GetResolve"):
            res = obj.GetResolve()
            if res:
                return res
    bmd = hint.get("bmd")
    if bmd is not None:
        res = bmd.scriptapp("Resolve")
        if res:
            return res

    if not os.environ.get("RESOLVE_SCRIPT_LIB") and _script_lib():
        os.environ["RESOLVE_SCRIPT_LIB"] = _script_lib()
    try:
        import DaVinciResolveScript as dvr  # type: ignore
    except ImportError:
        for folder in _module_dirs():
            if os.path.isdir(folder) and folder not in sys.path:
                sys.path.append(folder)
        try:
            import DaVinciResolveScript as dvr  # type: ignore
        except ImportError as exc:
            raise ResolveError(
                "Không tìm thấy module DaVinciResolveScript. "
                "Hãy cài DaVinci Resolve hoặc chạy AutoEdit từ menu "
                "Workspace > Scripts trong Resolve.") from exc
    res = dvr.scriptapp("Resolve")
    if not res:
        raise ResolveError(
            "Không kết nối được DaVinci Resolve. Hãy mở Resolve trước. "
            "Bản Free chỉ cho chạy script từ menu Workspace > Scripts; "
            "bản Studio cần bật Preferences > System > General > "
            "External scripting using: Local.")
    return res


def _as_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class ResolveBuilder:
    def __init__(self, resolve, log: Log = print):
        self.resolve = resolve
        self.log = log
        self.project = resolve.GetProjectManager().GetCurrentProject()
        if not self.project:
            raise ResolveError("Hãy mở một project trong DaVinci Resolve.")
        self.media_pool = self.project.GetMediaPool()
        self.end_inclusive: Optional[bool] = None

    # ---------------------------------------------------------------- setup
    def timeline_fps(self, fallback: Optional[float] = None) -> float:
        """Project timeline fps; set it from the footage on an empty project."""
        if fallback and self.project.GetTimelineCount() == 0:
            value = f"{fallback:.3f}".rstrip("0").rstrip(".")
            if self.project.SetSetting("timelineFrameRate", value):
                self.log(f"Đặt timeline frame rate của project = {value}")
        return _as_float(self.project.GetSetting("timelineFrameRate"),
                         fallback or 30.0)

    def _walk(self, folder) -> Iterable:
        for clip in folder.GetClipList() or []:
            yield clip
        for sub in folder.GetSubFolderList() or []:
            yield from self._walk(sub)

    def import_media(self, paths: Iterable[str]) -> Dict[str, object]:
        wanted = {os.path.normcase(os.path.abspath(p)): p for p in paths}
        found: Dict[str, object] = {}
        for clip in self._walk(self.media_pool.GetRootFolder()):
            key = os.path.normcase(os.path.abspath(clip.GetClipProperty("File Path") or "."))
            if key in wanted and wanted[key] not in found:
                found[wanted[key]] = clip

        missing = [p for p in wanted.values() if p not in found]
        if missing:
            root = self.media_pool.GetRootFolder()
            folder = next((f for f in root.GetSubFolderList() or []
                           if f.GetName() == "AutoEdit"), None)
            folder = folder or self.media_pool.AddSubFolder(root, "AutoEdit")
            if folder:
                self.media_pool.SetCurrentFolder(folder)
            for path in missing:
                items = self.media_pool.ImportMedia([path]) or []
                if not items:
                    raise ResolveError(f"Resolve không import được: {path}")
                found[path] = items[0]
            self.log(f"Đã import {len(missing)} file vào Media Pool (thư mục AutoEdit).")
        return found

    def _unique_name(self, name: str) -> str:
        existing = {self.project.GetTimelineByIndex(i).GetName()
                    for i in range(1, self.project.GetTimelineCount() + 1)}
        candidate, n = name, 2
        while candidate in existing:
            candidate, n = f"{name} {n}", n + 1
        return candidate

    # ---------------------------------------------------------------- build
    def _clip_info(self, event: ClipEvent, item, fps: float, start: int) -> dict:
        clip_fps = _as_float(item.GetClipProperty("FPS"), fps) or fps
        src_start = int(round(event.source_start * clip_fps))
        src_len = max(1, int(round(event.duration * clip_fps / fps)))
        end = src_start + src_len - (1 if self.end_inclusive else 0)
        return {
            "mediaPoolItem": item,
            "startFrame": src_start,
            "endFrame": end,
            "mediaType": event.media_type,
            "trackIndex": event.track,
            "recordFrame": start + event.record_frame,
        }

    def _calibrate(self, timeline, event: ClipEvent, item, fps: float, start: int):
        """Find out whether this Resolve version treats endFrame as inclusive."""
        self.end_inclusive = False
        placed = self.media_pool.AppendToTimeline(
            [self._clip_info(event, item, fps, start)]) or []
        if placed:
            got = placed[0].GetDuration()
            self.end_inclusive = got == event.duration + 1
            timeline.DeleteClips(placed, False)

    def build(self, plan: EditPlan, name: str) -> object:
        items = self.import_media({e.path for e in plan.events})
        timeline = self.media_pool.CreateEmptyTimeline(self._unique_name(name))
        if not timeline:
            raise ResolveError("Không tạo được timeline mới.")
        self.project.SetCurrentTimeline(timeline)
        start = timeline.GetStartFrame()

        tracks = max((e.track for e in plan.events if e.media_type == 1), default=1)
        while timeline.GetTrackCount("video") < tracks:
            if not timeline.AddTrack("video"):
                break

        events = sorted(plan.events, key=lambda e: (e.kind != "camera", e.record_frame))
        if events:
            self._calibrate(timeline, events[0], items[events[0].path], plan.fps, start)

        infos = [self._clip_info(e, items[e.path], plan.fps, start) for e in events]
        placed = 0
        for i in range(0, len(infos), 200):
            result = self.media_pool.AppendToTimeline(infos[i:i + 200]) or []
            placed += len(result)
        if placed < len(infos):
            self.log(f"Cảnh báo: chỉ đặt được {placed}/{len(infos)} clip lên timeline.")
        self.log(f"Đã tạo timeline '{timeline.GetName()}' với {placed} clip.")
        return timeline
