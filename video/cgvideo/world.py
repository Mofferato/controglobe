"""The maps on a globe: equirectangular textures of the alternate world, one per map state, for the
Shorts' three.js globe (cgvideo/shorts_engine) and for Blender's globe clips.

  base     Natural Earth II (land cover, shaded relief, water) for the land and ETOPO 2022's depth for
           the sea, resampled to the texture grid once (build/world/base_<W>.jpg)
  mesh     the long cut's regions, coloured by who holds them in that year, carried from the video's
           projection back to longitude and latitude
  realms   the empires whose ground runs past the mesh (data/world/realms.yaml): the caliphates at their
           fullest extent, Rome, Persia, the Yavana kingdom; unions of the atlases' traced nations and of
           rings drawn on the ground, clipped to the coast
  lines    thin lines between the states of one realm, a heavier frontier round each realm, a glow on
           the coast

Labels are not painted: the engine sets them in the page, upright and sharp, at `labels()` points.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

import numpy as np
import shapely
import yaml
from PIL import Image, ImageDraw, ImageFilter

from . import data as D
from . import geo
from .config import paths

Image.MAX_IMAGE_PIXELS = None
VERSION = 3


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def land_ll(cfg):
    import geopandas as gpd
    ne = paths(cfg).root / "cache" / "naturalearth"
    land = gpd.read_file(f"/vsizip/{(ne / 'ne_10m_land.zip').as_posix()}")
    return shapely.make_valid(shapely.union_all(list(land.geometry)))


# -- the realms beyond the mesh ---------------------------------------------------------------

def realms(cfg, log=print) -> list[dict]:
    """[{id, polity (or a list: polity, start, end, ...), years, geom (lon/lat, on land)}], cached."""
    src = paths(cfg).data / "world" / "realms.yaml"
    out = paths(cfg).build / "world" / "realms.geojson"
    spec = yaml.safe_load(src.read_text(encoding="utf8"))["realms"]
    key = hashlib.sha1(src.read_bytes() + f"v{VERSION}".encode()).hexdigest()[:10]
    if out.exists():
        js = json.loads(out.read_text(encoding="utf8"))
        if js.get("key") == key:
            geoms = {f["properties"]["id"]: shapely.from_geojson(json.dumps(f["geometry"])) for f in js["features"]}
            return [{**r, "geom": geoms[r["id"]]} for r in spec]
    from . import frontiers as fr
    land = land_ll(cfg)
    store = paths(cfg).data / "atlas"
    nations = {}
    res = []
    by_id = {}
    for r in spec:
        parts = []
        for region, keys in (r.get("nations") or {}).items():
            if region not in nations:
                log(f"  realms: the {region} atlas's nations")
                nations[region] = fr.held_nations(region, land, store)[0]
            parts += [nations[region][k] for k in keys if k in nations[region]]
        for ring in r.get("rings") or []:
            parts.append(shapely.Polygon(_chaikin(ring, 4)).buffer(0).intersection(land))
        if r.get("same_as"):
            parts.append(by_id[r["same_as"]])
        g = shapely.make_valid(shapely.union_all(parts)) if parts else shapely.GeometryCollection()
        if not g.is_empty:                           # close the hairline gaps between neighbouring nations
            g = shapely.make_valid(g.buffer(0.03).buffer(-0.03).intersection(land))
        by_id[r["id"]] = g
        res.append({**r, "geom": g})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"type": "FeatureCollection", "key": key, "features": [
        {"type": "Feature", "properties": {"id": r["id"], "years": r["years"]},
         "geometry": json.loads(shapely.to_geojson(r["geom"]))} for r in res]}), encoding="utf8")
    log(f"  realms: {len(res)} -> {out}")
    return res


def _chaikin(ring, n):
    """Corner cutting: a hand-drawn ring rounded into the line of the ground it follows."""
    pts = [tuple(p) for p in ring]
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    for _ in range(n):
        out = []
        for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
            out += [(0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1), (0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1)]
        pts = out + [out[0]]
    return pts


def realm_polity(r, year):
    p = r["polity"]
    if isinstance(p, str):
        return p if r["years"][0] <= year <= r["years"][1] else None
    for i in range(0, len(p), 3):
        if int(p[i + 1]) <= year <= int(p[i + 2]):
            return p[i]
    return None


# -- the mesh in longitude and latitude ---------------------------------------------------------

_MESH: dict = {}


def mesh_ll(cfg) -> dict:
    if "regions" not in _MESH:
        import geopandas as gpd
        regions = gpd.read_file(paths(cfg).mesh, layer="regions")
        inv = geo.to_lonlat(cfg)

        def to_ll(g):
            return shapely.transform(g, lambda c: np.column_stack(inv.transform(c[:, 0], c[:, 1])))
        _MESH["regions"] = {rid: to_ll(g) for rid, g in zip(regions["region_id"], regions.geometry)}
    return _MESH["regions"]


def state(cfg, data, year):
    """{polity: lon/lat geometry} and {top polity: geometry} for a year, mesh and realms together."""
    row = data.matrix[data.year_index(year)]
    mesh = mesh_ll(cfg)
    members: dict[str, list] = {}
    for k, rid in enumerate(data.region_ids):
        p = int(row[k])
        if p == D.UNCLAIMED or rid not in mesh:
            continue
        members.setdefault(data.polity_ids[p], []).append(mesh[rid])
    held = shapely.union_all([g for gs in members.values() for g in gs]) if members else shapely.GeometryCollection()
    for r in realms(cfg):
        pid = realm_polity(r, year)
        if pid and pid in data.polity:
            g = r["geom"].difference(held)                # the mesh's holders decide inside its frame
            if not g.is_empty:
                members.setdefault(pid, []).append(g)
    pols = {pid: shapely.make_valid(shapely.union_all(gs)) for pid, gs in members.items()}
    tops: dict[str, list] = {}
    for pid, g in pols.items():
        tops.setdefault(data.top(pid), []).append(g)
    return pols, {t: shapely.make_valid(shapely.union_all(gs)) for t, gs in tops.items()}


# -- textures ---------------------------------------------------------------------------------------

def base(cfg, W, log=print) -> Image.Image:
    H = W // 2
    out = paths(cfg).build / "world" / f"base_{W}.jpg"
    if out.exists():
        return Image.open(out).convert("RGB")
    log(f"  globe base {W}x{H}: Natural Earth II and ETOPO 2022")
    root = paths(cfg).root
    ne2 = Image.open(root / "cache" / "naturalearth" / "NE2" / "NE2_HR_LC_SR_W_DR.tif").convert("RGB").resize((W, H), Image.LANCZOS)
    land = np.asarray(ne2, np.float32)
    dem_p = root / "build" / "solms" / "globe" / "globe_dem.tif"
    if dem_p.exists():
        dem = np.asarray(Image.open(dem_p).resize((W, H), Image.BILINEAR), np.float32)
    else:
        dem = np.zeros((H, W), np.float32)
    st = cfg["style"]
    stops = sorted((int(k), _hex(v)) for k, v in (st.get("bathymetry") or {0: st["ocean"]}).items())
    depth = np.clip(-dem, 0, None)
    sea = np.stack([np.interp(depth, [s for s, _ in stops], [c[i] for _, c in stops]) for i in range(3)], -1)
    # land mask from Natural Earth land, drawn at the grid
    mask = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(mask)
    for poly in shapely.get_parts(land_ll(cfg)):
        if poly.geom_type != "Polygon":
            continue
        d.polygon([((x + 180) / 360 * W, (90 - y) / 180 * H) for x, y in poly.exterior.coords], fill=255)
        for hole in poly.interiors:
            d.polygon([((x + 180) / 360 * W, (90 - y) / 180 * H) for x, y in hole.coords], fill=0)
    a = np.asarray(mask.filter(ImageFilter.GaussianBlur(0.8)), np.float32)[..., None] / 255
    # the land a touch warmer and lighter than NE2's own, so the realms' colours read over it
    land = land * 0.82 + np.array([236, 226, 200], np.float32) * 0.18
    img = Image.fromarray(np.clip(land * a + sea * (1 - a), 0, 255).astype(np.uint8))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=94)
    return img


def _px(W, H):
    return lambda c: np.column_stack(((c[:, 0] + 180) / 360 * W, (90 - c[:, 1]) / 180 * H))


def texture(cfg, data, year, W=8192, log=print, highlight=None) -> pathlib.Path:
    """The world in `year` as an equirectangular JPG; cached by the year's map signature."""
    from .render import style_key
    H = W // 2
    pols, tops = state(cfg, data, year)
    sig = hashlib.sha1(("|".join(f"{p}:{shapely.area(g):.4f}" for p, g in sorted(pols.items())) +
                        f"|{style_key(cfg, data)}|{W}|{highlight}|v{VERSION}").encode()).hexdigest()[:10]
    out = paths(cfg).build / "world" / f"world_{year}_{sig}.jpg"
    if out.exists():
        return out
    from .render import Scene
    scene = _scene(cfg, data)
    img = base(cfg, W, log).convert("RGBA")
    tf = _px(W, H)
    fill = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fill)
    for pid, g in pols.items():
        r, gg, b = (int(v * 255) for v in scene.fill.get(pid, (0.7, 0.7, 0.7)))
        alpha = 205 if highlight in (None, data.top(pid), pid) else 70
        for poly in shapely.get_parts(shapely.transform(g, tf)):
            if poly.geom_type != "Polygon" or poly.area < 2:
                continue
            fd.polygon(list(poly.exterior.coords), fill=(r, gg, b, alpha))
            for hole in poly.interiors:
                fd.polygon(list(hole.coords), fill=(0, 0, 0, 0))
    img = Image.alpha_composite(img, fill)
    lines = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lines)
    s = W / 8192
    for pid, g in pols.items():                    # states inside a realm: a thin line
        for ring in _rings(shapely.transform(g, tf)):
            ld.line(ring, fill=(40, 34, 28, 150), width=max(1, int(2 * s)))
    for t, g in tops.items():                      # realms: a heavier frontier with a soft shadow
        for ring in _rings(shapely.transform(g, tf)):
            ld.line(ring, fill=(26, 22, 18, 235), width=max(2, int(5 * s)), joint="curve")
    shadow = lines.filter(ImageFilter.GaussianBlur(4 * s))
    img = Image.alpha_composite(Image.alpha_composite(img, shadow), lines)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out, quality=90)
    log(f"  globe texture {year}: {out.name}")
    return out


