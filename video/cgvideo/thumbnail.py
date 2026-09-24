"""The YouTube thumbnail: a countryball of the United States of Arabia beside a flag map of the
country, every other land darkened, and a white all-caps hook. Our own drawing throughout,
built from the canon flag; tweak text and layout with `build.py thumbnail --text ...`.
"""

from __future__ import annotations

import numpy as np
import shapely
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from . import assets, geo
from .config import paths
from .panel import _fontfile


def _mask(geom, extent, W, H, ss=2):
    x0, x1, y0, y1 = extent
    img = Image.new("L", (W * ss, H * ss), 0)
    d = ImageDraw.Draw(img)
    for poly in shapely.get_parts(geom):
        if poly.geom_type != "Polygon":
            continue
        def px(ring):
            c = np.asarray(ring.coords)
            return list(zip((c[:, 0] - x0) / (x1 - x0) * W * ss, (y1 - c[:, 1]) / (y1 - y0) * H * ss))
        d.polygon(px(poly.exterior), fill=255)
        for hole in poly.interiors:
            d.polygon(px(hole), fill=0)
    return img.resize((W, H), Image.LANCZOS)


def _land_for(cfg, extent):
    """Coastlines for exactly the thumbnail's frame (it reaches further west than the video)."""
    x0, x1, y0, y1 = extent
    lon, lat = geo.to_lonlat(cfg).transform([x0, x1, x0, x1], [y0, y0, y1, y1])
    bb = (min(lon) - 8, min(lat) - 5, max(lon) + 8, max(lat) + 5)
    gdf = geo.clip_project(cfg, geo.read_ne(cfg, "ne_10m_land"), bb)
    return shapely.union_all(list(gdf.geometry)).intersection(shapely.box(x0, y0, x1, y1).buffer(50_000))


def countryball(flag: Image.Image, D: int) -> Image.Image:
    """A flag-skinned ball with a heavy outline and two blank white eyes."""
    ss = 3
    S = D * ss
    ball = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    skin = flag.convert("RGBA")
    # fill the circle with the flag: scale so the flag's height covers the ball, keep the canton
    k = S / skin.height
    skin = skin.resize((int(skin.width * k * 1.05), int(S * 1.05)), Image.LANCZOS)
    tex = Image.new("RGBA", (S, S))
    tex.paste(skin, (-int(S * 0.08), -int(S * 0.02)))
    circle = Image.new("L", (S, S), 0)
    ImageDraw.Draw(circle).ellipse([4 * ss, 4 * ss, S - 4 * ss, S - 4 * ss], fill=255)
    ball.paste(tex, (0, 0), circle)
    # shading: a soft highlight top-left, a shadow bottom-right
    yy, xx = np.mgrid[0:S, 0:S] / S
    shade = 1.12 - 0.55 * np.clip(np.hypot(xx - 0.36, yy - 0.3), 0, 1) ** 1.4
    arr = np.asarray(ball).astype(np.float32)
    arr[..., :3] *= shade[..., None]
    ball = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(ball)
    lw = int(S * 0.028)
    d.ellipse([4 * ss, 4 * ss, S - 4 * ss, S - 4 * ss], outline=(12, 12, 12, 255), width=lw)
    # eyes: blank and white, glancing right toward the map
    for cx in (0.56, 0.78):
        ex, ey, rx, ry = cx * S, 0.40 * S, 0.085 * S, 0.12 * S
        d.ellipse([ex - rx, ey - ry, ex + rx, ey + ry], fill=(255, 255, 255, 255), outline=(12, 12, 12, 255), width=int(lw * 0.55))
    return ball.resize((D, D), Image.LANCZOS)


