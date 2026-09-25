"""Build the province mesh: the fixed set of cells every border in the video is made of.

Why a mesh: if each year's borders were drawn separately, neighbouring countries would
overlap or leave slivers, and a border would wobble from one year to the next. Here every
border is a chain of shared cell edges, so two neighbours always meet exactly, and a border
that does not move between two years is pixel-identical in both frames.

How the cells are made
  1. Seed points: a jittered grid over the land, finer inside the `focus` boxes, plus one
     point per region seed (so every region owns at least one cell).
  2. Voronoi edges between the seeds, each roughened with deterministic midpoint
     displacement, so borders read as hand-drawn rather than as straight lines, and no
     frontier is a meridian or a parallel (the setting's rule 2).
  3. The coastline, the named rivers and your custom lines (data/custom_lines.geojson)
     are added as extra edges, then everything is noded and polygonised into faces.
  4. Faces smaller than `min_cell_km2` are merged into the neighbour they share most edge with.

How cells become regions
  Each region in regions.csv grows outward from its seed over the cell adjacency graph
  (multi-source Dijkstra). Crossing a river or a custom line costs `barrier_penalty` times
  more, so regions stop at the Euphrates or at the Tuwayq escarpment the way real frontiers
  do. Polygons in data/overrides.geojson then force cells into a named region: that is the
  precise, hand-made correction step (draw it in QGIS).
"""

from __future__ import annotations

import heapq
import json
import math
import struct
import zlib

import geopandas as gpd
import numpy as np
import shapely
from shapely.geometry import LineString, MultiPoint, Point, shape
from shapely.strtree import STRtree

from . import geo
from .config import paths
from .data import Data


# -- seeds --------------------------------------------------------------------------

def _hex_points(bounds, spacing: float, rng: np.random.Generator) -> np.ndarray:
    x0, y0, x1, y1 = bounds
    dy = spacing * math.sqrt(3) / 2
    rows = np.arange(y0, y1 + dy, dy)
    pts = []
    for i, y in enumerate(rows):
        xs = np.arange(x0 + (spacing / 2 if i % 2 else 0), x1 + spacing, spacing)
        pts.append(np.column_stack([xs, np.full(xs.size, y)]))
    pts = np.vstack(pts)
    pts += rng.uniform(-0.35, 0.35, pts.shape) * spacing
    return pts


def seed_points(cfg: dict, land, region_xy: np.ndarray, rng) -> np.ndarray:
    m = cfg["mesh"]
    zones = [(geo.bbox_polygon(cfg, m["bbox"]), float(m["spacing_km"]) * 1000)]
    for extra in m.get("extra_bboxes", []):
        zones.append((geo.bbox_polygon(cfg, extra), float(m["spacing_km"]) * 1000))
    for f in m.get("focus", []):
        zones.append((geo.bbox_polygon(cfg, f["bbox"]), float(f["spacing_km"]) * 1000))
    # a later (finer) zone takes its area away from the earlier ones
    owned = []
    for i, (poly, sp) in enumerate(zones):
        later = [p for p, _ in zones[i + 1 :]]
        area = poly.difference(shapely.union_all(later)) if later else poly
        owned.append((area, sp))
    shapely.prepare(land)
    chunks = []
    for area, sp in owned:
        if area.is_empty:
            continue
        pts = _hex_points(area.bounds, sp, rng)
        keep = shapely.contains_xy(area, pts[:, 0], pts[:, 1]) & shapely.contains_xy(land, pts[:, 0], pts[:, 1])
        pts = pts[keep]
        if len(region_xy):
            # leave room around each region seed so it gets a full-sized cell of its own
            tree = STRtree(shapely.points(region_xy))
            near = tree.query(shapely.points(pts), predicate="dwithin", distance=sp * 0.55)
            pts = np.delete(pts, np.unique(near[0]), axis=0)
        chunks.append(pts)
    chunks.append(region_xy)
    return np.vstack(chunks)


# -- edges --------------------------------------------------------------------------

def _edge_rng(a, b) -> np.random.Generator:
    key = struct.pack("4q", *(int(round(v)) for v in (*a, *b)))
    return np.random.default_rng(zlib.crc32(key))


