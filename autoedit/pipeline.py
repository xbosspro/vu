"""Analysis pipeline: media files + settings -> EditPlan."""

from __future__ import annotations

import os
from typing import Callable, List, Optional

from . import broll as broll_mod
from . import ffmpeg_tools as ff
from .config import JobSettings
from .multicam import envelope_loudness, plan_shots
from .planner import EditPlan, build_plan
from .silence import TimeMap, keep_intervals
from .sync import find_offset

Log = Callable[[str], None]
SPEAKER_WINDOW = 0.1


def _name(path: str) -> str:
    return os.path.basename(path)


def analyze(job: JobSettings, fps: Optional[float] = None,
            log: Log = print) -> EditPlan:
    if not job.cameras:
        raise ValueError("Cần ít nhất 1 file camera.")
    for path in job.cameras + ([job.audio] if job.audio else []):
        if not os.path.isfile(path):
            raise FileNotFoundError(path)

    master = job.master_audio
    log(f"Đọc thông tin media...")
    cam_info = [ff.probe(p) for p in job.cameras]
    master_info = ff.probe(master) if job.audio else cam_info[0]
    if not master_info.has_audio:
        raise ValueError(f"{_name(master)} không có âm thanh.")
    fps = fps or cam_info[0].fps or 30.0

    # 1) Silence removal on the master audio.
    s = job.silence
    log(f"Phát hiện khoảng lặng ({s.threshold_db} dB, ≥{s.min_silence}s)...")
    silences = ff.detect_silence(master, s.threshold_db, s.min_silence,
                                 master_info.duration)
    intervals = keep_intervals(silences, master_info.duration, s.padding, s.min_keep)
    kept = sum(e - a for a, e in intervals)
    log(f"  Giữ {len(intervals)} đoạn: {master_info.duration:.1f}s -> {kept:.1f}s "
        f"(bỏ {master_info.duration - kept:.1f}s)")
    if not intervals:
        raise ValueError("Toàn bộ file bị coi là im lặng - hãy giảm ngưỡng dB.")

    # 2) Sync cameras to the master audio.
    mc = job.multicam
    offsets: List[float] = []
    for path, info in zip(job.cameras, cam_info):
        if os.path.abspath(path) == os.path.abspath(master) or mc.sync != "audio":
            offsets.append(0.0)
        elif not info.has_audio:
            log(f"  {_name(path)} không có âm thanh, không sync được - dùng offset 0.")
            offsets.append(0.0)
        else:
            log(f"Đồng bộ {_name(path)} theo sóng âm...")
            off = find_offset(ff.loudness_envelope, master, path,
                              mc.sync_analyze, mc.sync_max_offset)
            log(f"  lệch {off:+.2f}s")
            offsets.append(off)

    # 3) Camera switching.
    loudness = None
    if len(job.cameras) > 1 and mc.mode == "speaker":
        log("Đo âm lượng từng camera để nhận diện người nói...")
        envs = [ff.loudness_envelope(p, SPEAKER_WINDOW) if i.has_audio else []
                for p, i in zip(job.cameras, cam_info)]
        loudness = envelope_loudness(envs, offsets, SPEAKER_WINDOW)
    shots = plan_shots(intervals, len(job.cameras), mc, loudness, s.threshold_db)
    if len(job.cameras) > 1:
        log(f"  {len(shots)} shot, chế độ đảo camera: {mc.mode}")

    # 4) B-roll.
    placements = []
    b = job.broll
    if b.enabled and job.broll_dir:
        paths = broll_mod.list_broll(job.broll_dir)
        log(f"Tìm thấy {len(paths)} clip B-roll.")
        durations = [ff.probe(p).duration for p in paths]
        clips = broll_mod.load_clips(paths, durations)
        cues = []
        if job.srt and os.path.isfile(job.srt):
            with open(job.srt, encoding="utf-8-sig", errors="replace") as f:
                cues = broll_mod.parse_srt(f.read())
            cues = broll_mod.cues_to_output(cues, TimeMap(intervals))
            log(f"  Đọc {len(cues)} câu phụ đề để khớp từ khóa.")
        placements = broll_mod.plan_broll(kept, clips, b, cues)
        for start, name, reason in broll_mod.summarize(placements):
            log(f"  {start:7.1f}s  {name}  [{reason}]")

    return build_plan(fps, intervals, shots, master, job.cameras, offsets,
                      [i.duration for i in cam_info], placements, b.track)
