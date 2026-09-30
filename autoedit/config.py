"""Settings for an AutoEdit job."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import List, Optional


@dataclass
class SilenceSettings:
    threshold_db: float = -35.0   # quieter than this counts as silence
    min_silence: float = 0.5      # silence must last this long (s) to be cut
    padding: float = 0.12         # speech kept before/after each cut (s)
    min_keep: float = 0.3         # drop speech fragments shorter than this (s)


@dataclass
class MulticamSettings:
    mode: str = "rhythm"          # "speaker" | "rhythm" | "off"
    min_shot: float = 2.0         # never switch before a shot lasts this long (s)
    max_shot: float = 8.0         # force a switch after this long (s)
    wide_camera: Optional[int] = None  # index of the wide/master angle, if any
    margin_db: float = 3.0        # speaker mode: loudest mic must win by this much
    hide_jump_cuts: bool = True   # speaker mode: cut to wide on jump cuts
    sync: str = "audio"           # "audio" = auto sync by waveform, "none"
    sync_analyze: float = 300.0   # seconds of audio used for sync
    sync_max_offset: float = 120.0


@dataclass
class BrollSettings:
    enabled: bool = True
    fill: bool = True             # place B-roll at a regular interval
    interval: float = 12.0        # seconds between B-roll inserts
    duration: float = 3.0         # default length of an insert (s)
    max_duration: float = 6.0     # longest insert when matched to a subtitle
    first_after: float = 5.0      # keep the opening on the speaker (s)
    tail: float = 2.0             # keep the ending on the speaker (s)
    min_gap: float = 4.0          # minimum gap between inserts (s)
    track: int = 2                # video track for B-roll


@dataclass
class JobSettings:
    cameras: List[str] = field(default_factory=list)
    audio: Optional[str] = None       # external master audio; default camera 1
    broll_dir: Optional[str] = None
    srt: Optional[str] = None         # transcript used to match B-roll by keyword
    timeline_name: str = "AutoEdit"
    silence: SilenceSettings = field(default_factory=SilenceSettings)
    multicam: MulticamSettings = field(default_factory=MulticamSettings)
    broll: BrollSettings = field(default_factory=BrollSettings)

    @property
    def master_audio(self) -> str:
        return self.audio or self.cameras[0]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "JobSettings":
        data = dict(data)
        silence = SilenceSettings(**data.pop("silence", {}))
        multicam = MulticamSettings(**data.pop("multicam", {}))
        broll = BrollSettings(**data.pop("broll", {}))
        return cls(silence=silence, multicam=multicam, broll=broll, **data)

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> "JobSettings":
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