def roughen(line: LineString, amount: float, depth: int) -> LineString:
    """Midpoint displacement with endpoints fixed, seeded by the edge itself."""
    coords = np.asarray(line.coords)
    if amount <= 0 or len(coords) != 2:
        return line
    a, b = coords[0], coords[1]
    if tuple(a) > tuple(b):
        a, b = b, a
    rng = _edge_rng(a, b)
    pts = [a, b]
    amp = amount
    for _ in range(depth):
        out = [pts[0]]
        for p, q in zip(pts, pts[1:]):
            d = q - p
            length = math.hypot(*d)
            if length == 0:
                out.append(q)
                continue
            normal = np.array([-d[1], d[0]]) / length
            mid = (p + q) / 2 + normal * rng.uniform(-1, 1) * amp * length
            out.extend([mid, q])
        pts = out
        amp *= 0.9
    return LineString(pts)


def _lines_from_geojson(cfg: dict, path) -> list:
    if not path.exists():
        return []
    gj = json.loads(path.read_text(encoding="utf8"))
    feats = gj.get("features", [])
    if not feats:
        return []
    gdf = gpd.GeoDataFrame.from_features(feats, crs=geo.WGS84).to_crs(geo.crs(cfg))
    return [g for g in gdf.geometry if g is not None and not g.is_empty]


# -- faces --------------------------------------------------------------------------

def merge_small(faces: list, min_area: float) -> list:
    n = len(faces)
    parent = list(range(n))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    areas = np.array([f.area for f in faces])
    group_area = areas.copy()
    tree = STRtree(faces)
    for i in np.argsort(areas):
        if group_area[root(i)] >= min_area:
            continue
        cand = [j for j in tree.query(faces[i], predicate="intersects") if j != i]
        best, best_len = None, 0.0
        shared = {}
        for j in cand:
            rj = root(j)
            if rj == root(i):
                continue
            length = faces[i].intersection(faces[j]).length
            shared[rj] = shared.get(rj, 0.0) + length
        for rj, length in shared.items():
            if length > best_len:
                best, best_len = rj, length
        if best is None:
            continue  # an island: kept as it is
        ri = root(i)
        parent[ri] = best
        group_area[best] += group_area[ri]
    groups: dict[int, list] = {}
    for i in range(n):
        groups.setdefault(root(i), []).append(faces[i])
    return [shapely.union_all(g) if len(g) > 1 else g[0] for g in groups.values()]


# -- regions ------------------------------------------------------------------------

def adjacency(cells: np.ndarray, barrier) -> list[list[tuple[int, float, float]]]:
    """Neighbours of each cell: (cell, centroid distance, share of the shared edge on a barrier)."""
    tree = STRtree(cells)
    pairs = tree.query(cells, predicate="intersects")
    i, j = pairs
    keep = i < j
    i, j = i[keep], j[keep]
    shared = shapely.intersection(cells[i], cells[j])
    length = shapely.length(shared)
    ok = length > 1.0
    i, j, shared, length = i[ok], j[ok], shared[ok], length[ok]
    if barrier is not None:
        blocked = shapely.length(shapely.intersection(shared, barrier)) / length
    else:
        blocked = np.zeros(len(i))
    cen = shapely.centroid(cells)
    dist = shapely.distance(cen[i], cen[j])
    graph: list[list[tuple[int, float, float]]] = [[] for _ in range(len(cells))]
    for a, b, d, f in zip(i, j, dist, blocked):
        graph[a].append((b, d, f))
        graph[b].append((a, d, f))
    return graph


def grow_regions(cells, graph, seeds, penalty: float) -> np.ndarray:
    """seeds: list of (cell_index, region_index, weight). Returns region index per cell."""
    owner = np.full(len(cells), -1, dtype=np.int32)
    heap = [(0.0, c, r, w) for c, r, w in seeds]
    heapq.heapify(heap)
    while heap:
        cost, c, r, w = heapq.heappop(heap)
        if owner[c] != -1:
            continue
        owner[c] = r
        for nb, d, blocked in graph[c]:
            if owner[nb] == -1:
                heapq.heappush(heap, (cost + d * (1 + penalty * min(blocked, 1.0)) / w, nb, r, w))
    return owner


