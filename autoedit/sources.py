"""Camera sources: a folder of clips per camera, placed on one time axis.

Each clip's recording time is estimated from (in order of preference) a date
in its file name (DJI, phones), its creation_time metadata, or its timecode.
Audio sync (sync.py) then corrects the estimate.
"""

from __future__ import annotations

import calendar
import os
import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

from .broll import VIDEO_EXTS

_SKIP_DIRS = {"proxy", "proxies", "optimized media", "cachefiles", "cache",
              "$recycle.bin", ".trash", ".trashes"}
_NAME_TIME_RE = re.compile(
    r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})[-_T ]?(\d{2})[-_:.]?(\d{2})[-_:.]?(\d{2})")
_ISO_RE = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?")
_TC_RE = re.compile(r"(\d{1,2})[:;.](\d{2})[:;.](\d{2})[:;.](\d{2})")


@dataclass
class SourceClip:
    path: str
    duration: float
    fps: Optional[float] = None
    has_audio: bool = True
    has_video: bool = True
    creation_time: Optional[str] = None
    timecode: Optional[str] = None
    position: float = 0.0          # start on the shared time axis (s)
    synced: bool = False           # position confirmed by audio
    envelope: List[float] = field(default_factory=list)  # dB per analysis window

    @property
    def end(self) -> float:
        return self.position + self.duration

    @property
    def name(self) -> str:
        return os.path.basename(self.path)


def _natural_key(text: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", text)]


def collect_files(entry: str) -> List[str]:
    """Video files for one camera entry (a file, or a folder searched recursively)."""
    if os.path.isfile(entry):
        return [entry]
    if not os.path.isdir(entry):
        return []
    found = []
    for root, dirs, files in os.walk(entry):
        dirs[:] = [d for d in dirs if d.lower() not in _SKIP_DIRS and not d.startswith(".")]
        for name in files:
            if name.startswith(".") or os.path.splitext(name)[1].lower() not in VIDEO_EXTS:
                continue
            found.append(os.path.join(root, name))
    return sorted(found, key=lambda p: _natural_key(os.path.relpath(p, entry)))


def _timegm(y, mo, d, h, mi, s) -> Optional[float]:
    try:
        y, mo, d, h, mi, s = (int(v) for v in (y, mo, d, h, mi, s))
    except (TypeError, ValueError):
        return None
    if not (1 <= mo <= 12 and 1 <= d <= 31 and h < 24 and mi < 60 and s < 61):
        return None
    return float(calendar.timegm((y, mo, d, h, mi, s, 0, 0, 0)))


def filename_time(path: str) -> Optional[float]:
    m = _NAME_TIME_RE.search(os.path.basename(path))
    return _timegm(*m.groups()) if m else None


def creation_seconds(value: Optional[str]) -> Optional[float]:
    m = _ISO_RE.match(value or "")
    if not m:
        return None
    base = _timegm(*m.groups()[:6])
    if base is None or int(m.group(1)) < 1971:
        return None
    frac = float("0." + m.group(7)) if m.group(7) else 0.0
    return base + frac


def timecode_seconds(value: Optional[str], fps: Optional[float]) -> Optional[float]:
    m = _TC_RE.match(value or "")
    if not m:
        return None
    h, mi, s, f = (int(v) for v in m.groups())
    return h * 3600 + mi * 60 + s + (f / fps if fps else 0.0)


_METHODS: List[Tuple[str, Callable[[SourceClip], Optional[float]]]] = [
    ("tên file", lambda c: filename_time(c.path)),
    ("creation_time", lambda c: creation_seconds(c.creation_time)),
    ("timecode", lambda c: timecode_seconds(c.timecode, c.fps)),
]


def _overlaps(starts: Sequence[float], clips: Sequence[SourceClip]) -> float:
    spans = sorted(zip(starts, (c.duration for c in clips)))
    total = 0.0
    for (s1, d1), (s2, _) in zip(spans, spans[1:]):
        total += max(0.0, s1 + d1 - s2)
    return total


def estimate_starts(clips: Sequence[SourceClip]) -> Tuple[str, Optional[List[float]]]:
    """Recording start per clip on this camera's own clock.

    Returns (method, starts); starts is None when no clock information is
    shared by all clips. Some cameras stamp the *end* of a recording, so both
    readings are tried and the one with fewer overlapping clips wins.
    """
    for name, fn in _METHODS:
        values = [fn(c) for c in clips]
        if clips and all(v is not None for v in values):
            as_end = [v - c.duration for v, c in zip(values, clips)]
            if _overlaps(as_end, clips) + 0.5 < _overlaps(values, clips):
                return name + " (thời điểm kết thúc)", as_end
            return name, values
    return "thứ tự file", None


def sequential_starts(clips: Sequence[SourceClip]) -> List[float]:
    starts, t = [], 0.0
    for c in clips:
        starts.append(t)
        t += c.duration
    return starts
