"""Thin wrappers around ffmpeg/ffprobe used for audio analysis.

Only the standard library is used so the code also runs inside the Python
interpreter DaVinci Resolve launches for scripts.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Tuple

SILENCE_START_RE = re.compile(r"silence_start:\s*(-?[\d.]+)")
SILENCE_END_RE = re.compile(r"silence_end:\s*(-?[\d.]+)")
RMS_RE = re.compile(r"lavfi\.astats\.Overall\.RMS_level=(-?inf|nan|-?[\d.]+)")

FLOOR_DB = -120.0

_EXTRA_DIRS = [
    r"C:\ffmpeg\bin",
    r"C:\Program Files\ffmpeg\bin",
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/bin",
]


class FFmpegError(RuntimeError):
    pass


def find_binary(name: str) -> str:
    """Locate ffmpeg/ffprobe via $AUTOEDIT_FFMPEG_DIR, PATH or common folders."""
    exe = name + (".exe" if os.name == "nt" else "")
    custom = os.environ.get("AUTOEDIT_FFMPEG_DIR")
    if custom and os.path.isfile(os.path.join(custom, exe)):
        return os.path.join(custom, exe)
    found = shutil.which(name)
    if found:
        return found
    for folder in _EXTRA_DIRS:
        candidate = os.path.join(folder, exe)
        if os.path.isfile(candidate):
            return candidate
    raise FFmpegError(
        f"Không tìm thấy {name}. Hãy cài ffmpeg và thêm vào PATH "
        f"hoặc đặt biến môi trường AUTOEDIT_FFMPEG_DIR."
    )


def _run(args: List[str]) -> subprocess.CompletedProcess:
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    proc = subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        **kwargs,
    )
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-5:])
        raise FFmpegError(f"{os.path.basename(args[0])} lỗi:\n{tail}")
    return proc


@dataclass
class MediaInfo:
    path: str
    duration: float
    fps: Optional[float]
    has_video: bool
    has_audio: bool


def _parse_rate(rate: Optional[str]) -> Optional[float]:
    if not rate or rate in ("0/0", "0"):
        return None
    if "/" in rate:
        num, den = rate.split("/", 1)
        try:
            den_f = float(den)
            return float(num) / den_f if den_f else None
        except ValueError:
            return None
    try:
        return float(rate)
    except ValueError:
        return None


def parse_probe(path: str, data: dict) -> MediaInfo:
    streams = data.get("streams", [])
    video = [s for s in streams if s.get("codec_type") == "video"
             and not s.get("disposition", {}).get("attached_pic")]
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    fps = None
    if video:
        fps = _parse_rate(video[0].get("avg_frame_rate")) or _parse_rate(
            video[0].get("r_frame_rate"))
    duration = float(data.get("format", {}).get("duration") or 0.0)
    if not duration:
        for s in streams:
            if s.get("duration"):
                duration = max(duration, float(s["duration"]))
    return MediaInfo(path, duration, fps, bool(video), bool(audio))


def probe(path: str) -> MediaInfo:
    proc = _run([
        find_binary("ffprobe"), "-v", "error",
        "-show_entries",
        "format=duration:stream=codec_type,avg_frame_rate,r_frame_rate,duration"
        ":stream_disposition=attached_pic",
        "-of", "json", path,
    ])
    return parse_probe(path, json.loads(proc.stdout or "{}"))


def parse_silencedetect(log: str, duration: float) -> List[Tuple[float, float]]:
    """Turn ffmpeg silencedetect log output into (start, end) pairs."""
    silences = []
    start = None
    for line in log.splitlines():
        m = SILENCE_START_RE.search(line)
        if m:
            start = max(0.0, float(m.group(1)))
            continue
        m = SILENCE_END_RE.search(line)
        if m and start is not None:
            silences.append((start, float(m.group(1))))
            start = None
    if start is not None:  # silence runs to the end of the file
        silences.append((start, duration))
    return silences


def detect_silence(path: str, threshold_db: float, min_silence: float,
                   duration: float) -> List[Tuple[float, float]]:
    proc = _run([
        find_binary("ffmpeg"), "-hide_banner", "-nostats", "-i", path,
        "-vn", "-sn", "-dn",
        "-af", f"silencedetect=noise={threshold_db}dB:d={min_silence}",
        "-f", "null", "-",
    ])
    return parse_silencedetect(proc.stderr, duration)


def parse_rms_log(log: str) -> List[float]:
    values = []
    for m in RMS_RE.finditer(log):
        raw = m.group(1)
        if raw in ("-inf", "inf", "nan"):
            values.append(FLOOR_DB)
        else:
            values.append(max(FLOOR_DB, float(raw)))
    return values


def loudness_envelope(path: str, window: float,
                      limit: Optional[float] = None) -> List[float]:
    """RMS level in dB for every `window` seconds of the file's audio."""
    rate = 16000
    samples = max(1, int(round(rate * window)))
    args = [find_binary("ffmpeg"), "-hide_banner", "-nostats"]
    if limit:
        args += ["-t", f"{limit:.3f}"]
    args += [
        "-i", path, "-vn", "-sn", "-dn",
        "-af",
        f"aformat=channel_layouts=mono,aresample={rate},"
        f"asetnsamples=n={samples}:p=0,astats=metadata=1:reset=1,"
        "ametadata=mode=print:key=lavfi.astats.Overall.RMS_level",
        "-f", "null", "-",
    ]
    return parse_rms_log(_run(args).stderr)
