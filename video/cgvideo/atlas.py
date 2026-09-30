"""The reference atlases, redrawn on real coastlines, on frontiers traced on the ground.

Both atlases are drawn from their frontiers. data/atlas/<region>-frontiers.yaml says what each
frontier follows on the ground (a river, a watershed, an escarpment or crest, a dune sea, a lake),
QGIS traces it (integrations/qgis/cg_frontiers.py, with GRASS's river basins for the watersheds)
into data/atlas/<region>-frontiers.geojson, and `python build.py atlas` cuts the land with those
lines and hands each piece to the nation of data/atlas/<region>-nations.csv whose seed lies in it
(cgvideo/frontiers.py). The maps show them over the sea and relief of ETOPO 2022, projected and
shaded by QGIS and finished in GIMP (terrain.py), with the ribbons of a wall map along each
frontier (blurred and toned in GIMP) under a dash-dot line.

Africa sets its labels from the nations' table, in each edition's words. Europe keeps the words
of its hand-drawn maps (data/atlas/europe*.svg: the labels, leader lines, numbered keys and the
legend band of 1914), carried onto the real ground by a warp: the hand-drawn coast is matched to
Natural Earth's (an affine start from the labels that sit inside their nations, refined by a
thin-plate spline fitted by iterated closest points on the coast, with the labels, the far ends
of leader lines and a few capes held far tighter than the coast). A few names of ground rather
than of nations (AFRICA, the Caucasus) are set where that ground really is, and a key band under
the map stays where it is. The Europe atlas's second map (about 1914) fills the same nations in
the colour of the African power that governed each (colour_1914 in europe-nations.csv), and
Sápmi is hatched over the frontiers it crosses (`overlays` in europe-frontiers.yaml).
"""

from __future__ import annotations

import base64
import html
import io
import math
import re

import geopandas as gpd
import numpy as np
import shapely
from PIL import Image, ImageDraw, ImageFilter

from . import frontiers as fr
from . import geo
from .config import paths
from .sitemaps import SITE, _children, _poly_from_svg, path_d

NUM = r"-?\d+(?:\.\d+)?"

AFRICA = {
    "page": "africa.html", "maps": [("0 0 780 790", "af-al0")],
    "area": (0, 0, 780, 790),                   # the map on the canvas (no key band)
    "proj": "+proj=laea +lat_0=2 +lon_0=17 +datum=WGS84 +units=m +no_defs",
    "bbox": fr.BBOX,                     # what the map may show, lon/lat
    "centre": (17.0, 2.0), "islands": [(46.9, -18.9)],   # the continent, and Madagascar
    "asia": fr.ASIA,                     # Asia, cut off at Rafah, Aqaba and down the Red Sea
    "margin": 16, "margin_x": 44,
}

EUROPE = {
    "page": "europe.html", "maps": [("-14 -12 808 760", "eurland"), ("-14 -12 808 822", "eurland2")],
    "area": (-14, -12, 808, 690),               # the map; the key band under it stays put
    "proj": "+proj=laea +lat_0=53 +lon_0=15 +datum=WGS84 +units=m +no_defs",
    "bbox": (-75, 18, 100, 84),
    # labels that sit inside their nation, and a point well inside the real one
    "anchors": {"Iceland": (-18.6, 64.9), "Ireland": (-8.0, 53.2), "Anglia": (-1.8, 52.8), "Francia": (2.3, 46.6),
                "Spain": (-3.6, 40.0), "Italy": (12.8, 42.8), "Rhenia": (9.5, 51.0), "Poland": (19.2, 52.0),
                "Sweden": (15.5, 62.5), "Norway": (9.0, 61.0), "Finland": (26.0, 63.5), "Ukraine": (31.5, 49.0),
                "Belarus": (28.0, 53.5), "Romania": (25.0, 45.8), "Bulgaria": (25.2, 42.7), "Hungary": (19.3, 47.1),
                "Greece": (22.0, 39.3), "Czechia": (15.3, 49.8), "Estonia": (25.8, 58.7), "Latvia": (25.0, 56.9),
                "Lithuania": (23.9, 55.3), "Serbia": (20.8, 44.0), "Bosnia": (17.8, 44.2),
                "Switzerland": (8.2, 46.8), "Austria": (14.5, 47.5), "Bavaria": (11.4, 48.8),
                "Sardinia": (9.0, 40.1), "Russia": (40.0, 57.0), "Aquitaine": (-0.4, 44.3),
                "Turkey": (33.5, 39.2)},
    # labels set off in the sea: the far end of their leader line, and a point inside the real
    # nation (the hand-drawn Iberia is too narrow to be carried by the Spain label alone)
    "leads": {"Portugal": (-8.1, 39.7), "Galicia": (-7.9, 42.7), "Basque Country": (-2.2, 43.1),
              "Brittany": (-3.0, 48.1), "Normandy": (-0.2, 49.1), "Crimea": (34.2, 45.2)},
    # points of the hand-drawn map (atlas pixels) and the real ones, where the drawing is too
    # rough for the coast alone to carry it: the capes of Iberia (St Vincent, Tarifa, Roca,
    # Finisterre, Gata, la Nao), of Ireland (Malin, Erris, Slea, Mizen, Carnsore, Dublin) and of
    # Britain (Wrath, Duncansby, Ardnamurchan, Kintyre, St David's, Land's End, Lowestoft, North
    # Foreland); the shores of the Gulf of Bothnia (Grisslehamn, Umea, Lulea, Kemi, Vaasa, Pori,
    # Turku, Helsinki); Italy's toe and heel, Sicily, Malta, Crete, Methoni and Matapan; Russia's
    # corner on the Caspian; Turkey's at Batumi, Ararat and Hakkari
    "pins": [((167.4, 612.0), (-8.95, 37.02)), ((201.8, 630.0), (-5.60, 36.01)), ((161.2, 570.6), (-9.50, 38.78)),
             ((163.3, 505.8), (-9.27, 42.88)), ((252.7, 601.2), (-2.19, 36.73)), ((260.0, 567.0), (0.21, 38.73)),
             ((184.1, 280.8), (-7.37, 55.38)), ((157.0, 300.6), (-10.0, 54.30)), ((155.0, 338.4), (-10.46, 52.10)),
             ((161.2, 351.0), (-9.80, 51.45)), ((194.5, 343.8), (-6.36, 52.17)), ((197.6, 316.8), (-6.10, 53.40)),
             ((208.0, 228.6), (-5.00, 58.62)), ((239.2, 223.2), (-3.03, 58.64)), ((200.7, 243.0), (-6.20, 56.70)),
             ((199.7, 261.0), (-5.80, 55.30)), ((204.9, 347.4), (-5.30, 51.88)), ((205.9, 378.0), (-5.70, 50.07)),
             ((265.2, 327.6), (1.75, 52.48)), ((274.6, 352.8), (1.44, 51.36)),
             ((456.6, 187.2), (18.9, 60.2)), ((470.1, 133.2), (20.4, 63.7)), ((494.0, 93.6), (22.2, 65.55)),
             ((510.6, 93.6), (24.9, 65.4)), ((484.6, 142.2), (21.6, 63.1)), ((481.5, 171.0), (21.5, 61.5)),
             ((490.9, 190.8), (22.2, 60.3)), ((520.0, 194.4), (24.95, 60.15)),
             ((422.2, 594.0), (15.65, 38.1)), ((452.4, 556.2), (18.36, 39.8)), ((407.1, 601.9), (14.15, 37.55)),
             ((409.8, 631.3), (14.42, 35.9)), ((518.7, 645.0), (24.9, 35.25)), ((485.7, 615.6), (21.7, 36.82)),
             ((494.0, 622.8), (22.48, 36.39)),
             ((738.0, 506.0), (47.3, 45.0)), ((700.9, 524.7), (41.6, 41.55)), ((735.2, 570.2), (44.4, 39.8)),
             ((730.6, 607.9), (44.2, 37.3))],
    # names of ground rather than of nations, set where that ground really is
    "place": {"A F R I C A": (4.0, 32.2), "Aljazair · the Maghrib": (1.0, 34.6), "Caucasus": (44.2, 42.4),
              "the Mashriq": (38.6, 35.2)},
    "smooth": (4000.0, 2000.0, 1000.0, 600.0),
    "river_rank": 4,
    "margin": 14, "margin_x": 40,
}


