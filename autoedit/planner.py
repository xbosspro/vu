"""Frame-accurate edit plan, independent of DaVinci Resolve.

Layout: camera k (1-based) goes to video track Vk and audio track Ak; B-roll
goes to the track above the last camera. When angle switching is on, every
camera keeps all its synced footage, but a camera's video is disabled
wherever a lower-numbered camera is the chosen angle - so the chosen angle is
always the top enabled layer and any angle can be re-enabled by hand.
"""

from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass, field
from typing import List, Sequence, Tuple

from .broll import BrollPlacement
from .multicam import Shot
from .sources import SourceClip

VIDEO_ONLY = 1
AUDIO_ONLY = 2


@dataclass
class ClipEvent:
    kind: str            # "camera" | "audio" | "broll"
    path: str
    track: int
    media_type: int      # VIDEO_ONLY / AUDIO_ONLY
    record_frame: int    # offset from the start of the timeline
    duration: int        # timeline frames
    source_start: float  # seconds into the source file
    enabled: bool = True
    camera: int = 0      # 0-based camera index (camera/audio events)


@dataclass
class EditPlan:
    fps: float
    total_frames: int
    num_cameras: int = 1
    events: List[ClipEvent] = field(default_factory=list)
    shots: List[Tuple[int, int, int]] = field(default_factory=list)  # (record, frames, cam)
    notes: List[str] = field(default_factory=list)

    def by_kind(self, kind: str) -> List[ClipEvent]:
        return [e for e in self.events if e.kind == kind]

    def to_dict(self) -> dict:
        return asdict(self)


def build_plan(fps: float, intervals: Sequence[Tuple[float, float]],
               shots: Sequence[Shot], cameras: Sequence[Sequence[SourceClip]],
               switching: bool = True, broll: Sequence[BrollPlacement] = ()) -> EditPlan:
    to_f = lambda t: int(round(t * fps))
    n = len(cameras)

    segs = []  # (axis_first_frame, axis_end_frame, record_frame)
    out = 0
    for s, e in intervals:
        a, b = to_f(s), to_f(e)
        segs.append((a, b, out))
        out += max(0, b - a)
    plan = EditPlan(fps=fps, total_frames=out, num_cameras=n)

    shot_frames: List[List[Tuple[int, int, int]]] = [[] for _ in segs]
    for sh in shots:
        a, b, rec = segs[sh.interval]
        sa, sb = max(a, to_f(sh.start)), min(b, to_f(sh.end))
        if sb > sa:
            shot_frames[sh.interval].append((sa, sb, sh.camera))
            plan.shots.append((rec + sa - a, sb - sa, sh.camera))

    for cam, clips in enumerate(cameras):
        track = cam + 1
        for clip in clips:
            ca = int(math.ceil(clip.position * fps - 1e-6))
            cb = int(math.floor(clip.end * fps + 1e-6))
            for k, (a, b, rec) in enumerate(segs):
                x, y = max(a, ca), min(b, cb)
                if y <= x:
                    continue
                src = lambda f: f / fps - clip.position
                if clip.has_audio:
                    plan.events.append(ClipEvent("audio", clip.path, track, AUDIO_ONLY,
                                                 rec + x - a, y - x, src(x), True, cam))
                if not clip.has_video:
                    continue
                # split the video where this camera's enabled state changes
                cuts = {x, y}
                for sa, sb, _ in shot_frames[k]:
                    cuts.update(f for f in (sa, sb) if x < f < y)
                edges = sorted(cuts)
                for p, q in zip(edges, edges[1:]):
                    chosen = [c for sa, sb, c in shot_frames[k] if sa <= p < sb]
                    enabled = not switching or not chosen or cam <= chosen[0]
                    prev = plan.events[-1] if plan.events else None
                    if (prev and prev.kind == "camera" and prev.path == clip.path
                            and prev.enabled == enabled
                            and prev.record_frame + prev.duration == rec + p - a
                            and abs(prev.source_start + prev.duration / fps - src(p))
                            < 0.5 / fps):
                        prev.duration += q - p
                        continue
                    plan.events.append(ClipEvent("camera", clip.path, track, VIDEO_ONLY,
                                                 rec + p - a, q - p, src(p), enabled, cam))

    broll_track = n + 1
    for p in broll:
        rec = to_f(p.start)
        dur = min(to_f(p.duration), plan.total_frames - rec)
        if dur > 0:
            plan.events.append(ClipEvent("broll", p.clip.path, broll_track,
                                         VIDEO_ONLY, rec, dur, p.source_start))
    return plan


def describe(plan: EditPlan, max_lines: int = 40) -> str:
    def tc(frames: int) -> str:
        secs = frames / plan.fps
        return f"{int(secs // 3600):d}:{int(secs % 3600 // 60):02d}:{secs % 60:05.2f}"

    lines = [f"Độ dài timeline: {tc(plan.total_frames)} @ {plan.fps:g} fps"]
    for cam in range(plan.num_cameras):
        vids = [e for e in plan.events if e.kind == "camera" and e.camera == cam]
        shown = sum(f for _, f, c in plan.shots if c == cam)
        lines.append(f"  Cam {cam + 1}: V{cam + 1}/A{cam + 1}, {len(vids)} đoạn, "
                     f"được chọn {shown / plan.fps:.1f}s")
    brolls = plan.by_kind("broll")
    if brolls:
        lines.append(f"  B-roll: V{plan.num_cameras + 1}, {len(brolls)} đoạn")
    if plan.num_cameras > 1 and plan.shots:
        lines.append("Góc máy:")
        for rec, frames, cam in plan.shots[:max_lines]:
            lines.append(f"  {tc(rec)}  Cam {cam + 1}  ({frames / plan.fps:.1f}s)")
        if len(plan.shots) > max_lines:
            lines.append(f"  ... và {len(plan.shots) - max_lines} shot nữa")
    for e in brolls[:max_lines]:
        lines.append(f"  {tc(e.record_frame)}  B-roll {os.path.basename(e.path)}")
    lines.extend(plan.notes)
    return "\n".join(lines)
