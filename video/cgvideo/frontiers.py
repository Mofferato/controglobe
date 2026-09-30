"""The Africa atlas's frontiers, traced on the ground rather than drawn on a mesh.

Every frontier in data/atlas/africa-frontiers.yaml is a chain of legs, each tied to something
on the ground, in the way Europe's own frontiers are tied to the Rhine, the Pyrenean crest or
the Danube:

  river    follows a named river of Natural Earth from where the frontier is to a point on it
           (the shortest way along the river network, so a leg may pass from one named river
           into the next: the Ubangi into the Congo)
  divide   follows the rim of a river basin (the Congo's, the Niger's...) from where the
           frontier is to a point on it: a watershed, as the Alpine and Carpathian frontiers
           are. The basins are computed from ETOPO 2022 by GRASS r.watershed in QGIS (see
           integrations/qgis/cg_frontiers.py) and are smoothed of their grid's staircase
  via      a smooth curve through points set by hand along an escarpment, a crest, the edge of
           a dune sea or a lake's middle line

Frontiers start and end at named nodes (the points where three nations meet, which several
frontiers share exactly) or at a point out to sea. `trace` returns the lines; `nations` cuts
the land with them and hands each piece to the nation whose seed lies in it. Everything here is
plain shapely and numpy, so it runs the same inside QGIS and in the build.
"""

from __future__ import annotations

import csv
import heapq
import json
import math
import pathlib

import numpy as np
import shapely
import shapely.ops
from shapely.geometry import LineString, Point

# what the Africa atlas may show (lon/lat), and Asia cut off along Rafah to Aqaba (Sinai stays
# with Africa), then down the middle of the Red Sea and the Gulf of Aden and out past Madagascar
BBOX = (-30, -42, 66, 44)
ASIA = [(34.25, 31.3), (34.25, 60), (100, 60), (100, -45), (60, -45), (56.5, 11.5), (51.5, 13.8),
        (43.4, 12.6), (38.6, 20.0), (35.0, 29.5)]


def africa_land(land_ll):
    """Africa and its islands (lon/lat), without Asia, Europe's islands or Iberia."""
    land = shapely.difference(shapely.intersection(land_ll, shapely.box(*BBOX)), shapely.Polygon(ASIA))
    keep = []
    for p in shapely.get_parts(land):
        c = p.representative_point()
        if c.y > 36.0 or (c.y > 34.8 and c.x > 11.5):
            continue
        keep.append(p)
    return shapely.union_all(keep)


# Europe's atlas reaches from Iceland to the Urals and down to the Mediterranean; the land it cuts
# is Eurasia and its islands, without Africa (Sinai and all), which that map shows as neutral ground
EUROPE_BBOX = (-32, 30, 72, 82)


def europe_land(land_ll):
    """Eurasia and its islands within the Europe atlas's reach (lon/lat), without Africa."""
    land = shapely.intersection(land_ll, shapely.box(*EUROPE_BBOX))
    africa = shapely.Polygon([(-20, 38.0), (-5.8, 36.3), (-5.2, 35.7), (11.4, 37.6), (12.6, 35.2),
                              (32.3, 31.0), (34.25, 31.3), (35.0, 29.5), (43.4, 12.6), (-20, 10)])
    keep = [p for p in shapely.get_parts(land) if not africa.contains(p.representative_point())]
    return shapely.union_all(keep)


# North America's map reaches from Vancouver Island to Yucatan and from the Pacific to Puerto Rico;
# the land it cuts is the whole continent and the Antilles within that reach
NORTH_AMERICA_BBOX = (-140, 7, -52, 62)


# the Greater Antilles west of Puerto Rico and the Bahamas carry the Caucasus: neutral ground here
ANTILLES = [(-85.5, 21.6), (-82.0, 23.7), (-80.2, 23.9), (-79.6, 24.5), (-79.6, 27.6), (-76.5, 27.6),
            (-70.5, 22.5), (-68.0, 19.2), (-68.0, 17.5), (-72.0, 17.0), (-79.0, 17.0), (-85.5, 18.5)]


