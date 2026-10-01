"""Generate index.html for "Hành Trình 6 Năm" from transcript.json.

Run from the project root:  python3 tools/gen.py
Every time in the composition is global seconds; VOFF shifts the voiceover.
"""
import json
import html

VOFF = 0.35
TOTAL = 51.0
W = json.load(open("transcript.json", encoding="utf8"))


def ws(i):
    return round(W[i]["start"] + VOFF, 3)


def we(i):
    return round(W[i]["end"] + VOFF, 3)


END = round(we(174) + 0.42, 2)  # hard cut to black

# ---------- scene windows ----------
S = {
    "s1": (0.0, ws(17) - 0.07),       # split 50/50
    "s2": (ws(17) - 0.07, ws(30) - 0.12),  # full portrait + punch-in
    "s3": (ws(30) - 0.12, ws(42) - 0.07),  # red card "con số 0"
    "s4": (ws(42) - 0.07, ws(67) - 0.1),   # triple split
    "s5": (ws(67) - 0.1, ws(101) - 0.1),   # letterbox mentors
    "s6": (ws(101) - 0.1, ws(132) - 0.05),  # 2x2 grid
    "s7": (ws(132) - 0.05, ws(137) - 0.12),  # snap back to single frame
    "s8": (ws(137) - 0.12, END),            # center frame -> dolly
    "s9": (END, TOTAL),                      # black + KEEP MOVING
}
WHITE_CARD = (ws(153) - 0.08, ws(162) - 0.06)

# ---------- captions ----------
# (first word, last word, emphasised word indexes)
GROUPS = [
    (0, 4, []), (5, 8, [7, 8]), (9, 12, [9, 10]), (13, 16, [15, 16]),
    (17, 20, [19, 20]), (21, 25, [24, 25]), (26, 29, [28]),
    (42, 47, [46, 47]), (48, 52, [48, 49]), (53, 56, []), (57, 59, [58, 59]),
    (60, 62, [61, 62]), (63, 66, [65, 66]),
    (67, 72, [70, 71]), (73, 76, [73, 74]), (77, 82, []),
    (85, 89, [87]), (90, 95, [94, 95]), (96, 100, [99, 100]),
    (101, 105, [104, 105]), (106, 109, [108, 109]), (110, 113, [111]),
    (114, 117, [115]), (118, 121, [121]), (122, 126, []), (127, 131, [129]),
    (132, 136, [135, 136]),
    (137, 140, [139, 140]), (141, 146, [145, 146]), (147, 152, [147, 148]),
    (162, 166, [164, 165]), (167, 170, [168, 169]), (171, 174, [174]),
]


def esc(s):
    return html.escape(s, quote=True)


cap_html = []
cap_js = []
for gi, (a, b, emph) in enumerate(GROUPS):
    start = ws(a) - 0.04
    nxt = GROUPS[gi + 1][0] if gi + 1 < len(GROUPS) else None
    end = we(b) + 0.35
    if nxt is not None and nxt == b + 1:
        end = min(end, ws(nxt) - 0.05)
    end = min(end, END - 0.02)
    spans = []
    for i in range(a, b + 1):
        cls = "w em" if i in emph else "w"
        spans.append(f'<span id="w{i}" class="{cls}">{esc(W[i]["text"])}</span>')
    boxed = " boxed" if b < 17 else ""
    cap_html.append(f'<div id="g{gi}" class="cap-group{boxed}">{" ".join(spans)}</div>')
    cap_js.append(f'tl.set("#g{gi}", {{ opacity: 1 }}, {start:.3f}).set("#g{gi}", {{ opacity: 0 }}, {end:.3f});')
    for i in range(a, b + 1):
        if i in emph:
            cap_js.append(
                f'tl.fromTo("#w{i}", {{ opacity: 0, scale: 1.55, y: 10 }}, {{ opacity: 1, scale: 1, y: 0, duration: 0.24, ease: "expo.out" }}, {ws(i) - 0.03:.3f});'
            )
        else:
            cap_js.append(
                f'tl.fromTo("#w{i}", {{ opacity: 0, y: 22 }}, {{ opacity: 1, y: 0, duration: 0.18, ease: "power3.out" }}, {ws(i) - 0.03:.3f});'
            )


def clip(sid, inner, extra_cls=""):
    a, b = S[sid]
    return (
        f'<section id="{sid}" class="clip scene {extra_cls}" data-start="{a:.3f}" '
        f'data-duration="{b - a:.3f}" data-track-index="0">{inner}</section>'
    )


def portrait(pid, cls="cam", pos="50% 36%"):
    return (
        f'<div class="{cls}"><img id="{pid}" class="pimg" src="assets/portrait.png" '
        f'alt="" style="object-position:{pos};transform-origin:{pos}" /></div>'
    )


