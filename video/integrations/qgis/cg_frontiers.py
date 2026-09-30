"""The atlases' frontiers, traced in QGIS on the real ground.

Run it in QGIS (Python console, or from Claude through the QGIS MCP server's execute_code):
    exec(open(r"C:/path/to/controglobe/video/integrations/qgis/cg_frontiers.py").read())
    cg_frontiers("africa")          # or "europe", "north-america", then "solms-america"

It does the geographic work in the open application, where it can be seen and checked:
  1. ETOPO 2022 is cut to the region, resampled to three arc-minutes and its sea masked (GDAL),
     and GRASS r.watershed and r.water.outlet compute the basins of the great rivers from it;
     these give the watershed frontiers (the Congo-Nile divide, the Alpine crest as the Po's rim).
  2. data/atlas/<region>-frontiers.yaml is traced on those basins and on Natural Earth's rivers
     (cgvideo/frontiers.py), and the land is cut into the nations of <region>-nations.csv.
  3. The frontiers and the nations are added to the project under "Controglobe · <Region>
     frontiers", styled in the atlas's colours over the shaded relief, and the frontiers are
     written to data/atlas/<region>-frontiers.geojson, which `python build.py atlas` draws.

The basins are computed once and kept in build/frontiers/; recompute=True redoes them. The
regions (their extent, their land and the mouths of their rivers) are in cgvideo/frontiers.py.
"""

import os
import pathlib
import sys

VIDEO_DIR = ""  # e.g. r"C:\Users\you\controglobe\video"



def _video_dir() -> pathlib.Path:
    for cand in (VIDEO_DIR, os.environ.get("CG_VIDEO_DIR", "")):
        if cand and (pathlib.Path(cand) / "build.py").exists():
            return pathlib.Path(cand)
    here = globals().get("__file__")
    if here:
        p = pathlib.Path(here).resolve().parents[2]
        if (p / "build.py").exists():
            return p
    for p in pathlib.Path.cwd().resolve().parents:
        if (p / "video" / "build.py").exists():
            return p / "video"
    raise RuntimeError("set VIDEO_DIR at the top of cg_frontiers.py to the controglobe/video folder")