def north_america_land(land_ll):
    """North America, Puerto Rico and the coastal islands within the map's reach (lon/lat)."""
    land = shapely.intersection(land_ll, shapely.box(*NORTH_AMERICA_BBOX))
    antilles = shapely.Polygon(ANTILLES)
    keep = [p for p in shapely.get_parts(land) if not antilles.contains(p.representative_point())]
    return shapely.union_all(keep)


REGIONS = {
    "north-america": {"land": north_america_land, "grass": "-128,-64,14,54", "work": "north-america",
                      # a third value is the window (in cells) in which the outlet is moved onto the
                      # strongest flow; 0 takes the cell itself, where two streams run side by side
                      "outlets": {"mississippi": (-91.225, 30.075, 0), "arkansas": (-94.525, 35.325, 0),
                                  "kansas": (-94.975, 38.975, 0), "red": (-93.875, 33.625, 0),
                                  "canadian": (-100.425, 35.925, 0), "rio_grande": (-97.425, 26.375, 0),
                                  "pecos": (-101.525, 29.825, 0), "conchos": (-104.525, 29.625, 0),
                                  "colorado": (-114.825, 32.525, 0), "columbia": (-123.375, 46.175, 0),
                                  "upper_missouri": (-100.4, 44.4, 2), "trinity": (-94.75, 29.9, 2),
                                  "nueces": (-97.775, 27.925, 0), "yaqui": (-110.175, 27.275, 0)}},
    # the marches of Solms-America: the same ground, cut out of the nation the continent's frontiers leave
    "solms-america": {"of": ("north-america", "solms")},
    "africa": {"land": africa_land, "grass": "-20,55,-36,38", "work": "",
               "outlets": {"congo": (13.1, -5.85), "niger": (6.75, 6.1), "volta": (0.1, 6.2),
                           "senegal": (-15.8, 16.45), "gambia": (-14.6, 13.4), "zambezi": (35.4, -17.8),
                           "nile": (32.9, 24.2), "kwanza": (13.9, -9.35), "ogooue": (10.2, -0.7),
                           "limpopo": (33.2, -24.6), "orange": (17.2, -28.6), "chad": (14.3, 13.0)}},
    "europe": {"land": europe_land, "grass": "-25,62,34,72", "work": "europe",
               "outlets": {"rhine": (6.1, 51.85), "danube": (28.7, 45.25), "elbe": (9.95, 53.55),
                           "oder": (14.55, 53.35), "vistula": (18.85, 54.2), "neman": (21.6, 55.3),
                           "daugava": (24.15, 56.95), "dnieper": (32.6, 46.7), "dniester": (30.1, 46.45),
                           "don": (39.6, 47.2), "po": (12.1, 44.95),
                           "rhone": (4.6, 43.7), "loire": (-1.8, 47.2),
                           "garonne": (-0.6, 44.9), "ebro": (0.6, 40.75), "douro": (-8.55, 41.15),
                           "tagus": (-9.05, 38.75), "guadiana": (-7.4, 37.3), "maritsa": (26.1, 40.85),
                           "vardar": (22.6, 40.6), "weser": (8.55, 53.2),
                           "scheldt": (4.3, 51.3), "sava": (19.7, 44.75, 2), "drava": (18.7, 45.57, 2),
                           "tisza": (20.12, 45.62, 2), "morava": (21.33, 44.1, 2), "prut": (28.18, 45.95, 2),
                           "bug": (21.86, 52.68, 2), "pripyat": (29.25, 52.05, 2), "northern_dvina": (40.6, 64.5),
                           "torne": (24.15, 65.85), "kemi": (24.55, 65.8), "neva": (30.4, 59.9),
                           "narva": (28.0, 59.35), "kuban": (37.8, 45.3), "glomma": (10.95, 59.2),
                           "gota": (11.9, 57.7), "dalalven": (17.4, 60.6), "adour": (-1.45, 43.5),
                           "neretva": (17.6, 43.05), "drin": (19.6, 41.95), "struma": (23.6, 40.8)}},
}


# -- the data files -------------------------------------------------------------------------------

