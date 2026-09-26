"""The encyclopedia's world maps: sea by depth, shaded relief, rivers and a crisp coast.

Six world maps (the hub, the timeline's two, the History page's Cold War map and two in the
article on motor vehicles, and their Arabic twins) share one frame: the Natural Earth
projection centred on 11E, fitted to the maps' own outline to under half a pixel. Their
colours, labels, markers and legends are the pages' own and are left alone; `python build.py
sitemaps` slips the missing ground in between: the sea by its true depth with water lines
under the land, the relief over the colours (both from ETOPO 2022, projected and shaded by
QGIS and finished in GIMP: see terrain.py), the major rivers and lakes, and a thin dark
coastline. Everything added carries a cgw class, so a second run replaces it.
"""

from __future__ import annotations

import base64
import io
import re

import geopandas as gpd
import numpy as np
import shapely
from PIL import Image

from . import geo
from .fetch import layer_path
from .sitemaps import SITE, path_d

PROJ = "+proj=natearth +lon_0=11 +datum=WGS84 +units=m +no_defs"
SCALE, X0, Y0 = 2.7283177e-05, 480.0, 244.58       # px per metre and the centre, from the maps' outline
W, H = 960, 422                                     # the map area above each map's key band
VIEW = shapely.box(-4, -8, W + 4, H + 8)
CUT = 11 - 180                                      # the frame's antimeridian, 169W
PAGES = ("index.html", "timeline-of-the-global-swap.html", "history-of-the-united-states-of-arabia.html",
         "vehicles.html")
DEPTHS = {200: ("K", "#dfeaf1"), 3000: ("H", "#d5e5ee")}
SEA_BASE = "#e7f0f4"            # the maps' own sea: the shelf, shallower than 200 m
INK = {"coast": "#4a5a61", "river": "#6a9ac0", "lake": "#dcebf2"}


def _project(geoms) -> list:
    """Lon/lat shapes into the frame's pixels, cut at the frame's antimeridian first so nothing
    streaks across the map."""
    west, east = shapely.box(-180, -90, CUT - 1e-6, 90), shapely.box(CUT + 1e-6, -90, 180, 90)
    halves = []
    for g in geoms:
        g = shapely.make_valid(g)
        for side in (west, east):
            part = shapely.intersection(g, side)
            if not part.is_empty:
                halves.append(part)
    if not halves:
        return []
    s = gpd.GeoSeries(halves, crs=geo.WGS84).to_crs(PROJ)
    return [shapely.affinity.affine_transform(g, [SCALE, 0, 0, -SCALE, X0, Y0]) for g in s if not g.is_empty]


def _clip(geoms, tol, min_area=0.0, lines=False):
    geoms = [shapely.make_valid(g) for g in geoms]
    if not lines:
        geoms = [shapely.intersection(g, VIEW) for g in geoms]
        geoms = [g for g in geoms if not g.is_empty and g.area > 0]
    g = shapely.intersection(shapely.union_all(geoms, grid_size=0.01), VIEW)
    g = shapely.simplify(g, tol, preserve_topology=True)
    if lines:
        return g
    parts = [p for p in shapely.get_parts(g) if p.geom_type == "Polygon" and p.area >= min_area]
    return shapely.MultiPolygon(parts) if parts else shapely.Polygon()


def _ne(cfg: dict, name: str, layer: str | None = None) -> gpd.GeoDataFrame:
    path = layer_path(cfg, name)
    src = f"zip://{path.resolve().as_posix()}"
    g = gpd.read_file(src, layer=layer) if layer else gpd.read_file(src)
    return g.set_crs(geo.WGS84) if g.crs is None else g