def make(cfg, data, text: str = "SINCE WHEN?", sizes=((1280, 720), (1920, 1080))) -> list[str]:
    from .render import Scene
    scene = Scene(cfg, data)
    row = data.matrix[data.year_index(data.year_list[-1])]
    polities, tops = scene.state(row)
    usa = tops.get("usa")
    if usa is None:
        raise SystemExit("the Union holds nothing in the last year: nothing to draw")
    flag = assets.union_flag(cfg, 1200)
    out = []
    for W, H in sizes:
        s = H / 720
        # frame the mainland and Adharbaijan on the right two thirds
        bx0, by0, bx1, by1 = geo.bbox_polygon(cfg, [32.0, 10.5, 61.5, 42.5]).bounds
        h_m = (by1 - by0) * 1.04
        w_m = h_m * W / H
        cx = bx0 + (bx1 - bx0) * 0.5 - w_m * 0.16
        cy = (by0 + by1) / 2
        extent = (cx - w_m / 2, cx + w_m / 2, cy - h_m / 2, cy + h_m / 2)
        img = Image.new("RGB", (W, H), (0, 0, 0))
        # sea: a dark vertical gradient
        grad = np.linspace(0, 1, H)[:, None, None]
        sea = (np.array([14, 26, 40]) * (1 - grad) + np.array([6, 12, 20]) * grad).astype(np.uint8)
        img = Image.fromarray(np.broadcast_to(sea, (H, W, 3)).copy())
        land_geom = _land_for(cfg, extent)
        land = _mask(land_geom, extent, W, H)
        img.paste(Image.new("RGB", (W, H), (44, 48, 54)), (0, 0), land)
        country = _mask(usa, extent, W, H)
        # glow behind the country
        glow = country.filter(ImageFilter.GaussianBlur(18 * s))
        img.paste(Image.new("RGB", (W, H), (255, 214, 120)), (0, 0), glow.point(lambda v: int(v * 0.55)))
        # the flag across the country's bounding box
        cb = country.getbbox()
        if cb:
            fw, fh = cb[2] - cb[0], cb[3] - cb[1]
            k = max(fw / flag.width, fh / flag.height)
            f = flag.resize((int(flag.width * k), int(flag.height * k)), Image.LANCZOS)
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            layer.paste(f, (cb[0], cb[1]))
            img.paste(layer.convert("RGB"), (0, 0), ImageChops.multiply(country, layer.getchannel("A")))
        # terrain over the land and the flag alike, so the flag lies draped over the peninsula
        from . import relief as R
        try:
            shade = R.relief(cfg, extent, W, H).astype(np.float32)
            flat = float(np.argmax(np.bincount(shade.astype(np.uint8).ravel(), minlength=256)))
            k = np.clip(shade / max(flat, 1.0), 0.45, 1.3)[..., None]
            on = (np.asarray(land, np.float32) / 255.0)[..., None]
            a = np.asarray(img.convert("RGB")).astype(np.float32)
            img = Image.fromarray(np.clip(a * (1 - on) + a * k * on, 0, 255).astype(np.uint8))
        except SystemExit:
            pass
        edge = country.filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v > 40 else 0).filter(ImageFilter.MaxFilter(3))
        img.paste(Image.new("RGB", (W, H), (255, 255, 255)), (0, 0), edge)
        # the ball, bottom left, and the hook above it
        D = int(H * 0.56)
        ball = countryball(flag, D)
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        bx, by = int(W * 0.035), int(H - D - H * 0.05)
        ImageDraw.Draw(shadow).ellipse([bx + D * 0.12, by + D * 0.9, bx + D * 0.92, by + D * 1.02], fill=(0, 0, 0, 150))
        shadow = shadow.filter(ImageFilter.GaussianBlur(10 * s))
        img = Image.alpha_composite(img.convert("RGBA"), shadow)
        img.alpha_composite(ball, (bx, by))
        d = ImageDraw.Draw(img)
        size = int(118 * s)
        font = ImageFont.truetype(_fontfile("DejaVuSans-Bold.ttf"), size)
        while d.textlength(text, font=font) > W * 0.52 and size > 40:
            size -= 4
            font = ImageFont.truetype(_fontfile("DejaVuSans-Bold.ttf"), size)
        d.text((int(W * 0.035), int(H * 0.06)), text, font=font, fill=(255, 255, 255, 255),
               stroke_width=int(9 * s), stroke_fill=(0, 0, 0, 255))
        tagline = " ".join("ALTERNATE HISTORY OF ARABIA")
        tsize = int(29 * s)
        tag = ImageFont.truetype(_fontfile("DejaVuSans-Bold.ttf"), tsize)
        while d.textlength(tagline, font=tag) > W * 0.45 and tsize > 12:  # clear of the map
            tsize -= 1
            tag = ImageFont.truetype(_fontfile("DejaVuSans-Bold.ttf"), tsize)
        d.text((int(W * 0.038), int(H * 0.06 + size * 1.18)), tagline, font=tag,
               fill=(236, 190, 92, 255), stroke_width=int(5 * s), stroke_fill=(0, 0, 0, 255))
        # the channel's emblem in the empty sea, bottom right
        from .logo import emblem
        em = emblem(cfg, int(H * 0.24))
        img.alpha_composite(em, (int(W - em.width - W * 0.02), int(H - em.height - H * 0.02)))
        dest = paths(cfg).output / f"thumbnail_{W}x{H}.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.convert("RGB").save(dest)
        out.append(str(dest))
    return out