# ---------- line-art SVGs ----------
STETHO = """
<svg viewBox="0 0 400 520" class="art" aria-hidden="true">
  <g fill="none" stroke="#141414" stroke-width="7" stroke-linecap="round" stroke-linejoin="round">
    <path id="steth-path" d="M120 40 C110 120 110 190 160 230 C200 262 240 262 280 230 C330 190 330 120 320 40" />
    <path d="M220 258 C220 330 210 380 170 410 C130 440 120 470 150 492" />
    <circle cx="186" cy="470" r="34" />
    <circle cx="186" cy="470" r="14" />
    <circle cx="120" cy="34" r="10" fill="#141414" />
    <circle cx="320" cy="34" r="10" fill="#141414" />
  </g>
</svg>"""

KEYS = []
for r in range(4):
    for c in range(10 - (1 if r == 3 else 0)):
        x = 16 + c * 38 + (r * 10)
        y = 20 + r * 40
        KEYS.append(f'<rect id="k{r}{c}" class="key" x="{x}" y="{y}" width="32" height="32" rx="6" />')
KEYBOARD = f"""
<svg viewBox="0 0 420 200" class="art" aria-hidden="true">
  <rect x="4" y="6" width="412" height="186" rx="16" fill="#151515" stroke="#3a3a3a" stroke-width="2" />
  {''.join(KEYS)}
</svg>"""

TRACKS = []
import itertools
lens = [[(0, 70), (78, 40), (126, 90), (224, 50), (282, 110), (400, 60), (468, 80), (556, 70)],
        [(20, 120), (148, 60), (216, 140), (364, 90), (462, 120), (590, 50)],
        [(0, 40), (48, 30), (86, 60), (154, 30), (192, 80), (280, 40), (328, 70), (406, 50), (464, 30), (502, 90), (600, 40)],
        [(10, 260), (280, 330)]]
colors = ["#7a7a7a", "#a3a3a3", "#C8102E", "#4b5563"]
for ti, row in enumerate(lens):
    for (x, w) in row:
        TRACKS.append(f'<rect x="{x}" y="{16 + ti * 44}" width="{w - 4}" height="32" rx="4" fill="{colors[ti]}" opacity="0.9" />')
TIMELINE = f"""
<svg viewBox="0 0 330 200" class="art" aria-hidden="true">
  <rect x="0" y="0" width="330" height="200" fill="#111" />
  <g id="tl-strip">{''.join(TRACKS)}</g>
  <line id="playhead" x1="120" y1="4" x2="120" y2="196" stroke="#fff" stroke-width="3" />
</svg>"""

LENS = """
<svg viewBox="0 0 300 300" class="art" aria-hidden="true">
  <g fill="none" stroke="#e8e8e8" stroke-width="5">
    <circle cx="150" cy="150" r="128" />
    <circle cx="150" cy="150" r="96" stroke-width="3" />
    <circle cx="150" cy="150" r="58" />
    <circle cx="150" cy="150" r="22" fill="#C8102E" stroke="none" />
    <g id="lens-ring" stroke-width="3">
      <line x1="150" y1="8" x2="150" y2="34" /><line x1="150" y1="266" x2="150" y2="292" />
      <line x1="8" y1="150" x2="34" y2="150" /><line x1="266" y1="150" x2="292" y2="150" />
      <line x1="50" y1="50" x2="66" y2="66" /><line x1="250" y1="250" x2="234" y2="234" />
      <line x1="250" y1="50" x2="234" y2="66" /><line x1="50" y1="250" x2="66" y2="234" />
    </g>
  </g>
</svg>"""

GIMBAL = """
<svg viewBox="0 0 300 380" class="art" aria-hidden="true">
  <g fill="none" stroke="#e8e8e8" stroke-width="6" stroke-linecap="round" stroke-linejoin="round">
    <rect x="128" y="250" width="44" height="120" rx="18" />
    <path d="M150 250 V214 H222 V120" />
    <g id="gimbal-head">
      <path d="M222 120 H96 V70" />
      <rect x="40" y="20" width="130" height="80" rx="10" />
      <circle cx="105" cy="60" r="24" stroke="#C8102E" />
    </g>
    <circle cx="150" cy="300" r="7" fill="#e8e8e8" />
  </g>
</svg>"""

DRONE = """
<svg viewBox="0 0 320 260" class="art" aria-hidden="true">
  <g fill="none" stroke="#e8e8e8" stroke-width="6" stroke-linecap="round">
    <line x1="70" y1="70" x2="250" y2="190" /><line x1="250" y1="70" x2="70" y2="190" />
    <rect x="128" y="104" width="64" height="52" rx="12" fill="#151515" />
    <circle cx="160" cy="130" r="8" fill="#C8102E" stroke="none" />
    <g id="rotor1"><line x1="30" y1="70" x2="110" y2="70" /></g>
    <g id="rotor2"><line x1="210" y1="70" x2="290" y2="70" /></g>
    <g id="rotor3"><line x1="30" y1="190" x2="110" y2="190" /></g>
    <g id="rotor4"><line x1="210" y1="190" x2="290" y2="190" /></g>
    <circle cx="70" cy="70" r="6" fill="#e8e8e8" /><circle cx="250" cy="70" r="6" fill="#e8e8e8" />
    <circle cx="70" cy="190" r="6" fill="#e8e8e8" /><circle cx="250" cy="190" r="6" fill="#e8e8e8" />
  </g>
</svg>"""


