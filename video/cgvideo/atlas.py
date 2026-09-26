"""The reference atlases, redrawn on real coastlines with the video's kind of frontier.

The Africa and Europe atlases were drawn by hand: a schematic coast and straight-sided nations.
`python build.py atlas` keeps what they say (every nation, its colour, its label, its twin and
its leader line) and redraws what they show:

  1. Registration. The atlas's hand-drawn coast is matched to Natural Earth's real one by an
     affine fit on the continent's four extreme points, refined by a thin-plate spline fitted
     by iterated closest points. That warp carries anything drawn on the atlas to the real
     ground: its nations, its label points, its leader lines.
  2. A mesh, built the way the video's is: a jittered grid of seeds, Voronoi edges roughened by
     midpoint displacement, the coast and the great rivers as extra edges, faces polygonised
     and small ones merged. So no frontier is ruled, and a frontier that meets a river can
     follow it.
  3. Each cell goes to the nation whose warped shape covers most of it; a coastal sliver that
     no nation covers goes to the nearest one, and islands far from any stay neutral ground.
  4. The map is drawn afresh on an equal-area projection: sea by depth, relief projected by
     QGIS, rivers and lakes, the nations with white frontiers, and the page's own labels on
     top, carried through the warp. Both editions get the same ground under their own words.
"""

from __future__ import annotations

import base64
import io
import math
import re

import geopandas as gpd
import numpy as np
import shapely
from PIL import Image, ImageDraw, ImageFilter
from shapely.geometry import MultiPoint

from . import geo, mesh
from .sitemaps import SITE, _children, _poly_from_svg, path_d

AFRICA = {
    "page": "africa.html", "viewbox": (0, 0, 780, 790), "clip": "af-al0", "prefix": "af-n0-",
    "proj": "+proj=laea +lat_0=2 +lon_0=17 +datum=WGS84 +units=m +no_defs",
    "bbox": (-30, -42, 66, 44),                  # what the map may show, lon/lat
    "centre": (17.0, 2.0),                       # a point on the continent the atlas draws
    "islands": [(46.9, -18.9)],                  # and the great islands it draws with it: Madagascar
    # Asia, cut off along Rafah to Aqaba (Sinai stays with Africa, as the atlas draws it), then
    # down the middle of the Red Sea and the Gulf of Aden and out past Madagascar
    "asia": [(34.25, 31.3), (34.25, 60), (100, 60), (100, -45), (60, -45), (56.5, 11.5), (51.5, 13.8),
             (43.4, 12.6), (38.6, 20.0), (35.0, 29.5)],
    "spacing_km": 70, "min_cell_km2": 900, "noise": 0.22, "noise_depth": 4,
    "river_rank": 4, "margin": 16, "margin_x": 44,
    # finer cells where the nations are small: the Guinea coast, the Great Lakes, the far
    # south and the Horn (lon/lat boxes)
    "focus": [((-18, 3, 11, 16), 32), ((27.5, -5.5, 32, 0.5), 25), ((26, -31.5, 33.5, -24.5), 28),
              ((40.5, 10, 45, 13.5), 25)],
}


# -- reading the old atlas -------------------------------------------------------------------

def _svg(text: str, vb) -> tuple[int, int, str]:
    m = re.search(r'<svg\b[^>]*viewBox="%s"[^>]*>.*?</svg>' % " ".join(str(v) for v in vb), text, re.S)
    return m.start(), m.end(), m.group(0)


def old_nations(svg: str, prefix: str) -> list[tuple[str, str, shapely.Geometry]]:
    """(id, colour, shape in the atlas's pixels) of every nation drawn on the atlas."""
    out = []
    for m in re.finditer(r'<path id="(%s[^"]+)" d="([^"]+)" fill="([^"]+)"' % re.escape(prefix), svg):
        out.append((m.group(1), m.group(3), _poly_from_svg(f'<path d="{m.group(2)}">')))
    return out


def old_coast(svg: str, clip: str):
    d = re.search(r'<clipPath id="%s"><path d="([^"]+)"' % re.escape(clip), svg).group(1)
    return _poly_from_svg(f'<path d="{d}">')


# -- the real ground --------------------------------------------------------------------------

def _to(proj, geoms):
    return list(gpd.GeoSeries(list(geoms), crs=geo.WGS84).to_crs(proj))