# -- reading the hand-drawn atlas -------------------------------------------------------------

def _svg(text: str, vb: str):
    m = re.search(r'<svg\b[^>]*viewBox="%s"[^>]*>.*?</svg>' % re.escape(vb), text, re.S)
    return m.start(), m.end(), m.group(0)


def old_nations(svg: str, A: dict) -> list[tuple[str, str, object]]:
    """(key, fill, shape in the atlas's pixels) of every nation, in paint order. A hatched fill
    (url(#...)) is kept as it is: it is laid over the others, not given cells of its own."""
    import hashlib
    out = []
    group = _children(svg)[1][2]
    for m in re.finditer(r'<polygon\b([^>]*)>', group):
        attrs = m.group(1)
        fill = re.search(r'fill="([^"]+)"', attrs).group(1)
        points = re.search(r'points="([^"]+)"', attrs).group(1)
        key = "p" + hashlib.sha1(points.encode()).hexdigest()[:8]     # the same shape on every map
        out.append((key, fill, _poly_from_svg(f'<polygon {attrs}>')))
    return out


def old_coast(svg: str, clip: str):
    d = re.search(r'<clipPath id="%s">\s*<path d="([^"]+)"' % re.escape(clip), svg).group(1)
    return _poly_from_svg(f'<path d="{d}">')


# -- the real ground --------------------------------------------------------------------------

def _to(proj, geoms):
    return list(gpd.GeoSeries(list(geoms), crs=geo.WGS84).to_crs(proj))


def real_land_ll(cfg: dict, A: dict):
    w, s, e, n = A["bbox"]
    parts = []
    for name in ("ne_10m_land", "ne_10m_minor_islands"):
        g = geo.read_ne(cfg, name, bbox_ll=(w, s, e, n))
        parts.extend(shapely.make_valid(x) for x in g.geometry.intersection(shapely.box(w, s, e, n)))
    return shapely.union_all([p for p in parts if not p.is_empty])


def africa_body(A, land_ll):
    continent = shapely.difference(land_ll, shapely.Polygon(A["asia"]))
    pieces = [next(p for p in shapely.get_parts(continent) if p.contains(shapely.Point(x, y)))
              for x, y in [A["centre"], *A.get("islands", [])]]
    return shapely.union_all(pieces)


# -- registration: the atlas's pixels to real metres ------------------------------------------

def _sample_lines(g, step: float) -> np.ndarray:
    pts = []
    for line in shapely.get_parts(g):
        if line.length < step:
            continue
        n = max(2, int(line.length / step))
        pts.extend((p.x, p.y) for p in (line.interpolate(t, normalized=True) for t in np.linspace(0, 1, n)))
    return np.array(pts) if pts else np.zeros((0, 2))