def kw(text, kid, cls="kw"):
    return f'<div id="{kid}" class="{cls}">{esc(text)}</div>'


# ---------- scenes ----------
s1 = clip("s1", f"""
  <div class="split2">
    <div class="pane paper">
      <div class="lines"></div>
      <div id="s1-art" class="art-wrap">{STETHO}</div>
      <div class="pane-tag dark">01 — THÚ Y</div>
      {kw("VET", "kw-vet", "kw kw-dark")}
    </div>
    <div class="pane">{portrait("p1")}<div class="warm"></div></div>
    <div class="divider-v"></div>
  </div>""")

s2 = clip("s2", f"""{portrait("p2")}<div class="warm"></div><div class="vignette"></div>""")

s3 = clip("s3", f"""
  <div class="red-bg"><div class="red-glow"></div></div>
  <div class="card-stack">
    <div id="s3-a" class="card-small">6 NĂM TRƯỚC</div>
    <div id="s3-b" class="card-serif">xuất phát điểm</div>
    <div id="s3-zero-wrap" class="zero-wrap"><div id="s3-zero" class="zero">0</div></div>
    <div id="s3-c" class="card-small dim">CON SỐ</div>
  </div>""")

s4 = clip("s4", f"""
  <div id="s4-strip" class="strip3">
    <div class="col"><div class="col-in" id="s4-c1"><div class="art-wrap dark-pad big">{KEYBOARD}</div></div><div class="pane-tag">01 · INPUT</div></div>
    <div class="col">{portrait("p4", pos="50% 33%")}<div class="screen-glow"></div><div class="pane-tag">02 · FOCUS</div></div>
    <div class="col"><div class="col-in" id="s4-c3"><div class="art-wrap dark-pad big">{TIMELINE}</div></div><div class="pane-tag">03 · EDIT</div></div>
    <div class="divider-v at1"></div><div class="divider-v at2"></div>
  </div>
  {kw("DỰNG PHIM", "kw-dung")}""")

s5 = clip("s5", f"""
  {portrait("p5")}<div class="warm strong"></div><div class="vignette"></div>
  <div class="bar top"></div><div class="bar bottom"></div>
  <div id="s5-tag" class="corner-tag">[01. MENTORS &amp; GRATITUDE]</div>
  {kw("QUÝ NHÂN", "kw-quy", "kw kw-big")}""")

s6 = clip("s6", f"""
  <div class="grid4">
    <div class="tile" id="t1"><div class="tile-in" id="t1-in"><div class="art-wrap">{LENS}</div></div><div class="pane-tag">LENS</div></div>
    <div class="tile" id="t2"><div class="tile-in" id="t2-in"><div class="art-wrap">{GIMBAL}</div></div><div class="pane-tag">GIMBAL</div></div>
    <div class="tile" id="t3"><div class="tile-in" id="t3-in"><div class="art-wrap">{DRONE}</div></div><div class="pane-tag">FLYCAM</div></div>
    <div class="tile" id="t4"><div class="tile-in" id="t4-in">{portrait("p6", pos="50% 30%")}</div><div class="pane-tag">SKY</div></div>
    <div class="divider-v"></div><div class="divider-h"></div>
  </div>
  {kw("GIMBAL", "kw-gimbal")}{kw("FLYCAM", "kw-flycam")}""")

s7 = clip("s7", f"""{portrait("p7")}<div class="warm"></div><div class="vignette"></div>""")

s8 = clip("s8", f"""
  <div class="studio"></div>
  <div id="s8-frame" class="inset-frame">{portrait("p8")}<div class="warm"></div></div>
  {kw("BIẾT ƠN", "kw-bietan", "kw kw-big")}""")

wa, wb = WHITE_CARD
white = f"""
<section id="white-card" class="clip scene" data-start="{wa:.3f}" data-duration="{wb - wa:.3f}" data-track-index="2">
  <div class="paper-bg"><div class="grid-lines"></div></div>
  <div class="wc-text">
    <div id="wc1" class="wc-l1">Xuất phát điểm</div>
    <div id="wc2" class="wc-l2">KHÔNG</div>
    <div id="wc3" class="wc-l3">định nghĩa bạn là ai</div>
  </div>
  <div id="wc-photo" class="wc-photo">{portrait("p9", cls="cam bw")}</div>
  <div id="wc-q1" class="qmark">?</div>
</section>"""

