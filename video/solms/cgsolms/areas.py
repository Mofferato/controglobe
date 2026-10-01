"""A phase's areas, built from whole provinces, and who holds each of them from year to year.

The provinces are the half-basins GRASS cut from ETOPO (qgis_ground.py), so an area's edge is
always a crest or a river: compact, smooth and on the ground, never a meridian or a partition line.
`build(n)` reads phaseN/polities.yaml and writes build/solms/phaseN/map.json for the engine:

  areas     {id: {"d": SVG path in plate pixels, "c": [x, y] a label point, "km2": area}}
  polities  {id: {"colour", "holds": [[from, to, area, style], ...]}}
  plate     {"w", "h"}
"""

from __future__ import annotations

import json
import math

import numpy as np
import shapely
import yaml

from . import frame as F
from .ground import Plate


def _load(name):
    import geopandas as gpd
    G = F.ground_dir(name)
    prov = gpd.read_file(G / "provinces.gpkg")
    prov = prov[prov["basin"] > 0].dissolve(by="basin").reset_index()
    basins = {}
    for p in sorted(G.glob("basin_*.gpkg")):
        if p.stem.endswith("_ll"):
            continue
        b = gpd.read_file(p)
        b = b[b["v"] > 0] if "v" in b.columns else b
        if len(b):
            basins[p.stem[6:]] = shapely.make_valid(shapely.union_all(list(b.geometry)))
    return prov, basins


def _provinces(name):
    """Every province with its geometry (metres), centre (lon, lat), basin and height."""
    from pyproj import Transformer
    from PIL import Image
    fr = F.frame(name)
    prov, basins = _load(name)
    back = Transformer.from_crs(fr["proj"], "EPSG:4326", always_xy=True)
    dem = np.asarray(Image.open(F.ground_dir(name) / "dem_mesh.tif"), np.float32)
    mh, mw = dem.shape
    x0, y0, x1, y1 = fr["extent"]
    out = []
    for g in prov.geometry:
        g = shapely.make_valid(g)
        if g.area < 4e7:                                 # slivers under 40 km2
            continue
        c = g.representative_point()
        lon, lat = back.transform(c.x, c.y)
        # the smallest basin that holds most of the province (basins nest: the Salt in the Gila
        # in the Colorado)
        best, share, size = None, 0.0, float("inf")
        for k, b in basins.items():
            if not b.intersects(g):
                continue
            s = b.intersection(g).area / g.area
            if s > 0.5 and b.area < size:
                best, share, size = k, s, b.area
        col = int((c.x - x0) / (x1 - x0) * mw)
        row = int((y1 - c.y) / (y1 - y0) * mh)
        # the province's height: the median of the mesh's cells inside its box
        minx, miny, maxx, maxy = g.bounds
        c0, c1 = int((minx - x0) / (x1 - x0) * mw), int((maxx - x0) / (x1 - x0) * mw) + 1
        r0, r1 = int((y1 - maxy) / (y1 - y0) * mh), int((y1 - miny) / (y1 - y0) * mh) + 1
        h = float(np.median(dem[max(r0, 0):r1, max(c0, 0):c1])) if r1 > r0 and c1 > c0 else float(dem[row, col])
        out.append({"g": g, "lon": lon, "lat": lat, "basin": best if share > 0.5 else None, "h": h,
                    "x": c.x, "y": c.y})
    return out


def _west_of_gulf(lon, lat):
    return lon < np.interp(lat, [22.8, 31.8], [-109.5, -114.7])


def _select(rule, provs, built, fr):
    from pyproj import Transformer
    fwd = Transformer.from_crs("EPSG:4326", fr["proj"], always_xy=True)
    sel = set()
    if any(k in rule for k in ("basins", "lon", "lat", "below", "near", "west_of_gulf")):
        for i, p in enumerate(provs):
            if "basins" in rule and p["basin"] not in rule["basins"]:
                continue
            if "lon" in rule and not rule["lon"][0] <= p["lon"] <= rule["lon"][1]:
                continue
            if "lat" in rule and not rule["lat"][0] <= p["lat"] <= rule["lat"][1]:
                continue
            if "below" in rule and p["h"] > rule["below"]:
                continue
            if "near" in rule:
                lon, lat, km = rule["near"]
                x, y = fwd.transform(lon, lat)
                if math.hypot(p["x"] - x, p["y"] - y) > km * 1000:
                    continue
            if rule.get("west_of_gulf") and not _west_of_gulf(p["lon"], p["lat"]):
                continue
            sel.add(i)
    for k in rule.get("plus", []):
        sel |= built[k]
    for k in rule.get("minus", []):
        sel -= built[k]
    return sel


