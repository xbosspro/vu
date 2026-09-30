"""Frame-accurate edit plan, independent of DaVinci Resolve.

All timeline positions are integer frames at the timeline frame rate, so the
video shots and the continuous master audio line up without gaps.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Sequence, Tuple

from .broll import BrollPlacement
from .multicam import Shot

VIDEO_ONLY = 1
AUDIO_ONLY = 2


@dataclass
class ClipEvent:
    kind: str           # "camera" | "audio" | "broll"
    path: str
    track: int
    media_type: int     # VIDEO_ONLY / AUDIO_ONLY
    record_frame: int   # offset from the start of the timeline
    duration: int       # timeline frames
    source_start: float  # seconds into the source file


@dataclass
class EditPlan:
    fps: float
    total_frames: int
    events: List[ClipEvent] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def by_kind(self, kind: str) -> List[ClipEvent]:
        return [e for e in self.events if e.kind == kind]

    def to_dict(self) -> dict:
        return asdict(self)


def _covers(offset: float, duration: Optional[float], start: float, end: float) -> bool:
    if duration is None:
        return True
    return start + offset >= -1e-6 and end + offset <= duration + 0.05


def build_plan(fps: float, intervals: Sequence[Tuple[float, float]],
               shots: Sequence[Shot], audio_path: str, cameras: Sequence[str],
               offsets: Sequence[float], camera_durations: Sequence[Optional[float]],
               broll: Sequence[BrollPlacement] = (), broll_track: int = 2) -> EditPlan:
    to_f = lambda t: int(round(t * fps))

    # Snap kept segments to the frame grid and lay them end to end.
    seg_frames = []
    out = 0
    for s, e in intervals:
        a, b = to_f(s), to_f(e)
        seg_frames.append((a, b, out))
        if b > a:
            out += b - a
    plan = EditPlan(fps=fps, total_frames=out)

    for a, b, rec in seg_frames:
        if b > a:
            plan.events.append(ClipEvent("audio", audio_path, 1, AUDIO_ONLY,
                                         rec, b - a, a / fps))

    fallback_count = 0
    for shot in shots:
        a, b, rec = seg_frames[shot.interval]
        sa, sb = max(a, to_f(shot.start)), min(b, to_f(shot.end))
        if sb <= sa:
            continue
        start_s, end_s = sa / fps, sb / fps
        cam = shot.camera
        if not _covers(offsets[cam], camera_durations[cam], start_s, end_s):
            others = [c for c in range(len(cameras))
                      if _covers(offsets[c], camera_durations[c], start_s, end_s)]
            if others:
                cam = others[0]
                fallback_count += 1
        prev = plan.events[-1] if plan.events else None
        record = rec + (sa - a)
        if (prev and prev.kind == "camera" and prev.path == cameras[cam]
                and prev.record_frame + prev.duration == record
                and abs(prev.source_start + prev.duration / fps
                        - (start_s + offsets[cam])) < 0.5 / fps):
            prev.duration += sb - sa
            continue
        plan.events.append(ClipEvent("camera", cameras[cam], 1, VIDEO_ONLY,
                                     record, sb - sa, start_s + offsets[cam]))
    if fallback_count:
        plan.notes.append(
            f"{fallback_count} shot dùng góc máy khác vì camera đã chọn không quay đoạn đó.")

    for p in broll:
        rec = to_f(p.start)
        dur = min(to_f(p.duration), plan.total_frames - rec)
        if dur > 0:
            plan.events.append(ClipEvent("broll", p.clip.path, broll_track,
                                         VIDEO_ONLY, rec, dur, p.source_start))
    return plan


def describe(plan: EditPlan) -> str:
    def tc(frames: int) -> str:
        secs = frames / plan.fps
        return f"{int(secs // 60):02d}:{secs % 60:05.2f}"

    lines = [f"Độ dài timeline: {tc(plan.total_frames)} @ {plan.fps:g} fps"]
    for e in sorted(plan.events, key=lambda e: (e.record_frame, e.track)):
        if e.kind == "audio":
            continue
        lines.append(f"  {tc(e.record_frame)}  V{e.track}  {e.kind:<6} "
                     f"{os.path.basename(e.path)}  ({e.duration / plan.fps:.1f}s)")
    lines.extend(plan.notes)
    return "\n".join(lines)
