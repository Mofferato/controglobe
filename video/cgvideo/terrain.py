"""Terrain under the encyclopedia's maps, from a real elevation model, drawn by QGIS and
finished in GIMP.

Every redrawn map (the maps of al-Mashriq and the map of every year, the world maps, the two
atlases) stands on ETOPO 2022 (NOAA NCEI, public domain): land and sea floor on one grid of one
arc-minute, about 1.8 km. For each map frame:

  1. QGIS projects the grid onto exactly the frame's extent and pixels, averaging the cells
     under each pixel (gdal:warpreproject), and shades it from several lights at once
     (gdal:hillshade, multidirectional), exaggerated to suit the frame's scale.
  2. GIMP finishes the shading: a tone curve that deepens the shaded slopes and settles the
     flats, then an unsharp mask that crisps the ridges.
  3. From those the page gets two images: the relief, white on the flat and darker on shaded
     slopes, to multiply over the land; and the sea, tinted by its true depth on a smooth ramp,
     lightly shaded by the relief of the sea floor, with water lines along the coast.

When QGIS or GIMP is open with its MCP server started, the work is done in the open application:
the projected grid and its shading are added to the QGIS project under "Controglobe terrain",
and GIMP shows each shading it finished. Otherwise QGIS runs headless (qgis_process) and numpy
stands in for GIMP with the same curve and mask. Everything is cached in build/terrain/, keyed by
frame and settings, so a second build does no work.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import socket
import struct
import subprocess
import urllib.request

import numpy as np
import shapely
from PIL import Image, ImageDraw

from .config import paths

ETOPO = "ETOPO_2022_v1_60s_N90W180_surface.tif"
ETOPO_URL = ("https://www.ngdc.noaa.gov/mgg/global/relief/ETOPO2022/data/60s/60s_surface_elev_gtif/" + ETOPO)
QGIS_PORT, GIMP_PORT = 9876, 9877

# GIMP's finish: a tone curve (points in 0..1) and an unsharp mask (std-dev in pixels, amount)
CURVE = [(0.0, 0.0), (0.32, 0.22), (0.62, 0.66), (1.0, 1.0)]
UNSHARP = (1.1, 0.7)

# the sea by depth (metres): the maps' shelf tint at the shore, deepening on a smooth ramp
SEA_RAMP = [(0, "#e8f2f7"), (60, "#e1eef5"), (200, "#d8e9f2"), (1000, "#cce1ed"), (2500, "#c1d9e8"),
            (4500, "#b5d0e3"), (7000, "#a9c6dd")]
WATER_LINE = "#7fa6bf"


# -- the elevation model ----------------------------------------------------------------------

def etopo_path(cfg: dict):
    return paths(cfg).cache / "etopo" / ETOPO


def fetch(cfg: dict, force: bool = False) -> None:
    """Download ETOPO 2022 (444 MB, once)."""
    dest = etopo_path(cfg)
    if dest.exists() and not force:
        print(f"  have {dest.name}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    print(f"  get  {ETOPO_URL}")
    req = urllib.request.Request(ETOPO_URL, headers={"User-Agent": "controglobe-video/0.1"})
    with urllib.request.urlopen(req, timeout=300) as resp, open(tmp, "wb") as fh:
        while chunk := resp.read(1 << 20):
            fh.write(chunk)
    tmp.replace(dest)


# -- talking to the open applications ---------------------------------------------------------

def _qgis_live(kind: str, params: dict, timeout: float = 1800):
    """One command to a running QGIS's MCP server (length-prefixed JSON), or None if none runs."""
    try:
        s = socket.create_connection(("127.0.0.1", QGIS_PORT), timeout=2)
    except OSError:
        return None
    with s:
        s.settimeout(timeout)
        body = json.dumps({"type": kind, "params": params}).encode()
        s.sendall(struct.pack(">I", len(body)) + body)
        head = _recv(s, 4)
        reply = json.loads(_recv(s, struct.unpack(">I", head)[0]))
    return reply