def real_land(cfg: dict, A: dict):
    """All land in the map's box, and the continent the atlas draws, in the map's projection."""
    w, s, e, n = A["bbox"]
    parts = []
    for name in ("ne_10m_land", "ne_10m_minor_islands"):
        g = geo.read_ne(cfg, name, bbox_ll=(w, s, e, n))
        parts.extend(shapely.make_valid(x) for x in g.geometry.intersection(shapely.box(w, s, e, n)))
    land_ll = shapely.union_all([p for p in parts if not p.is_empty])
    continent_ll = shapely.difference(land_ll, shapely.Polygon(A["asia"]))
    pieces = []
    for x, y in [A["centre"], *A.get("islands", [])]:
        pieces.append(next(p for p in shapely.get_parts(continent_ll) if p.contains(shapely.Point(x, y))))
    land, body = _to(A["proj"], [land_ll, shapely.union_all(pieces)])
    return shapely.make_valid(land), shapely.make_valid(body)


# -- registration: the atlas's pixels to real metres ------------------------------------------

def _extremes(poly) -> np.ndarray:
    xy = np.asarray(max(shapely.get_parts(poly), key=lambda p: p.area).exterior.coords)
    return np.array([xy[xy[:, 0].argmin()], xy[xy[:, 0].argmax()], xy[xy[:, 1].argmin()], xy[xy[:, 1].argmax()]])


def _sample(poly, step: float) -> np.ndarray:
    pts = []
    for p in shapely.get_parts(poly):
        if p.geom_type != "Polygon" or p.area < 30 * step * step:
            continue
        ring = p.exterior
        n = max(8, int(ring.length / step))
        pts.extend((ring.interpolate(t, normalized=True).x, ring.interpolate(t, normalized=True).y)
                   for t in np.linspace(0, 1, n, endpoint=False))
    return np.array(pts)


class Warp:
    """Atlas pixels -> the map's projected metres: an affine, then a thin-plate spline on top."""

    def __init__(self, old_coast, real_body):
        from scipy.interpolate import RBFInterpolator
        from scipy.spatial import cKDTree
        src = _extremes(old_coast)
        # the atlas's y runs down the page: take the real extremes with y turned the same way,
        # so west, east, north and south pair with west, east, north and south
        dst = _extremes(shapely.affinity.scale(real_body, 1, -1, origin=(0, 0)))
        # x = a*px + b ; -y = c*py + d  (no rotation: both are north-up)
        ax = np.polyfit(src[:, 0], dst[:, 0], 1)
        ay = np.polyfit(src[:, 1], dst[:, 1], 1)
        self.ax, self.ay = ax, ay
        coast_pts = _sample(real_body, 8000.0)
        tree = cKDTree(coast_pts)
        p = _sample(old_coast, 3.0)
        disp = np.zeros_like(p)
        self.rbf = None
        # stop at a gentle smoothing: the coast is only the handle; what matters is that the
        # atlas's interior keeps its layout as it is carried onto the real ground
        for smooth in (3000.0, 900.0, 300.0, 120.0, 60.0):
            q = self._affine(p + disp)
            dist, idx = tree.query(q)
            target = self._affine_inv(coast_pts[idx])
            keep = dist <= max(3 * np.median(dist), 80_000)
            self.rbf = RBFInterpolator(p[keep], (target - p)[keep], kernel="thin_plate_spline",
                                       smoothing=smooth, degree=1)
            disp = self.rbf(p)
        q = self(p)
        self.error_km = float(np.median(tree.query(q)[0]) / 1000)

    def _affine(self, p):
        return np.c_[self.ax[0] * p[:, 0] + self.ax[1], -(self.ay[0] * p[:, 1] + self.ay[1])]

    def _affine_inv(self, q):
        return np.c_[(q[:, 0] - self.ax[1]) / self.ax[0], (-q[:, 1] - self.ay[1]) / self.ay[0]]

    def __call__(self, p: np.ndarray) -> np.ndarray:
        p = np.asarray(p, float).reshape(-1, 2)
        return self._affine(p + self.rbf(p))

    def geom(self, g, step: float = 1.5):
        g = shapely.segmentize(g, step)
        return shapely.make_valid(shapely.transform(g, lambda xy: self(xy)))


# -- the mesh ---------------------------------------------------------------------------------

