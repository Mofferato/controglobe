"""Countryballs and banners, drawn as SVG from each polity's flag in phaseN/cast.yaml.

The classic rules: the flag on the ball, a dark outline, two eyes with no pupils, the mood in the
shape of the eyes alone. Each ball has seven moods (neutral, happy, angry, worried, smug, surprised,
sad) and its accessory (the host's broad felt hat, Paquimé's scarlet macaw, the Queen's diadem, the
City's plumes, the Caddo bow, the Canal League's digging stick, the Nahua's codex, the bison's
horns). The same flag gives the polity's banner for army counters, cards and the infobox.
"""

from __future__ import annotations

import math
import re

MOODS = ("neutral", "happy", "angry", "worried", "smug", "surprised", "sad")
INK = "#141414"
CX, CY, R = 256, 286, 206          # the ball inside a 512 x 512 box, room above for a hat


def _wave(y, h, colour, w=440, x0=36, amp=10, n=3):
    """A wavy band (a canal) across the flag."""
    pts = []
    steps = 48
    for i in range(steps + 1):
        x = x0 + w * i / steps
        pts.append((x, y + amp * math.sin(i / steps * n * 2 * math.pi)))
    top = " ".join(f"{x:.1f},{yy:.1f}" for x, yy in pts)
    bot = " ".join(f"{x:.1f},{yy + h:.1f}" for x, yy in reversed(pts))
    return f'<polygon points="{top} {bot}" fill="{colour}"/>'