s9 = clip("s9", """
  <div class="black"></div>
  <div class="end-wrap"><div id="km" class="keep">KEEP MOVING</div><div id="km-line" class="km-line"></div></div>""")

fonts_css = open(".fonts.css", encoding="utf8").read()

# ---------- timeline ----------
a = lambda k: S[k][0]
b = lambda k: S[k][1]
js = []
J = js.append
# S1 split
J(f'tl.fromTo("#p1", {{ scale: 1.18, xPercent: 0 }}, {{ scale: 1.26, xPercent: -2, duration: {b("s1"):.2f}, ease: "none" }}, 0);')
J('tl.fromTo("#s1-art", { scale: 0.9, rotation: -4, opacity: 0 }, { scale: 1, rotation: 0, opacity: 1, duration: 0.9, ease: "expo.out" }, 0.05);')
J(f'tl.fromTo("#kw-vet", {{ opacity: 0, scale: 1.3 }}, {{ opacity: 1, scale: 1, duration: 0.6, ease: "power3.out" }}, {ws(7) - 0.05:.2f});')
J(f'tl.to("#s1-art", {{ x: -14, duration: {b("s1") - 1:.2f}, ease: "none" }}, 1);')
# S2 punch-in on "điên rồ"
J(f'tl.fromTo("#p2", {{ scale: 1.0, xPercent: 0, yPercent: 0 }}, {{ scale: 1.03, duration: {ws(19) - a("s2"):.2f}, ease: "none" }}, {a("s2"):.2f});')
J(f'tl.to("#p2", {{ scale: 1.25, yPercent: 2, duration: 0.12, ease: "power4.out" }}, {ws(19) - 0.02:.2f});')
J(f'tl.to("#p2", {{ scale: 1.29, duration: {ws(24) - ws(19) - 0.2:.2f}, ease: "none" }}, {ws(19) + 0.12:.2f});')
J(f'tl.to("#p2", {{ scale: 1.42, yPercent: 4, duration: 0.14, ease: "power4.out" }}, {ws(24) - 0.02:.2f});')
J(f'tl.to("#p2", {{ scale: 1.46, duration: {b("s2") - ws(24) - 0.12:.2f}, ease: "none" }}, {ws(24) + 0.14:.2f});')
# S3 red card
J(f'tl.fromTo("#s3-a", {{ opacity: 0, y: 30 }}, {{ opacity: 1, y: 0, duration: 0.35, ease: "power3.out" }}, {ws(30) - 0.02:.2f});')
J(f'tl.fromTo("#s3-b", {{ opacity: 0, y: 40 }}, {{ opacity: 1, y: 0, duration: 0.4, ease: "power3.out" }}, {ws(33) - 0.02:.2f});')
J(f'tl.fromTo("#s3-c", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.3 }}, {ws(39) - 0.02:.2f});')
J(f'tl.fromTo("#s3-zero", {{ opacity: 0, scale: 2.6 }}, {{ opacity: 1, scale: 1, duration: 0.28, ease: "expo.out" }}, {ws(41) - 0.04:.2f});')
J(f'tl.fromTo("#s3-zero-wrap", {{ x: 0 }}, {{ x: 10, duration: 0.05, repeat: 5, yoyo: true, ease: "none" }}, {ws(41) + 0.22:.2f});')
J(f'tl.fromTo(".red-glow", {{ opacity: 0.35, scale: 1 }}, {{ opacity: 0.8, scale: 1.25, duration: {b("s3") - a("s3"):.2f}, ease: "none" }}, {a("s3"):.2f});')
# S4 triple split: lateral pan + jitter cuts on phrase starts
J(f'tl.fromTo("#s4-strip", {{ x: 0 }}, {{ x: -180, duration: {b("s4") - a("s4"):.2f}, ease: "none" }}, {a("s4"):.2f});')
J(f'tl.fromTo("#p4", {{ scale: 1.9 }}, {{ scale: 2.15, duration: {b("s4") - a("s4"):.2f}, ease: "none" }}, {a("s4"):.2f});')
for i in (48, 53, 57, 60, 63):
    J(f'tl.fromTo("#s4-strip", {{ scale: 1.045 }}, {{ scale: 1, duration: 0.22, ease: "power3.out", immediateRender: false }}, {ws(i) - 0.02:.2f});')
# keyboard keys flicker (deterministic pattern)
seq = ["k12", "k25", "k03", "k31", "k17", "k22", "k08", "k35", "k14", "k20", "k06", "k33", "k11", "k27", "k02", "k38", "k19", "k24"]
t = a("s4") + 0.1
k = 0
while t < b("s4") - 0.2:
    J(f'tl.fromTo("#{seq[k % len(seq)]}", {{ fill: "#C8102E" }}, {{ fill: "#262626", duration: 0.25, immediateRender: false }}, {t:.2f});')
    t += 0.19 if k % 5 else 0.38
    k += 1