def build_cells(cfg: dict, A: dict, body, rivers):
    rng = np.random.default_rng(7)
    sp = A["spacing_km"] * 1000
    zones = [(body, sp)]
    for bbox, km in A.get("focus", []):
        w, s, e, n = bbox
        box = _to(A["proj"], [shapely.box(w, s, e, n).segmentize(0.5)])[0]
        zones.append((shapely.intersection(box, body), km * 1000))
    shapely.prepare(body)
    chunks = []
    for i, (area, spacing) in enumerate(zones):
        later = [z for z, _ in zones[i + 1:]]
        own = shapely.difference(area, shapely.union_all(later)) if later else area   # finer zones win
        if own.is_empty:
            continue
        pts = mesh._hex_points(own.bounds, spacing, rng)
        chunks.append(pts[shapely.contains_xy(own, pts[:, 0], pts[:, 1])])
    pts = np.vstack(chunks)
    edges = shapely.voronoi_polygons(MultiPoint(pts), extend_to=body.buffer(sp * 3), only_edges=True)
    rough = [mesh.roughen(e, A["noise"], A["noise_depth"]) for e in shapely.get_parts(edges)]
    lines = rough + [body.boundary]
    if rivers is not None and not rivers.is_empty:
        lines.append(rivers)
    network = shapely.union_all(lines)
    faces = np.array(list(shapely.get_parts(shapely.polygonize(list(shapely.get_parts(network))))))
    rp = shapely.point_on_surface(faces)
    faces = faces[shapely.contains_xy(body, shapely.get_x(rp), shapely.get_y(rp))]
    return np.array(mesh.merge_small(list(faces), A["min_cell_km2"] * 1e6))


def assign(cells, nations, reach_m: float):
    """Each cell to the nation covering most of it; else the nearest within reach; else none.
    A nation too small to win any cell keeps the one under its own centre."""
    tree = shapely.STRtree([g for _, _, g in nations])
    owner = np.full(len(cells), -1)
    for i, c in enumerate(cells):
        best, share = -1, 0.0
        for j in tree.query(c, predicate="intersects"):
            a = shapely.intersection(c, nations[j][2]).area
            if a > share:
                best, share = j, a
        if best >= 0 and share >= 0.3 * c.area:
            owner[i] = best
    lost = np.where(owner == -1)[0]
    for i in lost:
        j = int(tree.nearest(cells[i]))
        if shapely.distance(cells[i], nations[j][2]) <= reach_m:
            owner[i] = j
    ctree = shapely.STRtree(list(cells))
    for j, (nid, _, g) in enumerate(nations):
        if (owner == j).any() or g.is_empty:
            continue
        spot = shapely.point_on_surface(g)
        hit = ctree.query(spot, predicate="intersects")
        c = int(hit[0]) if len(hit) else int(ctree.nearest(spot))
        owner[c] = j
        print(f"    {nid} was too small for any cell: it keeps the one at its centre")
    return owner


# -- drawing ----------------------------------------------------------------------------------

class Frame:
    """The new map's frame: the map's projection scaled uniformly into the page's viewBox."""

    def __init__(self, A: dict, body, marks: np.ndarray | None = None):
        """marks: the page's own label and line points, in metres: the frame fits them too, with
        room for a label's width either side."""
        x0, y0, w, h = A["viewbox"]
        bx0, by0, bx1, by1 = body.bounds
        if marks is not None and len(marks):
            bx0, by0 = min(bx0, marks[:, 0].min()), min(by0, marks[:, 1].min())
            bx1, by1 = max(bx1, marks[:, 0].max()), max(by1, marks[:, 1].max())
        mx, my = A.get("margin_x", A["margin"]), A["margin"]
        self.k = min((w - 2 * mx) / (bx1 - bx0), (h - 2 * my) / (by1 - by0))
        self.tx = x0 + w / 2 - self.k * (bx0 + bx1) / 2
        self.ty = y0 + h / 2 + self.k * (by0 + by1) / 2
        self.box = shapely.box(x0 - 4, y0 - 4, x0 + w + 4, y0 + h + 4)
        self.vb = A["viewbox"]

    def xy(self, q: np.ndarray) -> np.ndarray:
        return np.c_[self.k * q[:, 0] + self.tx, -self.k * q[:, 1] + self.ty]

    def g(self, geom, tol=0.3, lines=False, min_area=0.4):
        g = shapely.affinity.affine_transform(geom, [self.k, 0, 0, -self.k, self.tx, self.ty])
        g = shapely.simplify(shapely.intersection(shapely.make_valid(g), self.box), tol, preserve_topology=True)
        if lines:
            return g
        parts = [p for p in shapely.get_parts(g) if p.geom_type == "Polygon" and p.area >= min_area]
        return shapely.MultiPolygon(parts) if parts else shapely.Polygon()

    def extent_m(self):
        x0, y0, w, h = self.vb
        return ((x0 - self.tx) / self.k, (x0 + w - self.tx) / self.k, (self.ty - (y0 + h)) / self.k, (self.ty - y0) / self.k)


