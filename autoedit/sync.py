"""Place every clip of every camera on Cam 1's time axis by audio waveform.

Cam 1's clips form the reference axis. For each other camera:
  1. its longest clip is searched across the whole axis to learn the
     offset between that camera's clock and Cam 1's clock;
  2. every other clip is searched near (its clock time + that offset), and
     across the whole axis if that fails;
  3. matches are refined to 50 ms, then 10 ms.

numpy is used when available; otherwise pure Python (slower but fine).
"""

from __future__ import annotations

import math
from operator import mul
from typing import Callable, List, Optional, Sequence, Tuple

from .sources import SourceClip

try:  # optional acceleration
    import numpy as _np  # type: ignore
except Exception:  # pragma: no cover - depends on the machine
    _np = None

WINDOW = 0.05       # analysis envelope resolution (s)
COARSE = 5          # coarse search works on WINDOW * COARSE = 0.25 s
FINE = 0.01
MIN_SCORE = 0.3     # below this a match is not trusted

Envelope = Callable[..., List[float]]
Log = Callable[[str], None]


def normalize(env_db: Sequence[float]) -> List[float]:
    amp = [10 ** (v / 20.0) for v in env_db]
    if not amp:
        return []
    mean = sum(amp) / len(amp)
    centered = [a - mean for a in amp]
    std = math.sqrt(sum(c * c for c in centered) / len(centered))
    if std < 1e-9:
        return [0.0] * len(amp)
    return [c / std for c in centered]


def downsample(env_db: Sequence[float], factor: int) -> List[float]:
    out = []
    for i in range(0, len(env_db), factor):
        chunk = env_db[i:i + factor]
        power = sum(10 ** (v / 10.0) for v in chunk) / len(chunk)
        out.append(10 * math.log10(power) if power > 0 else -120.0)
    return out


def best_lag(ref: Sequence[float], other: Sequence[float],
             lags: Sequence[int], min_overlap: int) -> Optional[int]:
    """Lag L maximising mean(ref[i] * other[i + L]) over the overlap."""
    best, best_score = None, -math.inf
    n_ref, n_other = len(ref), len(other)
    for lag in lags:
        lo = max(0, -lag)
        hi = min(n_ref, n_other - lag)
        if hi - lo < min_overlap:
            continue
        score = sum(map(mul, ref[lo:hi], other[lo + lag:hi + lag])) / (hi - lo)
        if score > best_score:
            best, best_score = lag, score
    return best


def search(axis: Sequence[float], clip: Sequence[float],
           lo: int, hi: int) -> Tuple[Optional[int], float]:
    """Axis index where `clip` fits best, for start indices in [lo, hi].

    The axis is zero outside its range, and in gaps between reference clips,
    so partial overlaps score proportionally less.
    """
    n = len(clip)
    if not n or not axis:
        return None, 0.0
    lo, hi = max(lo, -n + 1), min(hi, len(axis) - 1)
    if lo > hi:
        return None, 0.0
    if _np is not None:
        seg_lo, seg_hi = lo, hi + n
        a = _np.zeros(seg_hi - seg_lo)
        src_lo, src_hi = max(0, seg_lo), min(len(axis), seg_hi)
        a[src_lo - seg_lo:src_hi - seg_lo] = axis[src_lo:src_hi]
        scores = _np.correlate(a, _np.asarray(clip, dtype=float), "valid") / n
        i = int(scores.argmax())
        return lo + i, float(scores[i])
    padded_lo = lo
    padded = [0.0] * max(0, -lo) + list(axis[max(0, lo):hi + n])
    padded += [0.0] * (hi + n - lo - len(padded))
    best, best_score = None, -math.inf
    for i in range(hi - lo + 1):
        score = sum(map(mul, clip, padded[i:i + n]))
        if score > best_score:
            best, best_score = padded_lo + i, score
    return best, best_score / n


class Axis:
    """Normalised loudness of the reference camera along the time axis."""

    def __init__(self, clips: Sequence[SourceClip]):
        self.clips = [c for c in clips if c.has_audio and c.envelope]
        end = max((c.end for c in clips), default=0.0)
        self.fine = self._build(end, 1)
        self.coarse = self._build(end, COARSE)

    def _build(self, end: float, factor: int) -> List[float]:
        step = WINDOW * factor
        axis = [0.0] * (int(end / step) + 2)
        for c in self.clips:
            env = c.envelope if factor == 1 else downsample(c.envelope, factor)
            start = int(round(c.position / step))
            for i, v in enumerate(normalize(env)):
                if 0 <= start + i < len(axis):
                    axis[start + i] = v
        return axis


