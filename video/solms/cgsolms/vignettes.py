"""City vignettes: the architecture and life of each people, drawn as illustrated cards in the
phase's skin. Each card is an SVG: a painted scene above, the place's names in every language and
two lines on what it was like below. The drawings are our own, after the real sites the setting
stands on (Paquimé's T-shaped doors, macaw pens and cross-shaped mound; the canals and pit-houses
of the Gila; the D-shaped great house of Chaco and its kivas; the Caddo mounds; the earthworks of
the eastern woods; the stepped pyramid of the Valley of Mexico).
"""

from __future__ import annotations

import math
import random

W, H, SH = 640, 450, 290          # card size, height of the scene


def _ridge(rng, y0, amp, n=40, w=W, rough=0.5):
    pts = []
    y = y0
    for i in range(n + 1):
        y = y0 + amp * (math.sin(i * 0.45 + rng.random() * 2) * 0.5 + (rng.random() - 0.5) * rough)
        pts.append((w * i / n, y))
    return pts


def _poly(pts, fill, extra=""):
    return f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" fill="{fill}" {extra}/>'


def _mountains(rng, y0, amp, fill, h=SH):
    pts = _ridge(rng, y0, amp)
    return _poly([(0, h)] + pts + [(W, h)], fill)


def _sky(top, bottom, sun=None):
    out = (f'<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{top}"/>'
           f'<stop offset="1" stop-color="{bottom}"/></linearGradient></defs><rect width="{W}" height="{SH}" fill="url(#sky)"/>')
    if sun:
        x, y, r, c = sun
        out += f'<circle cx="{x}" cy="{y}" r="{r * 2.4}" fill="{c}" opacity=".25"/><circle cx="{x}" cy="{y}" r="{r}" fill="{c}"/>'
    return out


def _block(x, y, w, h, wall="#c99560", shade="#a87645", top="#d9aa72"):
    """An adobe block: front, a shaded side, roof beams."""
    out = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{wall}"/>'
    out += f'<polygon points="{x + w},{y} {x + w + 10},{y - 6} {x + w + 10},{y + h - 6} {x + w},{y + h}" fill="{shade}"/>'
    out += f'<polygon points="{x},{y} {x + 10},{y - 6} {x + w + 10},{y - 6} {x + w},{y}" fill="{top}"/>'
    for bx in range(int(x) + 6, int(x + w) - 2, 12):
        out += f'<rect x="{bx}" y="{y + 3}" width="3" height="3" fill="#5a3a1c"/>'
    return out


def _tdoor(x, y, s=1.0, c="#3a2410"):
    w, h = 14 * s, 22 * s
    return (f'<path d="M{x},{y} h{w} v{h * 0.35} h{-w * 0.28} v{h * 0.65} h{-w * 0.44} v{-h * 0.65} h{-w * 0.28}z" fill="{c}"/>')


def _saguaro(x, y, h, c="#3d6b3a"):
    w = h * 0.12
    return (f'<rect x="{x - w / 2}" y="{y - h}" width="{w}" height="{h}" rx="{w / 2}" fill="{c}"/>'
            f'<path d="M{x - w / 2},{y - h * 0.45} h{-w * 1.4} v{-h * 0.3}" stroke="{c}" stroke-width="{w * 0.8}" fill="none" stroke-linecap="round"/>'
            f'<path d="M{x + w / 2},{y - h * 0.6} h{w * 1.2} v{-h * 0.22}" stroke="{c}" stroke-width="{w * 0.8}" fill="none" stroke-linecap="round"/>')


def _pine(x, y, h, c="#24502e"):
    return "".join(_poly([(x, y - h + i * h * 0.22), (x - h * (0.18 + i * 0.07), y - h * 0.55 + i * h * 0.22),
                          (x + h * (0.18 + i * 0.07), y - h * 0.55 + i * h * 0.22)], c) for i in range(3)) + \
        f'<rect x="{x - 2}" y="{y - h * 0.15}" width="4" height="{h * 0.15}" fill="#4a3220"/>'


def _smoke(rng, x, y, n=6, c="#8a8a8a", op=0.45, rise=90):
    return "".join(f'<ellipse cx="{x + (rng.random() - 0.3) * 18 * i:.1f}" cy="{y - i * rise / n:.1f}" rx="{8 + i * 4}" ry="{6 + i * 3}" '
                   f'fill="{c}" opacity="{op * (1 - i / n):.2f}"/>' for i in range(n))