def _image(img: Image.Image, fmt="WEBP", **kw) -> str:
    buf = io.BytesIO()
    img.save(buf, fmt, **kw)
    return f"data:image/{fmt.lower()};base64," + base64.b64encode(buf.getvalue()).decode()


def relief_uri(cfg, A, F: Frame) -> str:
    from . import relief
    _, _, w, h = F.vb
    W, H = int(w * 1.5), int(h * 1.5)
    shade = relief.relief({**cfg, "projection": A["proj"]}, F.extent_m(), W, H).astype(np.float32)
    valid = shade > 0
    flat = float(np.argmax(np.bincount(shade[valid].astype(np.uint8).ravel(), minlength=256)))
    shade[~valid] = flat
    tone = 255 - np.clip((flat - shade) * 1.1, 0, 255)
    return _image(Image.fromarray(tone.astype(np.uint8), "L").convert("RGB"), quality=48, method=6)


def sea_uri(cfg, A, F: Frame) -> str:
    """Sea by depth, painted soft, with the maps' shelf colour where it is shallow."""
    x0, y0, w, h = F.vb
    k = 1.5
    img = Image.new("RGB", (int(w * k), int(h * k)), "#e3eef4")
    from .fetch import layer_path
    src = layer_path(cfg, "ne_10m_bathymetry_all")
    for depth, code, colour in ((200, "K", "#d8e8f0"), (2000, "I", "#cde1ec"), (4000, "G", "#c3d9e7")):
        g = gpd.read_file(f"zip://{src.resolve().as_posix()}", layer=f"ne_10m_bathymetry_{code}_{depth}",
                          bbox=A["bbox"])
        g = g.set_crs(geo.WGS84) if g.crs is None else g
        layer = Image.new("L", img.size, 0)
        draw = ImageDraw.Draw(layer)
        for geom in _to(A["proj"], [shapely.make_valid(x) for x in g.geometry if x is not None]):
            geom = shapely.affinity.affine_transform(geom, [F.k * k, 0, 0, -F.k * k, (F.tx - x0) * k, (F.ty - y0) * k])
            for p in shapely.get_parts(shapely.make_valid(geom)):
                if p.geom_type != "Polygon" or p.area < 1:
                    continue
                draw.polygon(list(p.exterior.coords), fill=255)
                for hole in p.interiors:
                    draw.polygon(list(hole.coords), fill=0)
        img.paste(Image.new("RGB", img.size, colour), (0, 0), layer)
    return _image(img.filter(ImageFilter.GaussianBlur(1.2)), quality=45, method=6)


def graticule(A, F: Frame, step=10):
    w, s, e, n = A["bbox"]
    lines = []
    for lon in range(int(math.ceil(w / step) * step), int(e) + 1, step):
        lats = np.linspace(s, n, 120)
        lines.append(shapely.LineString(np.c_[np.full_like(lats, lon), lats]))
    for lat in range(int(math.ceil(s / step) * step), int(n) + 1, step):
        lons = np.linspace(w, e, 160)
        lines.append(shapely.LineString(np.c_[lons, np.full_like(lons, lat)]))
    return F.g(shapely.MultiLineString([l for l in _to(A["proj"], lines)]), tol=0.4, lines=True)


# -- carrying the page's own drawing through the warp -----------------------------------------

NUM = r"-?\d+(?:\.\d+)?"