J(f'tl.fromTo("#tl-strip", {{ x: 0 }}, {{ x: -260, duration: {b("s4") - a("s4"):.2f}, ease: "none" }}, {a("s4"):.2f});')
J(f'tl.fromTo("#kw-dung", {{ opacity: 0, scale: 1.3 }}, {{ opacity: 1, scale: 1, duration: 0.5, ease: "power3.out" }}, {ws(58) - 0.05:.2f});')
J(f'tl.to("#kw-dung", {{ opacity: 0, duration: 0.3 }}, {b("s4") - 0.35:.2f});')
J(f'tl.fromTo(".screen-glow", {{ opacity: 0.25 }}, {{ opacity: 0.6, duration: 0.6, repeat: {int((b("s4") - a("s4")) / 1.2) - 1}, yoyo: true, ease: "sine.inOut" }}, {a("s4"):.2f});')
# S5 letterbox slow push-in
J(f'tl.fromTo("#p5", {{ scale: 1.02, yPercent: 0 }}, {{ scale: 1.2, yPercent: 3, duration: {b("s5") - a("s5"):.2f}, ease: "sine.inOut" }}, {a("s5"):.2f});')
J(f'tl.fromTo(".bar.top", {{ yPercent: -100 }}, {{ yPercent: 0, duration: 0.6, ease: "expo.out" }}, {a("s5"):.2f});')
J(f'tl.fromTo(".bar.bottom", {{ yPercent: 100 }}, {{ yPercent: 0, duration: 0.6, ease: "expo.out" }}, {a("s5"):.2f});')
J(f'tl.fromTo("#s5-tag", {{ opacity: 0, x: -20 }}, {{ opacity: 1, x: 0, duration: 0.5, ease: "power3.out" }}, {a("s5") + 0.5:.2f});')
J(f'tl.fromTo("#kw-quy", {{ opacity: 0, scale: 1.25 }}, {{ opacity: 1, scale: 1, duration: 0.5, ease: "expo.out" }}, {ws(83) - 0.05:.2f});')
J(f'tl.to("#kw-quy", {{ opacity: 0, duration: 0.4 }}, {ws(90):.2f});')
# S6 grid: tiles flicker on, zoom bursts on keywords, then snap
for n, tt in enumerate((0.0, 0.12, 0.24, 0.36)):
    J(f'tl.fromTo("#t{n + 1}-in", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.05, repeat: 3, yoyo: true, ease: "none" }}, {a("s6") + tt:.2f});')
    J(f'tl.set("#t{n + 1}-in", {{ opacity: 1 }}, {a("s6") + tt + 0.21:.2f});')
J(f'tl.fromTo("#lens-ring", {{ rotation: 0, transformOrigin: "150px 150px" }}, {{ rotation: 90, duration: {b("s6") - a("s6"):.2f}, ease: "none" }}, {a("s6"):.2f});')
J(f'tl.fromTo("#gimbal-head", {{ rotation: -6, transformOrigin: "222px 120px" }}, {{ rotation: 6, duration: 0.5, repeat: {int((b("s6") - a("s6")) / 0.5) - 1}, yoyo: true, ease: "sine.inOut" }}, {a("s6"):.2f});')
for r in range(1, 5):
    J(f'tl.fromTo("#rotor{r}", {{ scaleX: 1, transformOrigin: "50% 50%" }}, {{ scaleX: 0.15, duration: 0.06, repeat: {int((b("s6") - a("s6")) / 0.06) - 1}, yoyo: true, ease: "none" }}, {a("s6"):.2f});')
J(f'tl.fromTo("#p6", {{ scale: 1.6, yPercent: 0 }}, {{ scale: 1.75, yPercent: -2, duration: {b("s6") - a("s6"):.2f}, ease: "none" }}, {a("s6"):.2f});')
# shaky hands on "tay run bần bật"
J(f'tl.fromTo("#t1-in", {{ x: 0 }}, {{ x: 7, duration: 0.04, repeat: 19, yoyo: true, ease: "none", immediateRender: false }}, {ws(110):.2f});')
for tile, i in (("t1", 108), ("t2", 115), ("t3", 129), ("t4", 131)):
    J(f'tl.fromTo("#{tile}", {{ scale: 1.16, zIndex: 3 }}, {{ scale: 1, duration: 0.45, ease: "expo.out", immediateRender: false }}, {ws(i) - 0.03:.2f});')
    J(f'tl.set("#{tile}", {{ zIndex: 1 }}, {ws(i) + 0.5:.2f});')