def _smooth(g, plate: Plate):
    """In plate pixels, a hair rounded, simplified to a quarter pixel."""
    g = plate.geom(g)
    g = shapely.make_valid(g.buffer(1.2, join_style="round").buffer(-1.2, join_style="round"))
    return g.simplify(0.35, preserve_topology=True)


def path_d(g, nd=1):
    parts = []
    for p in shapely.get_parts(g):
        if p.geom_type != "Polygon" or p.is_empty:
            continue
        for ring in [p.exterior, *p.interiors]:
            xy = np.asarray(ring.coords)
            parts.append("M" + "L".join(f"{x:.{nd}f},{y:.{nd}f}" for x, y in xy) + "Z")
    return "".join(parts)


def build(n: int, log=print) -> dict:
    name = f"phase{n}"
    fr = F.frame(name)
    spec = yaml.safe_load((F.phase_dir(n) / "polities.yaml").read_text(encoding="utf8"))
    cast = yaml.safe_load((F.phase_dir(n) / "cast.yaml").read_text(encoding="utf8"))
    provs = _provinces(name)
    plate = Plate(fr, fr["grids"]["tex"])
    built, areas = {}, {}
    for k, rule in spec["areas"].items():
        built[k] = _select(rule, provs, built, fr)
        if not built[k]:
            log(f"  area {k}: no province matches")
            continue
        g = shapely.union_all([provs[i]["g"] for i in built[k]])
        km2 = g.area / 1e6
        gp = _smooth(g, plate)
        big = max(shapely.get_parts(gp), key=lambda q: q.area)
        lp = __import__("shapely.ops").ops.polylabel(big, 2.0) if big.geom_type == "Polygon" else big.representative_point()
        areas[k] = {"d": path_d(gp), "c": [round(lp.x, 1), round(lp.y, 1)], "km2": round(km2),
                    "n": len(built[k])}
    pol = {}
    for k, v in spec["polities"].items():
        c = cast.get(k, {})
        pol[k] = {"colour": c.get("colour", "#888888"), "holds": v.get("holds", [])}
    pol["queen"]["colour"] = pol["houses"]["colour"]
    # the provinces themselves, for the map's fine lines
    prov_d = path_d(shapely.union_all([_smooth(p["g"], plate).boundary.buffer(0.01) for p in provs[:0]])) if False else None
    out = {"areas": areas, "polities": pol, "plate": {"w": plate.W, "h": plate.H},
           "provinces": [path_d(_smooth(p["g"], plate)) for p in provs]}
    dst = F.build_dir(n) / "map.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out), encoding="utf8")
    log(f"  {len(areas)} areas from {len(provs)} provinces -> {dst}")
    for k, a in areas.items():
        log(f"    {k:16s} {a['n']:3d} provinces {a['km2']:9,d} km2")
    return out


def holder_at(pol: dict, area: str, year: float):
    """(polity, style) holding an area in a year, the later row winning."""
    best = None
    for pid, p in pol.items():
        for i, (a, b, ar, st) in enumerate(p["holds"]):
            if ar == area and a <= year < b:
                best = (pid, st)
    return best


def preview(n: int, years, skin="marble"):
    """PNG previews of the political map at the given years, over the plate."""
    from PIL import Image, ImageDraw, ImageFont
    import re
    data = json.loads((F.build_dir(n) / "map.json").read_text(encoding="utf8"))
    base = Image.open(F.ground_dir(f"phase{n}") / f"plate_{skin}_2k.jpg").convert("RGB")
    k = base.width / data["plate"]["w"]
    outs = []
    for y in years:
        img = base.copy()
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        # each area painted by its last holder in that year (later rows of later polities win)
        owner = {}
        for pid, p in data["polities"].items():
            for a, b, ar, st in p["holds"]:
                if a <= y < b:
                    owner[ar] = (pid, st)
        for ar, (pid, st) in owner.items():
            col = data["polities"][pid]["colour"]
            rgb = tuple(int(col[i:i + 2], 16) for i in (1, 3, 5))
            for ring in re.findall(r"M([^Z]+)Z", data["areas"][ar]["d"]):
                pts = [tuple(float(v) * k for v in pt.split(",")) for pt in ring.split("L")]
                if len(pts) > 2:
                    d.polygon(pts, fill=rgb + (150,), outline=rgb + (255,))
        img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
        dd = ImageDraw.Draw(img)
        for ar, (pid, st) in owner.items():
            cx, cy = data["areas"][ar]["c"]
            dd.text((cx * k, cy * k), f"{pid}\n{ar}\n{st}", fill="black")
        dd.text((20, 20), f"{y}", fill="white")
        p = F.build_dir(n) / "preview" / f"map_{y}.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        img.save(p)
        outs.append(p)
    return outs
