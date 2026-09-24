"""The opening: a premise card, then a lit globe that turns to Arabia and dives into the map.

The globe is ray-cast rather than drawn: every screen pixel inside the disc is turned back
into a longitude and latitude (inverse orthographic), looked up in a land mask, and shaded
by its angle to a light, with an atmosphere rim. That makes a true 3D sphere with no polygon
clipping at the horizon, and it is fast enough to draw every frame.
"""

from __future__ import annotations

import math
import pathlib

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .config import paths
from .panel import _fontfile, ease

MASK_W, MASK_H = 4320, 2160  # 1/12 degree


def mask_path(cfg) -> pathlib.Path:
    return paths(cfg).build / "land_mask.png"


def prepare(cfg) -> None:
    """Rasterise Natural Earth 1:50m land to an equirectangular mask, once."""
    out = mask_path(cfg)
    if out.exists():
        return
    from . import geo
    import shapely
    try:
        land = geo.read_ne(cfg, "ne_50m_land")
    except SystemExit:
        land = geo.read_ne(cfg, "ne_10m_land")
    img = Image.new("L", (MASK_W, MASK_H), 0)
    d = ImageDraw.Draw(img)
    sx, sy = MASK_W / 360, MASK_H / 180
    for g in land.geometry:
        for poly in shapely.get_parts(g):
            if poly.geom_type != "Polygon":
                continue
            ext = [((x + 180) * sx, (90 - y) * sy) for x, y in poly.exterior.coords]
            d.polygon(ext, fill=255)
            for hole in poly.interiors:
                d.polygon([((x + 180) * sx, (90 - y) * sy) for x, y in hole.coords], fill=0)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)


class Globe:
    def __init__(self, cfg, W, H):
        self.W, self.H = W, H
        self.mask = np.asarray(Image.open(mask_path(cfg))) > 127
        rng = np.random.default_rng(7)
        self.stars = [(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(0.3, 1.0)) for _ in range(int(W * H / 5000))]

    def render(self, lon0, lat0, radius, cx=None, cy=None, highlight=None) -> Image.Image:
        W, H = self.W, self.H
        cx = W / 2 if cx is None else cx
        cy = H / 2 if cy is None else cy
        img = Image.new("RGB", (W, H), (4, 6, 10))
        d = ImageDraw.Draw(img)
        for x, y, b in self.stars:
            v = int(90 * b)
            d.point((x, y), fill=(v, v, v + 10))
        # atmosphere
        glow = Image.new("L", (W, H), 0)
        gd = ImageDraw.Draw(glow)
        for k in range(24, 0, -1):
            r = radius * (1 + k * 0.006)
            gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=int(110 * (1 - k / 24) ** 2))
        img.paste(Image.new("RGB", (W, H), (70, 140, 220)), (0, 0), glow)
        # the sphere, ray-cast over its bounding box
        x0, x1 = int(max(0, cx - radius)), int(min(W, cx + radius + 1))
        y0, y1 = int(max(0, cy - radius)), int(min(H, cy + radius + 1))
        if x1 <= x0 or y1 <= y0:
            return img
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        nx, ny = (xx - cx) / radius, -(yy - cy) / radius
        rho2 = nx * nx + ny * ny
        inside = rho2 <= 1.0
        nz = np.sqrt(np.clip(1 - rho2, 0, 1))
        la0, lo0 = math.radians(lat0), math.radians(lon0)
        # inverse orthographic
        lat = np.arcsin(np.clip(nz * math.sin(la0) + ny * math.cos(la0), -1, 1))
        lon = lo0 + np.arctan2(nx, nz * math.cos(la0) - ny * math.sin(la0))
        u = ((np.degrees(lon) + 180) % 360) / 360 * MASK_W
        v = (90 - np.degrees(lat)) / 180 * MASK_H
        land = self.mask[np.clip(v.astype(int), 0, MASK_H - 1), np.clip(u.astype(int), 0, MASK_W - 1)]
        light = np.clip(0.25 + 0.95 * (nx * -0.45 + ny * 0.35 + nz * 0.82), 0.08, 1.15)
        ocean = np.stack([10 + 18 * light, 22 + 36 * light, 40 + 70 * light], -1)
        ground = np.stack([72 + 88 * light, 72 + 84 * light, 66 + 74 * light], -1)
        if highlight is not None:
            lon_d, lat_d = np.degrees(lon), np.degrees(lat)
            hl = ((((lon_d - highlight[0]) + 180) % 360 - 180) ** 2 / highlight[2] ** 2
                  + (lat_d - highlight[1]) ** 2 / highlight[3] ** 2) < 1
            tint = np.stack([200 * light, 170 * light, 90 * light], -1)
            ground = np.where((hl & land)[..., None], ground * (1 - highlight[4]) + tint * highlight[4], ground)
        col = np.where(land[..., None], ground, ocean)
        rim = np.clip((rho2 - 0.82) / 0.18, 0, 1)[..., None]
        col = col * (1 - 0.55 * rim) + np.array([90, 160, 240]) * 0.55 * rim
        base = np.asarray(img)[y0:y1, x0:x1].astype(np.float32)
        base = np.where(inside[..., None], col, base)
        arr = np.asarray(img).copy()
        arr[y0:y1, x0:x1] = np.clip(base, 0, 255).astype(np.uint8)
        return Image.fromarray(arr)


