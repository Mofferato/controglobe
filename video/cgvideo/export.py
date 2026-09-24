"""Write build/history.gpkg: every polity's shape for every span of unchanged borders.

This is the hand-off to QGIS (and to anyone else's GIS): one feature per polity per run of
years, with year_from and year_to, its colour and its parent. In QGIS, filter or style on
"year_from" <= @cg_year AND "year_to" >= @cg_year to see any year (see integrations/qgis).
"""

from __future__ import annotations

import geopandas as gpd
import shapely

from . import data as D
from . import geo
from .config import paths
from .render import Scene


def history(cfg: dict, data: D.Data) -> None:
    scene = Scene(cfg, data)
    rows = []
    for first, last, sig in D.runs(data):
        polities, tops = scene.state(data.matrix[data.year_index(first)])
        for pid, g in polities.items():
            p = data.polity[pid]
            rows.append({"year_from": first, "year_to": last, "polity_id": pid, "name": p["name"],
                         "name_ar": p.get("name_ar", ""), "parent": p.get("parent", ""), "top": data.top(pid),
                         "kind": p.get("kind", ""),
                         "color": "#%02x%02x%02x" % tuple(int(v * 255) for v in scene.fill[pid]),
                         "state": sig, "area_km2": round(g.area / 1e6), "geometry": shapely.make_valid(g)})
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=geo.crs(cfg))
    out = paths(cfg).history
    if out.exists():
        out.unlink()
    gdf.to_file(out, layer="polities", driver="GPKG")
    gdf.to_crs(geo.WGS84).to_file(out, layer="polities_wgs84", driver="GPKG")
    x0, x1, y0, y1 = geo.view_extent(cfg)
    gpd.GeoDataFrame({"name": ["video frame"]}, geometry=[shapely.box(x0, y0, x1, y1)],
                     crs=geo.crs(cfg)).to_file(out, layer="frame", driver="GPKG")
    print(f"  {len(gdf)} features over {len(D.runs(data))} runs -> {out}")