def _bird(x, y, c="#d7262b"):
    return f'<path d="M{x - 7},{y} q4,-6 7,0 q3,-6 7,0" fill="none" stroke="{c}" stroke-width="2.6" stroke-linecap="round"/>'


# -- the scenes ---------------------------------------------------------------------------------

def paquime(rng):
    out = _sky("#5d7fab", "#f4c27c", sun=(520, 140, 26, "#ffe3a0"))
    out += _mountains(rng, 150, 40, "#8a8fb0")
    out += _mountains(rng, 190, 28, "#7a6070")
    out += f'<rect y="215" width="{W}" height="{SH - 215}" fill="#cf9f63"/>'
    # the mound of the cross, its arms to the four roads
    out += _poly([(70, 255), (100, 255), (100, 243), (114, 243), (114, 255), (144, 255), (144, 263), (114, 263), (114, 276),
                  (100, 276), (100, 263), (70, 263)], "#b8854f", 'stroke="#7a5230" stroke-width="2"')
    # the house blocks, stepped
    for (x, y, w, h) in [(210, 190, 90, 40), (290, 170, 80, 60), (360, 185, 110, 45), (240, 150, 70, 40), (330, 130, 60, 40),
                         (420, 160, 60, 25)]:
        out += _block(x, y, w, h)
    for (x, y) in [(225, 205), (262, 205), (305, 190), (330, 195), (380, 200), (420, 200), (255, 162), (342, 145), (440, 168)]:
        out += _tdoor(x, y, 0.9)
    # the macaw pens: rows of adobe boxes with round doors
    for i in range(6):
        x = 480 + i * 22
        out += f'<rect x="{x}" y="235" width="18" height="16" fill="#c08a52" stroke="#7a5230"/><circle cx="{x + 9}" cy="243" r="3.6" fill="#3a2410"/>'
    for (x, y) in [(470, 120), (500, 100), (540, 112), (450, 90)]:
        out += _bird(x, y)
    # the ballcourt, I-shaped and sunken
    out += _poly([(170, 262), (240, 262), (240, 268), (225, 268), (225, 278), (240, 278), (240, 284), (170, 284), (170, 278), (185, 278),
                  (185, 268), (170, 268)], "#a0703f", 'stroke="#6b4626" stroke-width="2"')
    out += _smoke(rng, 300, 150, n=5, c="#d8c8b0", op=0.4)
    return out


def skoaquik(rng):
    out = _sky("#7fb0d8", "#f3dcb0", sun=(110, 70, 22, "#fff4cc"))
    out += _mountains(rng, 165, 34, "#a78a7a")
    out += f'<rect y="200" width="{W}" height="{SH - 200}" fill="#d8b47e"/>'
    # canals, and the headgate of brush and stone
    for i, y in enumerate((220, 245, 270)):
        out += f'<path d="M0,{y} C160,{y - 18} 360,{y + 14} {W},{y - 6}" stroke="#3f8bc0" stroke-width="{7 - i}" fill="none"/>'
        out += f'<path d="M0,{y + 4} C160,{y - 14} 360,{y + 18} {W},{y - 2}" stroke="#6aa8d0" stroke-width="2" fill="none" opacity=".7"/>'
    out += '<rect x="58" y="206" width="34" height="26" fill="#7a6a58" stroke="#3e3428" stroke-width="2"/>'
    out += '<path d="M62,212 l26,0 M62,220 l26,0" stroke="#3e3428" stroke-width="2"/>'
    # pit-houses
    for (x, y) in [(200, 236), (260, 250), (420, 230), (480, 252), (330, 262)]:
        out += f'<path d="M{x - 26},{y} q26,-30 52,0z" fill="#b88e5c" stroke="#6b4c2e" stroke-width="2"/><rect x="{x - 5}" y="{y - 12}" width="10" height="12" fill="#3a2410"/>'
    # the ballcourt, an oval bank
    out += '<ellipse cx="560" cy="270" rx="60" ry="14" fill="#c7a06a" stroke="#7a5230" stroke-width="3"/>'
    for x in (150, 380, 600, 30):
        out += _saguaro(x, 212 + rng.random() * 30, 46 + rng.random() * 20)
    return out


