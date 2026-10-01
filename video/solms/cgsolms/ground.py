"""The ground of a phase: the colour plate the camera looks at and the terrain it is draped on.

`python solms.py ground N` runs the geographic work in the open QGIS (qgis_ground.py: the relief
projected and shaded, Natural Earth II's land cover projected, the provinces and basins from GRASS),
then builds here, for the phase's skin:

  plate_<skin>.jpg   the colour plate (8192 x 5461 for Phase I): the land in its land cover, lit by the
                     relief of ETOPO 2022 at 15 arc-seconds; the sea tinted by its true depth, with
                     water lines along the coast; the natural lakes and the rivers (no reservoir, no
                     canal: the map is of the past); a grain under it all. GIMP finishes it in the
                     skin's grade (curves, a soft glow, an unsharp mask), in the open application.
  terrain.bin        the heights of the terrain mesh, int16 metres, sea and lakes flat at 0.
  provinces.json     the provinces (GRASS half-basins), in plate pixels, for the polities.

Everything is cached in build/solms/ground/<frame>/.
"""

from __future__ import annotations

import json
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import frame as F

Image.MAX_IMAGE_PIXELS = None

# the skins' grounds: sea by depth (m), land grade, waters
SKINS = {
    "marble": {
        "sea": [(0, "#4d9a9e"), (40, "#3e8a95"), (200, "#2f748a"), (1000, "#245e7a"), (2500, "#1d4e6a"),
                (4000, "#17425b"), (6000, "#12364b")],
        "lake": "#4d9a9e", "river": "#2f7792", "coast": "#1a2c31", "beach": "#e4d8b0",
        "lines": ((3.0, 0.12), (7.5, 0.07), (13.0, 0.04)), "shore_glow": 0.10,
        # land cover by Natural Earth II's hue (deg), from red rock and sand to the deep forest
        "biomes": [(28, "#bf8a5e"), (40, "#d6b27a"), (50, "#cfb27c"), (60, "#bba86e"), (72, "#9fa25f"),
                   (85, "#7f9450"), (98, "#5f8045"), (112, "#46703c"), (125, "#3d6638")],
        "keep": 0.22,                       # how much of Natural Earth's own colour stays
        "saturation": 1.3, "contrast": 1.08, "gain": 0.97, "warm": (1.03, 1.0, 0.95),
        "rock": "#8f8170", "snow": "#efece4",
        "grain": 0.04, "shade_dark": 0.78, "shade_lit": 0.30,
        # GIMP: a warm tone curve per channel, a soft glow, an unsharp mask
        "curves": {"value": [0.0, 0.0, 0.25, 0.2, 0.6, 0.6, 1.0, 0.98],
                   "red": [0.0, 0.02, 0.5, 0.53, 1.0, 1.0], "blue": [0.0, 0.0, 0.5, 0.46, 1.0, 0.95]},
        "glow": (6.0, 0.05), "unsharp": (1.4, 0.55),
    },
}

# Natural Earth calls many reservoirs lakes: of its North American supplement only these natural
# lakes are kept, and of the global set the reservoirs and these dammed or modern waters are dropped
DROP_LAKES = {"Salton Sea", "Lake Havasu", "Lake Walcott", "Lake Granby"}      # the Salton Sea formed in 1905
NATURAL_NA = {"Mono Lake", "Honey Lake", "Summer Lake", "Lake Abert", "Walker Lake", "Laguna Salada",
              "Laguna Babícora", "Laguna Santiaguillo", "Lago Cuitzeo", "Laguna Agua Brava", "Clear Lake",
              "Laguna Chila", "Laguna El Caimanero", "Caddo Lake", "Lago Petén Itzá", "Laguna de Bustillos",
              "Laguna de Guzmán", "Laguna de Santa María", "Laguna de Patos", "Laguna de Mayrán"}
ADD_LAKES = {                               # natural lakes Natural Earth no longer draws
    "Lake Texcoco": [(-99.15, 19.60), (-99.03, 19.62), (-98.93, 19.55), (-98.94, 19.43), (-99.0, 19.33),
                     (-99.06, 19.25), (-99.13, 19.27), (-99.16, 19.36), (-99.12, 19.47), (-99.17, 19.54)],
}


