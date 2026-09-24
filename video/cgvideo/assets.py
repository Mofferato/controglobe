"""Artwork for the infobox and the thumbnail, made at build time, never committed.

- The Union's flag, its Great Seal and the 47 presidential portraits are the encyclopedia's
  own inline SVG, cut out of ../united-states-of-arabia.html and rasterised.
- Every other polity gets a flag drawn from its colour and kind, and every other head of state
  a portrait drawn in the same engraved-card style, unless you supply your own art:
  assets/flags/<polity_id>.png and assets/portraits/<key>.png always win.
"""

from __future__ import annotations

import functools
import hashlib
import io
import math
import pathlib
import re

from PIL import Image

from .config import paths

HTML = "united-states-of-arabia.html"


# -- SVG rasterising -----------------------------------------------------------------

def rasterise(svg: str, width: int) -> Image.Image:
    """SVG text -> RGBA image. cairosvg if it loads (Linux, macOS, or Windows with GTK),
    otherwise the Chromium that Playwright installs (`pip install playwright` then
    `playwright install chromium`)."""
    try:
        import cairosvg
        png = cairosvg.svg2png(bytestring=svg.encode("utf8"), output_width=width)
        return Image.open(io.BytesIO(png)).convert("RGBA")
    except (ImportError, OSError):
        pass
    from playwright.sync_api import sync_playwright
    vb = re.search(r'viewBox="([\d.\s-]+)"', svg)
    w, h = (float(v) for v in vb.group(1).split()[2:4]) if vb else (width, width)
    height = round(width * h / w)
    page_html = (f"<html><body style='margin:0;background:transparent'>"
                 f"<div style='width:{width}px;height:{height}px'>{svg}</div></body></html>")
    page_html = page_html.replace("<svg ", f"<svg width='{width}' height='{height}' ", 1)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.set_content(page_html)
        png = page.screenshot(omit_background=True)
        browser.close()
    return Image.open(io.BytesIO(png)).convert("RGBA")


# -- canon artwork from the encyclopedia -------------------------------------------------

@functools.lru_cache(maxsize=1)
def _canon_svgs(root: str) -> dict[str, str]:
    html = (pathlib.Path(root) / HTML).read_text(encoding="utf8")
    out = {}
    for cls in ("flag", "seal"):
        m = re.search(rf'<svg class="{cls}"[^>]*>.*?</svg>', html, re.S)
        if m:
            out[cls] = m.group(0)
    for m in re.finditer(r'<figure class="pcard" data-pv="(pres-\d+)".*?(<svg class="pt".*?</svg>)', html, re.S):
        out[m.group(1)] = m.group(2)
    for k, v in out.items():
        if "xmlns=" not in v[:300]:
            out[k] = v.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
    return out


def _cache_dir(cfg) -> pathlib.Path:
    d = paths(cfg).build / "assets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _user_art(cfg, kind: str, key: str) -> Image.Image | None:
    for ext in (".png", ".webp", ".jpg"):
        p = paths(cfg).root / "assets" / kind / f"{key}{ext}"
        if p.exists():
            return Image.open(p).convert("RGBA")
    return None


def _cached(cfg, name: str, width: int, make) -> Image.Image:
    p = _cache_dir(cfg) / f"{name}_{width}.png"
    if p.exists():
        return Image.open(p).convert("RGBA")
    img = make()
    img.save(p)
    return img


def union_flag(cfg, width: int = 600) -> Image.Image:
    root = str(paths(cfg).root.parent)
    return _cached(cfg, "flag_usa", width, lambda: rasterise(_canon_svgs(root)["flag"], width))


def union_seal(cfg, width: int = 400) -> Image.Image:
    root = str(paths(cfg).root.parent)
    return _cached(cfg, "seal_usa", width, lambda: rasterise(_canon_svgs(root)["seal"], width))


# -- procedural flags ------------------------------------------------------------------

def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _shade(c, t):
    r, g, b = _hex(c)
    f = (lambda v: v + (255 - v) * t) if t > 0 else (lambda v: v * (1 + t))
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, f(v)))) for v in (r, g, b))


