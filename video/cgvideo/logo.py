"""The Controglobe logo, for the opening sting and the end card.

assets/logo.png (your own artwork: any size, ideally square on a transparent background)
always wins. Without it, the emblem is drawn in the style of the site's favicon (a turquoise
globe with the CONTROGLOBE wordmark across it) at whatever size the frame needs, ray-cast like
the opening globe, so it stays sharp at 4K and can turn slowly.
"""

from __future__ import annotations

import functools
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import paths


def _fontfile(name: str) -> str:
    import pathlib

    import matplotlib
    return str(pathlib.Path(matplotlib.get_data_path()) / "fonts" / "ttf" / name)


def user_logo(cfg: dict) -> Image.Image | None:
    p = paths(cfg).root / "assets" / "logo.png"
    return Image.open(p).convert("RGBA") if p.exists() else None


@functools.lru_cache(maxsize=2)
def _mask(mask_file: str) -> np.ndarray:
    return np.asarray(Image.open(mask_file)) > 127


def emblem(cfg: dict, size: int, lon0: float = 40.0, shine: float = -1.0) -> Image.Image:
    """The emblem at `size` px square (RGBA). lon0 turns the globe; shine in 0..1 sweeps a
    specular band across it (negative: none)."""
    mine = user_logo(cfg)
    if mine is not None:
        mine.thumbnail((size, size), Image.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.alpha_composite(mine, ((size - mine.width) // 2, (size - mine.height) // 2))
        return canvas
    from .globe import mask_path, prepare
    prepare(cfg)
    mask = _mask(str(mask_path(cfg)))
    n = size
    c, r = n / 2, n * 0.40
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    nx, ny = (xx - c) / r, -(yy - c) / r
    rho2 = nx * nx + ny * ny
    inside = rho2 <= 1.0
    nz = np.sqrt(np.clip(1 - rho2, 0, 1))
    la0, lo0 = math.radians(18), math.radians(lon0)
    lat = np.arcsin(np.clip(nz * math.sin(la0) + ny * math.cos(la0), -1, 1))
    lon = lo0 + np.arctan2(nx, nz * math.cos(la0) - ny * math.sin(la0))
    MH, MW = mask.shape
    u = ((np.degrees(lon) + 180) % 360) / 360 * MW
    v = (90 - np.degrees(lat)) / 180 * MH
    land = mask[np.clip(v.astype(int), 0, MH - 1), np.clip(u.astype(int), 0, MW - 1)]
    light = np.clip(0.30 + 0.85 * (nx * -0.45 + ny * 0.40 + nz * 0.80), 0.05, 1.15)[..., None]
    sea = np.array([30, 196, 190], np.float32) * (0.55 + 0.55 * light)
    ground = np.array([8, 84, 92], np.float32) * (0.6 + 0.6 * light)
    col = np.where(land[..., None], ground, sea)
    col = col * (0.72 + 0.28 * nz[..., None])                     # rim falls away
    spec = np.clip(nx * -0.38 + ny * 0.46 + nz * 0.80, 0, 1) ** 36
    col += spec[..., None] * 170
    if shine >= 0:                                                # a light sweep across the ball
        band = np.exp(-(((nx + ny * 0.6) - (-1.8 + 3.6 * shine)) / 0.22) ** 2) * inside
        col += band[..., None] * 90
    rgb = np.clip(col, 0, 255).astype(np.uint8)
    alpha = (np.clip((1.0 - np.sqrt(rho2)) * r, 0, 1) * 255).astype(np.uint8)  # antialiased edge
    ball = Image.fromarray(np.dstack([rgb, alpha]), "RGBA")
    # a soft turquoise halo behind the ball
    halo = Image.new("L", (n, n), 0)
    ImageDraw.Draw(halo).ellipse([c - r * 1.02, c - r * 1.02, c + r * 1.02, c + r * 1.02], fill=150)
    halo = halo.filter(ImageFilter.GaussianBlur(n * 0.045))
    out = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    out.paste(Image.new("RGBA", (n, n), (70, 225, 225, 255)), (0, 0), halo)
    out.alpha_composite(ball)
    # the wordmark across the globe, as on the favicon
    d = ImageDraw.Draw(out)
    word = "CONTROGLOBE"
    font = ImageFont.truetype(_fontfile("DejaVuSans-Bold.ttf"), int(n * 0.085))
    track = n * 0.012
    widths = [d.textlength(ch, font=font) for ch in word]
    total = sum(widths) + track * (len(word) - 1)
    x, y = c - total / 2, c + n * 0.02
    for ch, w in zip(word, widths):
        d.text((x, y), ch, font=font, fill=(34, 46, 52, 255), anchor="lm",
               stroke_width=max(1, int(n * 0.006)), stroke_fill=(214, 252, 250, 255))
        x += w + track
    return out