def chaco(rng):
    out = _sky("#7da7d6", "#efe0c4")
    # the canyon's north wall
    out += _poly([(0, 60), (90, 70), (160, 58), (260, 74), (380, 60), (500, 76), (640, 62), (640, 200), (0, 200)], "#c98c5a")
    for y in range(80, 200, 14):
        out += f'<path d="M0,{y} L{W},{y + 4}" stroke="#a96f43" stroke-width="2" opacity=".5"/>'
    out += f'<rect y="200" width="{W}" height="{SH - 200}" fill="#d7ad7a"/>'
    # Pueblo Bonito: a D-shaped great house, many storeys, round kivas in its plaza
    cx, cy = 320, 255
    out += f'<path d="M{cx - 200},{cy} A200,95 0 0 1 {cx + 200},{cy} L{cx + 200},{cy + 6} L{cx - 200},{cy + 6}z" fill="#b98a5c" stroke="#6e4a2a" stroke-width="3"/>'
    out += f'<path d="M{cx - 170},{cy} A170,72 0 0 1 {cx + 170},{cy}z" fill="#d9b483"/>'
    for i in range(16):
        a = math.pi * (0.06 + 0.88 * i / 15)
        x, y = cx - math.cos(a) * 186, cy - math.sin(a) * 84
        out += f'<rect x="{x - 4}" y="{y - 4}" width="8" height="8" fill="#3a2410"/>'
    for (x, y, r) in [(250, 238, 20), (320, 228, 24), (390, 238, 20), (285, 250, 12), (355, 250, 12)]:
        out += f'<ellipse cx="{x}" cy="{y}" rx="{r}" ry="{r * 0.42}" fill="#8a5f3a" stroke="#4e3220" stroke-width="2"/>'
    # the sun-dagger spiral on the cliff
    pts = []
    for i in range(120):
        a = i / 120 * 3 * 2 * math.pi
        r = 18 * i / 120
        pts.append(f"{560 + r * math.cos(a):.1f},{110 + r * math.sin(a):.1f}")
    out += f'<polyline points="{" ".join(pts)}" fill="none" stroke="#5a2e1a" stroke-width="2.4"/>'
    out += '<path d="M560,70 l4,60" stroke="#fff3c0" stroke-width="3" opacity=".9"/>'
    return out


def caddo(rng):
    out = _sky("#8db8dc", "#eef2dc")
    out += f'<rect y="170" width="{W}" height="{SH - 170}" fill="#7fa05a"/>'
    for i in range(22):
        out += _pine(rng.random() * W, 175 + rng.random() * 10, 60 + rng.random() * 40, "#2c5a32" if i % 2 else "#24502e")
    # the temple mound and the burial mound
    out += _poly([(150, 262), (210, 214), (300, 214), (360, 262)], "#7d8f4a", 'stroke="#4f5e2c" stroke-width="2"')
    out += '<path d="M228,214 l27,-34 l27,34z" fill="#c9a45a" stroke="#6b5230" stroke-width="2"/>'
    out += '<rect x="244" y="200" width="22" height="14" fill="#8a6a3a"/>'
    out += '<path d="M410,262 q60,-80 120,0z" fill="#7d8f4a" stroke="#4f5e2c" stroke-width="2"/>'
    # grass houses, beehive-shaped
    for (x, y) in [(70, 262), (110, 270), (560, 268), (600, 258)]:
        out += f'<path d="M{x - 22},{y} q22,-60 44,0z" fill="#c8a85e" stroke="#7a6230" stroke-width="2"/><path d="M{x},{y - 30} v-12" stroke="#7a6230" stroke-width="2"/>'
    out += f'<rect y="262" width="{W}" height="{SH - 262}" fill="#93b064"/>'
    for x in range(20, W, 18):
        out += f'<path d="M{x},{SH} l3,-18" stroke="#c9b45a" stroke-width="2"/>'
    out += _smoke(rng, 255, 175, n=5, c="#d0d0c8", op=0.4)
    return out


