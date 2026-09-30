"""Analysis pipeline: camera folders + settings -> EditPlan."""

from __future__ import annotations

import os
from typing import Callable, List, Optional

from . import broll as broll_mod
from . import ffmpeg_tools as ff
from .config import JobSettings
from .multicam import envelope_loudness, plan_shots
from .planner import EditPlan, build_plan
from .silence import (TimeMap, intersect, keep_intervals, silences_from_envelope,
                      union)
from .sources import SourceClip, collect_files, estimate_starts, sequential_starts
from .sync import WINDOW, Axis, sync_camera

Log = Callable[[str], None]


def load_camera(entry: str, label: str, log: Log) -> List[SourceClip]:
    paths = collect_files(entry)
    if not paths:
        raise ValueError(f"{label}: không tìm thấy file video trong {entry}")
    clips = []
    for p in paths:
        info = ff.probe(p)
        if info.duration <= 0:
            log(f"  ! Bỏ qua {os.path.basename(p)} (không đọc được độ dài)")
            continue
        clips.append(SourceClip(p, info.duration, info.fps, info.has_audio,
                                info.has_video, info.creation_time, info.timecode))
    total = sum(c.duration for c in clips)
    log(f"{label}: {len(clips)} clip, tổng {total / 60:.1f} phút")
    return clips


def _camera_envelopes(clips: List[SourceClip], label: str, log: Log) -> None:
    for i, c in enumerate(clips, 1):
        if c.has_audio:
            log(f"  Phân tích âm thanh {label} ({i}/{len(clips)}): {c.name}")
            c.envelope = ff.loudness_envelope(c.path, WINDOW)


def _axis_envelope(clips: List[SourceClip], length: int) -> List[float]:
    env = [ff.FLOOR_DB] * length
    for c in clips:
        start = int(round(c.position / WINDOW))
        for i, v in enumerate(c.envelope):
            if 0 <= start + i < length and v > env[start + i]:
                env[start + i] = v
    return env


def analyze(job: JobSettings, fps: Optional[float] = None,
            log: Log = print) -> EditPlan:
    if not job.cameras:
        raise ValueError("Cần ít nhất 1 camera.")
    labels = [f"Cam {i + 1}" for i in range(len(job.cameras))]
    log("Đọc danh sách clip...")
    cameras = [load_camera(e, l, log) for e, l in zip(job.cameras, labels)]
    if not cameras[0]:
        raise ValueError("Cam 1 không có clip nào dùng được.")
    fps = fps or next((c.fps for c in cameras[0] if c.fps), None) or 30.0

    for clips, label in zip(cameras, labels):
        _camera_envelopes(clips, label, log)

    # --- 1) Place clips on one time axis (Cam 1 = reference) ---------------
    mc = job.multicam
    clocks = []
    for clips, label in zip(cameras, labels):
        method, starts = estimate_starts(clips)
        log(f"{label}: xếp clip theo {method}")
        clocks.append(starts)
    ref_clock = clocks[0] or sequential_starts(cameras[0])
    origin = min(ref_clock)
    for c, t in zip(cameras[0], ref_clock):
        c.position, c.synced = t - origin, True

    if len(cameras) > 1:
        axis = Axis(cameras[0])
        for clips, clock, label in zip(cameras[1:], clocks[1:], labels[1:]):
            if mc.sync == "audio":
                log(f"Đồng bộ {label} với Cam 1 theo sóng âm...")
                sync_camera(axis, clips, clock, mc.sync_window, ff.loudness_envelope,
                            label, log, origin if clocks[0] else None)
                ok = sum(c.synced for c in clips)
                log(f"  {label}: khớp {ok}/{len(clips)} clip")
            else:
                own = clock or sequential_starts(clips)
                shift = -origin if clock and clocks[0] else -min(own)
                for c, t in zip(clips, own):
                    c.position = t + shift

    # Shift so the earliest clip starts at 0 and drop what is off the axis.
    first = min(c.position for clips in cameras for c in clips)
    for clips in cameras:
        for c in clips:
            c.position -= first
    axis_end = max(c.end for clips in cameras for c in clips)
    if axis_end > 24 * 3600:
        raise ValueError("Các clip trải dài hơn 24 giờ - giờ quay của máy có thể sai; "
                         "hãy bật đồng bộ theo sóng âm.")

    # --- 2) Remove silence and the gaps between recordings -----------------
    coverage = [union([(c.position, c.end) for c in clips]) for clips in cameras]
    any_coverage = union([span for spans in coverage for span in spans])
    s = job.silence
    if s.enabled:
        n = int(axis_end / WINDOW) + 1
        combined = [max(v) for v in zip(*[_axis_envelope(clips, n) for clips in cameras])]
        silences = silences_from_envelope(combined, WINDOW, s.threshold_db, s.min_silence)
        keep = keep_intervals(silences, axis_end, s.padding, s.min_keep)
        keep = intersect(keep, any_coverage, s.min_keep)
    else:
        keep = any_coverage
    recorded = sum(e - a for a, e in any_coverage)
    kept = sum(e - a for a, e in keep)
    log(f"Cắt phần thừa: {recorded:.1f}s -> {kept:.1f}s ({len(keep)} đoạn)")
    if not keep:
        raise ValueError("Không còn đoạn nào sau khi cắt - hãy giảm ngưỡng dB.")

    # --- 3) Choose the angle ------------------------------------------------
    loudness = None
    if len(cameras) > 1 and mc.mode == "speaker":
        n = int(axis_end / WINDOW) + 1
        loudness = envelope_loudness([_axis_envelope(c, n) for c in cameras], WINDOW)
    shots = plan_shots(keep, len(cameras), mc, loudness, s.threshold_db, coverage)

    # --- 4) B-roll ----------------------------------------------------------
    placements = []
    b = job.broll
    if b.enabled and job.broll_dir:
        paths = broll_mod.list_broll(job.broll_dir)
        log(f"Tìm thấy {len(paths)} clip B-roll.")
        clips = broll_mod.load_clips(paths, [ff.probe(p).duration for p in paths])
        cues = []
        if job.srt and os.path.isfile(job.srt):
            with open(job.srt, encoding="utf-8-sig", errors="replace") as f:
                cues = broll_mod.parse_srt(f.read())
            ref_start = cameras[0][0].position if cameras[0] else 0.0
            cues = [broll_mod.Cue(c.start + ref_start, c.end + ref_start, c.text)
                    for c in cues]
            cues = broll_mod.cues_to_output(cues, TimeMap(keep))
            log(f"  Đọc {len(cues)} câu phụ đề để khớp từ khoá.")
        placements = broll_mod.plan_broll(kept, clips, b, cues)

    return build_plan(fps, keep, shots, cameras,
                      switching=len(cameras) > 1 and mc.mode != "off",
                      broll=placements)
