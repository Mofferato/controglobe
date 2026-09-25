"""Terrain under the map: Natural Earth's shaded relief, projected into the video's projection.

QGIS does the projecting when it is installed: its headless processing tool runs GDAL's warper
(`qgis_process run gdal:warpreproject`) with a cubic kernel onto exactly the extent and pixel
size of the map being drawn. Without QGIS, a numpy resampler does the same job more slowly.
Each result is cached per extent and size in build/relief/, so a render projects it once.

The relief is then laid over the political colours as an overlay that only darkens the
shaded slopes and lightens the lit ones (render.relief_overlay), so borders and labels stay
crisp above it.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import zipfile

import numpy as np
from PIL import Image

from . import geo
from .config import paths
from .fetch import layer_path

SOURCE = "SR_HR"  # 1/60 degree shaded relief, 21600 x 10800, the whole world


def qgis_process() -> str | None:
    """QGIS's command-line processing tool, if QGIS is installed."""
    for name in ("qgis_process", "qgis_process-qgis-ltr", "qgis_process-qgis"):
        exe = shutil.which(name)
        if exe:
            return exe
    if sys.platform == "win32":
        hits = sorted(glob.glob(r"C:\Program Files\QGIS*\bin\qgis_process*.bat"))
        return hits[-1] if hits else None
    for p in ("/Applications/QGIS-LTR.app/Contents/MacOS/bin/qgis_process",
              "/Applications/QGIS.app/Contents/MacOS/bin/qgis_process"):
        if os.path.exists(p):
            return p
    return None


def _source(cfg: dict) -> pathlib.Path:
    """The relief GeoTIFF, unpacked once from its zip."""
    z = layer_path(cfg, SOURCE)
    if not z.exists():
        raise SystemExit(f"missing {z.name}: run `python build.py fetch` first")
    out = paths(cfg).cache / "naturalearth" / SOURCE
    hits = list(out.rglob("*.tif")) if out.exists() else []
    if hits:
        return hits[0]
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(z) as f:
        for n in f.namelist():
            if n.lower().endswith((".tif", ".tfw", ".prj")):
                f.extract(n, out)
    return next(out.rglob("*.tif"))


def _warp_qgis(qp: str, cfg: dict, tif: pathlib.Path, extent, W: int, H: int, dest: pathlib.Path):
    x0, x1, y0, y1 = extent
    job = {"inputs": {
        "INPUT": str(tif),
        "SOURCE_CRS": "EPSG:4326",
        "TARGET_CRS": "PROJ4:" + geo.crs(cfg),
        "RESAMPLING": 2,  # cubic
        "DATA_TYPE": 0,   # keep the source's 8-bit bytes
        "EXTRA": f"-te {x0:.3f} {y0:.3f} {x1:.3f} {y1:.3f} -ts {W} {H}",  # the tool adds -overwrite
        "OUTPUT": str(dest),
    }}
    try:
        p = subprocess.run([qp, "run", "gdal:warpreproject", "-"], input=json.dumps(job), text=True,
                           capture_output=True, timeout=1800)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"    QGIS warp failed ({exc}); using numpy")
        return None
    if p.returncode != 0 or not dest.exists():
        print(f"    QGIS warp failed (exit {p.returncode}); using numpy\n{p.stderr[-600:]}")
        return None
    Image.MAX_IMAGE_PIXELS = None
    arr = np.asarray(Image.open(dest).convert("L"))
    dest.unlink(missing_ok=True)
    return arr if arr.shape == (H, W) else None


def _warp_numpy(cfg: dict, tif: pathlib.Path, extent, W: int, H: int) -> np.ndarray:
    Image.MAX_IMAGE_PIXELS = None
    src = np.asarray(Image.open(tif).convert("L"), dtype=np.float32)
    SH, SW = src.shape
    x0, x1, y0, y1 = extent
    xs = x0 + (np.arange(W) + 0.5) * (x1 - x0) / W
    out = np.empty((H, W), np.uint8)
    inv = geo.to_lonlat(cfg)
    for r0 in range(0, H, 256):  # in bands, so a 4K plate never needs gigabytes
        r1 = min(H, r0 + 256)
        ys = y1 - (np.arange(r0, r1) + 0.5) * (y1 - y0) / H
        gx, gy = np.meshgrid(xs, ys)
        lon, lat = inv.transform(gx.ravel(), gy.ravel())
        u = (np.asarray(lon) + 180) / 360 * SW - 0.5
        v = (90 - np.asarray(lat)) / 180 * SH - 0.5
        u0 = np.floor(u).astype(int)
        v0 = np.floor(v).astype(int)
        fu, fv = u - u0, v - v0
        u0 %= SW
        u1 = (u0 + 1) % SW
        v0c, v1c = np.clip(v0, 0, SH - 1), np.clip(v0 + 1, 0, SH - 1)
        val = (src[v0c, u0] * (1 - fu) * (1 - fv) + src[v0c, u1] * fu * (1 - fv)
               + src[v1c, u0] * (1 - fu) * fv + src[v1c, u1] * fu * fv)
        out[r0:r1] = np.clip(val, 0, 255).reshape(r1 - r0, W).astype(np.uint8)
    return out


def relief(cfg: dict, extent, W: int, H: int) -> np.ndarray:
    """The shaded relief for exactly this extent and size, as an H x W uint8 array."""
    x0, x1, y0, y1 = extent
    key = hashlib.sha1(f"{SOURCE}|{geo.crs(cfg)}|{x0:.0f},{x1:.0f},{y0:.0f},{y1:.0f}|{W}x{H}".encode()).hexdigest()[:10]
    out = paths(cfg).build / "relief" / f"relief_{W}x{H}_{key}.png"
    if out.exists():
        return np.asarray(Image.open(out))
    out.parent.mkdir(parents=True, exist_ok=True)
    tif = _source(cfg)
    arr = None
    qp = qgis_process()
    if qp:
        print(f"    projecting the relief to {W}x{H} with QGIS (gdal:warpreproject)")
        arr = _warp_qgis(qp, cfg, tif, extent, W, H, out.with_name(out.stem + ".tmp.tif"))
    if arr is None:
        print(f"    projecting the relief to {W}x{H} with numpy")
        arr = _warp_numpy(cfg, tif, extent, W, H)
    tmp = out.with_name(out.stem + ".tmp.png")
    Image.fromarray(arr).save(tmp)
    os.replace(tmp, out)
    return arr


def overlay(shade: np.ndarray, strength: float = 0.5, highlight: float = 0.2) -> np.ndarray:
    """Relief as an RGBA overlay: black where the slope is shaded, white where it is lit, clear
    on the flat. The flat level is the relief's commonest value, so plains and sea stay clean."""
    hist = np.bincount(shade.ravel(), minlength=256)
    flat = float(np.argmax(hist))
    v = shade.astype(np.float32)
    dark = np.clip((flat - v) / max(flat * 0.75, 1), 0, 1) ** 0.9 * strength
    light = np.clip((v - flat) / max(255 - flat, 1), 0, 1) * highlight
    rgba = np.zeros(shade.shape + (4,), np.uint8)
    lit = light > dark
    rgba[..., :3] = np.where(lit[..., None], 255, 0).astype(np.uint8)
    rgba[..., 3] = (np.maximum(dark, light) * 255).astype(np.uint8)
    return rgba
