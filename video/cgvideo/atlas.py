"""The reference atlases, redrawn on real coastlines with the video's kind of frontier.

The Africa and Europe atlases were drawn by hand: a schematic coast and straight-sided nations.
`python build.py atlas` keeps what they say (every nation, its colour, its label, its twin and
its leader line) and redraws what they show:

  1. Registration. The atlas's hand-drawn coast is matched to Natural Earth's real one: an
     affine start (Africa's four extreme capes; for Europe, whose coast is too crude for that,
     the labels that sit inside their nations, each paired with that nation's real interior),
     refined by a thin-plate spline fitted by iterated closest points on the coast. Anchors are
     held far tighter than the coast: the labels, the far ends of leader lines, and pins where
     the drawing is too rough for the coast alone (the capes of Iberia, the British Isles, the
     Gulf of Bothnia, southern Italy and Greece). That warp carries anything drawn on the atlas
     onto the real ground: its nations, its label points, its leader lines. A few names of
     ground rather than of nations (AFRICA, the Caucasus) are set where that ground really is.
  2. A mesh, built the way the video's is: a jittered grid of seeds, Voronoi edges roughened by
     midpoint displacement, the coast and the great rivers as extra edges, faces polygonised
     and small ones merged, finer where the nations are small. So no frontier is ruled, and a
     frontier that meets a river can follow it.
  3. Each cell goes to the nation whose warped shape covers most of it, in the atlas's own
     paint order, counting only what the atlas showed (a shape its coast clipped away is not a
     nation on the ground); a coastal sliver no nation covers goes to the nearest one, and
     islands far from any stay neutral ground. A nation never takes a landmass it only grazes
     where another is at home, and Europe's nations never take Africa, the Mashriq or Asia
     behind the Urals and the Caucasus. Land the atlas left bare next to a nation joins it,
     ring by ring; a nation the atlas cut off at its edge (Russia) grows on to the frame. A
     hatched shape (Sapmi) is laid over the cells it covers.
  4. The map is drawn afresh on an equal-area projection: the sea by its true depth with water
     lines, the relief (both from ETOPO 2022, projected and shaded by QGIS and finished in GIMP:
     see terrain.py), rivers and lakes, the nations with white frontiers, and the page's own
     labels on top, carried through the warp. A key band under the map stays where it is. Both editions
     get the same ground under their own words.

The hand-drawn originals are kept in data/atlas/: the build reads them, not the pages, so it
can run again, and they are the place to move a nation's frontier, a label or a leader line.
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
from shapely.geometry import MultiPoint

from . import geo, mesh
from .config import paths
from .sitemaps import SITE, _children, _poly_from_svg, path_d

NUM = r"-?\d+(?:\.\d+)?"

AFRICA = {
    "page": "africa.html", "maps": [("0 0 780 790", "af-al0")], "nations": "ids", "prefix": "af-n0-",
    "area": (0, 0, 780, 790),                   # the map on the canvas (no key band)
    "proj": "+proj=laea +lat_0=2 +lon_0=17 +datum=WGS84 +units=m +no_defs",
    "bbox": (-30, -42, 66, 44),                 # what the map may show, lon/lat
    "start": "capes", "centre": (17.0, 2.0), "islands": [(46.9, -18.9)],   # the continent, and Madagascar
    # Asia, cut off along Rafah to Aqaba (Sinai stays with Africa, as the atlas draws it), then
    # down the middle of the Red Sea and the Gulf of Aden and out past Madagascar
    "asia": [(34.25, 31.3), (34.25, 60), (100, 60), (100, -45), (60, -45), (56.5, 11.5), (51.5, 13.8),
             (43.4, 12.6), (38.6, 20.0), (35.0, 29.5)],
    "smooth": (3000.0, 900.0, 300.0, 120.0, 60.0),
    "spacing_km": 70, "min_cell_km2": 900, "noise": 0.22, "noise_depth": 4, "river_rank": 4,
    "margin": 16, "margin_x": 44,
    # finer cells where the nations are small: the Guinea coast, the Great Lakes, the far
    # south and the Horn (lon/lat boxes, km)
    "focus": [((-18, 3, 11, 16), 32), ((27.5, -5.5, 32, 0.5), 25), ((26, -31.5, 33.5, -24.5), 28),
              ((40.5, 10, 45, 13.5), 25)],
}

EUROPE = {
    "page": "europe.html", "maps": [("-14 -12 808 760", "eurland"), ("-14 -12 808 822", "eurland2")],
    "nations": "polygons",
    "area": (-14, -12, 808, 690),               # the map; the key band under it stays put
    "proj": "+proj=laea +lat_0=53 +lon_0=15 +datum=WGS84 +units=m +no_defs",
    "bbox": (-75, 18, 100, 84),
    "start": "labels",
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
    "neutral": ["#cdc6b6", "#cfcabb"],          # the shapes marking Africa and the Mashriq: not Europe
    # ground no European nation takes, cell by cell (so a frontier with it still follows the
    # mesh): the African continent; the Mashriq south of the Taurus; and Asia behind the Urals,
    # the Ural river, the Caspian and the Kuma-Manych depression, the Caucasus with it, as far
    # as the Turkish frontier and the Aras
    "not_europe": {"africa": True,
                   "mashriq": [(34.25, 31.3), (34.3, 32.0), (34.6, 33.0), (34.9, 34.0), (35.4, 35.3), (35.7, 35.9),
                               (35.9, 36.2), (36.6, 36.9), (38.5, 36.9), (40.5, 37.1), (42.4, 37.2), (44.3, 37.1),
                               (44.8, 38.4), (48.0, 39.5), (60.0, 39.5), (60.0, 20.0), (34.25, 20.0)],
                   "asia": [(64.5, 82.0), (64.5, 70.5), (66.2, 68.5), (63.5, 66.5), (59.5, 65.0), (59.3, 62.0),
                            (59.3, 59.0), (59.6, 57.0), (58.5, 54.5), (58.6, 51.2), (57.0, 51.2), (55.1, 51.8),
                            (53.0, 51.6), (51.4, 51.2), (51.6, 49.5), (51.9, 47.1), (50.0, 46.0), (47.2, 44.8),
                            (45.5, 45.2), (44.0, 45.8), (43.0, 46.3), (41.5, 46.6), (40.2, 46.9), (39.3, 47.1),
                            (38.0, 46.4), (36.65, 45.25), (37.5, 44.0), (40.0, 42.3), (41.55, 41.52),
                            (42.8, 41.58), (43.47, 41.12), (43.75, 40.74), (43.6, 40.1), (44.8, 39.7),
                            (44.3, 37.1), (60.0, 37.0), (100.0, 37.0), (100.0, 82.0)]},
    "grow_km": 320,                             # how far a nation may grow into land the atlas left bare
                                                # (one the atlas cut off at its edge grows to the frame)
    "spacing_km": 55, "min_cell_km2": 600, "noise": 0.22, "noise_depth": 4, "river_rank": 4,
    "margin": 14, "margin_x": 40,
    "focus": [((2.5, 44.5, 20, 52.5), 30), ((13, 40, 30, 47), 28), ((20, 53, 29, 60), 30)],
}


# -- reading the hand-drawn atlas -------------------------------------------------------------

def _svg(text: str, vb: str):
    m = re.search(r'<svg\b[^>]*viewBox="%s"[^>]*>.*?</svg>' % re.escape(vb), text, re.S)
    return m.start(), m.end(), m.group(0)


def old_nations(svg: str, A: dict) -> list[tuple[str, str, object]]:
    """(key, fill, shape in the atlas's pixels) of every nation, in paint order. A hatched fill
    (url(#...)) is kept as it is: it is laid over the others, not given cells of its own."""
    out = []
    if A["nations"] == "ids":
        for m in re.finditer(r'<path id="(%s[^"]+)" d="([^"]+)" fill="([^"]+)"' % re.escape(A["prefix"]), svg):
            out.append((m.group(1), m.group(3), _poly_from_svg(f'<path d="{m.group(2)}">')))
        return out
    import hashlib
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

def _extremes_px(poly) -> np.ndarray:
    """West, east, north and south points of the largest piece, on a page (y runs down)."""
    xy = np.asarray(max(shapely.get_parts(poly), key=lambda p: p.area).exterior.coords)
    return np.array([xy[xy[:, 0].argmin()], xy[xy[:, 0].argmax()], xy[xy[:, 1].argmin()], xy[xy[:, 1].argmax()]])


def _extremes_m(poly) -> np.ndarray:
    """West, east, north and south points in projected metres (y runs up)."""
    xy = np.asarray(max(shapely.get_parts(poly), key=lambda p: p.area).exterior.coords)
    return np.array([xy[xy[:, 0].argmin()], xy[xy[:, 0].argmax()], xy[xy[:, 1].argmax()], xy[xy[:, 1].argmin()]])


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


# -- the mesh ---------------------------------------------------------------------------------

def build_cells(A: dict, body, rivers):
    rng = np.random.default_rng(7)
    zones = [(body, A["spacing_km"] * 1000)]
    for (w, s, e, n), km in A.get("focus", []):
        box = _to(A["proj"], [shapely.box(w, s, e, n).segmentize(0.5)])[0]
        zones.append((shapely.intersection(box, body), km * 1000))
    chunks = []
    for i, (area, spacing) in enumerate(zones):
        later = [z for z, _ in zones[i + 1:]]
        own = shapely.difference(area, shapely.union_all(later)) if later else area   # finer zones win
        if own.is_empty:
            continue
        pts = mesh._hex_points(own.bounds, spacing, rng)
        chunks.append(pts[shapely.contains_xy(own, pts[:, 0], pts[:, 1])])
    pts = np.vstack(chunks)
    sp = A["spacing_km"] * 1000
    edges = shapely.voronoi_polygons(MultiPoint(pts), extend_to=body.buffer(sp * 3), only_edges=True)
    rough = [mesh.roughen(e, A["noise"], A["noise_depth"]) for e in shapely.get_parts(edges)]
    lines = rough + [body.boundary]
    if rivers is not None and not rivers.is_empty:
        lines.append(rivers)
    network = shapely.union_all(lines)
    faces = np.array(list(shapely.get_parts(shapely.polygonize(list(shapely.get_parts(network))))))
    rp = shapely.point_on_surface(faces)
    shapely.prepare(body)
    faces = faces[shapely.contains_xy(body, shapely.get_x(rp), shapely.get_y(rp))]
    return np.array(mesh.merge_small(list(faces), A["min_cell_km2"] * 1e6))


def homes(cells, body, nations):
    """Which nations may hold ground on each landmass: (the landmass of each cell, a
    landmass x nation table). A nation whose warped shape only grazes a landmass (under a
    tenth of it) where another nation is at home (over half of that one) is kept off it: a
    rough drawing that set Anglia's coast against Ireland's does not give Anglia Ulster."""
    lands = [p for p in shapely.get_parts(body)]
    tree = shapely.STRtree(lands)
    spot = shapely.point_on_surface(cells)
    land_of = np.array([int(h[0]) if len(h := tree.query(s, predicate="intersects")) else -1 for s in spot])
    frac = np.zeros((len(lands), len(nations)))
    for j, (_, _, g) in enumerate(nations):
        if g.is_empty or g.area == 0:
            continue
        for k in tree.query(g, predicate="intersects"):
            frac[k, j] = shapely.intersection(lands[k], g).area / g.area
    allowed = ~((frac < 0.1) & (frac.max(axis=1, keepdims=True) > 0.5))
    return land_of, allowed


def assign(cells, nations, reach_m: float, exclude=None, home=None):
    """Each cell to the nation covering most of it; else the nearest within reach; else none.
    A nation too small to win any cell keeps the one under its own centre. `exclude` marks
    cells no nation may take; `home` (from homes()) which nations each landmass admits."""
    tree = shapely.STRtree([g for _, _, g in nations])
    owner = np.full(len(cells), -1)
    if exclude is None:
        exclude = np.zeros(len(cells), bool)

    def ok(i, j):
        if home is None:
            return True
        land_of, allowed = home
        return land_of[i] < 0 or allowed[land_of[i], j]

    for i, c in enumerate(cells):
        if exclude[i]:
            continue
        best, share = -1, 0.0
        for j in tree.query(c, predicate="intersects"):
            if not ok(i, j):
                continue
            a = shapely.intersection(c, nations[j][2]).area
            if a > share:
                best, share = j, a
        if best >= 0 and share >= 0.3 * c.area:
            owner[i] = best
    for i in np.where((owner == -1) & ~exclude)[0]:
        near = [j for j in tree.query(cells[i], predicate="dwithin", distance=reach_m) if ok(i, j)]
        if near:
            owner[i] = min(near, key=lambda j: shapely.distance(cells[i], nations[j][2]))
    ctree = shapely.STRtree(list(cells))
    for j, (key, _, g) in enumerate(nations):
        if (owner == j).any() or g.is_empty:
            continue
        spot = shapely.point_on_surface(g)
        hit = ctree.query(spot, predicate="intersects")
        c = int(hit[0]) if len(hit) else int(ctree.nearest(spot))
        owner[c] = j
        print(f"    {key} was too small for any cell: it keeps the one at its centre")
    return owner


def grow(cells, owner, nations, neutral, reach_m: float, rounds: int = 40, exclude=None, unbounded=()):
    """Land the atlas left bare, next to a nation and within reach of its drawn shape, joins it,
    a ring of cells at a time, the way the video's regions grow; land marked neutral stays so,
    and islands no nation touches stay bare. A nation in `unbounded` (cut off by the atlas's
    edge) grows as far as the ground goes."""
    tree = shapely.STRtree(list(cells))
    left, right = tree.query(list(cells), predicate="touches")
    nbrs = [[] for _ in cells]
    for a, b in zip(left, right):
        nbrs[a].append(b)
    blocked = np.zeros(len(cells), bool) if exclude is None else exclude.copy()
    for g in neutral:
        for i in tree.query(g, predicate="intersects"):
            if shapely.intersection(cells[i], g).area >= 0.5 * cells[i].area:
                blocked[i] = True
    owner = owner.copy()
    owner[blocked & (owner == -1)] = -2
    for _ in range(rounds):
        changes = {}
        for i in np.where(owner == -1)[0]:
            cand = {}
            for j in nbrs[i]:
                o = owner[j]
                if o >= 0:
                    cand[o] = cand.get(o, 0.0) + shapely.intersection(cells[i].boundary, cells[j].boundary).length
            for o, _ in sorted(cand.items(), key=lambda t: -t[1]):
                if o in unbounded or shapely.distance(cells[i], nations[o][2]) <= reach_m:
                    changes[i] = o
                    break
        if not changes:
            break
        for i, o in changes.items():
            owner[i] = o
    owner[owner == -2] = -1
    return owner


def paint_order(nations):
    """What shows is what counts: each nation loses whatever a later one covers."""
    out = []
    for i, (key, fill, g) in enumerate(nations):
        over = [h for _, _, h in nations[i + 1:] if h.intersects(g)]
        out.append((key, fill, shapely.make_valid(shapely.difference(g, shapely.union_all(over))) if over else g))
    return out


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
        if k < 2 or (k == 2 and A["nations"] == "polygons"):
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
    if A["start"] == "capes":
        body_ll = africa_body(A, land_ll)
        body = _to(A["proj"], [body_ll])[0]
        start_src, start_dst = _extremes_px(coast0), _extremes_m(body)
        anchors = None
        old_pts = _sample_lines(coast0.boundary, 3.0)
        real_pts = _sample_lines(body.boundary, 8000.0)
    else:
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
        body = None
    warp = Warp(old_pts, real_pts if body is not None else None, start_src, start_dst, anchors, A["smooth"]) \
        if body is not None else None
    if body is None:
        # Europe: the ground is whatever land the old map area covers, once carried over
        x0, y0, w, h = A["area"]
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
    """sources: page -> viewBox -> the hand-drawn map; texts: page -> page text. Returns the
    new page texts."""
    first_vb, first_clip = A["maps"][0]
    src_en = sources[A["page"]][first_vb]
    land_ll = real_land_ll(cfg, A)
    print("    registering the atlas to Natural Earth's coast")
    warp, body = register(cfg, A, src_en, first_vb, first_clip, land_ll)
    print(f"    median distance of the warped coast to the real one: {warp.error_km:.0f} km"
          + (f"; of the label anchors to their nations: {warp.anchor_km:.0f} km" if warp.anchor_km else ""))
    land = shapely.make_valid(_to(A["proj"], [land_ll])[0])
    geo_en, _ = overlays(src_en, A)
    marks = _marks(geo_en)
    place_px = {(float(m.group(1)), float(m.group(2)))
                for m in re.finditer(r'<text x="(%s)" y="(%s)"[^>]*>([^<]+)</text>' % (NUM, NUM), src_en)
                if _name(m.group(3)) in A.get("place", {})}
    marks = np.array([p for p in marks if tuple(p) not in place_px]).reshape(-1, 2)
    moved = warp(marks) if len(marks) else None
    if A["start"] == "capes":
        F = Frame(A, body.bounds, moved)
    else:
        # the map shows the drawn coast and everything drawn on it, carried over; its ground
        # runs past the frame so no cut is ever in view
        x0, y0, w, h = A["area"]
        inner = shapely.box(x0 + 3, y0 + 3, x0 + w - 3, y0 + h - 3)
        q = warp(_sample_lines(shapely.intersection(old_coast(src_en, first_clip).boundary, inner), 3.0))
        F = Frame(A, (q[:, 0].min(), q[:, 1].min(), q[:, 0].max(), q[:, 1].max()), moved)
        body = shapely.make_valid(shapely.intersection(land, F.ground_box_m().buffer(120_000)))
    rv = geo.read_ne(cfg, "ne_10m_rivers_lake_centerlines", bbox_ll=A["bbox"])
    rv = rv[rv["scalerank"].fillna(99) <= A["river_rank"]]
    rivers = shapely.intersection(shapely.union_all(_to(A["proj"], rv.geometry)), body)
    print("    building the mesh")
    cells = build_cells(A, body, rivers)
    exclude = None
    ne = A.get("not_europe")
    if ne:
        masks = []
        if ne.get("africa"):
            continent = shapely.difference(land_ll, shapely.Polygon(AFRICA["asia"]))
            sahara = shapely.Point(5, 30)
            masks.append(_to(A["proj"], [next(p for p in shapely.get_parts(continent) if p.contains(sahara))])[0])
        for part in ("mashriq", "asia"):
            if ne.get(part):
                masks.append(_to(A["proj"], [shapely.Polygon(ne[part]).segmentize(0.5)])[0])
        mask = shapely.union_all([shapely.make_valid(m) for m in masks])
        shapely.prepare(mask)
        c = shapely.point_on_surface(cells)
        exclude = shapely.contains_xy(mask, shapely.get_x(c), shapely.get_y(c))
    body_px = F.g(body, tol=0.3)
    other = F.g(shapely.difference(land, body.buffer(1)), tol=0.4, min_area=1.0)
    lk = geo.read_ne(cfg, "ne_10m_lakes", bbox_ll=A["bbox"])
    lk = lk[lk["scalerank"].fillna(99) <= 3]
    lakes = F.g(shapely.union_all(_to(A["proj"], lk.geometry)), tol=0.4, min_area=1.5)
    rivers_px = F.g(rivers, tol=0.5, lines=True)
    grat = graticule(A, F)
    sea, relief = ground_images(cfg, A, F, shapely.union(body_px, other))
    x0, y0, w, h = F.area
    grounds = {}
    neutral_keys = {key for key, fill, _ in old_nations(src_en, A) if fill in A.get("neutral", [])}
    outlines, defined = {}, {}                     # nation shape -> its path id, shared by the maps
    for n, (vb, clip) in enumerate(A["maps"]):
        src = sources[A["page"]][vb]
        # only what the atlas showed: a shape its coast clipped away (the Caucasus, drawn under
        # a sea) is not a nation on the ground
        shown = shapely.make_valid(old_coast(src, clip))
        drawn = []
        for key, fill, g in old_nations(src, A):
            seen = shapely.intersection(shapely.make_valid(g), shown)
            if seen.area >= 0.1 * g.area:
                drawn.append((key, fill, warp.geom(seen)))
        hatch = [(key, fill, g) for key, fill, g in drawn if fill.startswith("url(")]
        neutral = [g for key, fill, g in drawn if key in neutral_keys]
        nations = paint_order([t for t in drawn if not t[1].startswith("url(") and t[0] not in neutral_keys])
        owner = assign(cells, nations, reach_m=A["spacing_km"] * 1000 * 2.5, exclude=exclude,
                       home=homes(cells, body, nations))
        if A.get("grow_km"):
            ax0, ay0, aw, ah = A["area"]
            inside = shapely.box(ax0 + 2, ay0 + 2, ax0 + aw - 2, ay0 + ah - 2)
            at_edge = {key for key, _, g in old_nations(src, A) if not inside.contains(g)}
            unbounded = {j for j, (key, _, _) in enumerate(nations) if key in at_edge}
            print(f"    cut off by the atlas's edge: {', '.join(nations[j][0] for j in sorted(unbounded)) or 'none'}")
            owner = grow(cells, owner, nations, neutral, A["grow_km"] * 1000, exclude=exclude, unbounded=unbounded)
        print(f"    map {n + 1}: {len(cells)} cells, {int((owner >= 0).sum())} given to "
              f"{len(set(owner[owner >= 0]))} of {len(nations)} shapes")
        shapes = {}
        for j, (key, fill, _) in enumerate(nations):
            idx = np.flatnonzero(owner == j)
            if len(idx):
                shapes[key] = (fill, tuple(idx))
        new = [k for k in shapes if (k, shapes[k][1]) not in outlines]
        if new:
            geoms = [F.g(shapely.coverage_union_all(cells[list(shapes[k][1])]), tol=0.0, min_area=0.0) for k in new]
            for k, g in zip(new, shapely.coverage_simplify(np.array(geoms), 0.5)):
                pid = f"atl-{k}" if n == 0 else f"atl{n + 1}-{k}"
                outlines[(k, shapes[k][1])] = pid
                defined[pid] = path_d(g)
        ids_here = {k: outlines[(k, shapes[k][1])] for k in shapes}
        new_defs = "".join(f'<path id="{pid}" d="{defined[pid]}"/>' for k, pid in ids_here.items()
                           if pid.startswith(f"atl-" if n == 0 else f"atl{n + 1}-") and defined[pid])
        fills = "".join(f'<use href="#{ids_here[k]}" fill="{shapes[k][0]}"/>' for k in shapes if defined[ids_here[k]])
        hatches = ""
        for key, fill, g in hatch:
            covered = [c for c in cells if shapely.intersection(c, g).area >= 0.5 * c.area]
            if covered:
                hatches += (f'<path fill="{fill}" stroke="#3f7d6e" stroke-width=".6" stroke-opacity=".6" '
                            f'd="{path_d(F.g(shapely.coverage_union_all(covered), tol=0.5))}"/>')
        tag = "atl" if n == 0 else f"atl{n + 1}"
        grounds[vb] = (
            f'<defs><clipPath id="{tag}-frame"><rect x="{x0}" y="{y0}" width="{w}" height="{h}"/></clipPath>'
            + (f'<path id="atl-body" d="{path_d(body_px)}"/><path id="atl-other" d="{path_d(other)}"/>'
               f'<image id="atl-sea" x="{x0}" y="{y0}" width="{w}" height="{h}" preserveAspectRatio="none" href="{sea}"/>'
               f'<image id="atl-relief" x="{x0}" y="{y0}" width="{w}" height="{h}" preserveAspectRatio="none" '
               f'href="{relief}"/>'
               f'<path id="atl-grat" d="{path_d(grat)}"/><path id="atl-lakes" d="{path_d(lakes)}"/>'
               f'<path id="atl-rivers" d="{path_d(rivers_px)}"/>' if n == 0 else "")
            + new_defs + "</defs>"
            f'<g clip-path="url(#{tag}-frame)" class="atl-ground">'
            f'<use href="#atl-sea"/>'
            f'<use href="#atl-grat" fill="none" stroke="#8fa7b3" stroke-width=".6" stroke-opacity=".45"/>'
            f'<use href="#atl-other" fill="#d9d4ca"/>'
            f'<use href="#atl-body" fill="#e4ded2"/>'
            f'<g fill-rule="evenodd" stroke="#fff" stroke-width=".9" stroke-linejoin="round">{fills}</g>'
            f'{hatches}'
            f'<use href="#atl-relief" opacity=".55" style="mix-blend-mode:multiply"/>'
            f'<use href="#atl-lakes" fill="#dcebf2" stroke="#4a5a61" stroke-width=".4"/>'
            f'<use href="#atl-rivers" fill="none" stroke="#6a9ac0" stroke-width=".7" stroke-linejoin="round" '
            f'stroke-linecap="round"/>'
            f'<g fill="none" stroke="#4a5a61" stroke-width=".7" stroke-linejoin="round">'
            f'<use href="#atl-other"/><use href="#atl-body"/></g>'
            f"</g>")

    placed = {}                                    # a label set where its ground is (both editions)
    for drawn_map in sources[A["page"]].values():
        for m in re.finditer(r'<text x="(%s)" y="(%s)"[^>]*>([^<]+)</text>' % (NUM, NUM), drawn_map):
            ll = A.get("place", {}).get(_name(m.group(3)))
            if ll:
                q = F.xy(np.array([(p.x, p.y) for p in _to(A["proj"], [shapely.Point(ll)])]))[0]
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
            keep = _keep_defs(src) if A["nations"] == "polygons" else ""
            body_svg = keep + grounds[vb] + "".join(carry(p, move) for p in geo_part) + "".join(band)
            new = new[:a] + head + body_svg + "</svg>" + new[b:]
        out[page] = new
    return out


def install(cfg: dict, which=("africa", "europe")) -> list[str]:
    """Redraw each atlas map in both editions, from the hand-drawn originals in data/atlas/
    (saved from the pages the first time)."""
    store = paths(cfg).data / "atlas"
    store.mkdir(parents=True, exist_ok=True)
    changed = []
    for A in (AFRICA, EUROPE):
        if A["page"].split(".")[0] not in which:
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