def globe_mask(k: float) -> Image.Image:
    """The globe's outline at k times the map's pixels, white inside: past it the projection has
    no ground, and the warp of the relief returns whatever it finds there."""
    from PIL import ImageDraw
    lats = np.linspace(-90, 90, 721)
    t = gpd.GeoSeries.from_xy(np.r_[np.full(721, CUT + 1e-6), np.full(721, CUT + 360 - 1e-6)],
                              np.r_[lats, lats[::-1]], crs=geo.WGS84).to_crs(PROJ)
    pts = [((X0 + SCALE * p.x) * k, (Y0 - SCALE * p.y) * k) for p in t]
    mask = Image.new("L", (int(W * k), int(H * k)), 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    return mask


def relief_image(cfg: dict) -> str:
    from . import relief
    w, h = int(W * 1.5), int(H * 1.5)
    extent = ((0 - X0) / SCALE, (W - X0) / SCALE, (Y0 - H) / SCALE, Y0 / SCALE)
    shade = relief.relief({**cfg, "projection": PROJ}, extent, w, h).astype(np.float32)
    valid = (shade > 0) & (np.asarray(globe_mask(1.5)) > 0)
    flat = float(np.argmax(np.bincount(shade[valid].astype(np.uint8).ravel(), minlength=256)))
    shade[~valid] = flat
    tone = 255 - np.clip((flat - shade) * 1.1, 0, 255)
    buf = io.BytesIO()
    Image.fromarray(tone.astype(np.uint8), "L").convert("RGB").save(buf, "WEBP", quality=45, method=6)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()


def sea_image(cfg: dict) -> str:
    """The depth zones painted soft into one image: at world scale a vector outline of every
    seamount weighs hundreds of kilobytes and shows nothing a gentle gradient does not."""
    from PIL import ImageDraw, ImageFilter
    k = 1.5
    img = Image.new("RGBA", (int(W * k), int(H * k)), (0, 0, 0, 0))
    base = Image.new("RGBA", img.size, (255, 255, 255, 255))           # white past the globe, as the page
    base.paste(Image.new("RGBA", img.size, SEA_BASE), (0, 0), globe_mask(k))
    for depth, (code, colour) in sorted(DEPTHS.items()):
        try:
            g = _ne(cfg, "ne_10m_bathymetry_all", f"ne_10m_bathymetry_{code}_{depth}")
        except Exception as exc:
            print(f"    bathymetry {depth} m skipped ({exc})")
            continue
        rgb = tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5)) + (255,)
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))      # one depth on its own, then laid on
        draw = ImageDraw.Draw(layer)
        for shape in _project(g.geometry):
            for poly in shapely.get_parts(shapely.make_valid(shape)):
                if poly.geom_type != "Polygon" or poly.area < 0.5:
                    continue
                draw.polygon([(x * k, y * k) for x, y in poly.exterior.coords], fill=rgb)
                for hole in poly.interiors:
                    draw.polygon([(x * k, y * k) for x, y in hole.coords], fill=(0, 0, 0, 0))
        img.alpha_composite(layer)
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    base.alpha_composite(img)
    buf = io.BytesIO()
    base.convert("RGB").save(buf, "WEBP", quality=55, method=6)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()


def ground_images(cfg: dict, land) -> tuple[str, str]:
    """The frame's relief and sea from ETOPO 2022, drawn by QGIS and finished in GIMP (see
    terrain.py); without QGIS, Natural Earth's shaded relief and depth zones as before."""
    from . import terrain
    k = 1.5
    extent = ((0 - X0) / SCALE, (W - X0) / SCALE, (Y0 - H) / SCALE, Y0 / SCALE)
    try:
        return terrain.images(cfg, "World frame", PROJ, extent, int(W * k), int(H * k),
                              shapely.affinity.scale(land, k, k, origin=(0, 0)), z=16, floor=0.22,
                              lines=((2.2, .30), (5.0, .16)), outside=np.asarray(globe_mask(k)) < 128)
    except RuntimeError as exc:
        print(f"    {exc}; using Natural Earth's shaded relief")
        return relief_image(cfg), sea_image(cfg)


