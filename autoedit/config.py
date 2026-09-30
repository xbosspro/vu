"""Settings for an AutoEdit job."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from typing import List, Optional


@dataclass
class SilenceSettings:
    enabled: bool = True
    threshold_db: float = -35.0   # quieter than this on every camera = silence
    min_silence: float = 0.5      # silence must last this long (s) to be cut
    padding: float = 0.12         # kept before/after each cut (s)
    min_keep: float = 0.3         # drop fragments shorter than this (s)


@dataclass
class MulticamSettings:
    mode: str = "rhythm"          # "speaker" | "rhythm" | "off"
    min_shot: float = 2.0         # never switch before a shot lasts this long (s)
    max_shot: float = 8.0         # force a switch after this long (s)
    wide_camera: Optional[int] = None  # index of the wide angle, if any
    margin_db: float = 3.0        # speaker mode: loudest mic must win by this much
    hide_jump_cuts: bool = True   # speaker mode: cut to wide on jump cuts
    sync: str = "audio"           # "audio" = sync by waveform, "none" = by clock only
    sync_window: float = 20.0     # search +- this around the clock estimate (s)


@dataclass
class BrollSettings:
    enabled: bool = True
    fill: bool = True             # place B-roll at a regular interval
    interval: float = 12.0        # seconds between B-roll inserts
    duration: float = 3.0         # default length of an insert (s)
    max_duration: float = 6.0     # longest insert when matched to a subtitle
    first_after: float = 5.0      # keep the opening on the cameras (s)
    tail: float = 2.0             # keep the ending on the cameras (s)
    min_gap: float = 4.0          # minimum gap between inserts (s)


def _build(cls, data: dict):
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in (data or {}).items() if k in names})


@dataclass
class JobSettings:
    # One entry per camera: a folder (all videos inside, including subfolders)
    # or a single file. Camera 1 is the sync reference.
    cameras: List[str] = field(default_factory=list)
    broll_dir: Optional[str] = None
    srt: Optional[str] = None         # transcript timed from Cam 1's first clip
    timeline_name: str = "AutoEdit"
    silence: SilenceSettings = field(default_factory=SilenceSettings)
    multicam: MulticamSettings = field(default_factory=MulticamSettings)
    broll: BrollSettings = field(default_factory=BrollSettings)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "JobSettings":
        data = dict(data)
        job = _build(cls, {k: v for k, v in data.items()
                           if k not in ("silence", "multicam", "broll")})
        job.silence = _build(SilenceSettings, data.get("silence"))
        job.multicam = _build(MulticamSettings, data.get("multicam"))
        job.broll = _build(BrollSettings, data.get("broll"))
        return job

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> "JobSettings":
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