def _basins(video: pathlib.Path, R: dict, recompute: bool = False) -> dict:
    """{name: shapely polygon} of each great river's basin in region R, from GRASS. An outlet is
    a point near the river's mouth (lon, lat), moved onto the strongest flow within a few cells
    (lon, lat, cells: a tributary's point is set upstream of its confluence, with a tight window)."""
    import numpy as np
    import processing
    import shapely
    from osgeo import gdal
    from qgis.core import QgsVectorLayer

    work = video / "build" / "frontiers" / R["work"]
    work.mkdir(parents=True, exist_ok=True)
    region = R["grass"] + " [EPSG:4326]"
    etopo = video / "cache" / "etopo" / "ETOPO_2022_v1_60s_N90W180_surface.tif"
    dem, land, drain, accum = (work / n for n in ("dem3.tif", "dem3_land.tif", "drain.tif", "accum.tif"))
    if recompute or not drain.exists():
        processing.run("gdal:warpreproject", {"INPUT": str(etopo), "SOURCE_CRS": "EPSG:4326", "TARGET_CRS": "EPSG:4326",
                                              "RESAMPLING": 5, "TARGET_RESOLUTION": 0.05, "TARGET_EXTENT": region,
                                              "OUTPUT": str(dem)})
        processing.run("gdal:rastercalculator", {"INPUT_A": str(dem), "BAND_A": 1, "FORMULA": "where(A>0, A, -9999)",
                                                 "NO_DATA": -9999, "RTYPE": 5, "OUTPUT": str(land)})
        processing.run("grass:r.watershed", {"elevation": str(land), "threshold": 2000, "-s": True,
                                             "drainage": str(drain), "accumulation": str(accum),
                                             "GRASS_REGION_PARAMETER": region, "GRASS_REGION_CELLSIZE_PARAMETER": 0.05})
    ds = gdal.Open(str(accum))
    acc = np.abs(ds.GetRasterBand(1).ReadAsArray().astype(float))
    gt = ds.GetGeoTransform()
    out = {}
    for name, at in R["outlets"].items():
        lon, lat, k = (*at, 7) if len(at) == 2 else at
        raster, vector = work / f"basin_{name}.tif", work / f"basin_{name}.gpkg"
        if recompute or not vector.exists():
            c, r = int((lon - gt[0]) / gt[1]), int((lat - gt[3]) / gt[5])
            win = acc[r - k:r + k + 1, c - k:c + k + 1]
            if not np.isfinite(win).any():
                print(f"    {name}: no flow near its outlet {lon}, {lat}; skipped")
                continue
            i, j = np.unravel_index(np.nanargmax(win), win.shape)
            x, y = gt[0] + (c - k + j + 0.5) * gt[1], gt[3] + (r - k + i + 0.5) * gt[5]
            processing.run("grass:r.water.outlet", {"input": str(drain), "coordinates": f"{x},{y} [EPSG:4326]",
                                                    "output": str(raster), "GRASS_REGION_PARAMETER": region,
                                                    "GRASS_REGION_CELLSIZE_PARAMETER": 0.05})
            if vector.exists():                 # polygonize adds to a file that is there: start clean
                vector.unlink()
            processing.run("gdal:polygonize", {"INPUT": str(raster), "BAND": 1, "FIELD": "v",
                                               "EIGHT_CONNECTEDNESS": False, "OUTPUT": str(vector)})
        layer = QgsVectorLayer(str(vector), name, "ogr")
        parts = [shapely.from_wkb(bytes(f.geometry().asWkb())) for f in layer.getFeatures() if f["v"]]
        out[name] = shapely.make_valid(shapely.union_all(parts))
    return out


def _read(path: str, where=None) -> list:
    import shapely
    from qgis.core import QgsVectorLayer
    layer = QgsVectorLayer(path, "tmp", "ogr")
    feats = layer.getFeatures() if where is None else [f for f in layer.getFeatures() if where(f)]
    return [(f, shapely.from_wkb(bytes(f.geometry().asWkb()))) for f in feats]


def cg_frontiers(region: str = "africa", recompute: bool = False, show: bool = True):
    import shapely
    import yaml

    video = _video_dir()
    if str(video) not in sys.path:
        sys.path.insert(0, str(video))
    import importlib
    import cgvideo.frontiers as fr
    importlib.reload(fr)

    ne = video / "cache" / "naturalearth"
    rivers = {}
    for f, g in _read(f"/vsizip/{(ne / 'ne_10m_rivers_lake_centerlines.zip').as_posix()}"):
        name = f["name"]
        if name and isinstance(name, str):
            rivers.setdefault(name, []).append(g)
    rivers = {k: shapely.union_all(v) for k, v in rivers.items()}
    # the marches of one nation (solms-america) are traced on their continent's basins
    basins = _basins(video, fr.REGIONS[fr.region_basins(region)], recompute)
    ground = fr.Ground(rivers, basins)

    store = video / "data" / "atlas"
    spec = yaml.safe_load((store / f"{region}-frontiers.yaml").read_text(encoding="utf8"))
    traced = fr.trace(spec, ground)
    fr.write_geojson(store / f"{region}-frontiers.geojson", traced, name=f"{region}-frontiers")

    land_ll = shapely.union_all([g for _, g in _read(f"/vsizip/{(ne / 'ne_10m_land.zip').as_posix()}")] +
                                [g for _, g in _read(f"/vsizip/{(ne / 'ne_10m_minor_islands.zip').as_posix()}")])
    held, unclaimed, rows, spec = fr.held_nations(region, shapely.make_valid(land_ll), store)
    missing = [r["key"] for r in rows if r["key"] not in held]
    print(f"{region}: {len(traced)} frontiers traced; {len(held)} nations; {len(unclaimed)} neutral pieces"
          + (f"; no ground for {', '.join(missing)}" if missing else ""))
    if show:
        _show(f"Controglobe · {region.capitalize()} frontiers", traced, held, rows, basins)
    return traced, held