def _refine_fine(envelope: Envelope, axis: Axis, clip: SourceClip, pos: float) -> float:
    """10 ms refinement against the reference clip that overlaps the most."""
    best_ref, best_overlap = None, 0.0
    for ref in axis.clips:
        overlap = min(pos + clip.duration, ref.end) - max(pos, ref.position)
        if overlap > best_overlap:
            best_ref, best_overlap = ref, overlap
    if best_ref is None or best_overlap < 3.0:
        return pos
    margin = 0.15
    length = min(20.0, best_overlap - 2 * margin)
    t0 = max(pos, best_ref.position) + (best_overlap - length) / 2
    if t0 - pos - margin < 0:
        return pos
    ref = normalize(envelope(best_ref.path, FINE, length, t0 - best_ref.position))
    oth = normalize(envelope(clip.path, FINE, length + 2 * margin, t0 - pos - margin))
    steps = int(round(margin / FINE))
    lag = best_lag(ref, oth, range(0, 2 * steps + 1), max(10, len(ref) // 2))
    return pos if lag is None else pos + (steps - lag) * FINE


def locate(axis: Axis, clip: SourceClip, around: Optional[float],
           window: float) -> Tuple[Optional[float], float]:
    """Best position for `clip` near `around` (or anywhere when None)."""
    env_c = normalize(downsample(clip.envelope, COARSE))
    step = WINDOW * COARSE
    if around is None:
        lo, hi = -len(env_c) + 1, len(axis.coarse) - 1
    else:
        centre = int(round(around / step))
        span = int(math.ceil(window / step))
        lo, hi = centre - span, centre + span
    idx, score = search(axis.coarse, env_c, lo, hi)
    if idx is None or score < MIN_SCORE:
        return None, score
    # 50 ms refinement around the coarse match.
    env_f = normalize(clip.envelope)
    centre = idx * COARSE
    idx_f, score_f = search(axis.fine, env_f, centre - COARSE * 2, centre + COARSE * 2)
    if idx_f is None:
        return idx * step, score
    return idx_f * WINDOW, score_f


def sync_camera(axis: Axis, clips: Sequence[SourceClip],
                clock: Optional[Sequence[float]], window: float,
                envelope: Envelope, label: str, log: Log,
                ref_origin: Optional[float] = None) -> None:
    """Set .position/.synced for every clip of one non-reference camera.

    `ref_origin` is Cam 1's clock reading at axis time 0 (for the log only).
    """
    usable = [c for c in clips if c.has_audio and len(c.envelope) * WINDOW >= 2.0]
    offset = None  # this camera's clock -> axis time
    if clock is not None:
        order = sorted(range(len(clips)), key=lambda i: -clips[i].duration)
        for i in order[:3]:
            if clips[i] not in usable:
                continue
            pos, score = locate(axis, clips[i], None, 0)
            if pos is not None:
                offset = pos - clock[i]
                drift = (f"lệch đồng hồ so với Cam 1 = {-(offset + ref_origin):+.2f}s"
                         if ref_origin is not None else "đã tìm thấy vị trí")
                log(f"  {label}: {drift} (khớp theo {clips[i].name}, "
                    f"độ tin cậy {score:.2f})")
                break

    previous_end = 0.0
    for i, clip in enumerate(clips):
        guess = clock[i] + offset if clock is not None and offset is not None else None
        pos, score = (None, 0.0)
        if clip in usable:
            if guess is not None:
                pos, score = locate(axis, clip, guess, window)
            if pos is None:
                pos, score = locate(axis, clip, None, 0)
        if pos is not None:
            clip.position = _refine_fine(envelope, axis, clip, pos)
            clip.synced = True
        else:
            clip.position = guess if guess is not None else previous_end
            reason = "không có âm thanh" if clip not in usable else "không khớp được âm thanh"
            log(f"  ! {clip.name}: {reason} - đặt theo "
                f"{'giờ quay' if guess is not None else 'thứ tự'}")
        previous_end = clip.end
