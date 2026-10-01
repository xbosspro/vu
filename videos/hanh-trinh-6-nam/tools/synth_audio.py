"""Synthesize SFX + music bed for the draft (deterministic, seeded).
Times are global composition seconds. VOFF = voice offset in the composition."""
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt

SR = 48000
VOFF = 0.35
T = 51.0
rng = np.random.default_rng(6)


def buf():
    return np.zeros((int(T * SR), 2), dtype=np.float64)


def add(b, t, sig, gain=1.0, pan=0.0):
    i = int(t * SR)
    if sig.ndim == 1:
        sig = np.stack([sig * (1 - max(pan, 0)), sig * (1 + min(pan, 0))], axis=1)
    j = min(len(b), i + len(sig))
    if j > i:
        b[i:j] += sig[: j - i] * gain


def env(n, a, d):
    t = np.arange(n) / SR
    return np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / d)


def lp(x, f, order=2):
    return sosfilt(butter(order, f, "low", fs=SR, output="sos"), x)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, "high", fs=SR, output="sos"), x)


def bp(x, lo, hi):
    return sosfilt(butter(2, [lo, hi], "band", fs=SR, output="sos"), x)


def noise(sec):
    return rng.standard_normal(int(sec * SR))


def click(sec=0.012, f=(2000, 7000)):
    return bp(noise(sec), *f) * env(int(sec * SR), 0.0005, sec / 4)


def shutter():
    s = np.zeros(int(0.25 * SR))
    a = click(0.03, (1500, 9000)); s[: len(a)] += a * 1.2
    b = click(0.05, (800, 6000)); k = int(0.075 * SR); s[k : k + len(b)] += b
    return s


def tick():
    n = int(0.03 * SR); t = np.arange(n) / SR
    return (np.sin(2 * np.pi * 3200 * t) * 0.4 + bp(noise(0.03), 3000, 8000) * 0.6) * env(n, 0.0003, 0.004)


def whoosh(sec=0.6, up=True):
    n = int(sec * SR); x = noise(sec)
    t = np.linspace(0, 1, n)
    shape = np.sin(np.pi * t) ** 2
    lo = lp(x, 900); hi = hp(x, 2500)
    mix = lo * (1 - t if up else t)[:] + hi * (t if up else 1 - t)
    return mix * shape * 0.6


def boom(sec=1.2, f0=90, f1=38):
    n = int(sec * SR); t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-t * 9)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return (np.sin(ph) + 0.25 * lp(noise(sec), 300)) * env(n, 0.002, sec / 3.5)


def kick():
    return boom(0.35, 140, 45) * 1.1


def snare():
    n = int(0.22 * SR); t = np.arange(n) / SR
    return (bp(noise(0.22), 1200, 7000) * 0.8 + np.sin(2 * np.pi * 190 * t) * 0.4) * env(n, 0.001, 0.05)


def riser(sec):
    n = int(sec * SR); t = np.linspace(0, 1, n)
    f = 60 + 240 * t ** 2
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.6 + bp(noise(sec), 400, 6000) * t * 0.5
    return s * t ** 1.6


def motor(sec):
    n = int(sec * SR); t = np.arange(n) / SR
    f = 110 + 160 * np.clip(t / sec, 0, 1) ** 0.7
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sign(np.sin(ph)) * 0.3 + np.sin(2 * ph) * 0.3
    s = lp(s, 1800) + bp(noise(sec), 200, 900) * 0.2
    e = np.minimum(1, t / 0.4) * np.minimum(1, (sec - t) / 0.4)
    return s * e


def keys(t0, t1, b, gain=0.35):
    t = t0
    while t < t1:
        k = click(0.018, (1800, 6500)); k[:480] += click(0.01, (500, 1800)) * 0.6
        add(b, t, k, gain * rng.uniform(0.6, 1.0), rng.uniform(-0.3, 0.3))
        t += rng.uniform(0.06, 0.16) if rng.random() > 0.12 else rng.uniform(0.25, 0.45)


def note(freq, sec, kind="piano"):
    n = int(sec * SR); t = np.arange(n) / SR
    if kind == "piano":
        s = sum(np.sin(2 * np.pi * freq * h * t) * a for h, a in [(1, 1), (2, 0.4), (3, 0.15), (4, 0.06)])
        return s * env(n, 0.004, 0.9)
    s = sum(np.sin(2 * np.pi * freq * d * t) for d in (0.997, 1.0, 1.004)) / 3
    a = np.minimum(1, t / 1.2) * np.minimum(1, (sec - t) / 1.2)
    return lp(s, 1400) * a


def hz(m):
    return 440 * 2 ** ((m - 69) / 12)


# ---------- SFX ----------
sfx = buf()
add(sfx, 0.0, shutter(), 0.9)
for k in range(15):
    add(sfx, 0.25 + k * 0.5, tick(), 0.35 if k % 2 == 0 else 0.22)