def _hex(c):
    return np.array([int(c[i:i + 2], 16) for i in (1, 3, 5)], np.float32)


class Plate:
    """Lon/lat to plate pixels for a frame."""

    def __init__(self, fr: dict, size):
        from pyproj import Transformer
        self.fr = fr
        self.W, self.H = size
        self.x0, self.y0, self.x1, self.y1 = fr["extent"]
        self.fwd = Transformer.from_crs("EPSG:4326", fr["proj"], always_xy=True)

    def px(self, x, y):
        """Projected metres to plate pixels."""
        return ((np.asarray(x) - self.x0) / (self.x1 - self.x0) * self.W,
                (self.y1 - np.asarray(y)) / (self.y1 - self.y0) * self.H)

    def ll(self, lon, lat):
        x, y = self.fwd.transform(lon, lat)
        return self.px(x, y)

    def geom(self, g):
        """A shapely geometry in projected metres to plate pixels."""
        import shapely
        return shapely.transform(g, lambda c: np.column_stack(self.px(c[:, 0], c[:, 1])))


def _hue(rgb):
    """Hue in degrees of an H x W x 3 float array."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(-1), rgb.min(-1)
    d = np.maximum(mx - mn, 1e-6)
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4))
    return (h * 60.0).astype(np.float32)


def _read_f(path):
    return np.asarray(Image.open(path), dtype=np.float32)


def _mask(geoms, W, H, k=2):
    """Polygons in plate pixels, rasterised k times larger and brought back down: 0..1."""
    import shapely
    img = Image.new("L", (W * k, H * k), 0)
    d = ImageDraw.Draw(img)
    for g in geoms:
        for p in shapely.get_parts(g):
            if p.geom_type != "Polygon" or p.is_empty:
                continue
            d.polygon([(x * k, y * k) for x, y in p.exterior.coords], fill=255)
            for h in p.interiors:
                d.polygon([(x * k, y * k) for x, y in h.coords], fill=0)
    return np.asarray(img.resize((W, H), Image.BOX), np.float32) / 255.0


def _waters(fr, plate: Plate):
    """The land, the natural lakes and the rivers, projected onto the plate."""
    import geopandas as gpd
    import shapely
    ne = F.VIDEO / "cache" / "naturalearth"
    W, S, E, N = fr["ll_bbox"]
    clip = shapely.box(W, S, E, N)
    land = gpd.read_file(f"/vsizip/{(ne / 'ne_10m_land.zip').as_posix()}")
    isl = gpd.read_file(f"/vsizip/{(ne / 'ne_10m_minor_islands.zip').as_posix()}")
    land = gpd.GeoDataFrame(geometry=list(land.geometry) + list(isl.geometry), crs="EPSG:4326")
    land = land[land.intersects(clip)].clip(clip).to_crs(fr["proj"])
    lakes = gpd.read_file(f"/vsizip/{(ne / 'ne_10m_lakes.zip').as_posix()}")
    lakes_na = gpd.read_file(ne / "lakes_na" / "ne_10m_lakes_north_america.shp")
    lk = gpd.GeoDataFrame(geometry=list(lakes.geometry) + list(lakes_na.geometry),
                          data={"featurecla": list(lakes.featurecla) + list(lakes_na.featurecla),
                                "name": list(lakes["name"]) + list(lakes_na["name"])}, crs="EPSG:4326")
    names = lk["name"].fillna("")
    keep_na = np.r_[np.ones(len(lakes), bool), lakes_na["name"].isin(NATURAL_NA).to_numpy()]
    lk = lk[keep_na & (lk.featurecla != "Reservoir") & ~names.isin(DROP_LAKES) & ~names.str.startswith("Presa")
            & lk.intersects(clip)]
    extra = gpd.GeoDataFrame(geometry=[shapely.Polygon(v) for v in ADD_LAKES.values()], crs="EPSG:4326")
    lk = gpd.GeoDataFrame(geometry=list(lk.geometry) + list(extra.geometry), crs="EPSG:4326").to_crs(fr["proj"])
    rv = gpd.read_file(f"/vsizip/{(ne / 'ne_10m_rivers_lake_centerlines.zip').as_posix()}")
    rna = gpd.read_file(ne / "rivers_na" / "ne_10m_rivers_north_america.shp")
    rv = rv[rv.intersects(clip) & (rv.featurecla != "Canal")]
    rna = rna[rna.intersects(clip) & (rna.featurecla != "Canal") & (rna.scalerank <= 11)]
    rivers = [(g, int(r)) for g, r in zip(rv.to_crs(fr["proj"]).geometry, rv.scalerank)]
    rivers += [(g, int(r)) for g, r in zip(rna.to_crs(fr["proj"]).geometry, rna.scalerank)]
    return ([plate.geom(g) for g in land.geometry], [plate.geom(g) for g in lk.geometry],
            [(plate.geom(g), r) for g, r in rivers])


def _rivers_raster(rivers, W, H):
    """Antialiased river lines (Agg), 0..1, widths by Natural Earth's scale rank."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    import shapely
    dpi = 100
    fig = plt.figure(figsize=(W / dpi, H / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")
    fig.patch.set_facecolor("black")
    segs, widths = [], []
    for g, rank in rivers:
        w = 2.6 if rank <= 2 else 2.0 if rank <= 4 else 1.5 if rank <= 6 else 1.1 if rank <= 8 else 0.75
        for part in shapely.get_parts(g):
            if part.geom_type == "LineString" and len(part.coords) > 1:
                segs.append(np.asarray(part.coords))
                widths.append(w)
    ax.add_collection(LineCollection(segs, linewidths=np.array(widths) * 72 / dpi, colors="white",
                                     capstyle="round", joinstyle="round", antialiased=True))
    fig.canvas.draw()
    a = np.asarray(fig.canvas.buffer_rgba())[..., 0].astype(np.float32) / 255.0
    plt.close(fig)
    return a


def _noise(W, H, seed=7, octaves=5):
    """A fractal grain, mean 0, for the painted feel."""
    rng = np.random.default_rng(seed)
    out = np.zeros((H, W), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        s = 2 ** (o + 4)
        small = rng.standard_normal((H // s + 2, W // s + 2)).astype(np.float32)
        big = np.asarray(Image.fromarray(small).resize((W + s, H + s), Image.BICUBIC))[:H, :W]
        out += amp * big
        tot += amp
        amp *= 0.55
    return out / tot


def build_plate(name: str = "phase1", skin: str = "marble", gimp: bool = True, log=print) -> dict:
    fr = F.frame(name)
    G = F.ground_dir(name)
    S = SKINS[skin]
    out = G / f"plate_{skin}.jpg"
    W, H = fr["grids"]["tex"]
    plate = Plate(fr, (W, H))
    raw = G / f"plate_{skin}_raw.png"
    if not raw.exists():
        log("  reading the relief, the land cover and the waters")
        from scipy.ndimage import distance_transform_edt, gaussian_filter
        land_g, lake_g, rivers = _waters(fr, plate)
        land = _mask(land_g, W, H)
        u8 = lambda x: (np.clip(x, 0, 1) * 255).astype(np.uint8)
        lake = u8(_mask(lake_g, W, H) * land)
        river = u8(_rivers_raster(rivers, W, H) * land)
        dist = distance_transform_edt(land < 0.5).astype(np.float32)
        edge = u8(np.clip(1 - np.abs(gaussian_filter(land, 0.8) - 0.5) * 3.2, 0, 1))
        land = u8(land)
        small = _noise(W // 4, H // 4)
        grain = np.asarray(Image.fromarray(small).resize((W, H), Image.BICUBIC), np.float32).astype(np.float16)
        del small
        elev = _read_f(G / "dem_tex.tif")
        shade = np.asarray(Image.open(G / "shade_tex.tif"), np.uint8)
        cover = np.asarray(Image.open(G / "landcover_tex.tif").convert("RGB"), np.uint8)
        on = land > 127
        flat = float(np.median(shade[on]))
        sflat = float(np.median(shade[~on]))
        stops = np.array([d for d, _ in S["sea"]], np.float32)
        cols = np.array([_hex(c) for _, c in S["sea"]])
        out_img = np.zeros((H, W, 3), np.uint8)
        for r0 in range(0, H, 512):
            r1 = min(H, r0 + 512)
            sl = slice(r0, r1)
            cv = cover[sl].astype(np.float32)
            sh = shade[sl].astype(np.float32)
            el = elev[sl]
            ld = land[sl].astype(np.float32)[..., None] / 255.0
            # the land: its cover, warmed and saturated, lit by the relief
            grey = cv.mean(-1, keepdims=True)
            own = (grey + (cv - grey) * S["saturation"]) * np.array(S["warm"], np.float32)
            hue = _hue(cv)
            bst = np.array([h for h, _ in S["biomes"]], np.float32)
            bcol = np.array([_hex(c) for _, c in S["biomes"]])
            painted = np.stack([np.interp(hue, bst, bcol[:, i]) for i in range(3)], -1)
            painted *= (0.9 + 0.35 * (grey / 255.0 - 0.85))      # keep the cover's light and shade
            rgb = painted * (1 - S["keep"]) + own * S["keep"]
            rgb = (128 + (rgb - 128) * S["contrast"]) * S["gain"]
            lit = np.clip((sh - flat) / max(255 - flat, 1), 0, 1)[..., None]
            dark = np.clip((flat - sh) / max(flat, 1), 0, 1)[..., None]
            rgb = rgb * (1 - S["shade_dark"] * dark) + (255 - rgb) * S["shade_lit"] * lit
            hi = np.clip((el - 2300) / 1400, 0, 1)[..., None] * 0.28
            rgb = rgb * (1 - hi) + _hex(S["rock"]) * hi
            sn = np.clip((el - 3700) / 600, 0, 1)[..., None] * 0.45
            rgb = rgb * (1 - sn) + _hex(S["snow"]) * sn
            # the sea: depth on the ramp, the sea floor's relief laid in lightly, water lines, a shore glow
            depth = np.clip(-el, 0, None)
            sea = np.stack([np.interp(depth, stops, cols[:, i]) for i in range(3)], -1).astype(np.float32)
            sea *= np.clip(1 - 0.35 * (sflat - sh) / 255.0, 0.7, 1.1)[..., None]
            dd = dist[sl]
            for rr, aa in S["lines"]:
                band = (aa * np.clip(1 - np.abs(dd - rr) / 1.0, 0, 1))[..., None]
                sea = sea * (1 - band) + _hex(S["beach"]) * band
            glow = (np.exp(-dd / 5.0) * S["shore_glow"])[..., None]
            sea = sea * (1 - glow) + _hex(S["beach"]) * glow
            rgb = rgb * ld + sea * (1 - ld)
            # the lakes, the rivers and the coast
            lk = lake[sl].astype(np.float32)[..., None] / 255.0
            rgb = rgb * (1 - lk) + _hex(S["lake"]) * lk
            rv = river[sl].astype(np.float32)[..., None] / 255.0 * 0.85
            rgb = rgb * (1 - rv) + _hex(S["river"]) * rv
            eg = edge[sl].astype(np.float32)[..., None] / 255.0 * 0.55
            rgb = rgb * (1 - eg) + _hex(S["coast"]) * eg
            rgb *= (1 + S["grain"] * grain[sl].astype(np.float32))[..., None]
            out_img[sl] = np.clip(rgb, 0, 255).astype(np.uint8)
        Image.fromarray(out_img).save(raw)
        del out_img, cover, elev, shade, dist, grain
        log(f"  composed the plate ({W}x{H})")
        land = land.astype(np.float32) / 255.0
        lake = lake.astype(np.float32) / 255.0
        # the terrain's heights and the land mask for the engine
        mw, mh = fr["grids"]["mesh"]
        mesh = _read_f(G / "dem_mesh.tif")
        lm = np.asarray(Image.fromarray((land * 255).astype(np.uint8)).resize((mw, mh), Image.BILINEAR)) > 127
        lk = np.asarray(Image.fromarray((lake * 255).astype(np.uint8)).resize((mw, mh), Image.BILINEAR)) > 127
        h = np.where(lm & ~lk, np.clip(mesh, 0, None), 0).astype(np.int16)
        h.tofile(G / "terrain.bin")
        json.dump({"w": mw, "h": mh, "max": int(h.max())}, open(G / "terrain.json", "w"))
    if not out.exists():
        _finish(raw, out, S, skin, gimp, log)
    small = G / f"plate_{skin}_2k.jpg"
    if not small.exists():
        Image.open(out).resize((2048, round(2048 * H / W)), Image.LANCZOS).save(small, quality=88)
    return {"plate": out, "small": small}


def _finish(raw, out, S, skin, gimp, log):
    """GIMP's grade, in the open application; the same in numpy without it."""
    from cgvideo.terrain import _gimp_live
    cmds = None
    if gimp:
        c = S["curves"]
        gx, ga = S["glow"]
        us, ua = S["unsharp"]
        cmds = [
            "from gi.repository import Gimp, Gio",
            f"cg_img = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path({str(raw)!r}))",
            "cg_layer = cg_img.get_layers()[0]",
            f"cg_layer.curves_spline(Gimp.HistogramChannel.VALUE, {c['value']!r})",
            f"cg_layer.curves_spline(Gimp.HistogramChannel.RED, {c['red']!r})",
            f"cg_layer.curves_spline(Gimp.HistogramChannel.BLUE, {c['blue']!r})",
            "cg_f = Gimp.DrawableFilter.new(cg_layer, 'gegl:softglow', '')",
            "cg_c = cg_f.get_config()",
            f"cg_c.set_property('glow-radius', {gx!r})",
            f"cg_c.set_property('brightness', {ga!r})",
            "cg_c.set_property('sharpness', 0.75)",
            "cg_layer.merge_filter(cg_f)",
            "cg_f = Gimp.DrawableFilter.new(cg_layer, 'gegl:unsharp-mask', '')",
            "cg_c = cg_f.get_config()",
            f"cg_c.set_property('std-dev', {us!r})",
            f"cg_c.set_property('scale', {ua!r})",
            "cg_layer.merge_filter(cg_f)",
            f"Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, cg_img, Gio.File.new_for_path({str(out)!r}), None)",
            f"cg_img.set_file(Gio.File.new_for_path({str(out)!r}))",
            "cg_img.clean_all()",
            "cg_shown = globals().setdefault('cg_shown', {})",
            f"cg_old = cg_shown.pop('solms-plate-{skin}', None)",
            "Gimp.Display.get_by_id(cg_old).delete() if cg_old and Gimp.Display.id_is_valid(cg_old) else None",
            f"cg_shown['solms-plate-{skin}'] = Gimp.Display.new(cg_img).get_id()",
            "Gimp.displays_flush()",
        ]
    reply = _gimp_live(cmds, timeout=1800) if cmds else None
    if reply is not None and reply.get("status") == "success" and out.exists():
        log("  graded in GIMP (curves, soft glow, unsharp mask)")
        return
    if reply is not None:
        log(f"  GIMP could not grade the plate ({str(reply)[:300]}); numpy does")
    from scipy.interpolate import PchipInterpolator
    from scipy.ndimage import gaussian_filter
    a = np.asarray(Image.open(raw), np.float32) / 255.0
    for ch, key in ((slice(None), "value"), (0, "red"), (2, "blue")):
        pts = S["curves"][key]
        xs, ys = pts[0::2], pts[1::2]
        a[..., ch] = PchipInterpolator(xs, ys)(a[..., ch])
    a = a + S["unsharp"][1] * (a - gaussian_filter(a, (S["unsharp"][0], S["unsharp"][0], 0)))
    Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)).save(out, quality=92)
    log("  graded with numpy (GIMP not open)")