def great_bottom(rng):
    out = _sky("#7da2c8", "#f1e6cf")
    out += f'<rect y="150" width="{W}" height="{SH - 150}" fill="#88a45e"/>'
    for i in range(30):
        x = rng.random() * W
        out += f'<circle cx="{x}" cy="{150 + rng.random() * 8}" r="{12 + rng.random() * 10}" fill="#4f7a3e"/>'
    out += '<path d="M0,290 C180,250 300,280 640,232 L640,290z" fill="#4f8fb8"/>'
    # the earthworks: a great circle and an octagon, joined by walls
    out += '<ellipse cx="220" cy="215" rx="120" ry="40" fill="none" stroke="#5f7a3a" stroke-width="9"/>'
    out += '<ellipse cx="220" cy="215" rx="120" ry="40" fill="none" stroke="#a7c06a" stroke-width="3"/>'
    oc = [(440 + 70 * math.cos(a), 210 + 26 * math.sin(a)) for a in [i * math.pi / 4 + math.pi / 8 for i in range(8)]]
    out += _poly(oc, "none", 'stroke="#5f7a3a" stroke-width="9"') + _poly(oc, "none", 'stroke="#a7c06a" stroke-width="3"')
    out += '<path d="M340,212 L370,210" stroke="#5f7a3a" stroke-width="9"/>'
    # the sacred fire on its platform
    out += '<rect x="205" y="208" width="30" height="10" fill="#8a6a3a"/>'
    out += '<path d="M220,180 q14,14 6,28 h-12 q-8,-14 6,-28z" fill="#f08a24"/><path d="M220,192 q6,6 3,16 h-6 q-3,-10 3,-16z" fill="#ffd36b"/>'
    out += _smoke(rng, 220, 175, n=6, c="#bcbcbc", op=0.35)
    return out


def _pyramid(cx, base, w0=300, steps=5, wall="#a58a6a", tab="#8c7356"):
    out = ""
    h = 26
    for i in range(steps):
        w = w0 * (1 - i * 0.16)
        y = base - (i + 1) * h
        out += _poly([(cx - w / 2, y + h), (cx - w / 2 + 10, y + 8), (cx + w / 2 - 10, y + 8), (cx + w / 2, y + h)], wall)  # talud
        out += f'<rect x="{cx - w / 2 + 10}" y="{y}" width="{w - 20}" height="8" fill="{tab}"/>'                             # tablero
    out += f'<rect x="{cx - 14}" y="{base - steps * h - 24}" width="28" height="24" fill="#7a5a3a"/>'
    out += f'<rect x="{cx - 12}" y="{base - steps * h}" width="24" height="{steps * h}" fill="{tab}" opacity=".55"/>'
    return out


def city(rng):
    out = _sky("#6f9fd0", "#f2e3c0", sun=(540, 70, 20, "#fff1c0"))
    out += _mountains(rng, 150, 30, "#8f98ae")
    out += f'<rect y="200" width="{W}" height="{SH - 200}" fill="#bfa070"/>'
    out += _pyramid(300, 260)
    out += _pyramid(520, 255, w0=150, steps=3)
    out += '<path d="M120,290 L280,262 L330,262 L520,290z" fill="#a88a60"/>'
    return out


def city_burns(rng):
    out = _sky("#1d1420", "#b0442a")
    out += _mountains(rng, 160, 26, "#3a2430")
    out += f'<rect y="200" width="{W}" height="{SH - 200}" fill="#5a3a2a"/>'
    out += _pyramid(300, 262, wall="#6a4a3a", tab="#4e3428")
    out += _pyramid(520, 257, w0=150, steps=3, wall="#6a4a3a", tab="#4e3428")
    for (x, y, s) in [(300, 120, 1.4), (520, 175, 0.9), (170, 230, 0.7), (420, 240, 0.8)]:
        out += (f'<path d="M{x},{y - 40 * s} q{24 * s},{30 * s} {10 * s},{44 * s} h{-20 * s} q{-14 * s},{-14 * s} {10 * s},{-44 * s}z" fill="#ff7a24"/>'
                f'<path d="M{x},{y - 18 * s} q{10 * s},{12 * s} {4 * s},{22 * s} h{-8 * s} q{-6 * s},{-10 * s} {4 * s},{-22 * s}z" fill="#ffd36b"/>')
        out += _smoke(rng, x, y - 40 * s, n=7, c="#2a2226", op=0.6, rise=140)
    return out