def build(cfg: dict, data: Data) -> None:
    m = cfg["mesh"]
    P = paths(cfg)
    P.build.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(int(m.get("seed", 0)))

    boxes = [m["bbox"]] + list(m.get("extra_bboxes", []))
    domain = shapely.union_all([geo.bbox_polygon(cfg, b) for b in boxes])
    margin = [(b[0] - 2, b[1] - 2, b[2] + 2, b[3] + 2) for b in boxes]

    print("  land")
    land_parts = []
    for name in ("ne_10m_land", "ne_10m_minor_islands"):
        try:
            src = geo.read_ne(cfg, name)
        except SystemExit:
            if name == "ne_10m_land":
                raise
            continue
        for bb in margin:
            clipped = geo.clip_project(cfg, src, bb)
            land_parts.extend(clipped.geometry)
    land = shapely.make_valid(shapely.union_all(land_parts)).intersection(domain)
    min_island = float(m.get("min_island_km2", 25)) * 1e6
    parts = [p for p in shapely.get_parts(land) if p.geom_type == "Polygon" and p.area >= min_island]
    land = shapely.union_all(parts)

    print("  rivers")
    rivers_src = geo.read_ne(cfg, "ne_10m_rivers_lake_centerlines")
    wanted = {r.lower() for r in m.get("rivers", [])}
    rivers_src = rivers_src[rivers_src["name"].fillna("").str.lower().isin(wanted)]
    river_lines = []
    for bb in margin:
        river_lines.extend(geo.clip_project(cfg, rivers_src, bb).geometry)
    rivers = shapely.union_all(river_lines).intersection(land) if river_lines else None
    custom = _lines_from_geojson(cfg, P.data / "custom_lines.geojson")
    custom = [g.intersection(land) for g in custom]

    print("  seeds and voronoi")
    region_ll = [(float(r["lon"]), float(r["lat"])) for r in data.regions]
    rx, ry = geo.project_points(cfg, [p[0] for p in region_ll], [p[1] for p in region_ll])
    region_pts = np.column_stack([rx, ry])
    inside = shapely.contains_xy(land, rx, ry)
    # a seed a little offshore (an island or a coastal town) still counts if a cell is near
    near = shapely.distance(shapely.points(region_pts), land) < 30_000
    in_mesh = inside | near
    pts = seed_points(cfg, land, region_pts[inside], rng)
    edges = shapely.voronoi_polygons(MultiPoint(pts), extend_to=domain.buffer(200_000), only_edges=True)
    amount, depth = float(m.get("noise", 0.2)), int(m.get("noise_depth", 4))
    rough = [roughen(e, amount, depth) for e in shapely.get_parts(edges)]

    print("  polygonize")
    lines = rough + [land.boundary]
    if rivers is not None and not rivers.is_empty:
        lines.append(rivers)
    lines.extend(g for g in custom if not g.is_empty)
    network = shapely.union_all(lines)
    faces = list(shapely.get_parts(shapely.polygonize(list(shapely.get_parts(network)))))
    faces = np.array(faces)
    rp = shapely.point_on_surface(faces)
    shapely.prepare(land)
    faces = faces[shapely.contains_xy(land, shapely.get_x(rp), shapely.get_y(rp))]
    print(f"  {len(faces)} faces; merging small ones")
    cells = np.array(merge_small(list(faces), float(m.get("min_cell_km2", 100)) * 1e6))
    print(f"  {len(cells)} cells")

    print("  growing regions")
    barrier_lines = [g for g in [rivers, *custom] if g is not None and not g.is_empty]
    barrier = shapely.union_all(barrier_lines).buffer(400) if barrier_lines else None
    graph = adjacency(cells, barrier)
    tree = STRtree(cells)
    seeds = []
    taken = {}
    for k, r in enumerate(data.regions):
        if not in_mesh[k]:
            continue
        pt = Point(region_pts[k])
        hit = tree.query(pt, predicate="intersects")
        c = int(hit[0]) if len(hit) else int(tree.nearest(pt))
        if c in taken:
            data.problems.append(
                f"regions '{taken[c]}' and '{r['region_id']}' share a seed cell: move one or refine the mesh")
            continue
        taken[c] = r["region_id"]
        seeds.append((c, k, float(r.get("weight") or 1.0)))
    owner = grow_regions(cells, graph, seeds, float(m.get("barrier_penalty", 10)))

    # cells no seed could reach (islands): nearest region seed in a straight line
    lost = np.where(owner == -1)[0]
    if len(lost):
        seed_geoms = shapely.points(region_pts[[k for _, k, _ in seeds]])
        seed_regions = [k for _, k, _ in seeds]
        stree = STRtree(seed_geoms)
        for c in lost:
            owner[c] = seed_regions[int(stree.nearest(shapely.point_on_surface(cells[c])))]

    overrides = P.data / "overrides.geojson"
    if overrides.exists():
        gj = json.loads(overrides.read_text(encoding="utf8"))
        feats = gj.get("features", [])
        if feats:
            ov = gpd.GeoDataFrame.from_features(feats, crs=geo.WGS84).to_crs(geo.crs(cfg))
            rp = shapely.point_on_surface(cells)
            for geom, rid in zip(ov.geometry, ov["region_id"]):
                if rid not in data.region_index:
                    data.problems.append(f"overrides.geojson: unknown region '{rid}'")
                    continue
                hit = shapely.contains(geom, rp)
                owner[hit] = data.region_index[rid]

    region_of_cell = [data.region_ids[k] for k in owner]
    cells_gdf = gpd.GeoDataFrame(
        {"cell_id": np.arange(len(cells)), "region_id": region_of_cell,
         "area_km2": np.round(shapely.area(cells) / 1e6, 1)},
        geometry=list(cells), crs=geo.crs(cfg))
    regions_gdf = cells_gdf.dissolve(by="region_id", as_index=False, aggfunc={"area_km2": "sum", "cell_id": "count"})
    regions_gdf = regions_gdf.rename(columns={"cell_id": "n_cells"})
    names = {r["region_id"]: r["name"] for r in data.regions}
    regions_gdf["name"] = regions_gdf["region_id"].map(names)
    for k, r in enumerate(data.regions):
        if in_mesh[k] and r["region_id"] not in set(region_of_cell):
            data.problems.append(f"region '{r['region_id']}' ended up with no cells")

    out = P.mesh
    if out.exists():
        out.unlink()
    cells_gdf.to_file(out, layer="cells", driver="GPKG")
    regions_gdf.to_file(out, layer="regions", driver="GPKG")
    seeds_gdf = gpd.GeoDataFrame(
        {"region_id": data.region_ids, "name": [r["name"] for r in data.regions], "in_mesh": in_mesh},
        geometry=shapely.points(region_pts), crs=geo.crs(cfg))
    seeds_gdf.to_file(out, layer="region_seeds", driver="GPKG")
    if rivers is not None and not rivers.is_empty:
        gpd.GeoDataFrame(geometry=[rivers], crs=geo.crs(cfg)).to_file(out, layer="mesh_rivers", driver="GPKG")
    write_view_layers(cfg, out, data)
    print(f"  wrote {out}")