def _recv(s, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("QGIS closed the connection")
        buf += chunk
    return buf


def _gimp_live(cmds: list[str], timeout: float = 600):
    """Python run inside a running GIMP by its MCP plug-in, or None if GIMP is not listening."""
    try:
        s = socket.create_connection(("127.0.0.1", GIMP_PORT), timeout=2)
    except OSError:
        return None
    with s:
        s.settimeout(timeout)
        s.sendall(json.dumps({"cmds": cmds}).encode())
        buf = b""
        while True:
            chunk = s.recv(1 << 16)
            if not chunk:
                break
            buf += chunk
            try:
                return json.loads(buf)
            except ValueError:
                continue
    return json.loads(buf) if buf else None


def _qgis(alg: str, params: dict, label: str) -> str:
    """Run a processing algorithm in the open QGIS if there is one, else headless."""
    reply = _qgis_live("execute_processing", {"algorithm": alg, "parameters": params, "timeout": 1800})
    if reply is not None and reply.get("status") == "success":
        return "QGIS"
    if reply is not None:
        print(f"    the open QGIS could not run {alg} ({str(reply.get('message'))[:200]}); running it headless")
    from .relief import qgis_process
    qp = qgis_process()
    if not qp:
        raise RuntimeError("QGIS is needed to draw the terrain: install QGIS or open it")
    p = subprocess.run([qp, "run", alg, "-"], input=json.dumps({"inputs": params}), text=True,
                       capture_output=True, timeout=3600)
    if p.returncode != 0:
        raise RuntimeError(f"{alg} failed in {label}:\n{p.stderr[-800:]}")
    return "qgis_process"


def _show_in_qgis(path, name: str) -> None:
    """Add a result to the open QGIS project, once, in a group of its own."""
    code = f"""
from qgis.core import QgsProject, QgsRasterLayer
p = QgsProject.instance()
if not any(l.source() == {str(path)!r} for l in p.mapLayers().values()):
    root = p.layerTreeRoot()
    grp = root.findGroup('Controglobe terrain') or root.insertGroup(0, 'Controglobe terrain')
    lyr = QgsRasterLayer({str(path)!r}, {name!r})
    if lyr.isValid():
        p.addMapLayer(lyr, False)
        grp.addLayer(lyr)
"""
    _qgis_live("execute_code", {"code": code, "timeout": 60}, timeout=90)


# -- one frame's terrain ----------------------------------------------------------------------

def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def elevation(cfg: dict, name: str, proj: str, extent, w: int, h: int):
    """The elevation model projected onto the frame: (path of the GeoTIFF, H x W metres)."""
    x0, x1, y0, y1 = extent
    key = hashlib.sha1(f"{ETOPO}|{proj}|{x0:.0f},{x1:.0f},{y0:.0f},{y1:.0f}|{w}x{h}".encode()).hexdigest()[:10]
    out = paths(cfg).build / "terrain" / f"{_slug(name)}_{key}_elevation.tif"
    if not out.exists():
        src = etopo_path(cfg)
        if not src.exists():
            fetch(cfg)
        out.parent.mkdir(parents=True, exist_ok=True)
        how = _qgis("gdal:warpreproject", {
            "INPUT": str(src), "SOURCE_CRS": "EPSG:4326", "TARGET_CRS": "PROJ4:" + proj,
            "RESAMPLING": 5,                        # average: every source cell under a pixel counts
            "DATA_TYPE": 0, "MULTITHREADING": True,
            "EXTRA": f"-te {x0:.3f} {y0:.3f} {x1:.3f} {y1:.3f} -ts {w} {h}",
            "OUTPUT": str(out)}, name)
        print(f"    {name}: elevation projected to {w}x{h} by {how} (gdal:warpreproject)")
        _show_in_qgis(out, f"{name}: elevation (ETOPO 2022)")
    Image.MAX_IMAGE_PIXELS = None
    return out, np.asarray(Image.open(out), dtype=np.float32)


def hillshade(cfg: dict, name: str, dem, z: float):
    """QGIS's multidirectional hillshade of the projected model, H x W bytes."""
    out = dem.with_name(dem.stem.replace("_elevation", "") + f"_shade_z{z:g}.tif")
    if not out.exists():
        how = _qgis("gdal:hillshade", {
            "INPUT": str(dem), "BAND": 1, "Z_FACTOR": z, "SCALE": 1.0, "AZIMUTH": 315.0, "ALTITUDE": 45.0,
            "COMPUTE_EDGES": True, "ZEVENBERGEN": False, "COMBINED": False, "MULTIDIRECTIONAL": True,
            "OUTPUT": str(out)}, name)
        print(f"    {name}: shaded by {how} (gdal:hillshade, multidirectional, z {z:g})")
        _show_in_qgis(out, f"{name}: hillshade (multidirectional)")
    return out


def finish(name: str, raw) -> np.ndarray:
    """GIMP's tone curve and unsharp mask on the shading; numpy's, the same, without GIMP."""
    key = hashlib.sha1(json.dumps([CURVE, UNSHARP]).encode()).hexdigest()[:8]
    out = raw.with_name(raw.stem + f"_finished_{key}.png")
    if out.exists():
        return np.asarray(Image.open(out).convert("L"))
    png = raw.with_suffix(".png")
    Image.open(raw).convert("L").save(png)
    flat = [v for pt in CURVE for v in pt]
    reply = _gimp_live([
        "from gi.repository import Gimp, Gio",
        f"cg_img = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path({str(png)!r}))",
        "cg_layer = cg_img.get_layers()[0]",
        f"cg_layer.curves_spline(Gimp.HistogramChannel.VALUE, {flat!r})",
        "cg_f = Gimp.DrawableFilter.new(cg_layer, 'gegl:unsharp-mask', '')",
        "cg_c = cg_f.get_config()",
        f"cg_c.set_property('std-dev', {UNSHARP[0]!r})",
        f"cg_c.set_property('scale', {UNSHARP[1]!r})",
        "cg_layer.merge_filter(cg_f)",
        f"Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, cg_img, Gio.File.new_for_path({str(out)!r}), None)",
        f"cg_img.set_file(Gio.File.new_for_path({str(out)!r}))",
        "cg_img.clean_all()",
        # one image a frame on show: the frame's last finish is closed (with its window) first
        "cg_shown = globals().setdefault('cg_shown', {})",
        f"cg_old = cg_shown.pop({_slug(name)!r}, None)",
        "Gimp.Display.get_by_id(cg_old).delete() if cg_old and Gimp.Display.id_is_valid(cg_old) else None",
        f"cg_shown[{_slug(name)!r}] = Gimp.Display.new(cg_img).get_id()",
        "Gimp.displays_flush()",
    ])
    if reply is not None and reply.get("status") == "success" and out.exists():
        print(f"    {name}: finished in GIMP (curves, unsharp mask)")
        return np.asarray(Image.open(out).convert("L"))
    if reply is not None:
        print(f"    {name}: GIMP could not finish the shading ({str(reply)[:200]}); numpy does")
    arr = _finish_numpy(np.asarray(Image.open(png).convert("L"), dtype=np.float32))
    Image.fromarray(arr).save(out)
    print(f"    {name}: finished with numpy (GIMP not open)")
    return arr


def _finish_numpy(a: np.ndarray) -> np.ndarray:
    from scipy.interpolate import PchipInterpolator
    from scipy.ndimage import gaussian_filter
    xs, ys = zip(*CURVE)
    a = PchipInterpolator(xs, ys)(a / 255.0) * 255.0
    a = a + UNSHARP[1] * (a - gaussian_filter(a, UNSHARP[0]))
    return np.clip(a, 0, 255).astype(np.uint8)


def _mask(geom, w: int, h: int, k: float = 1.0, dx: float = 0.0, dy: float = 0.0) -> np.ndarray:
    """A shape in map pixels, rasterised at k times: True inside."""
    img = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(img)
    for p in shapely.get_parts(geom):
        if p.geom_type != "Polygon" or p.is_empty:
            continue
        draw.polygon([((x - dx) * k, (y - dy) * k) for x, y in p.exterior.coords], fill=255)
        for hole in p.interiors:
            draw.polygon([((x - dx) * k, (y - dy) * k) for x, y in hole.coords], fill=0)
    return np.asarray(img) > 127


def _ramp(depth: np.ndarray) -> np.ndarray:
    stops = np.array([d for d, _ in SEA_RAMP], np.float32)
    cols = np.array([[int(c[i:i + 2], 16) for i in (1, 3, 5)] for _, c in SEA_RAMP], np.float32)
    return np.stack([np.interp(depth, stops, cols[:, i]) for i in range(3)], axis=-1)


def _uri(img: Image.Image, quality: int) -> str:
    buf = io.BytesIO()
    img.save(buf, "WEBP", quality=quality, method=6)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()


def images(cfg: dict, name: str, proj: str, extent, w: int, h: int, land, *, z: float,
           gain: float = 1.0, halo: float = 14.0, floor: float = 0.3,
           lines=((3.0, .38), (7.0, .24), (12.5, .13)),
           outside: np.ndarray | None = None, quality=(48, 58)) -> tuple[str, str]:
    """The relief and the sea of one frame, as WebP data URIs. `land` is the frame's land in the
    terrain images' own pixels; `outside` (True where the frame has no ground, as past a world
    map's edge) is left white."""
    dem, elev = elevation(cfg, name, proj, extent, w, h)
    shade = finish(name, hillshade(cfg, name, dem, z)).astype(np.float32)
    on_land = _mask(land, w, h)
    ground = ~on_land if outside is None else ~on_land & ~outside
    # the relief, to multiply over the land: the flat a shade under white (`halo`), slopes lit by
    # the lights rising to white and those turned from them darkening, so a ridge has two sides;
    # the sea stays white
    vals = shade[on_land] if on_land.any() else shade.ravel()
    flat = float(np.argmax(np.bincount(vals.astype(np.uint8).ravel(), minlength=256)))
    white = max(float(np.percentile(vals, 99.5)), flat + 1)
    lit = np.clip((shade - flat) / (white - flat), 0, 1)
    tone = np.where(shade >= flat, 255 - halo * (1 - lit),
                    (255 - halo) - np.clip((flat - shade) * gain, 0, 255) * (255 - halo) / 255)
    tone[~on_land] = 255
    relief = Image.fromarray(tone.astype(np.uint8), "L").convert("RGB")
    # the sea: its depth on the ramp, the sea floor's shading laid in lightly, then water lines
    rgb = _ramp(np.clip(-elev, 0, None))
    sea_flat = float(np.median(shade[ground])) if ground.any() else flat
    rgb *= np.clip(1 - floor * (sea_flat - shade) / 255.0, 0.6, 1.08)[..., None]
    if lines:
        from scipy.ndimage import distance_transform_edt
        dist = distance_transform_edt(~on_land)
        ink = np.array([int(WATER_LINE[i:i + 2], 16) for i in (1, 3, 5)], np.float32)
        for r, alpha in lines:
            a = alpha * np.clip(1 - np.abs(dist - r) / 0.8, 0, 1)
            rgb = rgb * (1 - a[..., None]) + ink * a[..., None]
    if outside is not None:
        rgb[outside] = 255
    sea = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")
    return _uri(relief, quality[0]), _uri(sea, quality[1])