def _emblem(kind, colour, cx, cy, s):
    """The flag's emblem, centred at cx, cy, about s across."""
    if kind == "t_door":        # Paquimé's T-shaped doorway
        w, h = s * 0.62, s * 0.86
        x0, y0 = cx - w / 2, cy - h / 2
        sw = w * 0.30
        return (f'<path d="M{x0:.1f},{y0:.1f} h{w:.1f} v{h * 0.34:.1f} h{-(w - sw) / 2:.1f} v{h * 0.66:.1f} '
                f'h{-sw:.1f} v{-h * 0.66:.1f} h{-(w - sw) / 2:.1f}z" fill="{colour}"/>')
    if kind == "creed_sabre":   # Solms-America on a ball: the creed in two lines, the sabre below the eyes
        y_text = cy - s * 1.45
        sabre = (f'<g transform="translate({cx - s * 0.95:.1f},{cy + s * 0.05:.1f}) scale({s / 330:.4f})">'
                 '<path d="M0,0C160,56 410,64 550,36L552,60C410,100 150,88 -8,18Z"/><path d="M550,14h16v66h-16z"/>'
                 '<path d="M566,33h66c11,0 18,7 18,14.5s-7,14.5 -18,14.5h-66z"/><circle cx="654" cy="47.5" r="10"/></g>')
        return (f'<g fill="{colour}" font-family="Georgia,serif" font-weight="700" text-anchor="middle">'
                f'<text x="{cx:.1f}" y="{y_text:.1f}" font-size="{s * 0.23:.1f}" letter-spacing="2">ALLEIN GOTT</text>'
                f'<text x="{cx:.1f}" y="{y_text + s * 0.27:.1f}" font-size="{s * 0.23:.1f}" letter-spacing="2">DIE EHRE</text>'
                f'{sabre}</g>')
    if kind == "spiral":        # the sun-dagger spiral of the Great Houses
        pts = []
        for i in range(200):
            a = i / 200 * 3.2 * 2 * math.pi
            r = s * 0.5 * i / 200
            pts.append(f"{cx + r * math.cos(a):.1f},{cy + r * math.sin(a):.1f}")
        return f'<polyline points="{" ".join(pts)}" fill="none" stroke="{colour}" stroke-width="{s * 0.075:.1f}" stroke-linecap="round"/>'
    if kind == "scroll":        # the engraved scroll of Caddo pottery
        r = s * 0.22
        d = (f"M{cx - s * 0.48:.1f},{cy:.1f} "
             f"C{cx - s * 0.3:.1f},{cy - s * 0.45:.1f} {cx - r * 0.2:.1f},{cy - s * 0.35:.1f} {cx:.1f},{cy:.1f} "
             f"S{cx + s * 0.3:.1f},{cy + s * 0.45:.1f} {cx + s * 0.48:.1f},{cy:.1f}")
        c1 = f'<circle cx="{cx - s * 0.3:.1f}" cy="{cy - s * 0.1:.1f}" r="{s * 0.09:.1f}" fill="none" stroke="{colour}" stroke-width="{s * 0.05:.1f}"/>'
        c2 = f'<circle cx="{cx + s * 0.3:.1f}" cy="{cy + s * 0.1:.1f}" r="{s * 0.09:.1f}" fill="none" stroke="{colour}" stroke-width="{s * 0.05:.1f}"/>'
        return f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="{s * 0.08:.1f}" stroke-linecap="round"/>' + c1 + c2
    if kind == "pyramid":       # the City of the Gods: a stepped pyramid, talud and tablero
        out = []
        steps = 4
        for i in range(steps):
            w = s * (1.0 - i * 0.2)
            h = s * 0.16
            y = cy + s * 0.4 - (i + 1) * h
            out.append(f'<rect x="{cx - w / 2:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h * 0.92:.1f}" fill="{colour}"/>')
        out.append(f'<rect x="{cx - s * 0.06:.1f}" y="{cy - s * 0.26:.1f}" width="{s * 0.12:.1f}" height="{s * 0.66:.1f}" fill="{colour}" opacity="0.55"/>')
        return "".join(out)
    if kind == "flame":         # the Fire-Keepers' flame
        d = (f"M{cx:.1f},{cy - s * 0.5:.1f} C{cx + s * 0.32:.1f},{cy - s * 0.15:.1f} {cx + s * 0.36:.1f},{cy + s * 0.3:.1f} "
             f"{cx:.1f},{cy + s * 0.42:.1f} C{cx - s * 0.36:.1f},{cy + s * 0.3:.1f} {cx - s * 0.3:.1f},{cy - s * 0.05:.1f} "
             f"{cx - s * 0.1:.1f},{cy - s * 0.2:.1f} C{cx - s * 0.08:.1f},{cy:.1f} {cx + s * 0.02:.1f},{cy - s * 0.25:.1f} {cx:.1f},{cy - s * 0.5:.1f}z")
        inner = (f"M{cx:.1f},{cy - s * 0.05:.1f} C{cx + s * 0.15:.1f},{cy + s * 0.1:.1f} {cx + s * 0.14:.1f},{cy + s * 0.3:.1f} "
                 f"{cx:.1f},{cy + s * 0.34:.1f} C{cx - s * 0.14:.1f},{cy + s * 0.3:.1f} {cx - s * 0.12:.1f},{cy + s * 0.1:.1f} {cx:.1f},{cy - s * 0.05:.1f}z")
        return f'<path d="{d}" fill="{colour}"/><path d="{inner}" fill="#ffd36b"/>'
    if kind == "heron":         # Aztlan, the place of herons
        d = (f"M{cx - s * 0.32:.1f},{cy + s * 0.1:.1f} C{cx - s * 0.1:.1f},{cy - s * 0.05:.1f} {cx + s * 0.1:.1f},{cy - s * 0.05:.1f} "
             f"{cx + s * 0.18:.1f},{cy - s * 0.25:.1f} C{cx + s * 0.22:.1f},{cy - s * 0.4:.1f} {cx + s * 0.1:.1f},{cy - s * 0.46:.1f} "
             f"{cx + s * 0.06:.1f},{cy - s * 0.36:.1f} L{cx + s * 0.38:.1f},{cy - s * 0.33:.1f} L{cx + s * 0.08:.1f},{cy - s * 0.3:.1f} "
             f"C{cx + s * 0.05:.1f},{cy - s * 0.12:.1f} {cx - s * 0.05:.1f},{cy + s * 0.12:.1f} {cx - s * 0.32:.1f},{cy + s * 0.1:.1f}z")
        legs = (f'<path d="M{cx - s * 0.05:.1f},{cy + s * 0.06:.1f} L{cx - s * 0.08:.1f},{cy + s * 0.42:.1f} '
                f'M{cx + s * 0.04:.1f},{cy + s * 0.05:.1f} L{cx + s * 0.06:.1f},{cy + s * 0.42:.1f}" stroke="{colour}" stroke-width="{s * 0.035:.1f}"/>')
        return f'<path d="{d}" fill="{colour}"/>' + legs
    return ""