def drawn_extent(cfg: dict, data: Data | None = None):
    """The projected box any frame can show: the default view, and every camera keyframe's
    screen rectangle from data/camera.csv (motion.views_extent, the same measure the motion
    plates use), so the motion cut never looks past the edge of the drawn land."""
    x0, x1, y0, y1 = geo.view_extent(cfg)
    rows = sorted(getattr(data, "camera", None) or [], key=lambda k: int(k["year"]))
    if rows:
        from .motion import camera_views, views_extent
        xs, ys = geo.project_points(cfg, [float(k["lon"]) for k in rows], [float(k["lat"]) for k in rows])
        keys = [(float(cx), float(cy), float(k["zoom"]), math.radians(float(k["rotation"])))
                for cx, cy, k in zip(xs, ys, rows)]
        v = views_extent(cfg, camera_views(cfg, keys), cfg["frame"]["width"], cfg["frame"]["height"])
        x0, x1, y0, y1 = min(x0, v[0]), max(x1, v[1]), min(y0, v[2]), max(y1, v[3])
    return x0, x1, y0, y1


def write_view_layers(cfg: dict, out, data: Data | None = None) -> None:
    """Land, lakes and rivers for everything a frame can show (wider than the mesh), for drawing."""
    x0, x1, y0, y1 = drawn_extent(cfg, data)
    bb = geo.lonlat_bbox(cfg, x0, x1, y0, y1)
    frame = shapely.box(x0, y0, x1, y1).buffer(300_000)
    layers = {}
    land = []
    for name in ("ne_10m_land", "ne_10m_minor_islands"):
        try:
            land.extend(geo.clip_project(cfg, geo.read_ne(cfg, name), bb).geometry)
        except SystemExit:
            if name == "ne_10m_land":
                raise
    # repair each piece first: a continent clipped wide and projected can come out self-touching
    land = [g for g in (shapely.make_valid(g) for g in land) if not g.is_empty]
    layers["view_land"] = shapely.make_valid(shapely.union_all(land)).intersection(frame)
    for ins in cfg.get("insets", []):
        ibb = [ins["bbox"][0] - 2, ins["bbox"][1] - 2, ins["bbox"][2] + 2, ins["bbox"][3] + 2]
        extra = geo.clip_project(cfg, geo.read_ne(cfg, "ne_10m_land"), ibb).geometry
        try:
            extra = list(extra) + list(geo.clip_project(cfg, geo.read_ne(cfg, "ne_10m_minor_islands"), ibb).geometry)
        except SystemExit:
            pass
        layers["view_land"] = shapely.union_all([layers["view_land"], *extra])
    lakes = geo.clip_project(cfg, geo.read_ne(cfg, "ne_10m_lakes"), bb)
    layers["view_lakes"] = shapely.union_all(list(lakes.geometry)).intersection(frame)
    rv = geo.read_ne(cfg, "ne_10m_rivers_lake_centerlines")
    rv = rv[rv["scalerank"].fillna(99) <= 6]
    rv = geo.clip_project(cfg, rv, bb)
    layers["view_rivers"] = shapely.union_all(list(rv.geometry)).intersection(frame)
    for name, geom in layers.items():
        gpd.GeoDataFrame(geometry=[geom], crs=geo.crs(cfg)).to_file(out, layer=name, driver="GPKG")
    write_bathymetry(cfg, out, bb, frame)