def _rings(g):
    for poly in shapely.get_parts(g):
        if poly.geom_type != "Polygon" or poly.area < 4:
            continue
        for ring in [poly.exterior, *poly.interiors]:
            c = list(ring.coords)
            # break rings where they jump the antimeridian
            seg = [c[0]]
            for p in c[1:]:
                if abs(p[0] - seg[-1][0]) > 1000:
                    if len(seg) > 1:
                        yield seg
                    seg = [p]
                else:
                    seg.append(p)
            if len(seg) > 1:
                yield seg


_SC: dict = {}


def _scene(cfg, data):
    if "s" not in _SC:
        from .render import Scene
        _SC["s"] = Scene(cfg, data)
    return _SC["s"]


def labels(cfg, data, year, min_km2=60000) -> list[dict]:
    """Where to set each realm's name in a year: [{id, en, ar, lon, lat, size}] (largest first)."""
    _p, tops = state(cfg, data, year)
    eq = geo.to_proj(cfg)
    out = []
    for t, g in tops.items():
        if g.is_empty:
            continue
        big = max(shapely.get_parts(g), key=lambda q: q.area)
        area = shapely.area(big) * 111.0 * 111.0 * np.cos(np.radians(big.centroid.y))
        if area < min_km2:
            continue
        pt = shapely.point_on_surface(big)
        pol = data.polity[t]
        out.append({"id": t, "en": pol.get("short") or pol["name"], "ar": pol.get("name_ar", ""),
                    "lon": round(pt.x, 3), "lat": round(pt.y, 3), "km2": int(area)})
    return sorted(out, key=lambda r: -r["km2"])