def carry(el: str, move) -> str:
    """One overlay element (text, circle, path, line) with its points moved to the new map."""
    def xy_attr(s, ax, ay):
        mx = re.search(r'\b%s="(%s)"' % (ax, NUM), s)
        my = re.search(r'\b%s="(%s)"' % (ay, NUM), s)
        if not (mx and my):
            return s
        nx, ny = move(float(mx.group(1)), float(my.group(1)))
        s = re.sub(r'\b%s="%s"' % (ax, NUM), f'{ax}="{nx:.1f}"', s, count=1)
        return re.sub(r'\b%s="%s"' % (ay, NUM), f'{ay}="{ny:.1f}"', s, count=1)

    def tag(m):
        t = m.group(0)
        if t.startswith(("<text", "<tspan")):
            return xy_attr(t, "x", "y")
        if t.startswith("<circle"):
            return xy_attr(t, "cx", "cy")
        if t.startswith("<line"):
            return xy_attr(xy_attr(t, "x1", "y1"), "x2", "y2")
        if t.startswith("<path"):
            d = re.search(r'\bd="([^"]+)"', t).group(1)
            if re.search(r"[a-zA-Z]", d.replace("M", "").replace("L", "")):
                return t                                  # only straight leader lines are carried
            pts = [(float(a), float(b)) for a, b in re.findall(r"(%s)[ ,](%s)" % (NUM, NUM), d)]
            new = "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in (move(*p) for p in pts))
            return t.replace(d, new)
        return t

    return re.sub(r"<(?:text|tspan|circle|line|path)\b[^>]*>", tag, el)


def draw(cfg, A, sources: dict[str, str], text_by_page: dict[str, str]) -> dict[str, str]:
    """The redrawn map for each page (English and Arabic), as {page: new page text}. `sources`
    holds each page's hand-drawn atlas, the drawing everything is read from."""
    svg = sources[A["page"]]
    coast0 = old_coast(svg, A["clip"])
    nations0 = old_nations(svg, A["prefix"])
    land, body = real_land(cfg, A)
    print(f"    registering the atlas to Natural Earth's coast")
    warp = Warp(coast0, body)
    print(f"    median distance of the warped coast to the real one: {warp.error_km:.0f} km")
    nations = [(nid, colour, warp.geom(g)) for nid, colour, g in nations0]
    # the atlas paints later nations over earlier ones (Songhai over Jolof): what shows is what
    # counts, so each nation loses whatever a later one covers
    shown = []
    for i, (nid, colour, g) in enumerate(nations):
        over = [h for _, _, h in nations[i + 1:] if h.intersects(g)]
        shown.append((nid, colour, shapely.make_valid(shapely.difference(g, shapely.union_all(over))) if over else g))
    nations = shown
    rv = geo.read_ne(cfg, "ne_10m_rivers_lake_centerlines", bbox_ll=A["bbox"])
    rv = rv[rv["scalerank"].fillna(99) <= A["river_rank"]]
    rivers = shapely.intersection(shapely.union_all(_to(A["proj"], rv.geometry)), body)
    print(f"    building the mesh")
    cells = build_cells(cfg, A, body, rivers)
    owner = assign(cells, nations, reach_m=A["spacing_km"] * 1000 * 2.5)
    print(f"    {len(cells)} cells, {int((owner >= 0).sum())} given to {len(set(owner[owner >= 0]))} nations")
    marks = []
    for k, (tag, attrs, full) in enumerate(_children(svg)):
        if k < 2:
            continue
        for a, b in re.findall(r'\b(?:x|cx|x1|x2)="(%s)"[^>]*?\b(?:y|cy|y1|y2)="(%s)"' % (NUM, NUM), full):
            marks.append((float(a), float(b)))
        for d in re.findall(r'\bd="([^"]+)"', full):
            marks.extend((float(a), float(b)) for a, b in re.findall(r"(%s)[ ,](%s)" % (NUM, NUM), d))
    F = Frame(A, body, warp(np.array(marks)) if marks else None)
    shapes = {}
    for j, (nid, colour, _) in enumerate(nations):
        members = cells[owner == j]
        if len(members):
            shapes[nid] = (colour, shapely.coverage_union_all(members) if hasattr(shapely, "coverage_union_all")
                           else shapely.union_all(members))
    # the nations share edges exactly: simplify them as one coverage
    ids = list(shapes)
    pix = [F.g(shapes[i][1], tol=0.0, min_area=0.0) for i in ids]
    simple = shapely.coverage_simplify(np.array(pix), 0.5)
    fills = "".join(f'<path fill="{shapes[i][0]}" d="{path_d(g)}"/>' for i, g in zip(ids, simple) if not g.is_empty)
    body_px = F.g(body, tol=0.3)
    other = F.g(shapely.difference(land, body.buffer(1)), tol=0.4, min_area=1.0)
    lk = geo.read_ne(cfg, "ne_10m_lakes", bbox_ll=A["bbox"])
    lk = lk[lk["scalerank"].fillna(99) <= 3]
    lakes = F.g(shapely.union_all(_to(A["proj"], lk.geometry)), tol=0.4, min_area=1.5)
    rivers_px = F.g(rivers, tol=0.5, lines=True)
    grat = graticule(A, F)
    x0, y0, w, h = F.vb
    # one outline for each land, drawn filled and then stroked as the coast (the frame clips the
    # land's straight cut at the edge, which the clip hides)
    ground = (f'<defs><clipPath id="atl-frame"><rect x="{x0}" y="{y0}" width="{w}" height="{h}"/></clipPath>'
              f'<path id="atl-body" d="{path_d(body_px)}"/><path id="atl-other" d="{path_d(other)}"/></defs>'
              f'<g clip-path="url(#atl-frame)" class="atl-ground">'
              f'<image x="{x0}" y="{y0}" width="{w}" height="{h}" preserveAspectRatio="none" href="{sea_uri(cfg, A, F)}"/>'
              f'<path fill="none" stroke="#8fa7b3" stroke-width=".6" stroke-opacity=".45" d="{path_d(grat)}"/>'
              f'<use href="#atl-other" fill="#d9d4ca"/>'
              f'<use href="#atl-body" fill="#e4ded2"/>'
              f'<g fill-rule="evenodd" stroke="#fff" stroke-width=".9" stroke-linejoin="round">{fills}</g>'
              f'<image x="{x0}" y="{y0}" width="{w}" height="{h}" preserveAspectRatio="none" opacity=".55" '
              f'style="mix-blend-mode:multiply" href="{relief_uri(cfg, A, F)}"/>'
              f'<path fill="#dcebf2" stroke="#4a5a61" stroke-width=".4" d="{path_d(lakes)}"/>'
              f'<path fill="none" stroke="#6a9ac0" stroke-width=".7" stroke-linejoin="round" stroke-linecap="round" '
              f'd="{path_d(rivers_px)}"/>'
              f'<g fill="none" stroke="#4a5a61" stroke-width=".7" stroke-linejoin="round">'
              f'<use href="#atl-other"/><use href="#atl-body"/></g>'
              f"</g>")

    def move(px, py):
        q = F.xy(warp(np.array([[px, py]])))[0]
        return float(q[0]), float(q[1])

    out = {}
    for key, text in text_by_page.items():
        src = sources[key]
        a, b, _ = _svg(text, A["viewbox"])
        head = src[: src.index(">") + 1]
        overlays = "".join(carry(full, move) for k, (tag, attrs, full) in enumerate(_children(src)) if k >= 2)
        out[key] = text[:a] + head + ground + overlays + "</svg>" + text[b:]
    return out


