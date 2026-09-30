"""Decide which camera angle is shown at every moment of the edit."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

from .config import MulticamSettings

Interval = Tuple[float, float]
LoudnessFn = Callable[[int, float, float], float]

BLOCK = 0.5      # decision granularity (s)
LOOKAHEAD = 1.0  # loudness is measured over this window (s)


@dataclass
class Shot:
    start: float      # master time (s)
    end: float
    camera: int
    interval: int     # index of the kept segment this shot belongs to


def envelope_loudness(envelopes: Sequence[Sequence[float]],
                      offsets: Sequence[float], window: float) -> LoudnessFn:
    """Mean loudness (dB) of camera `cam` over master time [t0, t1)."""

    def loudness(cam: int, t0: float, t1: float) -> float:
        env = envelopes[cam]
        a = int((t0 + offsets[cam]) / window)
        b = max(a + 1, int(math.ceil((t1 + offsets[cam]) / window)))
        values = env[max(0, a):max(0, min(len(env), b))]
        if not values:
            return -120.0
        power = sum(10 ** (v / 10.0) for v in values) / len(values)
        return 10 * math.log10(power) if power > 0 else -120.0

    return loudness


class _Director:
    def __init__(self, num_cams: int, settings: MulticamSettings,
                 loudness: Optional[LoudnessFn], silence_db: float):
        self.n = num_cams
        self.s = settings
        self.loudness = loudness
        self.silence_db = silence_db
        wide = settings.wide_camera
        self.wide = wide if wide is not None and 0 <= wide < num_cams else None
        self.speakers = [c for c in range(num_cams) if c != self.wide]
        self.cam = self.wide if self.wide is not None else 0
        self.shot_len = 0.0

    def next_cam(self) -> int:
        return (self.cam + 1) % self.n

    def active_speaker(self, t0: float, t1: float) -> Optional[int]:
        if not self.loudness or len(self.speakers) < 1:
            return None
        levels = sorted(((self.loudness(c, t0, t1), c) for c in self.speakers),
                        reverse=True)
        best_db, best = levels[0]
        if best_db < self.silence_db:
            return None
        if len(levels) > 1 and best_db - levels[1][0] < self.s.margin_db:
            return None
        return best

    def on_jump_cut(self, t: float) -> None:
        if self.shot_len < self.s.min_shot:
            return
        if self.s.mode == "rhythm":
            self.switch(self.next_cam())
        elif (self.s.mode == "speaker" and self.s.hide_jump_cuts
              and self.wide is not None and self.cam != self.wide):
            speaker = self.active_speaker(t, t + LOOKAHEAD)
            if speaker is None or speaker == self.cam:
                self.switch(self.wide)

    def on_block(self, t0: float) -> None:
        if self.s.mode == "rhythm":
            if self.shot_len >= self.s.max_shot:
                self.switch(self.next_cam())
            return
        speaker = self.active_speaker(t0, t0 + LOOKAHEAD)
        if speaker is not None and speaker != self.cam:
            if self.shot_len >= self.s.min_shot:
                self.switch(speaker)
        elif (self.shot_len >= self.s.max_shot and self.wide is not None
              and self.cam != self.wide):
            self.switch(self.wide)

    def switch(self, cam: int) -> None:
        if cam != self.cam:
            self.cam = cam
            self.shot_len = 0.0


def plan_shots(intervals: Sequence[Interval], num_cams: int,
               settings: MulticamSettings, loudness: Optional[LoudnessFn] = None,
               silence_db: float = -35.0) -> List[Shot]:
    if num_cams <= 1 or settings.mode == "off":
        cam = 0
        if num_cams > 1 and settings.wide_camera is not None:
            cam = settings.wide_camera
        return [Shot(s, e, cam, i) for i, (s, e) in enumerate(intervals)]
    if settings.mode == "speaker" and loudness is None:
        raise ValueError("speaker mode needs a loudness function")

    director = _Director(num_cams, settings, loudness, silence_db)
    shots: List[Shot] = []
    for idx, (s, e) in enumerate(intervals):
        if shots:
            director.on_jump_cut(s)
        t = s
        while t < e - 1e-9:
            t_end = min(e, t + BLOCK)
            director.on_block(t)
            last = shots[-1] if shots else None
            if last and last.camera == director.cam and last.interval == idx:
                last.end = t_end
            else:
                shots.append(Shot(t, t_end, director.cam, idx))
            director.shot_len += t_end - t
            t = t_end
    return shots