def _show(GROUP, traced, held, rows, basins):
    tag = GROUP.split("·")[-1].strip().split()[0]            # Africa, Europe
    from qgis.core import (QgsFeature, QgsGeometry, QgsPalLayerSettings, QgsProject, QgsRendererCategory,
                           QgsCategorizedSymbolRenderer, QgsFillSymbol, QgsLineSymbol, QgsSingleSymbolRenderer,
                           QgsTextBufferSettings, QgsTextFormat, QgsVectorLayer, QgsVectorLayerSimpleLabeling)
    from qgis.PyQt.QtGui import QColor

    proj = QgsProject.instance()
    root = proj.layerTreeRoot()
    grp = root.findGroup(GROUP) or root.insertGroup(0, GROUP)
    for name in (f"{tag}: frontiers (traced)", f"{tag}: nations", f"{tag}: river basins (GRASS)"):
        for old in proj.mapLayersByName(name):
            proj.removeMapLayer(old)

    nat = QgsVectorLayer("MultiPolygon?crs=EPSG:4326&field=key:string(20)&field=name:string(40)&field=twin:string(40)",
                         f"{tag}: nations", "memory")
    feats = []
    for r in rows:
        if r["key"] not in held:
            continue
        f = QgsFeature(nat.fields())
        f.setGeometry(QgsGeometry.fromWkt(held[r["key"]].wkt))
        f["key"], f["name"], f["twin"] = r["key"], r["name"], r.get("twin", "")
        feats.append(f)
    nat.dataProvider().addFeatures(feats)
    cats = [QgsRendererCategory(r["key"], QgsFillSymbol.createSimple(
        {"color": r["colour"], "outline_color": "#ffffff", "outline_width": "0.4"}), r["name"]) for r in rows]
    nat.setRenderer(QgsCategorizedSymbolRenderer("key", cats))
    nat.setOpacity(0.72)
    lab = QgsPalLayerSettings()
    lab.isExpression = True
    lab.fieldName = "\"name\" || if(\"twin\" <> '', '\n' || \"twin\", '')"
    fmt = QgsTextFormat()
    fmt.setSize(9)
    buf = QgsTextBufferSettings()
    buf.setEnabled(True)
    buf.setSize(0.8)
    fmt.setBuffer(buf)
    lab.setFormat(fmt)
    nat.setLabeling(QgsVectorLayerSimpleLabeling(lab))
    nat.setLabelsEnabled(True)

    fl = QgsVectorLayer("LineString?crs=EPSG:4326&field=id:string(40)&field=follows:string(200)",
                        f"{tag}: frontiers (traced)", "memory")
    lf = []
    for t in traced:
        f = QgsFeature(fl.fields())
        f.setGeometry(QgsGeometry.fromWkt(t["line"].wkt))
        f["id"], f["follows"] = t["id"], t["follows"]
        lf.append(f)
    fl.dataProvider().addFeatures(lf)
    fl.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#2b2b2b", "width": "0.5"})))

    bl = QgsVectorLayer("MultiPolygon?crs=EPSG:4326&field=basin:string(20)", f"{tag}: river basins (GRASS)", "memory")
    bf = []
    for k, g in basins.items():
        f = QgsFeature(bl.fields())
        f.setGeometry(QgsGeometry.fromWkt(g.wkt))
        f["basin"] = k
        bf.append(f)
    bl.dataProvider().addFeatures(bf)
    bl.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
        {"color": "0,0,0,0", "outline_color": "#c0392b", "outline_width": "0.3", "outline_style": "dash"})))

    for layer in (bl, nat, fl):
        proj.addMapLayer(layer, False)
        grp.insertLayer(0, layer)
    bl.setName(f"{tag}: river basins (GRASS)")
    root.findLayer(bl.id()).setItemVisibilityChecked(False)