def _text_card(r, t) -> Image.Image:
    """The premise, in the channel's own words, line by line."""
    W, H, s = r.W, r.H, r.H / 1080
    img = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(img)
    total = r.m["intro_text_seconds"]
    out = 1 - ease((t - (total - 0.8)) / 0.8)
    blue, red = (82, 176, 222), (214, 40, 40)
    lines = [
        (0.4, [("In this ", False), ("transposed", True), (" timeline", False)], 64, blue, 0.20),
        (2.6, [("From 500 BCE the Global North and the Global South", True)], 34, blue, 0.40),
        (2.9, [("trade histories. The land stays exactly where it is.", True)], 34, blue, 0.46),
        (5.0, [("This is how the United States would have", True)], 46, red, 0.62),
        (5.3, [("emerged in what we know today as Arabia.", True)], 46, red, 0.70),
    ]
    for start, runs, size, col, yfrac in lines:
        a = ease((t - start) / 0.9) * out
        if a <= 0:
            continue
        fonts = [ImageFont.truetype(_fontfile("DejaVuSans-Bold.ttf" if b else "DejaVuSans.ttf"), int(size * s)) for _, b in runs]
        widths = [d.textlength(txt, font=f) for (txt, _), f in zip(runs, fonts)]
        x = (W - sum(widths)) / 2
        y = H * yfrac + (1 - a) * 18 * s
        c = tuple(int(v * a) for v in col)
        for (txt, _), f, w in zip(runs, fonts, widths):
            d.text((x, y), txt, font=f, fill=c, anchor="lm")
            x += w
    return img


def intro_frame(r, f) -> Image.Image:
    fps = r.fps
    t = f / fps
    t_text = r.m["intro_text_seconds"]
    if t < t_text:
        return _text_card(r, t)
    if r.globe is None:
        r.globe = Globe(r.cfg, r.W, r.H)
    tg = t - t_text
    dur = r.m["globe_seconds"]
    k = ease(min(1.0, tg / (dur - 1.4)))
    lon = -38 + (46.5 - -38) * k
    lat = 8 + (25 - 8) * k
    radius = r.H * (0.40 + 0.06 * k)
    dive = max(0.0, (tg - (dur - 1.4)) / 1.4)
    radius *= 1 + 4.5 * ease(dive) ** 2
    img = r.globe.render(lon, lat, radius, cx=r.W * 0.5, cy=r.H * 0.56,
                         highlight=(46, 24, 16, 14, 0.55 * ease((tg - 2.0) / 1.5)))
    s = r.H / 1080
    d = ImageDraw.Draw(img)
    ta = ease((tg - 0.6) / 1.0) * (1 - ease((tg - (dur - 1.8)) / 0.6))
    if ta > 0:
        f1 = ImageFont.truetype(_fontfile("DejaVuSerif-Bold.ttf"), int(64 * s))
        f2 = ImageFont.truetype(_fontfile("DejaVuSans.ttf"), int(30 * s))
        f3 = ImageFont.truetype(_fontfile("DejaVuSans-Bold.ttf"), int(22 * s))
        c = lambda rgb: tuple(int(v * ta) for v in rgb)
        d.text((r.W / 2, r.H * 0.12), "ALTERNATE HISTORY OF ARABIA", font=f1, fill=c((245, 240, 230)), anchor="mm",
               stroke_width=int(3 * s), stroke_fill=(0, 0, 0))
        d.text((r.W / 2, r.H * 0.12 + 58 * s), "(in place of the United States)", font=f2, fill=c((210, 200, 180)), anchor="mm")
        d.text((r.W / 2, r.H * 0.9), "EVERY YEAR  |  500 BCE - 2026  |  CONTROGLOBE: THE GLOBAL SWAP", font=f3,
               fill=c((226, 182, 89)), anchor="mm")
    if dive > 0.55:  # hand over to the first map
        first = r.main_frame(0).convert("RGB")
        img = Image.blend(img, first, ease((dive - 0.55) / 0.45))
    return img