SCENES = {
    "paquime": (paquime, {"en": "Paquimé", "de": "Paquimé", "ar": "باكيمي", "role": "Makkah",
                          "lines": ["The caravan city where the road from the Rio Grande meets the passes of the Sierra Madre.",
                                    "T-shaped doors · pens for scarlet macaws · the Mound of the Cross, its arms to the four roads."]}),
    "skoaquik": (skoaquik, {"en": "Skoaquik", "de": "Skoakwik", "ar": "سكواكيك", "native": "O'odham, “place of snakes”", "role": "Saba",
                            "lines": ["The royal town of the Canal League, between the Gila and the Salt.",
                                      "Canals for a hundred kilometres · the Great Headgate · pit-houses and ballcourts."]}),
    "chaco": (chaco, {"en": "Chaco", "de": "Chaco", "ar": "تشاكو", "role": "Petra",
                      "lines": ["The seat of the Great Houses, under the north wall of its canyon.",
                                "A D-shaped great house of many storeys · round kivas · the sun-dagger on the cliff."]}),
    "caddo": (caddo, {"en": "The mounds of the Neches", "de": "Die Hügel am Neches", "ar": "تلال نيتشيس", "native": "Caddo: Hasinai", "role": "Gerrha",
                      "lines": ["The seat of the Caddo League, in the pine woods of the east.",
                                "A temple on its flat-topped mound · grass houses · maize, beans and bois d'arc bows."]}),
    "great_bottom": (great_bottom, {"en": "The Great Bottom", "de": "Der Große Grund", "ar": "القاع الكبير", "role": "Ctesiphon",
                                    "lines": ["The Fire-Keepers' capital on the Mississippi, where Cahokia will rise.",
                                              "A great circle and an octagon of earth · the fire that is never let out."]}),
    "city": (city, {"en": "City of the Gods", "de": "Götterstadt", "ar": "مدينة الآلهة", "native": "Nahuatl: Teōtīhuacān", "role": "Rome",
                    "lines": ["The hegemony of the Valley of Mexico, a hundred thousand strong at its height.",
                              "Stepped pyramids of slope and panel · an avenue two kilometres long."]}),
    "city_burns": (city_burns, {"en": "The City of the Gods burns", "de": "Die Götterstadt brennt", "ar": "مدينة الآلهة تحترق",
                                "role": "598", "lines": ["Its temples are fired from within; its northern march falls away.",
                                                          "By 603 the Turquoise Road has no master but the caravan city."]}),
}


def card(key, seed=7):
    """One card; its ids carry the key, so several cards can live in one page (they are inlined,
    so that they draw with the page's fonts and marble)."""
    fn, info = SCENES[key]
    rng = random.Random(seed)
    scene = fn(rng).replace('id="sky"', f'id="sky-{key}"').replace("url(#sky)", f"url(#sky-{key})")
    sub = " · ".join(v for v in (info.get("de") if info.get("de") != info["en"] else None, info.get("native")) if v)
    import textwrap
    wrapped = [w for l in info["lines"] for w in textwrap.wrap(l, 74)][:4]
    lines = "".join(f'<text x="24" y="{368 + i * 22}" font-family="Cormorant, Georgia, serif" font-size="17.5" font-weight="600" '
                    f'fill="#2b2117">{_esc(l)}</text>' for i, l in enumerate(wrapped))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
<defs><linearGradient id="bz-{key}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f0d699"/><stop offset=".3" stop-color="#a77a35"/>
<stop offset=".55" stop-color="#6e4a1c"/><stop offset=".8" stop-color="#c99a52"/><stop offset="1" stop-color="#f0d699"/></linearGradient>
<clipPath id="sc-{key}"><rect x="12" y="12" width="{W - 24}" height="{SH - 12}"/></clipPath>
<pattern id="mb-{key}" width="600" height="600" patternUnits="userSpaceOnUse"><image href="assets/skin/marble.jpg" width="600" height="600"/></pattern></defs>
<rect width="{W}" height="{H}" fill="url(#mb-{key})"/><rect x="3" y="3" width="{W - 6}" height="{H - 6}" fill="none" stroke="url(#bz-{key})" stroke-width="6"/>
<g clip-path="url(#sc-{key})">{scene}</g>
<rect x="12" y="12" width="{W - 24}" height="{SH - 12}" fill="none" stroke="#3b2710" stroke-width="2"/>
<rect x="12" y="{SH}" width="{W - 24}" height="4" fill="#6e1d1d"/>
<text x="24" y="{SH + 34}" font-family="Cinzel, Georgia, serif" font-weight="800" font-size="27" fill="#2a1608">{_esc(info["en"])}</text>
<text x="{W - 24}" y="{SH + 34}" text-anchor="end" font-family="Amiri, serif" font-weight="700" font-size="25" fill="#3a2814">{_esc(info["ar"])}</text>
<text x="24" y="{SH + 56}" font-family="Cormorant, Georgia, serif" font-style="italic" font-weight="600" font-size="18" fill="#6b4e28">{_esc(sub)}{' · carries ' + _esc(info['role']) if info.get('role') and not info['role'].isdigit() else ''}</text>
{lines}
</svg>'''


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build(n, out):
    d = out / "vignettes"
    d.mkdir(exist_ok=True)
    for k in SCENES:
        (d / f"{k}.svg").write_text(card(k), encoding="utf8")
    return list(SCENES)