class Warp:
    """Atlas pixels -> the map's projected metres: a per-axis affine, then a thin-plate spline
    fitted by iterated closest points on the coast, holding any anchor points it is given."""

    def __init__(self, old_pts, real_pts, start_src, start_dst, anchors=None, smooth=(3000.0, 300.0, 60.0)):
        from scipy.interpolate import RBFInterpolator
        from scipy.spatial import cKDTree
        self.ax = np.polyfit(start_src[:, 0], start_dst[:, 0], 1)
        self.ay = np.polyfit(start_src[:, 1], start_dst[:, 1], 1)
        tree = cKDTree(real_pts)
        p = old_pts
        a_src, a_dst = anchors if anchors is not None else (np.zeros((0, 2)), np.zeros((0, 2)))
        a_disp = self._affine_inv(a_dst) - a_src
        disp = np.zeros_like(p)
        for s in smooth:
            dist, idx = tree.query(self._affine(p + disp))
            keep = dist <= max(3 * np.median(dist), 80_000)
            src = np.vstack([p[keep], a_src])
            dst = np.vstack([(self._affine_inv(real_pts[idx]) - p)[keep], a_disp])
            # an anchor is one point against thousands on the coast: it is held far tighter
            smooth_at = np.r_[np.full(int(keep.sum()), s), np.full(len(a_src), s * 0.02)]
            self.rbf = RBFInterpolator(src, dst, kernel="thin_plate_spline", smoothing=smooth_at, degree=1)
            disp = self.rbf(p)
        self.error_km = float(np.median(tree.query(self(p))[0]) / 1000)
        self.anchor_km = float(np.median(np.hypot(*(self(a_src) - a_dst).T)) / 1000) if len(a_src) else 0.0

    def _affine(self, p):
        return np.c_[self.ax[0] * p[:, 0] + self.ax[1], self.ay[0] * p[:, 1] + self.ay[1]]

    def _affine_inv(self, q):
        return np.c_[(q[:, 0] - self.ax[1]) / self.ax[0], (q[:, 1] - self.ay[1]) / self.ay[0]]

    def __call__(self, p) -> np.ndarray:
        p = np.asarray(p, float).reshape(-1, 2)
        return self._affine(p + self.rbf(p))

    def geom(self, g, step: float = 1.5):
        """A shape carried over. Each ring is closed again by hand: the spline is evaluated in
        batches, and a ring's first and last point can come out a hair apart."""
        polys = []
        for p in shapely.get_parts(shapely.segmentize(g, step)):
            if p.geom_type != "Polygon":
                continue
            rings = []
            for ring in [p.exterior, *p.interiors]:
                xy = self(np.asarray(ring.coords)[:-1])
                if len(xy) >= 3:
                    rings.append(np.vstack([xy, xy[:1]]))
            if rings:
                polys.append(shapely.make_valid(shapely.Polygon(rings[0], rings[1:])))
        return shapely.union_all(polys) if polys else shapely.Polygon()


# -- drawing ----------------------------------------------------------------------------------

class Frame:
    """The new map on the canvas: the map's projection scaled uniformly into the map area, fitted
    to the ground and to every mark the page draws on it."""

    def __init__(self, A: dict, extent: tuple, marks: np.ndarray | None = None):
        x0, y0, w, h = A["area"]
        bx0, by0, bx1, by1 = extent
        if marks is not None and len(marks):
            bx0, by0 = min(bx0, marks[:, 0].min()), min(by0, marks[:, 1].min())
            bx1, by1 = max(bx1, marks[:, 0].max()), max(by1, marks[:, 1].max())
        mx, my = A.get("margin_x", A["margin"]), A["margin"]
        self.k = min((w - 2 * mx) / (bx1 - bx0), (h - 2 * my) / (by1 - by0))
        self.tx = x0 + w / 2 - self.k * (bx0 + bx1) / 2
        self.ty = y0 + h / 2 + self.k * (by0 + by1) / 2
        self.box = shapely.box(x0 - 4, y0 - 4, x0 + w + 4, y0 + h + 4)
        self.area = A["area"]

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
        x0, y0, w, h = self.area
        return ((x0 - self.tx) / self.k, (x0 + w - self.tx) / self.k, (self.ty - (y0 + h)) / self.k, (self.ty - y0) / self.k)

    def ground_box_m(self):
        e = self.extent_m()
        return shapely.box(e[0], e[2], e[1], e[3])


def _image(img: Image.Image, **kw) -> str:
    buf = io.BytesIO()
    img.save(buf, "WEBP", **kw)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()


def relief_uri(cfg, A, F: Frame) -> str:
    from . import relief
    _, _, w, h = F.area
    shade = relief.relief({**cfg, "projection": A["proj"]}, F.extent_m(), int(w * 1.5), int(h * 1.5)).astype(np.float32)
    valid = shade > 0
    flat = float(np.argmax(np.bincount(shade[valid].astype(np.uint8).ravel(), minlength=256)))
    shade[~valid] = flat
    tone = 255 - np.clip((flat - shade) * 1.1, 0, 255)
    return _image(Image.fromarray(tone.astype(np.uint8), "L").convert("RGB"), quality=48, method=6)


def sea_uri(cfg, A, F: Frame) -> str:
    """Sea by depth, painted soft, with the maps' shelf colour where it is shallow."""
    from .fetch import layer_path
    x0, y0, w, h = F.area
    k = 1.5
    img = Image.new("RGB", (int(w * k), int(h * k)), "#e3eef4")
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