def flag_svg(polity: dict) -> str:
    """A simple, original flag from a polity's colour and kind: seeded, so it never changes."""
    base = polity.get("color") or "#8a8f94"
    seed = int(hashlib.sha1(polity["polity_id"].encode()).hexdigest(), 16)
    dark, light = _shade(base, -0.45), _shade(base, 0.7)
    kind = polity.get("kind", "")
    w, h = 300, 200
    parts = [f'<rect width="{w}" height="{h}" fill="{base}"/>']
    style = seed % 4
    if kind in ("empire", "caliphate"):
        parts.append(f'<rect width="{w}" height="{h}" fill="{dark}"/>')
        parts.append(f'<circle cx="{w * .5}" cy="{h * .5}" r="46" fill="none" stroke="{light}" stroke-width="10"/>')
        parts.append(f'<circle cx="{w * .5}" cy="{h * .5}" r="18" fill="{base}"/>')
    elif kind in ("kingdom", "city"):
        if style % 2:
            parts.append(f'<rect y="{h * .66}" width="{w}" height="{h * .34}" fill="{dark}"/>')
        else:
            parts.append(f'<rect width="{w * .33}" height="{h}" fill="{dark}"/>')
        star = " ".join(f"{w * .66 + 34 * math.cos(math.pi / 2 + k * math.pi * 4 / 5):.1f},"
                        f"{h * .4 - 34 * math.sin(math.pi / 2 + k * math.pi * 4 / 5):.1f}" for k in range(5))
        parts.append(f'<polygon points="{star}" fill="{light}"/>')
    elif kind in ("confederation", "league", "imamate"):
        for k in range(3):
            parts.append(f'<rect y="{k * h / 3}" width="{w}" height="{h / 3}" fill="{[dark, base, light][(k + style) % 3]}"/>')
    elif kind in ("colony", "company"):
        parts.append(f'<rect width="{w * .4}" height="{h * .5}" fill="{dark}"/>')
        parts.append(f'<circle cx="{w * .2}" cy="{h * .25}" r="22" fill="{light}"/>')
    else:  # union, republic and the rest
        for k in range(7):
            parts.append(f'<rect y="{k * h / 7}" width="{w}" height="{h / 7}" fill="{base if k % 2 else light}"/>')
        parts.append(f'<rect width="{w * .4}" height="{h * 4 / 7}" fill="{dark}"/>')
        parts.append(f'<circle cx="{w * .2}" cy="{h * 2 / 7}" r="20" fill="{light}"/>')
    parts.append(f'<rect width="{w}" height="{h}" fill="none" stroke="#000" stroke-opacity=".35" stroke-width="4"/>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">{"".join(parts)}</svg>'


def flag(cfg, polity: dict, width: int = 300) -> Image.Image:
    pid = polity["polity_id"]
    own = _user_art(cfg, "flags", pid)
    if own is not None:
        return own.resize((width, round(width * own.height / own.width)), Image.LANCZOS)
    if pid == "usa":
        return union_flag(cfg, width)
    return _cached(cfg, f"flag_{pid}", width, lambda: rasterise(flag_svg(polity), width))


# -- portraits -------------------------------------------------------------------------

def portrait_svg(key: str, name: str, accent: str = "#8a6d3b") -> str:
    """An engraved-card bust in the encyclopedia's portrait style: original, seeded by name."""
    h = int(hashlib.sha1((key + name).encode()).hexdigest(), 16)
    skin = ["#c89a6c", "#b98a5c", "#d6ab7c", "#a97a4f", "#dbb58a"][h % 5]
    robe = ["#5b3a29", "#3e4a5c", "#6b2f2f", "#4a5a3a", "#2f2f45"][(h >> 3) % 5]
    wrap = ["#efe6cf", "#d9c28f", "#b8322a", "#f4f0e2", "#c9a24a"][(h >> 6) % 5]
    beard = ["#2b1d12", "#3d2b1a", "#5b4a3a", "#1c1410"][(h >> 9) % 4]
    crown = (h >> 12) % 3 == 0
    top = (f'<path d="M52,38 L60,20 L70,34 L80,16 L90,34 L100,20 L108,38 Z" fill="#c9a24a" stroke="#7a5a1a" stroke-width="2"/>'
           if crown else "")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 196">
<defs><radialGradient id="bg" cx="50%" cy="36%" r="74%"><stop offset="0" stop-color="#e8dcc0"/><stop offset="1" stop-color="#cbb894"/></radialGradient></defs>
<rect width="160" height="196" fill="url(#bg)"/>
<path d="M2,196 C6,150 38,127 80,127 C122,127 154,150 158,196 Z" fill="{robe}"/>
<path d="M60,130 C70,140 90,140 100,130 L96,196 L64,196 Z" fill="{wrap}" opacity=".85"/>
<path d="M68,102 h24 v27 c-12,8 -12,8 -24,0 z" fill="{skin}"/>
<ellipse cx="80" cy="78" rx="29" ry="35" fill="{skin}"/>
<path d="M50,84 C52,106 64,118 80,118 C96,118 108,106 110,84 C104,96 96,100 80,100 C64,100 56,96 50,84 Z" fill="{beard}"/>
<path d="M66,95 C72,92 88,92 94,95 C90,99 70,99 66,95 Z" fill="{beard}"/>
<ellipse cx="70" cy="76" rx="3.6" ry="2.5" fill="#2a1d0e"/><ellipse cx="90" cy="76" rx="3.6" ry="2.5" fill="#2a1d0e"/>
<path d="M64,67 C68,63 74,63 77,66 M83,66 C86,63 92,63 96,67" stroke="#3a2a18" stroke-width="2.4" fill="none" stroke-linecap="round"/>
<path d="M44,70 C42,40 60,30 80,30 C100,30 118,40 116,70 C104,56 56,56 44,70 Z" fill="{wrap}"/>
<path d="M44,70 C40,92 42,118 50,134 L58,128 C52,110 52,90 56,72 Z M116,70 C120,92 118,118 110,134 L102,128 C108,110 108,90 104,72 Z" fill="{wrap}"/>
{top}
<rect width="160" height="196" fill="none" stroke="rgba(0,0,0,.18)" stroke-width="2"/>
<rect x="3" y="3" width="154" height="190" fill="none" stroke="{accent}" stroke-width="5" opacity=".6"/>
</svg>'''


def portrait(cfg, key: str, name: str, width: int = 240, accent: str = "#8a6d3b") -> Image.Image:
    own = _user_art(cfg, "portraits", key)
    if own is not None:
        return own.resize((width, round(width * own.height / own.width)), Image.LANCZOS)
    root = str(paths(cfg).root.parent)
    svgs = _canon_svgs(root)
    if key in svgs:
        return _cached(cfg, f"portrait_{key}", width, lambda: rasterise(svgs[key], width))
    return _cached(cfg, f"portrait_{key}", width, lambda: rasterise(portrait_svg(key, name, accent), width))


def build_all(cfg, data) -> int:
    """Pre-render everything the motion pass will ask for (so workers only read files)."""
    n = 0
    union_flag(cfg, 600)
    union_seal(cfg, 400)
    for p in data.polities:
        flag(cfg, p, 300)
        n += 1
    for r in getattr(data, "rulers", []):
        portrait(cfg, r["portrait"], r["name"], 240)
        n += 1
    return n
