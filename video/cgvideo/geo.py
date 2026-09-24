"""Projection and extent helpers shared by the mesh builder and the renderer."""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import Polygon, box

from .fetch import layer_path

WGS84 = "EPSG:4326"


def crs(cfg: dict) -> str:
    return cfg["projection"]


def to_proj(cfg: dict) -> Transformer:
    return Transformer.from_crs(WGS84, crs(cfg), always_xy=True)


def to_lonlat(cfg: dict) -> Transformer:
    return Transformer.from_crs(crs(cfg), WGS84, always_xy=True)


def project_points(cfg: dict, lons, lats):
    x, y = to_proj(cfg).transform(np.asarray(lons, float), np.asarray(lats, float))
    return np.asarray(x), np.asarray(y)


def bbox_polygon(cfg: dict, bbox, steps: int = 64) -> Polygon:
    """A lon/lat box, densified so it stays a faithful outline once projected."""
    w, s, e, n = bbox
    lon = np.concatenate([np.linspace(w, e, steps), np.full(steps, e), np.linspace(e, w, steps), np.full(steps, w)])
    lat = np.concatenate([np.full(steps, s), np.linspace(s, n, steps), np.full(steps, n), np.linspace(n, s, steps)])
    x, y = project_points(cfg, lon, lat)
    return shapely.make_valid(Polygon(np.column_stack([x, y])))


def view_extent(cfg: dict, width: int | None = None, height: int | None = None):
    """(x0, x1, y0, y1) in projected metres for the main frame."""
    width = width or cfg["frame"]["width"]
    height = height or cfg["frame"]["height"]
    cx, cy = project_points(cfg, [cfg["view"]["center"][0]], [cfg["view"]["center"][1]])
    h = float(cfg["view"]["height_km"]) * 1000.0
    w = h * width / height
    return float(cx[0] - w / 2), float(cx[0] + w / 2), float(cy[0] - h / 2), float(cy[0] + h / 2)


def view_lonlat_bbox(cfg: dict, margin_deg: float = 3.0):
    """A generous lon/lat box around the frame, for pre-clipping source data."""
    x0, x1, y0, y1 = view_extent(cfg)
    xs = np.linspace(x0, x1, 50)
    ys = np.linspace(y0, y1, 50)
    gx, gy = np.meshgrid(xs, ys)
    lon, lat = to_lonlat(cfg).transform(gx.ravel(), gy.ravel())
    return (float(lon.min() - margin_deg), float(lat.min() - margin_deg),
            float(lon.max() + margin_deg), float(lat.max() + margin_deg))


def read_ne(cfg: dict, name: str, bbox_ll=None) -> gpd.GeoDataFrame:
    path = layer_path(cfg, name)
    if not path.exists():
        raise SystemExit(f"missing {path.name}: run `python build.py fetch` first")
    gdf = gpd.read_file(f"zip://{path.resolve().as_posix()}", bbox=tuple(bbox_ll) if bbox_ll else None)
    if gdf.crs is None:
        gdf = gdf.set_crs(WGS84)
    return gdf


def clip_project(cfg: dict, gdf: gpd.GeoDataFrame, bbox_ll) -> gpd.GeoDataFrame:
    """Clip in lon/lat (with the caller's margin), then project."""
    gdf = gdf.copy()
    gdf["geometry"] = gdf.geometry.intersection(box(*bbox_ll))
    gdf = gdf[~gdf.geometry.is_empty]
    return gdf.to_crs(crs(cfg))