def ground_images(cfg, A, F: Frame, land_px) -> tuple[str, str]:
    """(sea, relief) from ETOPO 2022, drawn by QGIS and finished in GIMP (see terrain.py), with
    the relief exaggerated to suit the atlas's scale; without QGIS, Natural Earth's as before."""
    from . import terrain
    x0, y0, w, h = F.area
    k = 1.5
    metres = 1 / (F.k * k)                              # one terrain pixel on the ground
    land = shapely.affinity.affine_transform(land_px, [k, 0, 0, k, -x0 * k, -y0 * k])
    name = A["page"].split(".")[0].capitalize() + " atlas"
    try:
        relief, sea = terrain.images(cfg, name, A["proj"], F.extent_m(), int(w * k), int(h * k), land,
                                     z=round(6 * math.sqrt(metres / 3393), 1), floor=0.2)
        return sea, relief
    except RuntimeError as exc:
        print(f"    {exc}; using Natural Earth's shaded relief")
        return sea_uri(cfg, A, F), relief_uri(cfg, A, F)


def graticule(A, F: Frame, step=10):
    w, s, e, n = A["bbox"]
    lines = []
    for lon in range(int(math.ceil(w / step) * step), int(e) + 1, step):
        lats = np.linspace(s, n, 120)
        lines.append(shapely.LineString(np.c_[np.full_like(lats, lon), lats]))
    for lat in range(int(math.ceil(s / step) * step), int(n) + 1, step):
        lons = np.linspace(w, e, 160)
        lines.append(shapely.LineString(np.c_[lons, np.full_like(lons, lat)]))
    return F.g(shapely.MultiLineString(_to(A["proj"], lines)), tol=0.4, lines=True)