J(f'tl.fromTo("#kw-gimbal", {{ opacity: 0, y: 20 }}, {{ opacity: 1, y: 0, duration: 0.3, ease: "power3.out" }}, {ws(115) - 0.03:.2f});')
J(f'tl.to("#kw-gimbal", {{ opacity: 0, duration: 0.25 }}, {ws(122) - 0.1:.2f});')
J(f'tl.fromTo("#kw-flycam", {{ opacity: 0, y: 20 }}, {{ opacity: 1, y: 0, duration: 0.3, ease: "power3.out" }}, {ws(129) - 0.03:.2f});')
J(f'tl.to("#kw-flycam", {{ opacity: 0, duration: 0.2 }}, {b("s6") - 0.22:.2f});')
J(f'tl.fromTo("#t3-in .art", {{ y: 20 }}, {{ y: -60, duration: {b("s6") - ws(122):.2f}, ease: "power2.in" }}, {ws(122):.2f});')
# S7 snap back to one frame (zoom burst out)
J(f'tl.fromTo("#p7", {{ scale: 1.5 }}, {{ scale: 1.12, duration: 0.35, ease: "expo.out" }}, {a("s7"):.2f});')
J(f'tl.to("#p7", {{ scale: 1.08, duration: {b("s7") - a("s7") - 0.35:.2f}, ease: "none" }}, {a("s7") + 0.35:.2f});')
# S8 center frame -> dolly-in to chest close-up
J(f'tl.fromTo("#s8-frame", {{ scale: 0.78, borderRadius: 18 }}, {{ scale: 1, borderRadius: 0, duration: {WHITE_CARD[0] - a("s8"):.2f}, ease: "power1.inOut" }}, {a("s8"):.2f});')
J(f'tl.fromTo("#p8", {{ scale: 1.0, yPercent: 0 }}, {{ scale: 1.15, yPercent: 2, duration: {WHITE_CARD[0] - a("s8"):.2f}, ease: "none" }}, {a("s8"):.2f});')
J(f'tl.to("#p8", {{ scale: 1.5, yPercent: 6, duration: {END - WHITE_CARD[1]:.2f}, ease: "power1.in" }}, {WHITE_CARD[1]:.2f});')
J(f'tl.fromTo("#kw-bietan", {{ opacity: 0, scale: 1.25 }}, {{ opacity: 1, scale: 1, duration: 0.45, ease: "expo.out" }}, {ws(168) - 0.05:.2f});')
J(f'tl.to("#kw-bietan", {{ opacity: 0, duration: 0.3 }}, {ws(172):.2f});')
# white card
J(f'tl.fromTo("#wc1", {{ opacity: 0, y: 30 }}, {{ opacity: 1, y: 0, duration: 0.3, ease: "power3.out" }}, {ws(153) - 0.04:.2f});')
J(f'tl.fromTo("#wc2", {{ opacity: 0, scale: 1.6 }}, {{ opacity: 1, scale: 1, duration: 0.3, ease: "expo.out" }}, {ws(156) - 0.04:.2f});')
J(f'tl.fromTo("#wc3", {{ opacity: 0, y: 30 }}, {{ opacity: 1, y: 0, duration: 0.35, ease: "power3.out" }}, {ws(157) - 0.04:.2f});')
J(f'tl.fromTo("#wc-photo", {{ opacity: 0, y: 60 }}, {{ opacity: 1, y: 0, duration: 0.5, ease: "expo.out" }}, {WHITE_CARD[0]:.2f});')
J(f'tl.fromTo("#p9", {{ scale: 1.15 }}, {{ scale: 1.25, duration: {WHITE_CARD[1] - WHITE_CARD[0]:.2f}, ease: "none" }}, {WHITE_CARD[0]:.2f});')
J(f'tl.fromTo("#wc-q1", {{ opacity: 0, rotation: -20, scale: 0.6 }}, {{ opacity: 1, rotation: 8, scale: 1, duration: 0.45, ease: "back.out(2)" }}, {ws(160) - 0.05:.2f});')
# S9 end card
J(f'tl.fromTo("#km", {{ opacity: 0, scale: 1.35 }}, {{ opacity: 1, scale: 1, duration: 0.9, ease: "expo.out" }}, {END + 0.25:.2f});')
J(f'tl.fromTo("#km-line", {{ scaleX: 0 }}, {{ scaleX: 1, duration: 0.7, ease: "expo.out" }}, {END + 0.45:.2f});')

