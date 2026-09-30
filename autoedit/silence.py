"""Turn detected silences into the list of segments to keep."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

Interval = Tuple[float, float]


def keep_intervals(silences: Sequence[Interval], duration: float,
                   padding: float = 0.12, min_keep: float = 0.3) -> List[Interval]:
    """Complement of `silences` inside [0, duration], padded and cleaned up."""
    speech: List[Interval] = []
    cursor = 0.0
    for start, end in sorted(silences):
        start, end = max(0.0, start), min(duration, end)
        if start > cursor:
            speech.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < duration:
        speech.append((cursor, duration))

    padded = [(max(0.0, s - padding), min(duration, e + padding)) for s, e in speech]

    merged: List[Interval] = []
    for s, e in padded:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return [(s, e) for s, e in merged if e - s >= min_keep]


class TimeMap:
    """Maps source (master) time to time on the cut-down timeline."""

    def __init__(self, intervals: Sequence[Interval]):
        self.intervals = list(intervals)
        self.out_starts = []
        total = 0.0
        for s, e in self.intervals:
            self.out_starts.append(total)
            total += e - s
        self.duration = total

    def to_output(self, t: float, snap_forward: bool = True) -> Optional[float]:
        """Output time for master time `t`.

        Times that fall inside a removed gap snap to the start of the next
        kept segment (or return None when `snap_forward` is False).
        """
        for (s, e), out in zip(self.intervals, self.out_starts):
            if t < s:
                return out if snap_forward else None
            if t <= e:
                return out + (t - s)
        return None


def silences_from_envelope(env_db: Sequence[float], window: float,
                           threshold_db: float, min_silence: float) -> List[Interval]:
    """Runs of the envelope below `threshold_db` lasting at least `min_silence`."""
    out: List[Interval] = []
    start = None
    for i, v in enumerate(list(env_db) + [float("inf")]):
        if v < threshold_db:
            if start is None:
                start = i
        elif start is not None:
            if (i - start) * window >= min_silence:
                out.append((start * window, i * window))
            start = None
    return out


def union(intervals: Sequence[Interval]) -> List[Interval]:
    merged: List[Interval] = []
    for s, e in sorted(intervals):
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def intersect(a: Sequence[Interval], b: Sequence[Interval],
              min_keep: float = 0.0) -> List[Interval]:
    out: List[Interval] = []
    i = j = 0
    while i < len(a) and j < len(b):
        s, e = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if e - s > max(min_keep, 1e-9):
            out.append((s, e))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return out