# -- carrying the page's own drawing through the warp -----------------------------------------

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
            pts = [(float(a), float(b)) for a, b in re.findall(r"(%s)[ ,]\s*(%s)" % (NUM, NUM), d)]
            return t.replace(d, "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in (move(*p) for p in pts)))
        return t

    return re.sub(r"<(?:text|tspan|circle|line|path)\b[^>]*>", tag, el)


def _name(text: str) -> str:
    """A label's words, without entities' marks: 'Turkey &#10043;' is Turkey."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s·'-]", "", html.unescape(text))).strip()


def _first_y(full: str) -> float | None:
    m = re.search(r'\b(?:y|cy|y1)="(%s)"' % NUM, full)
    return float(m.group(1)) if m else None


def overlays(src: str, A: dict):
    """The page's own drawing on an atlas map: (geographic, band) children, in order. The key
    band under the map (anything starting below the map area) is not moved."""
    x0, y0, w, h = A["area"]
    band_y = y0 + h - 2
    geo_part, band = [], []
    for k, (tag, attrs, full) in enumerate(_children(src)):
        if k < 3:
            continue                                       # defs, the drawn ground, the drawn coast
        y = _first_y(full)
        (band if y is not None and y >= band_y else geo_part).append(full)
    return geo_part, band


def _marks(parts: list[str]) -> np.ndarray:
    pts = []
    for full in parts:
        for a, b in re.findall(r'\b(?:x|cx|x1|x2)="(%s)"[^>]*?\b(?:y|cy|y1|y2)="(%s)"' % (NUM, NUM), full):
            pts.append((float(a), float(b)))
        for d in re.findall(r'\bd="([^"]+)"', full):
            pts.extend((float(a), float(b)) for a, b in re.findall(r"(%s)[ ,]\s*(%s)" % (NUM, NUM), d))
    return np.array(pts) if pts else np.zeros((0, 2))


def _keep_defs(src: str) -> str:
    """The hand-drawn map's own <defs> (styles, hatch patterns, markers), without its clip."""
    defs = _children(src)[0][2]
    return re.sub(r"<clipPath\b.*?</clipPath>", "", defs, flags=re.S)


def register(cfg, A, src_en: str, vb: str, clip: str, land_ll):
    """The warp for an atlas, and the ground the map covers (in metres)."""
    coast0 = old_coast(src_en, clip)
    lbl = re.search(r'<g class="lbl">(.*?)</g>', src_en, re.S).group(1)
    src, dst = [], []
    for m in re.finditer(r'<text x="(%s)" y="(%s)"[^>]*>([^<]+)</text>' % (NUM, NUM), lbl):
        name = _name(m.group(3))
        if name in A["anchors"]:
            src.append((float(m.group(1)), float(m.group(2))))
            dst.append(A["anchors"][name])
    leads = [np.array(re.findall(NUM, d), float).reshape(-1, 2)
             for d in re.findall(r'<path class="lead" d="([^"]+)"', src_en)]
    for m in re.finditer(r'<text x="(%s)" y="(%s)"[^>]*>([^<]+)</text>' % (NUM, NUM), src_en):
        name = _name(m.group(3))
        if name in A.get("leads", {}) and leads:
            at = np.array([float(m.group(1)), float(m.group(2))])
            line = min(leads, key=lambda p: np.hypot(*(p[0] - at)))
            src.append(tuple(line[-1]))
            dst.append(A["leads"][name])
    for px, ll in A.get("pins", []):
        src.append(px)
        dst.append(ll)
    dst_m = np.array([(p.x, p.y) for p in _to(A["proj"], [shapely.Point(ll) for ll in dst])])
    start_src, start_dst, anchors = np.array(src), dst_m, (np.array(src), dst_m)
    # the drawn coast, without the frame's edges; the real coast, near where the map looks
    x0, y0, w, h = A["area"]
    inner = shapely.box(x0 + 3, y0 + 3, x0 + w - 3, y0 + h - 3)
    old_pts = _sample_lines(shapely.intersection(coast0.boundary, inner), 3.0)
    # the ground is whatever land the old map area covers, once carried over
    start = Warp.__new__(Warp)
    start.ax = np.polyfit(start_src[:, 0], start_dst[:, 0], 1)
    start.ay = np.polyfit(start_src[:, 1], start_dst[:, 1], 1)
    corners = start._affine(np.array([[x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h]]))
    region = shapely.Polygon(corners).buffer(150_000)
    land = shapely.make_valid(_to(A["proj"], [land_ll])[0])
    body = shapely.make_valid(shapely.intersection(land, region))
    real_pts = _sample_lines(shapely.intersection(body.boundary, shapely.Polygon(corners).buffer(-20_000)), 8000.0)
    warp = Warp(old_pts, real_pts, start_src, start_dst, anchors, A["smooth"])
    return warp, body


def draw(cfg, A, sources: dict[str, dict[str, str]], texts: dict[str, str]) -> dict[str, str]:
    """Europe. sources: page -> viewBox -> the hand-drawn map; texts: page -> page text. The nations
    are cut by the traced frontiers (data/atlas/europe-frontiers.geojson) and filled, on each map,
    in that map's colour for them (europe-nations.csv); everything the page drew on the map (its
    labels, leader lines, keys and legend band) is carried over by the warp. Returns the new page
    texts."""
    from . import terrain
    first_vb, first_clip = A["maps"][0]
    src_en = sources[A["page"]][first_vb]
    held, unclaimed, rows, spec, land_ll = traced_ground(cfg, A, "europe")
    rows = [r for r in rows if r["key"] in held]
    print(f"    {len(held)} nations cut by {len(spec['frontiers'])} frontiers; {len(unclaimed)} pieces left neutral")
    print("    registering the atlas to Natural Earth's coast")
    warp, _ = register(cfg, A, src_en, first_vb, first_clip, land_ll)
    print(f"    median distance of the warped coast to the real one: {warp.error_km:.0f} km"
          + (f"; of the label anchors to their nations: {warp.anchor_km:.0f} km" if warp.anchor_km else ""))
    proj = A["proj"]
    land = shapely.make_valid(_to(proj, [land_ll])[0])
    geo_en, _ = overlays(src_en, A)
    marks = _marks(geo_en)
    place_px = {(float(m.group(1)), float(m.group(2)))
                for m in re.finditer(r'<text x="(%s)" y="(%s)"[^>]*>([^<]+)</text>' % (NUM, NUM), src_en)
                if _name(m.group(3)) in A.get("place", {})}
    marks = np.array([p for p in marks if tuple(p) not in place_px]).reshape(-1, 2)
    moved = warp(marks) if len(marks) else None
    # the map shows the drawn coast and everything drawn on it, carried over; its ground runs past
    # the frame so no cut is ever in view
    x0, y0, w, h = A["area"]
    inner = shapely.box(x0 + 3, y0 + 3, x0 + w - 3, y0 + h - 3)
    q = warp(_sample_lines(shapely.intersection(old_coast(src_en, first_clip).boundary, inner), 3.0))
    F = Frame(A, (q[:, 0].min(), q[:, 1].min(), q[:, 0].max(), q[:, 1].max()), moved)
    body = shapely.make_valid(shapely.intersection(land, F.ground_box_m().buffer(120_000)))
    body_px = F.g(body, tol=0.3)
    other = F.g(shapely.difference(land, body.buffer(1)), tol=0.4, min_area=1.0)
    # the nations as one coverage, simplified together so neighbours keep one shared edge; the
    # frontiers are their edges that are not coast
    geoms = [F.g(_to(proj, [held[r["key"]]])[0], tol=0.0, min_area=0.0) for r in rows]
    geoms = list(shapely.coverage_simplify(np.array(geoms), 0.35))
    edges = shapely.union_all([g.boundary for g in geoms])
    frontier_px = shapely.difference(edges, shapely.union(body_px, other).boundary.buffer(0.25))
    frontier_px = shapely.line_merge(shapely.union_all([p for p in shapely.get_parts(frontier_px)
                                                        if p.geom_type == "LineString" and p.length > 0.6]))
    sapmi = (spec.get("overlays") or {}).get("sapmi")
    sapmi_px = (F.g(_to(proj, [shapely.intersection(fr.europe_land(land_ll), shapely.Polygon(sapmi))])[0], tol=0.4)
                if sapmi else shapely.Polygon())
    rv = geo.read_ne(cfg, "ne_10m_rivers_lake_centerlines", bbox_ll=A["bbox"])
    rv = rv[rv["scalerank"].fillna(99) <= A["river_rank"]]
    rivers_px = F.g(shapely.intersection(shapely.union_all(_to(proj, rv.geometry)), body), tol=0.5, lines=True)
    lk = geo.read_ne(cfg, "ne_10m_lakes", bbox_ll=A["bbox"])
    lk = lk[lk["scalerank"].fillna(99) <= 3]
    lakes = F.g(shapely.union_all(_to(proj, lk.geometry)), tol=0.4, min_area=1.5)
    grat = graticule(A, F)
    sea, relief = ground_images(cfg, A, F, shapely.union(body_px, other))
    shapes = "".join(f'<path id="atl-n-{r["key"]}" d="{path_d(g)}"/>' for g, r in zip(geoms, rows) if not g.is_empty)
    grounds = {}
    for n, (vb, clip) in enumerate(A["maps"]):
        src = sources[A["page"]][vb]
        fill_of = [r["colour"] if n == 0 else r["colour_1914"] for r in rows]
        hatch = next((f for _, f, _ in old_nations(src, A) if f.startswith("url(")), None)
        ribbons = terrain.ribbons(cfg, f"Europe atlas {n + 1}", F.area, list(zip(geoms, fill_of)), frontier_px)
        fills = "".join(f'<use href="#atl-n-{r["key"]}" fill="{f}"/>' for g, r, f in zip(geoms, rows, fill_of)
                        if not g.is_empty)
        hatches = (f'<path fill="{hatch}" stroke="#3f7d6e" stroke-width=".6" stroke-opacity=".6" d="{path_d(sapmi_px)}"/>'
                   if hatch and not sapmi_px.is_empty else "")
        tag = "atl" if n == 0 else f"atl{n + 1}"
        shared = (f'<path id="atl-body" d="{path_d(body_px)}"/><path id="atl-other" d="{path_d(other)}"/>'
                  f'<image id="atl-sea" x="{x0}" y="{y0}" width="{w}" height="{h}" preserveAspectRatio="none" href="{sea}"/>'
                  f'<image id="atl-relief" x="{x0}" y="{y0}" width="{w}" height="{h}" preserveAspectRatio="none" '
                  f'href="{relief}"/>'
                  f'<path id="atl-grat" d="{path_d(grat)}"/><path id="atl-lakes" d="{path_d(lakes)}"/>'
                  f'<path id="atl-rivers" d="{path_d(rivers_px)}"/><path id="atl-frontiers" d="{path_d(frontier_px)}"/>'
                  + shapes) if n == 0 else ""
        grounds[vb] = (
            f'<defs><clipPath id="{tag}-frame"><rect x="{x0}" y="{y0}" width="{w}" height="{h}"/></clipPath>'
            + shared + "</defs>"
            f'<g clip-path="url(#{tag}-frame)" class="atl-ground">'
            f'<use href="#atl-sea"/>'
            f'<use href="#atl-grat" fill="none" stroke="#8fa7b3" stroke-width=".6" stroke-opacity=".45"/>'
            f'<use href="#atl-other" fill="{INK["other"]}"/>'
            f'<use href="#atl-body" fill="{INK["base"]}"/>'
            f'<g fill-rule="evenodd">{fills}</g>'
            f'<image x="{x0}" y="{y0}" width="{w}" height="{h}" preserveAspectRatio="none" href="{ribbons}"/>'
            f'{hatches}'
            f'<use href="#atl-relief" opacity=".55" style="mix-blend-mode:multiply"/>'
            f'<use href="#atl-lakes" fill="#dcebf2" stroke="{INK["coast"]}" stroke-width=".4"/>'
            f'<use href="#atl-rivers" fill="none" stroke="#6a9ac0" stroke-width=".6" stroke-linejoin="round" '
            f'stroke-linecap="round"/>'
            f'<use href="#atl-frontiers" fill="none" stroke="#fff" stroke-width="1.7" stroke-opacity=".7" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
            f'<use href="#atl-frontiers" fill="none" stroke="{INK["frontier"]}" stroke-width=".75" '
            f'stroke-dasharray="3.2 1.3 .9 1.3" stroke-linejoin="round"/>'
            f'<g fill="none" stroke="{INK["coast"]}" stroke-width=".7" stroke-linejoin="round">'
            f'<use href="#atl-other"/><use href="#atl-body"/></g>'
            f"</g>")

    placed = {}                                    # a label set where its ground is (both editions)
    for drawn_map in sources[A["page"]].values():
        for m in re.finditer(r'<text x="(%s)" y="(%s)"[^>]*>([^<]+)</text>' % (NUM, NUM), drawn_map):
            ll = A.get("place", {}).get(_name(m.group(3)))
            if ll:
                q = F.xy(np.array([(p.x, p.y) for p in _to(proj, [shapely.Point(ll)])]))[0]
                placed[(float(m.group(1)), float(m.group(2)))] = (float(q[0]), float(q[1]))

    def move(px, py):
        if (px, py) in placed:
            return placed[(px, py)]
        q = F.xy(warp(np.array([[px, py]])))[0]
        return float(q[0]), float(q[1])

    out = {}
    for page, text in texts.items():
        new = text
        for vb, clip in A["maps"]:
            src = sources[page][vb]
            a, b, _ = _svg(new, vb)
            head = src[: src.index(">") + 1]
            geo_part, band = overlays(src, A)
            body_svg = _keep_defs(src) + grounds[vb] + "".join(carry(p, move) for p in geo_part) + "".join(band)
            new = new[:a] + head + body_svg + "</svg>" + new[b:]
        out[page] = new
    return out


# -- the Africa atlas, on frontiers traced on the ground ----------------------------------------

LABELS = {
    "en": {"font": 'ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif', "dir": ""},
    "ar": {"font": '"Segoe UI",Tahoma,Arial,sans-serif', "dir": ' direction="rtl"'},
}
INK = {"frontier": "#4d4d4d", "coast": "#4a5a61", "other": "#d9d4ca", "base": "#e4ded2"}


def _text_w(text: str, size: float) -> float:
    return 0.56 * size * len(text)


def traced_ground(cfg, A, region: str):
    """The nations of a traced atlas in lon/lat: ({key: shape}, [neutral pieces], rows, spec, land)."""
    import yaml
    store = paths(cfg).data / "atlas"
    spec = yaml.safe_load((store / f"{region}-frontiers.yaml").read_text(encoding="utf8"))
    rows = fr.read_nations(store / f"{region}-nations.csv")
    lines = fr.read_geojson(store / f"{region}-frontiers.geojson")
    land_ll = real_land_ll(cfg, A)
    seeds = {r["key"]: [(r["seed_lon"], r["seed_lat"])] for r in rows}
    for k, pts in (spec.get("seeds") or {}).items():
        seeds[k] = seeds.get(k, []) + [tuple(p) for p in pts]
    held, unclaimed = fr.nations(lines, fr.REGIONS[region]["land"](land_ll), seeds, spec.get("neutral", []))
    missing = [r["key"] for r in rows if r["key"] not in held]
    if missing:
        raise SystemExit(f"no ground for {', '.join(missing)}: check the frontiers around their seeds")
    return held, unclaimed, rows, spec, land_ll


def draw_africa(cfg, A, texts: dict[str, str], ground=None) -> dict[str, str]:
    """The Africa atlas from data/atlas/africa-frontiers.geojson and africa-nations.csv: the
    nations cut by their frontiers, drawn on the real ground with the ribbons of a wall map,
    and labelled from the nations' own table, in each edition's words."""
    from . import terrain
    held, unclaimed, rows, spec, land_ll = ground or traced_ground(cfg, A, "africa")
    rows = [r for r in rows if r["key"] in held]
    print(f"    {len(held)} nations cut by {len(spec['frontiers'])} frontiers; {len(unclaimed)} islands left neutral")
    proj = A["proj"]
    nat_m = dict(zip([r["key"] for r in rows], _to(proj, [held[r["key"]] for r in rows])))
    body = _to(proj, [africa_body(A, land_ll)])[0]
    land = shapely.make_valid(_to(proj, [land_ll])[0])
    pt = lambda lon, lat: np.array([(p.x, p.y) for p in _to(proj, [shapely.Point(lon, lat)])])[0]
    labels_m = np.array([pt(r["label_lon"], r["label_lat"]) for r in rows])
    F = Frame(A, body.bounds, labels_m)
    africa_m = shapely.union_all(list(nat_m.values()))
    body_px = F.g(africa_m, tol=0.3)
    other = F.g(shapely.difference(land, africa_m.buffer(1)), tol=0.4, min_area=1.0)
    # the nations as one coverage, simplified together so neighbours keep one shared edge
    geoms = [F.g(nat_m[r["key"]], tol=0.0, min_area=0.0) for r in rows]
    geoms = list(shapely.coverage_simplify(np.array(geoms), 0.35))
    edges = shapely.union_all([g.boundary for g in geoms])
    coast = shapely.union_all([g.boundary for g in shapely.get_parts(shapely.union_all(geoms))])
    frontier_px = shapely.difference(edges, coast.buffer(0.25))
    frontier_px = shapely.line_merge(shapely.union_all([p for p in shapely.get_parts(frontier_px)
                                                        if p.geom_type == "LineString" and p.length > 0.6]))
    lk = geo.read_ne(cfg, "ne_10m_lakes", bbox_ll=A["bbox"])
    lk = lk[lk["scalerank"].fillna(99) <= 3]
    lakes = F.g(shapely.union_all(_to(proj, lk.geometry)), tol=0.4, min_area=1.5)
    rv = geo.read_ne(cfg, "ne_10m_rivers_lake_centerlines", bbox_ll=A["bbox"])
    rv = rv[rv["scalerank"].fillna(99) <= 6]
    rivers_px = F.g(shapely.intersection(shapely.union_all(_to(proj, rv.geometry)), africa_m), tol=0.5, lines=True)
    grat = graticule(A, F)
    sea, relief = ground_images(cfg, A, F, shapely.union(body_px, other))
    x0, y0, w, h = F.area
    ribbons = terrain.ribbons(cfg, "Africa atlas", F.area, list(zip(geoms, [r["colour"] for r in rows])), frontier_px)

    fills = "".join(f'<path d="{path_d(g)}" fill="{r["colour"]}"/>' for g, r in zip(geoms, rows) if not g.is_empty)
    ground = (
        f'<defs><clipPath id="atl-frame"><rect x="{x0}" y="{y0}" width="{w}" height="{h}"/></clipPath>'
        f'<path id="atl-body" d="{path_d(body_px)}"/><path id="atl-other" d="{path_d(other)}"/>'
        f'<path id="atl-frontiers" d="{path_d(frontier_px)}"/></defs>'
        f'<g clip-path="url(#atl-frame)" class="atl-ground">'
        f'<image x="{x0}" y="{y0}" width="{w}" height="{h}" preserveAspectRatio="none" href="{sea}"/>'
        f'<path d="{path_d(grat)}" fill="none" stroke="#8fa7b3" stroke-width=".6" stroke-opacity=".45"/>'
        f'<use href="#atl-other" fill="{INK["other"]}"/>'
        f'<use href="#atl-body" fill="{INK["base"]}"/>'
        f'<g fill-rule="evenodd">{fills}</g>'
        f'<image x="{x0}" y="{y0}" width="{w}" height="{h}" preserveAspectRatio="none" href="{ribbons}"/>'
        f'<image x="{x0}" y="{y0}" width="{w}" height="{h}" preserveAspectRatio="none" href="{relief}" '
        f'opacity=".55" style="mix-blend-mode:multiply"/>'
        f'<path d="{path_d(lakes)}" fill="#dcebf2" stroke="{INK["coast"]}" stroke-width=".4"/>'
        f'<path d="{path_d(rivers_px)}" fill="none" stroke="#6a9ac0" stroke-width=".6" stroke-linejoin="round" '
        f'stroke-linecap="round"/>'
        f'<use href="#atl-frontiers" fill="none" stroke="#fff" stroke-width="1.7" stroke-opacity=".7" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<use href="#atl-frontiers" fill="none" stroke="{INK["frontier"]}" stroke-width=".75" '
        f'stroke-dasharray="3.2 1.3 .9 1.3" stroke-linejoin="round"/>'
        f'<g fill="none" stroke="{INK["coast"]}" stroke-width=".7" stroke-linejoin="round">'
        f'<use href="#atl-other"/><use href="#atl-body"/></g>'
        f"</g>")

    # islands outside the swap, ringed
    rings, seen = "", []
    for lon, lat in spec.get("neutral", []):
        q = F.xy(pt(lon, lat)[None])[0]
        if any(np.hypot(*(q - s)) < 26 for s in seen):
            continue
        cluster = [F.xy(pt(a, b)[None])[0] for a, b in spec["neutral"]]
        near = np.array([c for c in cluster if np.hypot(*(c - q)) < 26])
        c = near.mean(axis=0)
        seen.append(q)
        if x0 + 6 < c[0] < x0 + w - 6 and y0 + 6 < c[1] < y0 + h - 6:
            rings += f'<circle cx="{c[0]:.1f}" cy="{c[1]:.1f}" r="6"/>'

    out = {}
    for page, text in texts.items():
        ed = "ar" if page.startswith("ar/") else "en"
        L = LABELS[ed]
        big_n, big_t, small, leads = [], [], [], []
        for r in rows:
            name = r["name_ar"] if ed == "ar" else r["name"]
            twin = r["twin_ar"] if ed == "ar" else r["twin"]
            cx, cy = F.xy(pt(r["label_lon"], r["label_lat"])[None])[0]
            if r["size"] == "big":
                big_n.append(f'<text x="{cx:.1f}" y="{cy - 1.5:.1f}">{html.escape(name)}</text>')
                if twin:
                    big_t.append(f'<text x="{cx:.1f}" y="{cy + 11.5:.1f}">{html.escape(twin)}</text>')
            else:
                small.append(f'<text x="{cx:.1f}" y="{cy + 3.5:.1f}">{html.escape(name)}</text>')
            if r["lead"]:
                sx, sy = F.xy(pt(r["seed_lon"], r["seed_lat"])[None])[0]
                half = _text_w(name, 10) / 2 + 3
                dx, dy = sx - cx, sy - cy
                if abs(dx) > abs(dy) * 1.2:
                    ax_, ay_ = cx + np.sign(dx) * half, cy
                else:
                    ax_, ay_ = cx, cy + np.sign(dy) * 8
                n = np.hypot(sx - ax_, sy - ay_)
                ex, ey = sx - (sx - ax_) / n * 2.5, sy - (sy - ay_) / n * 2.5
                leads.append(f'<path d="M{ax_:.1f} {ay_:.1f}L{ex:.1f} {ey:.1f}"/>')
        style = (f"font-family='{L['font']}' text-anchor=\"middle\" paint-order=\"stroke\" "
                 f"stroke=\"rgba(255,255,255,.75)\" stroke-linejoin=\"round\"")
        overlay = (
            f'<g fill="#8d8d8d" fill-opacity=".35" stroke="#2a2a2a" stroke-width=".9">{rings}</g>'
            f'<g stroke="#333" stroke-width=".9" fill="none" opacity=".6">{"".join(leads)}</g>'
            f'<g {style} font-size="13" fill="#141414" font-weight="700" stroke-width="2.4"{L["dir"]}>{"".join(big_n)}</g>'
            f'<g {style} font-size="9.6" fill="#2b2b2b" font-style="italic" font-weight="600" stroke-width="2.2"'
            f'{L["dir"]}>{"".join(big_t)}</g>'
            f'<g {style} font-size="10" fill="#141414" font-weight="700" stroke-width="2.4"{L["dir"]}>{"".join(small)}</g>')
        vb = A["maps"][0][0]
        a, b, old = _svg(text, vb)
        head = old[: old.index(">") + 1]
        out[page] = text[:a] + head + ground + overlay + "</svg>" + text[b:]
    return out


def install(cfg: dict, which=("africa", "europe")) -> list[str]:
    """Redraw each atlas map in both editions: Africa from its traced frontiers, Europe from the
    hand-drawn originals in data/atlas/ (saved from the pages the first time)."""
    store = paths(cfg).data / "atlas"
    store.mkdir(parents=True, exist_ok=True)
    changed = []
    for A in (AFRICA, EUROPE):
        if A["page"].split(".")[0] not in which:
            continue
        if A is AFRICA:
            from . import worldmaps
            print(f"  {A['page']}")
            ground = traced_ground(cfg, A, "africa")
            # the atlas itself, then every world map that colours Africa, on the same frontiers
            for pages, redraw in (((A["page"],), lambda t: draw_africa(cfg, A, t, ground)),
                                  (worldmaps.PAGES, lambda t: worldmaps.lay_africa(t, ground[0]))):
                texts = {}
                for page in pages:
                    for p in (page, "ar/" + page):
                        if (SITE / p).exists():
                            with open(SITE / p, encoding="utf8", newline="") as fh:
                                texts[p] = fh.read()
                for page, new in redraw(texts).items():
                    if new != texts[page]:
                        with open(SITE / page, "w", encoding="utf8", newline="") as fh:
                            fh.write(new)
                        changed.append(page)
            continue
        texts, sources = {}, {}
        for page in (A["page"], "ar/" + A["page"]):
            p = SITE / page
            if not p.exists():
                continue
            with open(p, encoding="utf8", newline="") as fh:
                texts[page] = fh.read()
            sources[page] = {}
            for n, (vb, clip) in enumerate(A["maps"]):
                stem = A["page"].split(".")[0] + ("" if n == 0 else f"-{n + 1}")
                f = store / (stem + (".ar.svg" if page.startswith("ar/") else ".svg"))
                if not f.exists():
                    svg = _svg(texts[page], vb)[2]
                    if f'id="{clip}"' not in svg:
                        raise SystemExit(f"{page}: the atlas is already redrawn and {f.name} is missing")
                    f.write_text(svg.replace("\r\n", "\n") + "\n", encoding="utf8", newline="\n")
                    print(f"    saved the hand-drawn map to {f.relative_to(SITE).as_posix()}")
                sources[page][vb] = f.read_text(encoding="utf8").strip()
        print(f"  {A['page']}")
        for page, new in draw(cfg, A, sources, texts).items():
            if new != texts[page]:
                with open(SITE / page, "w", encoding="utf8", newline="") as fh:
                    fh.write(new)
                changed.append(page)
    return changed