page = f"""<!doctype html>
<html lang="vi">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1080, height=1920" />
    <title>Hành Trình 6 Năm — Talking Head</title>
    <script src="assets/gsap.min.js"></script>
    <style>
{fonts_css}
      :root {{
        --red: #c8102e;
        --red-hot: #ff3b4a;
        --ink: #0b0b0c;
        --paper: #f3f1ec;
        --line: #cbd5e1;
        --sans: "Be Vietnam Pro", sans-serif;
        --serif: "Playfair Display", serif;
      }}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: 1080px; height: 1920px; overflow: hidden; background: var(--ink); }}
      #root {{ position: relative; width: 100%; height: 100%; overflow: hidden; background: var(--ink); font-family: var(--sans); }}
      .scene {{ position: absolute; inset: 0; overflow: hidden; }}
      .cam {{ position: absolute; inset: 0; overflow: hidden; }}
      .pimg {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; display: block; }}
      .bw .pimg {{ filter: grayscale(1) contrast(1.1); }}
      .warm {{ position: absolute; inset: 0; background: linear-gradient(180deg, rgba(255,140,40,0.06), rgba(0,0,0,0) 40%, rgba(0,0,0,0.55) 100%); }}
      .warm.strong {{ background: linear-gradient(180deg, rgba(255,150,60,0.14), rgba(0,0,0,0) 45%, rgba(0,0,0,0.6) 100%); }}
      .vignette {{ position: absolute; inset: 0; background: radial-gradient(ellipse at 50% 40%, rgba(0,0,0,0) 55%, rgba(0,0,0,0.55) 100%); }}
      /* split layouts */
      .split2 {{ position: absolute; inset: 0; display: grid; grid-template-columns: 1fr 1fr; }}
      .pane {{ position: relative; overflow: hidden; }}
      .paper {{ background: var(--paper); }}
      .lines {{ position: absolute; inset: 0; background: repeating-linear-gradient(180deg, transparent 0 58px, rgba(20,20,20,0.12) 58px 60px); }}
      .art-wrap {{ position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; }}
      .art {{ width: 78%; height: auto; display: block; }}
      .dark-pad {{ background: #0e0e0e; }}
      .art-wrap.big .art {{ width: 300%; flex: none; }}
      .key {{ fill: #262626; stroke: #3d3d3d; stroke-width: 1.5; }}
      .divider-v {{ position: absolute; top: 0; bottom: 0; left: 50%; width: 2px; margin-left: -1px; background: var(--line); opacity: 0.85; }}
      .divider-h {{ position: absolute; left: 0; right: 0; top: 50%; height: 2px; margin-top: -1px; background: var(--line); opacity: 0.85; }}
      .divider-v.at1 {{ left: 33.333%; }}
      .divider-v.at2 {{ left: 66.666%; }}
      .pane-tag {{ position: absolute; top: 210px; left: 36px; font: 600 22px/1 var(--sans); letter-spacing: 0.3em; color: rgba(255,255,255,0.8); }}
      .pane-tag.dark {{ color: rgba(20,20,20,0.75); }}
      .strip3 {{ position: absolute; top: 0; bottom: 0; left: 0; width: 1260px; display: grid; grid-template-columns: repeat(3, 1fr); }}
      .col {{ position: relative; overflow: hidden; }}
      .col-in {{ position: absolute; inset: 0; }}
      .screen-glow {{ position: absolute; inset: 0; background: linear-gradient(200deg, rgba(90,160,255,0.35), rgba(0,0,0,0) 55%); mix-blend-mode: screen; }}
      .grid4 {{ position: absolute; inset: 0; display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; background: #0d0d0d; }}
      .tile {{ position: relative; overflow: hidden; background: #121212; }}
      .tile-in {{ position: absolute; inset: 0; }}
      .tile .pane-tag {{ top: 40px; }}
      .cap-group.boxed {{ left: 150px; right: 150px; padding: 18px 26px 26px; background: rgba(10,10,10,0.82); border-radius: 6px; }}
      /* keywords */
      .kw {{ position: absolute; left: 0; right: 0; top: 330px; text-align: center; font: 800 64px/1 var(--sans); letter-spacing: 0.3em; color: #fff; text-shadow: 0 4px 30px rgba(0,0,0,0.6); }}
      .kw-dark {{ top: auto; bottom: 560px; left: 0; right: 50%; color: var(--ink); font-size: 96px; text-shadow: none; }}
      .kw-big {{ top: 360px; font: italic 700 150px/1 var(--serif); letter-spacing: 0; color: var(--red-hot); text-shadow: 0 6px 40px rgba(0,0,0,0.7); }}
      #kw-gimbal {{ top: 880px; left: 540px; right: 0; font-size: 44px; }}
      #kw-flycam {{ top: 1840px; top: auto; bottom: 1000px; left: 0; right: 540px; font-size: 44px; }}
      #kw-dung {{ top: 300px; }}
      /* red card */
      .red-bg {{ position: absolute; inset: 0; background: linear-gradient(180deg, #b30d22, #8a0617); overflow: hidden; }}
      .red-glow {{ position: absolute; left: -20%; right: -20%; top: -10%; height: 70%; background: radial-gradient(ellipse at 50% 30%, rgba(255,90,90,0.55), rgba(0,0,0,0) 60%); }}
      .card-stack {{ position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 26px; padding-bottom: 160px; }}
      .card-small {{ font: 700 46px/1 var(--sans); letter-spacing: 0.4em; color: #fff; }}
      .card-small.dim {{ color: rgba(255,255,255,0.75); font-size: 34px; }}
      .card-serif {{ font: italic 700 92px/1.05 var(--serif); color: #fff; }}
      .zero-wrap {{ display: block; }}
      .zero {{ display: block; font: 800 520px/0.95 var(--sans); color: #fff; letter-spacing: -0.04em; }}
      /* letterbox */
      .bar {{ position: absolute; left: 0; right: 0; height: 250px; background: #000; }}
      .bar.top {{ top: 0; }}
      .bar.bottom {{ bottom: 0; }}
      .corner-tag {{ position: absolute; left: 48px; bottom: 290px; font: 600 26px/1 var(--sans); letter-spacing: 0.22em; color: rgba(255,255,255,0.88); }}
      /* center frame */
      .studio {{ position: absolute; inset: 0; background: radial-gradient(ellipse at 50% 40%, #3a3b3e, #17181a 75%); }}
      .inset-frame {{ position: absolute; inset: 0; overflow: hidden; outline: 2px solid rgba(203,213,225,0.7); }}
      /* white card */
      .paper-bg {{ position: absolute; inset: 0; background: linear-gradient(180deg, #ffffff, #ececec); }}
      .grid-lines {{ position: absolute; left: 240px; right: 240px; top: 820px; height: 640px; background-image: linear-gradient(rgba(0,0,0,0.08) 2px, transparent 2px), linear-gradient(90deg, rgba(0,0,0,0.08) 2px, transparent 2px); background-size: 80px 80px; }}
      .wc-text {{ position: absolute; left: 0; right: 0; top: 360px; display: flex; flex-direction: column; align-items: center; gap: 12px; }}
      .wc-l1 {{ font: 800 74px/1.1 var(--sans); color: var(--ink); }}
      .wc-l2 {{ font: 800 150px/1 var(--sans); color: var(--red); letter-spacing: 0.06em; }}
      .wc-l3 {{ font: italic 700 72px/1.1 var(--serif); color: #2a2a2a; }}
      .wc-photo {{ position: absolute; left: 290px; right: 290px; top: 900px; height: 600px; overflow: hidden; }}
      .qmark {{ position: absolute; right: 150px; top: 960px; font: 800 240px/1 var(--sans); color: var(--red); }}
      /* end */
      .black {{ position: absolute; inset: 0; background: #000; }}
      .end-wrap {{ position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 30px; padding-bottom: 120px; }}
      .keep {{ font: 800 70px/1 var(--sans); color: #fff; letter-spacing: 0.42em; padding-left: 0.42em; }}
      .km-line {{ width: 320px; height: 3px; background: var(--red); display: block; }}
      /* captions */
      #captions {{ position: absolute; inset: 0; z-index: 20; pointer-events: none; }}
      .cap-group {{ position: absolute; left: 90px; right: 90px; top: 1130px; display: flex; flex-wrap: wrap; justify-content: center; align-items: baseline; column-gap: 16px; row-gap: 0; opacity: 0; }}
      .w {{ display: inline-block; font: 800 58px/1.15 var(--sans); color: #fff; text-shadow: 0 3px 18px rgba(0,0,0,0.85), 0 0 2px rgba(0,0,0,0.9); }}
      .w.em {{ font: italic 700 104px/1 var(--serif); color: var(--red-hot); text-shadow: 0 4px 26px rgba(0,0,0,0.9), 0 0 3px rgba(0,0,0,0.8); }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{TOTAL}" data-width="1080" data-height="1920">
      {s1}
      {s2}
      {s3}
      {s4}
      {s5}
      {s6}
      {s7}
      {s8}
      {white}
      {s9}
      <section id="captions" class="clip" data-start="0" data-duration="{END:.3f}" data-track-index="5">
        {''.join(cap_html)}
      </section>
      <audio id="vo" src="assets/voice.mp3" data-start="{VOFF}" data-duration="{W[-1]['end'] + 0.6:.3f}" data-track-index="10" data-volume="1"></audio>
      <audio id="music" src="assets/music.wav" data-start="0" data-duration="{TOTAL}" data-track-index="11" data-volume="0.55"></audio>
      <audio id="sfx" src="assets/sfx.wav" data-start="0" data-duration="{TOTAL}" data-track-index="12" data-volume="0.8"></audio>
    </div>
    <script>
      const tl = gsap.timeline({{ paused: true }});
      {chr(10).join('      ' + x for x in js).strip()}
      {chr(10).join('      ' + x for x in cap_js).strip()}
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
"""
open("index.html", "w", encoding="utf8").write(page)
print("scenes:", {k: (round(v[0], 2), round(v[1], 2)) for k, v in S.items()}, "END", END)
