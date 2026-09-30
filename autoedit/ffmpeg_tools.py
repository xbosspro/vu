"""Thin wrappers around ffmpeg/ffprobe used for audio analysis.

Only the standard library is used so the code also runs inside the Python
interpreter DaVinci Resolve launches for scripts.
"""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional

RMS_RE = re.compile(r"lavfi\.astats\.Overall\.RMS_level=(-?inf|nan|-?[\d.]+)")

FLOOR_DB = -120.0

_REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _candidate_dirs() -> List[str]:
    """Folders where ffmpeg is commonly installed (PATH is often stale in Resolve)."""
    dirs = [os.path.join(_REPO_DIR, "ffmpeg", "bin"), os.path.join(_REPO_DIR, "ffmpeg")]
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "")
        home = os.path.expanduser("~")
        dirs += [
            r"C:\ffmpeg\bin",
            r"C:\Program Files\ffmpeg\bin",
            os.path.join(local, "Microsoft", "WinGet", "Links"),
            os.path.join(home, "scoop", "shims"),
            r"C:\ProgramData\chocolatey\bin",
        ]
        # winget (Gyan.FFmpeg) unpacks into ...\Packages\Gyan.FFmpeg*\ffmpeg-*\bin
        dirs += glob.glob(os.path.join(local, "Microsoft", "WinGet", "Packages",
                                       "*FFmpeg*", "*", "bin"))
        dirs += glob.glob(r"C:\ffmpeg*\bin") + glob.glob(r"C:\ffmpeg*\*\bin")
    else:
        dirs += ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"]
    return dirs


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
    for folder in _candidate_dirs():
        candidate = os.path.join(folder, exe)
        if os.path.isfile(candidate):
            return candidate
    raise FFmpegError(
        f"Không tìm thấy {name}.\n\n"
        f"Cách nhanh nhất: tải ffmpeg (bản 'release essentials' tại "
        f"https://www.gyan.dev/ffmpeg/builds/), giải nén rồi đổi tên thư mục "
        f"thành 'ffmpeg' và đặt vào:\n{_REPO_DIR}\n"
        f"(sao cho có file {os.path.join(_REPO_DIR, 'ffmpeg', 'bin', exe)}).\n\n"
        f"Hoặc mở Command Prompt chạy: winget install Gyan.FFmpeg "
        f"rồi khởi động lại DaVinci Resolve."
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
    creation_time: Optional[str] = None
    timecode: Optional[str] = None


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
    fmt = data.get("format", {})
    duration = float(fmt.get("duration") or 0.0)
    if not duration:
        for s in streams:
            if s.get("duration"):
                duration = max(duration, float(s["duration"]))
    creation = (fmt.get("tags") or {}).get("creation_time")
    timecode = (fmt.get("tags") or {}).get("timecode")
    for s in streams:
        tags = s.get("tags") or {}
        creation = creation or tags.get("creation_time")
        timecode = timecode or tags.get("timecode")
    return MediaInfo(path, duration, fps, bool(video), bool(audio), creation, timecode)


def probe(path: str) -> MediaInfo:
    proc = _run([
        find_binary("ffprobe"), "-v", "error",
        "-show_entries",
        "format=duration:format_tags=creation_time,timecode"
        ":stream=codec_type,avg_frame_rate,r_frame_rate,duration"
        ":stream_tags=creation_time,timecode:stream_disposition=attached_pic",
        "-of", "json", path,
    ])
    return parse_probe(path, json.loads(proc.stdout or "{}"))


def parse_rms_log(log: str) -> List[float]:
    values = []
    for m in RMS_RE.finditer(log):
        raw = m.group(1)
        if raw in ("-inf", "inf", "nan"):
            values.append(FLOOR_DB)
        else:
            values.append(max(FLOOR_DB, float(raw)))
    return values


def loudness_envelope(path: str, window: float, limit: Optional[float] = None,
                      start: Optional[float] = None) -> List[float]:
    """RMS level in dB for every `window` seconds of the file's audio."""
    rate = 16000
    samples = max(1, int(round(rate * window)))
    args = [find_binary("ffmpeg"), "-hide_banner", "-nostats"]
    if start:
        args += ["-ss", f"{start:.3f}"]
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