def read_nations(path) -> list[dict]:
    with open(path, encoding="utf8") as fh:
        rows = [r for r in csv.DictReader(line for line in fh if not line.startswith("#"))]
    for r in rows:
        for k in ("seed_lon", "seed_lat", "label_lon", "label_lat"):
            if k in r:
                r[k] = float(r[k])
        r["lead"] = r.get("lead") == "1"
    return rows


def write_geojson(path, traced: list[dict], ndigits: int = 4, tol: float = 0.004, name: str = "africa-frontiers") -> None:
    feats = []
    for t in traced:
        line = shapely.simplify(t["line"], tol)
        xy = [[round(x, ndigits), round(y, ndigits)] for x, y in line.coords]
        feats.append({"type": "Feature", "properties": {"id": t["id"], "nations": " | ".join(t["nations"]),
                                                        "follows": t["follows"]},
                      "geometry": {"type": "LineString", "coordinates": xy}})
    doc = {"type": "FeatureCollection", "name": name,
           "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}}, "features": feats}
    text = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
    # one feature to a line, so a change to one frontier is one line of a diff
    text = text.replace(',{"type":"Feature"', ',\n{"type":"Feature"').replace('"features":[{', '"features":[\n{')
    pathlib.Path(path).write_text(text + "\n", encoding="utf8", newline="\n")


def read_geojson(path) -> list[LineString]:
    doc = json.loads(pathlib.Path(path).read_text(encoding="utf8"))
    return [LineString(f["geometry"]["coordinates"]) for f in doc["features"]]


# -- smoothing ----------------------------------------------------------------------------------

def catmull_rom(pts, per_seg: int = 12) -> np.ndarray:
    """A curve through every point (centripetal Catmull-Rom), ends included."""
    p = np.asarray(pts, float)
    if len(p) < 3:
        return p
    ext = np.vstack([2 * p[0] - p[1], p, 2 * p[-1] - p[-2]])
    out = [p[0]]
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        t0 = 0.0
        t1 = t0 + max(np.linalg.norm(p1 - p0) ** 0.5, 1e-9)
        t2 = t1 + max(np.linalg.norm(p2 - p1) ** 0.5, 1e-9)
        t3 = t2 + max(np.linalg.norm(p3 - p2) ** 0.5, 1e-9)
        for t in np.linspace(t1, t2, per_seg + 1)[1:]:
            a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
            a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
            a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
            b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
            b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
            out.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
    return np.array(out)


def chaikin(xy: np.ndarray, rounds: int = 3) -> np.ndarray:
    """Corner-cutting that keeps both ends where they are."""
    p = np.asarray(xy, float)
    for _ in range(rounds):
        if len(p) < 3:
            return p
        q = 0.75 * p[:-1] + 0.25 * p[1:]
        r = 0.25 * p[:-1] + 0.75 * p[1:]
        mid = np.empty((2 * (len(p) - 1), 2))
        mid[0::2], mid[1::2] = q, r
        p = np.vstack([p[0], mid[1:-1], p[-1]])
    return p


# -- the ground ---------------------------------------------------------------------------------

class Ground:
    """What legs can follow: rivers by name (lines, lon/lat) and basins by name (polygons)."""

    def __init__(self, rivers: dict[str, object], basins: dict[str, object]):
        self.rivers = rivers
        self.basins = basins
        self._rims = {}

    def river(self, names: list[str]):
        parts = [self.rivers[n] for n in names if n in self.rivers]
        if not parts:
            raise KeyError(f"no river named {names}")
        return shapely.union_all(parts)

    def rim(self, name: str) -> LineString:
        """A basin's outer rim, freed of the grid's staircase."""
        if name not in self._rims:
            poly = self.basins[name]
            poly = max(shapely.get_parts(poly), key=lambda g: g.area)
            p = np.asarray(shapely.simplify(poly.exterior, 0.04).coords)[:-1]
            for _ in range(3):                      # Chaikin's corner-cutting, all the way round
                nxt = np.roll(p, -1, axis=0)
                q = np.empty((2 * len(p), 2))
                q[0::2], q[1::2] = 0.75 * p + 0.25 * nxt, 0.25 * p + 0.75 * nxt
                p = q
            self._rims[name] = LineString(np.vstack([p, p[:1]]))
        return self._rims[name]


def _graph_path(lines, a, b, tol=0.02) -> np.ndarray:
    """Shortest way from a to b over a network of lines (lon/lat), vertices merged within tol."""
    key = lambda x, y: (round(x / tol), round(y / tol))
    nodes, adj = {}, {}

    def nid(x, y):
        k = key(x, y)
        if k not in nodes:
            nodes[k] = (len(nodes), (x, y))
            adj[nodes[k][0]] = []
        return nodes[k][0]

    coords, ends, owner = {}, [], {}
    for k, ln in enumerate(shapely.get_parts(lines)):
        xy = np.asarray(ln.coords)
        ids = [nid(*p) for p in xy]
        for i in ids:
            owner.setdefault(i, k)
        ends.append((ids[0], k))
        ends.append((ids[-1], k))
        for (i, j), p, q in zip(zip(ids[:-1], ids[1:]), xy[:-1], xy[1:]):
            if i == j:
                continue
            d = float(np.hypot(*(q - p)))
            adj[i].append((j, d))
            adj[j].append((i, d))
    for (i, xy) in nodes.values():
        coords[i] = xy
    pts = np.array([coords[i] for i in range(len(coords))])
    # a tributary drawn to within a few km of its main stream joins it there
    for i, k in ends:
        d = np.hypot(*(pts - pts[i]).T)
        d[[j for j in range(len(pts)) if owner.get(j) == k]] = np.inf
        j = int(np.argmin(d))
        if d[j] <= 0.08:
            adj[i].append((j, float(d[j])))
            adj[j].append((i, float(d[j])))
    s = int(np.argmin(np.hypot(*(pts - a).T)))
    t = int(np.argmin(np.hypot(*(pts - b).T)))
    dist, prev, heap = {s: 0.0}, {}, [(0.0, s)]
    while heap:
        d, u = heapq.heappop(heap)
        if u == t:
            break
        if d > dist.get(u, math.inf):
            continue
        for v, w in adj[u]:
            nd = d + w
            if nd < dist.get(v, math.inf):
                dist[v], prev[v] = nd, u
                heapq.heappush(heap, (nd, v))
    if t not in dist:
        raise ValueError(f"no way along the river from {tuple(a)} to {tuple(b)}")
    path = [t]
    while path[-1] != s:
        path.append(prev[path[-1]])
    return pts[path[::-1]]


def _along(line: LineString, a, b) -> np.ndarray:
    """The part of a line (or closed rim) between the points nearest a and b; on a closed rim,
    the shorter way round."""
    da, db = line.project(Point(a)), line.project(Point(b))
    closed = line.is_ring or np.allclose(line.coords[0], line.coords[-1])
    if not closed:
        seg = shapely.ops.substring(line, min(da, db), max(da, db))
        xy = np.asarray(seg.coords)
        return xy if da <= db else xy[::-1]
    L = line.length
    fwd = (db - da) % L
    if fwd <= L / 2:
        if da <= db:
            xy = np.asarray(shapely.ops.substring(line, da, db).coords)
        else:
            xy = np.vstack([np.asarray(shapely.ops.substring(line, da, L).coords),
                            np.asarray(shapely.ops.substring(line, 0, db).coords)[1:]])
        return xy
    return _along(line, b, a)[::-1]


# -- tracing ------------------------------------------------------------------------------------

def _pt(spec_nodes, v):
    if isinstance(v, str):
        return np.array(spec_nodes[v], float)
    return np.array(v, float)


def resolve_nodes(spec: dict, ground: Ground) -> dict[str, tuple]:
    """Nodes put exactly on the river or rim they are said to lie on."""
    out = {}
    for name, n in spec["nodes"].items():
        if isinstance(n, dict):
            p = Point(n["at"])
            if "river" in n:
                g = ground.river(n["river"] if isinstance(n["river"], list) else [n["river"]])
            else:
                g = ground.rim(n["divide"])
            q = shapely.ops.nearest_points(g, p)[0]
            out[name] = (q.x, q.y)
        else:
            out[name] = tuple(n)
    return out


def trace(spec: dict, ground: Ground) -> list[dict]:
    """Every frontier as {id, nations, follows, line (lon/lat LineString)}."""
    nodes = resolve_nodes(spec, ground)
    out = []
    for f in spec["frontiers"]:
        cur = _pt(nodes, f["from"])
        xy = [cur]
        for leg in f["legs"]:
            if "via" in leg:
                pts = [cur] + [_pt(nodes, p) for p in leg["via"]]
                curve = catmull_rom(pts, leg.get("detail", 10))
                xy.extend(curve[1:])
                cur = pts[-1]
                continue
            end = _pt(nodes, leg["to"])
            if "river" in leg:
                names = leg["river"] if isinstance(leg["river"], list) else [leg["river"]]
                path = _graph_path(ground.river(names), cur, end)
            else:
                path = _along(ground.rim(leg["divide"]), cur, end)
            # the frontier joins the feature where it meets it, and leaves it at the node
            xy.extend(path)
            xy.append(end)
            cur = end
        line = LineString(_dedupe(np.array(xy)))
        out.append({"id": f["id"], "nations": f["nations"], "follows": f.get("follows", ""), "line": line})
    return out


def _dedupe(xy: np.ndarray) -> np.ndarray:
    keep = np.r_[True, np.hypot(*np.diff(xy, axis=0).T) > 1e-7]
    return xy[keep]


# -- nations ------------------------------------------------------------------------------------

def _joined(lines: list[LineString], land=None, reach: float = 0.05, snap: bool = False) -> list[LineString]:
    """A frontier that stops a hair short of the one it meets (simplified, or edited by hand in
    QGIS) is carried on to it; one that stops short of the sea, on a coast finer than the one it
    was drawn against, is carried on in its own direction until it is off the land. With `snap`
    (the marches of one nation, whose land ends at that nation's own frontiers) an end just inside
    the land's edge is carried straight to it."""
    out = []
    for i, ln in enumerate(lines):
        xy = [tuple(c) for c in ln.coords]
        others = shapely.union_all([g for j, g in enumerate(lines) if j != i])
        for end in (0, -1):
            p = Point(xy[end])
            d = others.distance(p)
            if snap and land is not None and land.contains(p) and land.boundary.distance(p) <= reach:
                q = shapely.ops.nearest_points(land.boundary, p)[0]
                dx, dy = q.x - p.x, q.y - p.y
                n = math.hypot(dx, dy) or 1e-12
                q2 = (q.x + dx / n * 1e-4, q.y + dy / n * 1e-4)
                if end == 0:
                    xy.insert(0, q2)
                else:
                    xy.append(q2)
                continue
            if d > reach and land is not None and land.contains(p) and len(xy) > 1:
                a, b = np.array(xy[end + (1 if end == 0 else -1)]), np.array(xy[end])
                step = (b - a) / max(np.hypot(*(b - a)), 1e-9) * 0.01
                q = b.copy()
                for _ in range(150):
                    q = q + step
                    if not land.contains(Point(q)):
                        q = q + step * 3
                        break
                if end == 0:
                    xy.insert(0, tuple(q))
                else:
                    xy.append(tuple(q))
                continue
            if 0 < d <= reach:
                q = shapely.ops.nearest_points(others, p)[0]
                # overshoot a little so the two lines cross rather than merely touch
                dx, dy = q.x - p.x, q.y - p.y
                n = math.hypot(dx, dy) or 1e-12
                q2 = (q.x + dx / n * 1e-6, q.y + dy / n * 1e-6)
                if end == 0:
                    xy.insert(0, q2)
                else:
                    xy.append(q2)
        out.append(LineString(xy))
    return out


def nations(lines: list[LineString], land, seeds: dict[str, list[tuple]], neutral=(), island_reach: float = 1.5,
            snap: bool = False):
    """Cut the land (lon/lat) with the frontiers and give each piece to the nation whose seed is
    in it. A piece with no seed on the mainland (a sliver) joins the neighbour it shares most
    frontier with; an island with none goes to the nearest nation within reach (degrees), or
    stays neutral, as does any island with a `neutral` point on it (the islands outside the
    swap). Returns ({nation: MultiPolygon}, [unclaimed pieces])."""
    shapely.prepare(land)
    lines = _joined(list(lines), land, snap=snap)
    net = shapely.union_all([land.boundary] + lines)
    faces = [f for f in shapely.get_parts(shapely.polygonize(list(shapely.get_parts(net))))]
    shapely.prepare(land)
    faces = [f for f in faces if land.contains(f.representative_point())]
    owner = [None] * len(faces)
    tree = shapely.STRtree(faces)
    for p in neutral:
        for i in tree.query(Point(p).buffer(0.3), predicate="intersects"):
            owner[i] = ""
    for key, pts in seeds.items():
        for p in pts:
            hit = [i for i in tree.query(Point(p), predicate="intersects")]
            if not hit:                           # an island's seed a little off its coast
                near = [i for i in tree.query(Point(p), predicate="dwithin", distance=0.15)]
                hit = sorted(near, key=lambda i: faces[i].distance(Point(p)))[:1]
            if not hit:
                raise ValueError(f"the seed of {key} at {p} is not on land")
            owner[hit[0]] = key
    # slivers: merge into the neighbour sharing the longest edge
    for _ in range(4):
        for i, f in enumerate(faces):
            if owner[i] is not None:
                continue
            best, share = None, 0.0
            for j in tree.query(f, predicate="touches"):
                if not owner[j]:
                    continue
                s = shapely.intersection(f.boundary, faces[j].boundary).length
                if s > share:
                    best, share = owner[j], s
            if best is not None and share > 0:
                owner[i] = best
    held = {}
    for f, o in zip(faces, owner):
        if o:
            held.setdefault(o, []).append(f)
    held = {k: shapely.union_all(v) for k, v in held.items()}
    unclaimed = [f for f, o in zip(faces, owner) if o == ""]
    names = list(held)
    geoms = [held[k] for k in names]
    for f, o in zip(faces, owner):
        if o is not None:
            continue
        d = [shapely.distance(f, g) for g in geoms]
        j = int(np.argmin(d))
        if d[j] <= island_reach:
            held[names[j]] = shapely.union(held[names[j]], f)
        else:
            unclaimed.append(f)
    return held, unclaimed


# -- a region's ground ----------------------------------------------------------------------------

def region_ground(region: str, land_ll, store):
    """(the land a region's frontiers cut, whether ends snap to its edge): a continent's own land,
    or, for the marches of one nation (`of` in REGIONS), that nation as its continent's frontiers
    leave it."""
    R = REGIONS[region]
    if "of" not in R:
        return R["land"](land_ll), False
    parent, nation = R["of"]
    return held_nations(parent, land_ll, store)[0][nation], True


def region_basins(region: str) -> str:
    """The region whose river basins a region is traced on (its own, or its continent's)."""
    R = REGIONS[region]
    return R["of"][0] if "of" in R else region


def held_nations(region: str, land_ll, store):
    """A traced region's nations from its files in `store` (data/atlas): ({key: shape},
    [neutral pieces], the nations' rows, the frontiers' spec)."""
    import yaml
    store = pathlib.Path(store)
    spec = yaml.safe_load((store / f"{region}-frontiers.yaml").read_text(encoding="utf8"))
    rows = read_nations(store / f"{region}-nations.csv")
    seeds = {r["key"]: [(r["seed_lon"], r["seed_lat"])] for r in rows}
    for k, pts in (spec.get("seeds") or {}).items():
        seeds[k] = seeds.get(k, []) + [tuple(p) for p in pts]
    land, snap = region_ground(region, land_ll, store)
    held, unclaimed = nations(read_geojson(store / f"{region}-frontiers.geojson"), land, seeds,
                              spec.get("neutral", []), snap=snap)
    return held, unclaimed, rows, spec
