"""Audio-waveform sync between cameras (like Resolve's "sync by waveform")."""

from __future__ import annotations

import math
from typing import Callable, List, Optional, Sequence


def _normalize(env_db: Sequence[float]) -> List[float]:
    amp = [10 ** (v / 20.0) for v in env_db]
    if not amp:
        return []
    mean = sum(amp) / len(amp)
    centered = [a - mean for a in amp]
    std = math.sqrt(sum(c * c for c in centered) / len(centered)) or 1.0
    return [c / std for c in centered]


def best_lag(ref: Sequence[float], other: Sequence[float],
             lags: Sequence[int], min_overlap: int) -> Optional[int]:
    """Lag L maximising mean(ref[i] * other[i + L])."""
    best, best_score = None, -math.inf
    n_ref, n_other = len(ref), len(other)
    for lag in lags:
        lo = max(0, -lag)
        hi = min(n_ref, n_other - lag)
        if hi - lo < min_overlap:
            continue
        score = 0.0
        for i in range(lo, hi):
            score += ref[i] * other[i + lag]
        score /= hi - lo
        if score > best_score:
            best, best_score = lag, score
    return best


def find_offset(envelope: Callable[[str, float, Optional[float]], List[float]],
                master: str, other: str, analyze: float = 300.0,
                max_offset: float = 120.0) -> float:
    """Seconds to add to master time to get the same moment in `other`.

    `envelope(path, window, limit)` returns a dB loudness envelope (see
    ffmpeg_tools.loudness_envelope). A coarse 100 ms search over the full
    offset range is refined with a 10 ms search around the best match.
    """
    coarse = 0.1
    ref = _normalize(envelope(master, coarse, analyze))
    oth = _normalize(envelope(other, coarse, analyze + max_offset))
    span = int(max_offset / coarse)
    lag = best_lag(ref, oth, range(-span, span + 1), max(10, len(ref) // 4))
    if lag is None:
        return 0.0

    fine = 0.01
    fine_limit = min(analyze, 60.0)
    ref_f = _normalize(envelope(master, fine, fine_limit))
    oth_f = _normalize(envelope(other, fine, fine_limit + max_offset))
    center = int(round(lag * coarse / fine))
    fine_lag = best_lag(ref_f, oth_f, range(center - 15, center + 16),
                        max(10, len(ref_f) // 4))
    return (fine_lag if fine_lag is not None else center) * fine