add(sfx, VOFF + 4.22, whoosh(0.35), 0.5)            # punch-in "điên rồ"
add(sfx, VOFF + 4.30, kick(), 0.5)
add(sfx, VOFF + 7.30, whoosh(0.55), 0.6)            # -> red card
add(sfx, VOFF + 11.25, boom(1.4), 0.8)              # "con số 0"
keys(VOFF + 11.70, VOFF + 18.9, sfx)                # keyboard bed
for t in (12.95, 15.2, 16.9, 18.4):
    add(sfx, VOFF + t, click(0.012, (2500, 9000)) * 1.3, 0.6)   # mouse clicks
add(sfx, VOFF + 18.95, whoosh(0.8, up=False), 0.55)  # -> mentors
add(sfx, VOFF + 22.85, click(0.4, (3000, 9000)) * 0.15, 0.4)
add(sfx, VOFF + 27.25, whoosh(0.5), 0.55)           # -> grid
for t in (29.88, 31.97, 35.58, 36.81):
    add(sfx, VOFF + t, kick(), 0.55)                # zoom bursts
    add(sfx, VOFF + t - 0.12, whoosh(0.2), 0.35)
add(sfx, VOFF + 31.70, click(0.02, (900, 4000)) * 2, 0.7)   # gimbal axis lock
add(sfx, VOFF + 32.0, click(0.02, (900, 4000)) * 2, 0.5)
add(sfx, VOFF + 34.0, motor(3.0), 0.28, 0.1)         # drone takeoff
add(sfx, VOFF + 33.3, riser(3.5), 0.3)
add(sfx, VOFF + 38.3, whoosh(0.6), 0.55)            # -> center frame
add(sfx, VOFF + 43.20, whoosh(0.4), 0.4)            # -> white card
add(sfx, VOFF + 45.55, whoosh(0.35, up=False), 0.4)
END = VOFF + 48.96
add(sfx, END, boom(1.6, 110, 32), 1.0)              # "bụp" cut to black
add(sfx, END + 0.05, shutter(), 0.8)                # shutter close
add(sfx, END + 0.9, shutter(), 0.5)

# ---------- MUSIC ----------
mus = buf()
# Am - F - C - G  (lo-fi ambient pad), 0 -> 19.5
prog = [(57, 60, 64), (53, 57, 60), (48, 55, 64), (55, 59, 62)]
t = 0.0; i = 0
while t < VOFF + 19.0:
    for m in prog[i % 4]:
        add(mus, t, note(hz(m), 4.4, "pad"), 0.09)
    add(mus, t, note(hz(prog[i % 4][0] - 12), 4.4, "pad"), 0.07)
    t += 4.0; i += 1
# warm piano 19.3 -> 38.5 (arpeggios), tempo 96 bpm
beat = 60 / 96
t = VOFF + 19.0; i = 0
while t < VOFF + 38.3:
    ch = prog[(i // 8) % 4]
    seq = [ch[0], ch[1], ch[2], ch[1] + 12, ch[2], ch[1], ch[0] + 12, ch[2]]
    add(mus, t, note(hz(seq[i % 8]), 1.6), 0.10, (-0.2 if i % 2 else 0.2))
    if i % 8 == 0:
        add(mus, t, note(hz(ch[0] - 12), 3.0), 0.12)
    t += beat / 2; i += 1
# pulse kicks in grid section
t = VOFF + 27.7
while t < VOFF + 38.3:
    add(mus, t, kick(), 0.30); t += beat
# cinematic build 38.5 -> END
t = VOFF + 38.4; i = 0
while t < END - 0.05:
    prog_t = (t - VOFF - 38.4) / (END - VOFF - 38.4)
    add(mus, t, kick(), 0.30 + 0.25 * prog_t)
    if i % 2 == 1:
        add(mus, t, snare(), 0.12 + 0.2 * prog_t)
    t += beat; i += 1
t = VOFF + 38.4; i = 0
while t < END:
    for m in prog[i % 4]:
        add(mus, t, note(hz(m), min(2 * beat * 4 + 0.6, END - t + 0.01), "pad"), 0.10)
    t += beat * 4; i += 1
add(mus, VOFF + 45.4, riser(END - VOFF - 45.4), 0.35)
# hard stop at the cut
mus[int(END * SR):] *= 0
fade = int(0.02 * SR)
k = int(END * SR)
mus[k - fade:k] *= np.linspace(1, 0, fade)[:, None]


def save(name, b, peak):
    b = b / max(1e-9, np.abs(b).max()) * peak
    wavfile.write(name, SR, (b * 32767).astype(np.int16))


save("assets/sfx.wav", sfx, 0.7)
save("assets/music.wav", mus, 0.6)
print("ok")