def shared_defs(cfg: dict) -> str:
    land = _clip(_project(_ne(cfg, "ne_50m_land").geometry), 0.45, min_area=0.8)
    relief_uri, sea_uri = ground_images(cfg, land)
    rv = _ne(cfg, "ne_10m_rivers_lake_centerlines")
    rv = rv[rv["scalerank"].fillna(99) <= 3]
    rivers = _clip(_project(rv.geometry), 0.7, lines=True)
    lk = _ne(cfg, "ne_10m_lakes")
    lk = lk[lk["scalerank"].fillna(99) <= 2]
    lakes = _clip(_project(lk.geometry), 0.6, min_area=2)
    return ('<defs class="cgw-shared">'
            f'<image id="cgw-sea" width="{W}" height="{H}" preserveAspectRatio="none" href="{sea_uri}"/>'
            f'<path id="cgw-land" d="{path_d(land)}"/>'
            f'<image id="cgw-relief" width="{W}" height="{H}" preserveAspectRatio="none" href="{relief_uri}"/>'
            f'<g id="cgw-water"><path fill="{INK["lake"]}" stroke="{INK["coast"]}" stroke-width=".4" '
            f'd="{path_d(lakes)}"/><path fill="none" stroke="{INK["river"]}" stroke-width=".6" '
            f'stroke-linejoin="round" stroke-linecap="round" d="{path_d(rivers)}"/></g>'
            "</defs>")


SEA = '<use class="cgw" href="#cgw-sea"/>'
OVER = ('<use class="cgw" href="#cgw-relief" opacity=".6" style="mix-blend-mode:multiply"/>'
        '<use class="cgw" href="#cgw-water"/>'
        f'<use class="cgw" href="#cgw-land" fill="none" stroke="{INK["coast"]}" stroke-width=".55" '
        'stroke-linejoin="round"/>')


def _world_maps(text: str):
    """(start, end) of every full-world map's <svg> on a page."""
    out = []
    for m in re.finditer(r'<svg\b[^>]*viewBox="0 0 960 \d+"[^>]*>.*?</svg>', text, re.S):
        svg = m.group(0)
        clip = re.search(r'<clipPath id="([^"]*-frame)"><rect width="960" height="(\d+)"', svg)
        if clip and clip.group(2) == str(H) and f'clip-path="url(#{clip.group(1)})"' in svg:
            out.append((m.start(), m.end()))
    return out


def dress(svg: str, defs: str | None) -> str:
    """One world map with the ground slipped in around its own colours."""
    svg = re.sub(r'<defs class="cgw-shared">.*?</defs>', "", svg, flags=re.S)
    svg = re.sub(r'<use class="cgw"[^>]*/>', "", svg)
    frame = re.search(r'<g clip-path="url\(#[^"]*-frame\)">', svg)
    head_end = frame.end()
    # inside the frame: the sea's outline first, then the grid, then the land's colours
    kids = []
    depth, start = 0, None
    for m in re.finditer(r"<(/?)([a-zA-Z]+)([^>]*?)(/?)>", svg[head_end:]):
        close, tag, attrs, selfc = m.groups()
        if not close:
            if depth == 0:
                start = m.start()
            if selfc:
                if depth == 0:
                    kids.append((start, m.end(), tag))
            else:
                depth += 1
        else:
            if depth == 0:
                break                                    # the frame group's own closing tag
            depth -= 1
            if depth == 0:
                kids.append((start, m.end(), tag))
    after_sea = head_end + kids[0][1]
    land = next(k for k in kids if k[2] == "g")
    after_land = head_end + land[1]
    svg = svg[:after_land] + OVER + svg[after_land:]
    svg = svg[:after_sea] + SEA + svg[after_sea:]
    if defs:
        opening = svg[: svg.index(">") + 1]
        svg = opening + defs + svg[len(opening):]
    return svg


def install(cfg: dict) -> list[str]:
    defs = shared_defs(cfg)
    changed = []
    for page in PAGES:
        for path in (SITE / page, SITE / "ar" / page):
            if not path.exists():
                continue
            with open(path, encoding="utf8", newline="") as fh:
                text = fh.read()
            spans = _world_maps(text)
            out, last = [], 0
            for n, (a, b) in enumerate(spans):
                out.append(text[last:a] + dress(text[a:b], defs if n == 0 else None))
                last = b
            out.append(text[last:])
            new = "".join(out)
            if new != text:
                with open(path, "w", encoding="utf8", newline="") as fh:
                    fh.write(new)
                changed.append(path.relative_to(SITE).as_posix())
    return changed