BATHY = [(0, "L"), (200, "K"), (1000, "J"), (2000, "I"), (3000, "H"), (4000, "G"), (5000, "F"), (6000, "E")]


def write_bathymetry(cfg: dict, out, bb, frame) -> None:
    """Natural Earth's depth zones (sea deeper than 0, 200, 1000 ... 6000 m), for stepped ocean
    tints. Optional: without ne_10m_bathymetry_all the ocean stays one colour."""
    from .fetch import layer_path
    src = layer_path(cfg, "ne_10m_bathymetry_all")
    if not src.exists():
        return
    rows = []
    for depth, code in BATHY:
        try:
            g = gpd.read_file(f"zip://{src.resolve().as_posix()}", layer=f"ne_10m_bathymetry_{code}_{depth}", bbox=bb)
        except Exception as exc:  # a layer missing from the archive is not worth failing over
            print(f"  bathymetry {depth} m skipped ({exc})")
            continue
        if g.crs is None:
            g = g.set_crs(geo.WGS84)
        parts = [shapely.make_valid(p) for p in geo.clip_project(cfg, g, bb).geometry]
        parts = [p for p in parts if not p.is_empty]
        if parts:
            rows.append({"depth": depth, "geometry": shapely.union_all(parts).intersection(frame)})
    if rows:
        gpd.GeoDataFrame(rows, geometry="geometry", crs=geo.crs(cfg)).to_file(out, layer="view_bathy", driver="GPKG")
