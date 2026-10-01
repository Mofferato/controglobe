"""The Turquoise syllabary: the script of the turquoise kingdoms (canon on the Solms-America page:
a syllabary first cut on shell, later painted on deerskin and cotton paper). The glyphs are the
setting's own invention, drawn for the video and marked so on screen.

A glyph is a consonant's shape, cut in straight strokes as on shell, with the vowel as a mark: a for
none, e a bar above, i a dot to the right, o a ring below, u a tick to the left. A final consonant
takes the consonant's shape with a slash through it. `svg("pa-ki-me")` draws a word.
"""

from __future__ import annotations

CONS = ["ts", "p", "t", "k", "s", "h", "m", "n", "w", "y", "r", ""]
VOWELS = "aeiou"

# each consonant's strokes in a 0..100 box (polylines)
SHAPES = {
    "": [[(50, 12), (82, 50), (50, 88), (18, 50), (50, 12)]],
    "p": [[(20, 88), (20, 14), (80, 14), (80, 88)], [(50, 14), (50, 60)]],
    "t": [[(16, 18), (84, 18)], [(50, 18), (50, 88)], [(28, 58), (72, 58)]],
    "k": [[(24, 12), (24, 88)], [(80, 14), (26, 50), (80, 86)]],
    "ts": [[(16, 20), (84, 20), (20, 52), (84, 52), (18, 86)]],
    "s": [[(80, 16), (22, 16), (22, 50), (78, 50), (78, 86), (18, 86)]],
    "h": [[(22, 12), (22, 88)], [(78, 12), (78, 88)], [(22, 70), (78, 30)]],
    "m": [[(14, 86), (14, 18), (50, 56), (86, 18), (86, 86)]],
    "n": [[(22, 88), (22, 14), (78, 86), (78, 12)]],
    "w": [[(12, 16), (32, 86), (50, 40), (68, 86), (88, 16)]],
    "y": [[(18, 14), (50, 50), (82, 14)], [(50, 50), (50, 88)], [(34, 72), (66, 72)]],
    "r": [[(50, 50), (64, 38), (50, 24), (30, 36), (30, 66), (60, 80), (84, 58), (84, 20)]],
}


def parse(word: str):
    """'ha-si-na-i' -> [('h','a'), ('s','i'), ('n','a'), ('','i')]; a syllable with no vowel is final."""
    out = []
    for syl in word.replace(" ", "-").split("-"):
        syl = syl.lower().strip()
        if not syl:
            continue
        for c in CONS:
            if syl.startswith(c) and (len(syl) == len(c) or syl[len(c)] in VOWELS):
                v = syl[len(c):][:1]
                out.append((c, v))
                break
    return out


def glyph(c: str, v: str, x0: float, s: float, stroke: str, w: float) -> str:
    def P(px, py):
        return f"{x0 + px * s / 100:.1f},{py * s / 100:.1f}"
    out = []
    for line in SHAPES.get(c, SHAPES[""]):
        out.append(f'<polyline points="{" ".join(P(*p) for p in line)}" fill="none" stroke="{stroke}" '
                   f'stroke-width="{w:.1f}" stroke-linecap="square" stroke-linejoin="miter"/>')
    if v == "e":
        out.append(f'<line x1="{x0 + 0.3 * s:.1f}" y1="{-0.08 * s:.1f}" x2="{x0 + 0.7 * s:.1f}" y2="{-0.08 * s:.1f}" stroke="{stroke}" stroke-width="{w:.1f}"/>')
    elif v == "i":
        out.append(f'<circle cx="{x0 + 1.04 * s:.1f}" cy="{0.3 * s:.1f}" r="{w * 0.9:.1f}" fill="{stroke}"/>')
    elif v == "o":
        out.append(f'<circle cx="{x0 + 0.5 * s:.1f}" cy="{1.1 * s:.1f}" r="{s * 0.09:.1f}" fill="none" stroke="{stroke}" stroke-width="{w * 0.8:.1f}"/>')
    elif v == "u":
        out.append(f'<line x1="{x0 - 0.04 * s:.1f}" y1="{0.2 * s:.1f}" x2="{x0 + 0.12 * s:.1f}" y2="{0.42 * s:.1f}" stroke="{stroke}" stroke-width="{w:.1f}"/>')
    elif v == "":          # a final consonant: slashed
        out.append(f'<line x1="{x0 + 0.05 * s:.1f}" y1="{0.95 * s:.1f}" x2="{x0 + 0.95 * s:.1f}" y2="{0.05 * s:.1f}" stroke="{stroke}" stroke-width="{w * 0.7:.1f}" opacity="0.8"/>')
    return "".join(out)


def svg(word: str, size: float = 40, stroke: str = "#2fb3a6", width: float | None = None) -> str:
    """A word in the syllabary, as a standalone SVG of height `size`."""
    syl = parse(word)
    s = size * 0.78
    w = width or max(1.6, s * 0.1)
    gap = s * 0.42
    total = len(syl) * (s + gap) - gap if syl else 0
    body = "".join(glyph(c, v, i * (s + gap), s, stroke, w) for i, (c, v) in enumerate(syl))
    pad = s * 0.18
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-pad:.1f} {-0.2 * s:.1f} {total + 2 * pad:.1f} {s * 1.45:.1f}" '
            f'height="{size}" width="{size * (total + 2 * pad) / (s * 1.45):.1f}">{body}</svg>')


def build(n: int, out):
    """Every name the cast and the map use, drawn once."""
    import yaml
    from . import frame as F
    cast = yaml.safe_load((F.phase_dir(n) / "cast.yaml").read_text(encoding="utf8"))
    d = out / "glyphs"
    d.mkdir(exist_ok=True)
    for cid, c in cast.items():
        ts = (c.get("names") or {}).get("ts")
        if ts:
            (d / f"{cid}.svg").write_text(svg(ts), encoding="utf8")