SOURCE = SITE / "video" / "data" / "atlas"


def install(cfg: dict) -> list[str]:
    """Redraw each atlas map in both editions. The hand-drawn originals are kept in
    data/atlas/ (saved from the pages the first time): they are the source the build reads, and
    the place to move a nation's frontier, a label or a leader line."""
    changed = []
    SOURCE.mkdir(parents=True, exist_ok=True)
    for A in (AFRICA,):
        texts, sources = {}, {}
        for key in (A["page"], "ar/" + A["page"]):
            page = SITE / key
            if not page.exists():
                continue
            with open(page, encoding="utf8", newline="") as fh:
                texts[key] = fh.read()
            src = SOURCE / (A["page"].replace(".html", ".ar.svg" if key.startswith("ar/") else ".svg"))
            if not src.exists():
                svg = _svg(texts[key], A["viewbox"])[2]
                if f'id="{A["clip"]}"' not in svg:
                    raise SystemExit(f"{key}: the atlas is already redrawn and {src.name} is missing")
                src.write_text(svg.replace("\r\n", "\n") + "\n", encoding="utf8", newline="\n")
                print(f"    saved the hand-drawn atlas to {src.relative_to(SITE).as_posix()}")
            sources[key] = src.read_text(encoding="utf8").strip()
        print(f"  {A['page']}")
        for key, new in draw(cfg, A, sources, texts).items():
            if new != texts[key]:
                with open(SITE / key, "w", encoding="utf8", newline="") as fh:
                    fh.write(new)
                changed.append(key)
    return changed
