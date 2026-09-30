"""Choose where B-roll clips go on the edited timeline.

Two strategies, used together:
  * keyword: if a transcript (.srt) is given, a clip whose file name matches
    words being spoken is placed right there. Name clips after what they show,
    e.g. ``ca-phe.mp4`` or ``sai-gon+dem.mp4`` ("+" or "," separates phrases).
  * fill: remaining clips are spread at a regular interval.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple

from .config import BrollSettings

VIDEO_EXTS = {".mp4", ".mov", ".mxf", ".mkv", ".avi", ".m4v", ".mts", ".m2ts",
              ".webm", ".braw"}
_IGNORED = {"broll", "b", "roll", "clip", "video", "img", "dsc", "dji", "gopr",
            "mvi", "final", "copy"}


@dataclass
class BrollClip:
    path: str
    duration: float
    phrases: List[List[str]] = field(default_factory=list)


@dataclass
class Cue:
    start: float
    end: float
    text: str


@dataclass
class BrollPlacement:
    start: float        # output timeline time (s)
    duration: float
    clip: BrollClip
    source_start: float
    reason: str         # "keyword: ..." or "fill"


def normalize(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


def tokens(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", normalize(text))


def phrases_from_filename(path: str) -> List[List[str]]:
    stem = os.path.splitext(os.path.basename(path))[0]
    phrases = []
    for part in re.split(r"[+,]", stem):
        words = [w for w in tokens(part) if not w.isdigit() and w not in _IGNORED]
        if words:
            phrases.append(words)
    return phrases


def list_broll(folder: str) -> List[str]:
    if not folder or not os.path.isdir(folder):
        return []
    return sorted(
        os.path.join(folder, name) for name in os.listdir(folder)
        if os.path.splitext(name)[1].lower() in VIDEO_EXTS
        and not name.startswith(".")
    )


_TIME_RE = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)")


def _srt_time(value: str) -> float:
    h, m, s, ms = _TIME_RE.match(value.strip()).groups()
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")[:3]) / 1000


def parse_srt(text: str) -> List[Cue]:
    cues = []
    for block in re.split(r"\r?\n\s*\r?\n", text.strip().lstrip("﻿")):
        lines = [l for l in block.splitlines() if l.strip()]
        for i, line in enumerate(lines):
            if "-->" in line:
                start, end = line.split("-->", 1)
                try:
                    cues.append(Cue(_srt_time(start), _srt_time(end.split()[0]),
                                    " ".join(lines[i + 1:])))
                except (AttributeError, IndexError):
                    pass
                break
    return cues


def _contains(haystack: Sequence[str], needle: Sequence[str]) -> bool:
    n = len(needle)
    return any(list(haystack[i:i + n]) == list(needle)
               for i in range(len(haystack) - n + 1))


def match_phrase(clip: BrollClip, text: str) -> Optional[str]:
    words = tokens(text)
    for phrase in clip.phrases:
        if _contains(words, phrase):
            return " ".join(phrase)
    return None


def plan_broll(output_duration: float, clips: Sequence[BrollClip],
               settings: BrollSettings,
               cues: Iterable[Cue] = ()) -> List[BrollPlacement]:
    """`cues` must already be in output-timeline time."""
    placements: List[BrollPlacement] = []
    usage = {id(c): 0 for c in clips}
    earliest = settings.first_after
    latest = output_duration - settings.tail

    def is_free(start: float, end: float) -> bool:
        if start < earliest or end > latest:
            return False
        return all(end + settings.min_gap <= p.start
                   or start >= p.start + p.duration + settings.min_gap
                   for p in placements)

    def place(start: float, length: float, clip: BrollClip, reason: str) -> bool:
        length = min(length, clip.duration)
        if length < 0.5 or not is_free(start, start + length):
            return False
        src = max(0.0, (clip.duration - length) / 2)
        placements.append(BrollPlacement(start, length, clip, src, reason))
        usage[id(clip)] += 1
        return True

    for cue in sorted(cues, key=lambda c: c.start):
        for clip in sorted(clips, key=lambda c: usage[id(c)]):
            phrase = match_phrase(clip, cue.text)
            if not phrase:
                continue
            length = min(settings.max_duration,
                         max(settings.duration, cue.end - cue.start))
            if place(cue.start, length, clip, f"keyword: {phrase}"):
                break

    if settings.fill and clips:
        t = earliest
        while t + settings.duration <= latest:
            usable = [c for c in clips if c.duration >= 0.5]
            if not usable:
                break
            clip = min(usable, key=lambda c: usage[id(c)])
            place(t, settings.duration, clip, "fill")
            t += settings.interval

    placements.sort(key=lambda p: p.start)
    return placements


def cues_to_output(cues: Sequence[Cue], time_map) -> List[Cue]:
    """Convert transcript cues from master time to output time."""
    out = []
    for cue in cues:
        start = time_map.to_output(cue.start)
        end = time_map.to_output(cue.end)
        if start is None:
            continue
        if end is None or end < start:
            end = start + (cue.end - cue.start)
        out.append(Cue(start, end, cue.text))
    return out


def load_clips(paths: Sequence[str], durations: Sequence[float]) -> List[BrollClip]:
    return [BrollClip(p, d, phrases_from_filename(p)) for p, d in zip(paths, durations)]


def summarize(placements: Sequence[BrollPlacement]) -> List[Tuple[float, str, str]]:
    return [(p.start, os.path.basename(p.clip.path), p.reason) for p in placements]