# -- for the live globe: fills, vector borders, a sharp relief patch over the stage -------------------

def fills(cfg, data, year, W=4096, log=print) -> pathlib.Path:
    """Only the realms' colours, on transparency (PNG): the engine lays them over the relief and draws
    the borders itself as vectors, so a soft texture still gives crisp frontiers."""
    from .render import style_key
    H = W // 2
    pols, _tops = state(cfg, data, year)
    sig = hashlib.sha1(("|".join(f"{p}:{shapely.area(g):.4f}" for p, g in sorted(pols.items())) +
                        f"|{style_key(cfg, data)}|{W}|v{VERSION}").encode()).hexdigest()[:10]
    out = paths(cfg).build / "world" / f"fills_{year}_{sig}.png"
    if out.exists():
        return out
    scene = _scene(cfg, data)
    img = Image.new("RGBA", (W * 2, H * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    tf = _px(W * 2, H * 2)
    for pid, g in pols.items():
        r, gg, b = (int(v * 255) for v in scene.fill.get(pid, (0.7, 0.7, 0.7)))
        for poly in shapely.get_parts(shapely.transform(g, tf)):
            if poly.geom_type != "Polygon" or poly.area < 2:
                continue
            d.polygon(list(poly.exterior.coords), fill=(r, gg, b, 255))
            for hole in poly.interiors:
                d.polygon(list(hole.coords), fill=(0, 0, 0, 0))
    img = img.resize((W, H), Image.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, optimize=True)
    log(f"  fills {year}: {out.name}")
    return out


def borders(cfg, data, year, tol=0.03) -> dict:
    """{'outer': [[lon, lat, ...] flat rings], 'inner': [...]}: realms' frontiers and the lines between
    the states of one realm, simplified for drawing every frame."""
    pols, tops = state(cfg, data, year)

    def rings(g):
        res = []
        for poly in shapely.get_parts(shapely.simplify(g, tol)):
            if poly.geom_type != "Polygon" or poly.area < 0.05:
                continue
            for ring in [poly.exterior, *poly.interiors]:
                c = np.round(np.asarray(ring.coords), 3)
                if len(c) > 3:
                    res.append(c.ravel().tolist())
        return res
    outer = [r for g in tops.values() for r in rings(g)]
    inner_lines = []
    for t, tg in tops.items():
        kids = [g for p, g in pols.items() if data.top(p) == t and p != t]
        if len(kids) > 1:
            edges = shapely.union_all([k.boundary for k in kids]).difference(tg.boundary.buffer(0.02))
            for ln in shapely.get_parts(shapely.simplify(shapely.line_merge(edges) if edges.geom_type == "MultiLineString" else edges, tol)):
                if ln.geom_type == "LineString" and ln.length > 0.2:
                    inner_lines.append(np.round(np.asarray(ln.coords), 3).ravel().tolist())
    return {"outer": outer, "inner": inner_lines}


def detail_base(cfg, bbox=(-25, -15, 85, 72), W=6144, log=print) -> pathlib.Path:
    """The relief at full Natural Earth II resolution over the stage, with the sea by depth: one patch,
    the same for every year, so the camera can come close without blurring."""
    w, s, e, n = bbox
    H = int(round(W * (n - s) / (e - w)))
    out = paths(cfg).build / "world" / f"detail_{W}x{H}_{w}_{s}_{e}_{n}.jpg"
    if out.exists():
        return out
    root = paths(cfg).root
    full = Image.open(root / "cache" / "naturalearth" / "NE2" / "NE2_HR_LC_SR_W_DR.tif").convert("RGB")
    FW, FH = full.size
    box = ((w + 180) / 360 * FW, (90 - n) / 180 * FH, (e + 180) / 360 * FW, (90 - s) / 180 * FH)
    land = np.asarray(full.crop(tuple(int(round(v)) for v in box)).resize((W, H), Image.LANCZOS), np.float32)
    dem_p = root / "build" / "solms" / "globe" / "globe_dem.tif"
    dem = Image.open(dem_p)
    DW, DH = dem.size
    dbox = ((w + 180) / 360 * DW, (90 - n) / 180 * DH, (e + 180) / 360 * DW, (90 - s) / 180 * DH)
    depth = np.clip(-np.asarray(dem.crop(tuple(int(round(v)) for v in dbox)).resize((W, H), Image.BILINEAR), np.float32), 0, None)
    st = cfg["style"]
    stops = sorted((int(k), _hex(v)) for k, v in (st.get("bathymetry") or {0: st["ocean"]}).items())
    sea = np.stack([np.interp(depth, [a for a, _ in stops], [c[i] for _, c in stops]) for i in range(3)], -1)
    mask = Image.new("L", (W, H), 0)
    dr = ImageDraw.Draw(mask)
    clip = shapely.box(w, s, e, n)
    for poly in shapely.get_parts(land_ll(cfg).intersection(clip)):
        if poly.geom_type != "Polygon":
            continue
        f = lambda c: [((x - w) / (e - w) * W, (n - y) / (n - s) * H) for x, y in c]
        dr.polygon(f(poly.exterior.coords), fill=255)
        for hole in poly.interiors:
            dr.polygon(f(hole.coords), fill=0)
    a = np.asarray(mask.filter(ImageFilter.GaussianBlur(0.8)), np.float32)[..., None] / 255
    land = land * 0.82 + np.array([236, 226, 200], np.float32) * 0.18
    Image.fromarray(np.clip(land * a + sea * (1 - a), 0, 255).astype(np.uint8)).save(out, quality=92)
    log(f"  detail relief {W}x{H} over {bbox}")
    return out