def flag_svg(spec: dict, cast_dir=None, w=440, h=440, x0=36, y0=76, clip=None, ball=False) -> str:
    """The flag's drawing in a box (by default the ball's square). On a ball the emblem sits below
    the eyes, smaller, and an image flag can be zoomed and moved (`zoom`, `dy`) to clear them."""
    if "svg" in spec:
        from pathlib import Path
        src = (Path(cast_dir) / spec["svg"]).read_text(encoding="utf8")
        vb = re.search(r'viewBox="([^"]+)"', src).group(1).split()
        vw, vh = float(vb[2]), float(vb[3])
        inner = re.sub(r"^<svg[^>]*>|</svg>$", "", src.strip())
        k = max(w / vw, h / vh) * (spec.get("zoom", 1.0) if ball else 1.0)
        tx = x0 + (w - vw * k) / 2
        ty = y0 + (h - vh * k) / 2 + (spec.get("dy", 0.0) * h if ball else 0.0)
        return f'<g transform="translate({tx:.2f},{ty:.2f}) scale({k:.4f})">{inner}</g>'
    out = [f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="{spec.get("field", "#888")}"/>']
    for b in spec.get("bands", []):
        yy, hh = y0 + b["y"] * h, b["h"] * h
        if b.get("wave"):
            out.append(_wave(yy, hh, b["colour"], w=w, x0=x0, amp=h * 0.022))
        else:
            out.append(f'<rect x="{x0}" y="{yy:.1f}" width="{w}" height="{hh:.1f}" fill="{b["colour"]}"/>')
    if spec.get("base"):
        out.append(f'<rect x="{x0}" y="{y0 + h * 0.8:.1f}" width="{w}" height="{h * 0.2:.1f}" fill="{spec["base"]}"/>')
    if spec.get("border") == "fret":
        c = spec.get("border_colour", INK)
        t = h * 0.07
        out.append(f'<rect x="{x0}" y="{y0}" width="{w}" height="{t:.1f}" fill="{c}"/>')
        out.append(f'<rect x="{x0}" y="{y0 + h - t:.1f}" width="{w}" height="{t:.1f}" fill="{c}"/>')
        n = 9
        for i in range(n):
            x = x0 + w * (i + 0.5) / n
            out.append(f'<path d="M{x - w / n * 0.35:.1f},{y0 + t:.1f} v{t * 0.9:.1f} h{w / n * 0.35:.1f} v{-t * 0.5:.1f}" '
                       f'fill="none" stroke="{c}" stroke-width="{t * 0.35:.1f}"/>')
            out.append(f'<path d="M{x + w / n * 0.35:.1f},{y0 + h - t:.1f} v{-t * 0.9:.1f} h{-w / n * 0.35:.1f} v{t * 0.5:.1f}" '
                       f'fill="none" stroke="{c}" stroke-width="{t * 0.35:.1f}"/>')
    if spec.get("trim"):
        out.append(f'<rect x="{x0}" y="{y0 + h * 0.86:.1f}" width="{w}" height="{h * 0.05:.1f}" fill="{spec["trim"]}"/>')
    cx, cy = x0 + w / 2, y0 + h * (0.7 if ball else 0.46)
    es = h * (0.3 if ball else 0.42)
    if spec.get("disc"):
        out.append(f'<circle cx="{cx}" cy="{cy:.1f}" r="{es * 0.62:.1f}" fill="{spec["disc"]}"/>')
    if spec.get("sun"):
        out.append(f'<circle cx="{cx + w * 0.22:.1f}" cy="{y0 + h * 0.2:.1f}" r="{h * 0.08:.1f}" fill="{spec["sun"]}"/>')
    if spec.get("emblem"):
        out.append(_emblem(spec["emblem"], spec.get("emblem_colour", "#fff"), cx, cy, es))
    return "".join(out)


# -- eyes ---------------------------------------------------------------------------------------

def _eye(ex, ey, mood, side, look=(0.0, 0.0), uid=""):
    """One eye: a white oval with a dark rim; the mood cuts it."""
    rx, ry = 31, 43
    if mood == "surprised":
        rx, ry = 38, 52
    ex += look[0] * 6
    ey += look[1] * 6
    if mood == "happy":       # closed, smiling: an arc
        return (f'<path d="M{ex - rx:.1f},{ey + 8:.1f} Q{ex:.1f},{ey - ry * 0.95:.1f} {ex + rx:.1f},{ey + 8:.1f}" '
                f'fill="none" stroke="{INK}" stroke-width="13" stroke-linecap="round"/>')
    cut = None
    s = 1 if side == "left" else -1           # which way the brow slopes
    if mood == "angry":       # the top cut down toward the nose
        cut = [(ex - rx - 10, ey - ry - 10 + (0 if s > 0 else 30)), (ex + rx + 10, ey - ry - 10 + (30 if s > 0 else 0))]
        cut = [(cut[0][0], ey - ry * 0.25 - 18 * s), (cut[1][0], ey - ry * 0.25 + 18 * s)]
    elif mood in ("worried", "sad"):          # the top cut up toward the nose
        cut = [(ex - rx - 10, ey - ry * 0.35 + 16 * s), (ex + rx + 10, ey - ry * 0.35 - 16 * s)]
    elif mood == "smug":      # half-lidded
        cut = [(ex - rx - 10, ey - ry * 0.05 + 6 * s), (ex + rx + 10, ey - ry * 0.05 - 6 * s)]
    oval = f'<ellipse cx="{ex:.1f}" cy="{ey:.1f}" rx="{rx}" ry="{ry}"'
    if not cut:
        return oval + f' fill="#fff" stroke="{INK}" stroke-width="8"/>'
    (x1, y1), (x2, y2) = cut
    cid = f"c{uid}{side}"
    poly = f"{x1:.1f},{y1:.1f} {x2:.1f},{y2:.1f} {x2:.1f},{ey + ry + 20:.1f} {x1:.1f},{ey + ry + 20:.1f}"
    out = (f'<clipPath id="{cid}"><polygon points="{poly}"/></clipPath>'
           f'<g clip-path="url(#{cid})">{oval} fill="#fff" stroke="{INK}" stroke-width="8"/></g>'
           f'<line x1="{x1 + 8:.1f}" y1="{y1 + (y2 - y1) * 8 / (x2 - x1):.1f}" x2="{x2 - 8:.1f}" y2="{y2 - (y2 - y1) * 8 / (x2 - x1):.1f}" '
           f'stroke="{INK}" stroke-width="9" stroke-linecap="round"/>')
    if mood == "sad":
        out += (f'<path d="M{ex + 4:.1f},{ey + ry + 6:.1f} q-9,18 0,26 q9,-8 0,-26z" fill="#7fc4ff" stroke="{INK}" '
                f'stroke-width="3"/>')
    return out


# -- accessories --------------------------------------------------------------------------------

def _hat(kind, uid):
    if kind == "felt_hat":      # the plains rider's broad felt hat, white for summer
        return (f'<g><ellipse cx="256" cy="112" rx="186" ry="34" fill="#efe9dc" stroke="{INK}" stroke-width="8"/>'
                f'<path d="M160,112 C160,40 190,18 256,18 C322,18 352,40 352,112 Z" fill="#f4efe3" stroke="{INK}" stroke-width="8"/>'
                f'<path d="M222,34 C240,52 272,52 290,34" fill="none" stroke="#cfc6b2" stroke-width="7"/>'
                f'<rect x="160" y="86" width="192" height="20" fill="#3a2b1e"/>'
                f'<path d="M160,112 C200,124 312,124 352,112" fill="none" stroke="{INK}" stroke-width="6"/></g>')
    if kind == "macaw":         # a scarlet macaw on the ball
        return (f'<g transform="translate(300,24) rotate(8)">'
                f'<path d="M30,96 C10,140 20,170 6,210 L28,206 C40,170 60,150 62,110 Z" fill="#1f5fb8" stroke="{INK}" stroke-width="5"/>'
                f'<ellipse cx="44" cy="70" rx="34" ry="46" fill="#d7262b" stroke="{INK}" stroke-width="6"/>'
                f'<path d="M24,74 C34,104 60,110 74,92 C60,100 40,94 34,72Z" fill="#f2c230"/>'
                f'<path d="M30,84 C40,112 62,118 72,104 C58,108 44,104 38,86Z" fill="#2a7fd4"/>'
                f'<circle cx="44" cy="36" r="24" fill="#d7262b" stroke="{INK}" stroke-width="6"/>'
                f'<ellipse cx="38" cy="34" rx="9" ry="10" fill="#fff" stroke="{INK}" stroke-width="3"/>'
                f'<path d="M58,30 C80,28 82,52 66,58 C68,48 64,42 56,44Z" fill="#e8e2d2" stroke="{INK}" stroke-width="4"/>'
                f'<path d="M30,112 L22,126 M42,114 L40,128" stroke="{INK}" stroke-width="5"/></g>')
    if kind == "diadem":        # the Turquoise Queen
        gems = "".join(f'<circle cx="{x}" cy="{y}" r="11" fill="#33c2b0" stroke="{INK}" stroke-width="4"/>'
                       for x, y in ((206, 92), (256, 72), (306, 92)))
        return (f'<path d="M172,108 L196,62 L226,98 L256,44 L286,98 L316,62 L340,108 Z" fill="#d9a92b" stroke="{INK}" '
                f'stroke-width="7" stroke-linejoin="round"/>' + gems)
    if kind == "plumes":        # the City's feathered headdress
        out = []
        for i, a in enumerate((-48, -30, -14, 0, 14, 30, 48)):
            col = "#1d8a4e" if i % 2 == 0 else "#2fb36a"
            out.append(f'<path d="M256,110 C236,60 240,10 256,-6 C272,10 276,60 256,110Z" fill="{col}" stroke="{INK}" '
                       f'stroke-width="5" transform="rotate({a} 256 112)"/>')
        out.append(f'<rect x="170" y="94" width="172" height="26" rx="6" fill="#d9a92b" stroke="{INK}" stroke-width="6"/>')
        out.append('<circle cx="256" cy="107" r="9" fill="#33c2b0"/>')
        return "".join(out)
    if kind == "bow":           # a bois d'arc bow behind the ball
        return (f'<path d="M470,150 C540,260 520,380 448,452" fill="none" stroke="#8a5a2b" stroke-width="16" stroke-linecap="round"/>'
                f'<path d="M470,150 L448,452" stroke="#e8dcc0" stroke-width="4"/>')
    if kind == "digging_stick":  # the canal-digger's stick
        return (f'<path d="M58,474 L150,150" stroke="#7a4e25" stroke-width="18" stroke-linecap="round"/>'
                f'<path d="M150,150 L168,96 L136,140Z" fill="#5d3a1a" stroke="{INK}" stroke-width="5"/>')
    if kind == "codex":         # a screenfold book
        return (f'<g transform="translate(18,330) rotate(-12)">'
                f'<rect x="0" y="0" width="120" height="86" fill="#f4ecd6" stroke="{INK}" stroke-width="6"/>'
                f'<path d="M30,0 v86 M60,0 v86 M90,0 v86" stroke="#b9a678" stroke-width="3"/>'
                f'<path d="M8,20 h14 M38,30 h16 M68,18 h14 M98,40 h12" stroke="#b33a3a" stroke-width="5"/></g>')
    if kind == "horns":         # the bison
        return (f'<path d="M110,170 C60,150 50,90 90,70 C84,110 110,140 150,150Z" fill="#e8e0cc" stroke="{INK}" stroke-width="7"/>'
                f'<path d="M402,170 C452,150 462,90 422,70 C428,110 402,140 362,150Z" fill="#e8e0cc" stroke="{INK}" stroke-width="7"/>'
                f'<path d="M150,120 C190,60 322,60 362,120 C330,100 182,100 150,120Z" fill="#3b2516"/>')
    return ""


def ball_svg(cid: str, char: dict, mood: str = "neutral", cast_dir=None, look=(0.0, 0.0), size=512) -> str:
    """One countryball as a standalone SVG."""
    flag = char.get("ball_flag") or char.get("flag", {})
    if "same_as" in flag:
        flag = char["_cast"][flag["same_as"]]["flag"]
    uid = f"{cid}{mood}"
    hat = char.get("hat", "none")
    behind = hat in ("bow",)
    body = (f'<clipPath id="b{uid}"><circle cx="{CX}" cy="{CY}" r="{R}"/></clipPath>'
            f'<g clip-path="url(#b{uid})">{flag_svg(flag, cast_dir, w=2 * R + 40, h=2 * R + 40, x0=CX - R - 20, y0=CY - R - 20, ball=True)}'
            f'<circle cx="{CX}" cy="{CY}" r="{R}" fill="url(#hl{uid})"/>'
            f'<circle cx="{CX}" cy="{CY}" r="{R}" fill="url(#sh{uid})"/></g>'
            f'<circle cx="{CX}" cy="{CY}" r="{R}" fill="none" stroke="{INK}" stroke-width="10"/>')
    defs = (f'<defs><radialGradient id="hl{uid}" cx="0.34" cy="0.28" r="0.5">'
            f'<stop offset="0" stop-color="#fff" stop-opacity="0.42"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
            f'<radialGradient id="sh{uid}" cx="0.5" cy="0.45" r="0.62">'
            f'<stop offset="0.62" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="0.38"/></radialGradient></defs>')
    ex = 64
    eyes = _eye(CX - ex, CY - 18, mood, "left", look, uid) + _eye(CX + ex, CY - 18, mood, "right", look, uid)
    accessory = _hat(hat, uid)
    parts = [defs]
    if behind:
        parts.append(accessory)
    parts.append(body)
    parts.append(eyes)
    if not behind:
        parts.append(accessory)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -20 512 532" width="{size}" height="{size}">'
            + "".join(parts) + "</svg>")


def banner_svg(char: dict, cast_dir=None, w=300, h=200) -> str:
    """The polity's flag as a rectangle, for counters, cards and the infobox."""
    flag = char.get("flag", {})
    if "same_as" in flag:
        flag = char["_cast"][flag["same_as"]]["flag"]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid slice">'
            f'<clipPath id="r"><rect width="{w}" height="{h}"/></clipPath><g clip-path="url(#r)">'
            + flag_svg(flag, cast_dir, w=w, h=h, x0=0, y0=0) + "</g></svg>")
