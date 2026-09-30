"""Decide which camera angle is shown at every moment of the edit."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Iterator, List, Optional, Sequence, Tuple

from .config import MulticamSettings

Interval = Tuple[float, float]
LoudnessFn = Callable[[int, float, float], float]

BLOCK = 0.5      # decision granularity (s)
LOOKAHEAD = 1.0  # loudness is measured over this window (s)


@dataclass
class Shot:
    start: float      # axis time (s)
    end: float
    camera: int
    interval: int     # index of the kept segment this shot belongs to


def envelope_loudness(envelopes: Sequence[Sequence[float]], window: float) -> LoudnessFn:
    """Mean loudness (dB) of camera `cam` over axis time [t0, t1)."""

    def loudness(cam: int, t0: float, t1: float) -> float:
        env = envelopes[cam]
        a = max(0, int(t0 / window))
        b = min(len(env), max(a + 1, int(math.ceil(t1 / window))))
        values = env[a:b]
        if not values:
            return -120.0
        power = sum(10 ** (v / 10.0) for v in values) / len(values)
        return 10 * math.log10(power) if power > 0 else -120.0

    return loudness


def _pieces(s: float, e: float, num_cams: int,
            coverage: Optional[Sequence[Sequence[Interval]]]) -> Iterator[Tuple[float, float, List[int]]]:
    """Split [s, e] where the set of cameras with footage changes."""
    if coverage is None:
        yield s, e, list(range(num_cams))
        return
    points = {s, e}
    for spans in coverage:
        for a, b in spans:
            if s < a < e:
                points.add(a)
            if s < b < e:
                points.add(b)
    edges = sorted(points)
    for p, q in zip(edges, edges[1:]):
        if q - p < 1e-6:
            continue
        avail = [c for c, spans in enumerate(coverage)
                 if any(a <= p + 1e-6 and b >= q - 1e-6 for a, b in spans)]
        if avail:
            yield p, q, avail


class _Director:
    def __init__(self, num_cams: int, settings: MulticamSettings,
                 loudness: Optional[LoudnessFn], silence_db: float):
        self.s = settings
        self.loudness = loudness
        self.silence_db = silence_db
        wide = settings.wide_camera
        self.wide = wide if wide is not None and 0 <= wide < num_cams else None
        self.cam: Optional[int] = None
        self.shot_len = 0.0

    def default(self, avail: List[int]) -> int:
        return self.wide if self.wide in avail else avail[0]

    def next_cam(self, avail: List[int]) -> int:
        if self.cam not in avail:
            return self.default(avail)
        order = sorted(avail)
        return order[(order.index(self.cam) + 1) % len(order)]

    def active_speaker(self, t0: float, t1: float, avail: List[int]) -> Optional[int]:
        cands = [c for c in avail if c != self.wide]
        if not self.loudness or not cands:
            return None
        levels = sorted(((self.loudness(c, t0, t1), c) for c in cands), reverse=True)
        best_db, best = levels[0]
        if best_db < self.silence_db:
            return None
        if len(levels) > 1 and best_db - levels[1][0] < self.s.margin_db:
            return None
        return best

    def switch(self, cam: int) -> None:
        if cam != self.cam:
            self.cam = cam
            self.shot_len = 0.0

    def on_jump_cut(self, t: float, avail: List[int]) -> None:
        if self.cam not in avail or self.shot_len < self.s.min_shot:
            return
        if self.s.mode == "rhythm":
            self.switch(self.next_cam(avail))
        elif (self.s.mode == "speaker" and self.s.hide_jump_cuts
              and self.wide in avail and self.cam != self.wide):
            speaker = self.active_speaker(t, t + LOOKAHEAD, avail)
            if speaker is None or speaker == self.cam:
                self.switch(self.wide)

    def on_block(self, t0: float, avail: List[int]) -> None:
        speaker = (self.active_speaker(t0, t0 + LOOKAHEAD, avail)
                   if self.s.mode == "speaker" else None)
        if self.cam not in avail:  # current angle has no footage here
            self.switch(speaker if speaker is not None else self.default(avail))
            return
        if self.s.mode == "rhythm":
            if self.shot_len >= self.s.max_shot:
                self.switch(self.next_cam(avail))
        elif speaker is not None and speaker != self.cam:
            if self.shot_len >= self.s.min_shot:
                self.switch(speaker)
        elif (self.shot_len >= self.s.max_shot and self.wide in avail
              and self.cam != self.wide):
            self.switch(self.wide)


def plan_shots(intervals: Sequence[Interval], num_cams: int,
               settings: MulticamSettings, loudness: Optional[LoudnessFn] = None,
               silence_db: float = -35.0,
               coverage: Optional[Sequence[Sequence[Interval]]] = None) -> List[Shot]:
    """Camera per moment. `coverage[c]` lists the axis spans camera c recorded."""
    if settings.mode == "speaker" and num_cams > 1 and loudness is None:
        raise ValueError("speaker mode needs a loudness function")
    switching = num_cams > 1 and settings.mode != "off"
    director = _Director(num_cams, settings, loudness, silence_db)
    shots: List[Shot] = []

    def emit(p: float, q: float, cam: int, idx: int) -> None:
        last = shots[-1] if shots else None
        if last and last.camera == cam and last.interval == idx and abs(last.end - p) < 1e-9:
            last.end = q
        else:
            shots.append(Shot(p, q, cam, idx))

    for idx, (s, e) in enumerate(intervals):
        first_piece = True
        for p, q, avail in _pieces(s, e, num_cams, coverage):
            if not switching:
                emit(p, q, director.default(avail), idx)
                continue
            if first_piece and shots:
                director.on_jump_cut(p, avail)
            first_piece = False
            t = p
            while t < q - 1e-9:
                t_end = min(q, t + BLOCK)
                director.on_block(t, avail)
                emit(t, t_end, director.cam, idx)
                director.shot_len += t_end - t
                t = t_end
    return shots
