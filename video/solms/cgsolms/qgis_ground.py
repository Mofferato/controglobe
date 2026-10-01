"""The ground of a phase, made in the open QGIS (run by `python solms.py ground N` through the
QGIS MCP socket, or by hand in QGIS's Python console).

    exec(open(r"<video>/solms/cgsolms/qgis_ground.py", encoding="utf8").read())
    solms_ground(FRAME, OUT)          # FRAME: cgsolms.frame.FRAME as a dict, OUT: build folder

Every step is a QGIS processing algorithm, so it can be watched and checked in the application:

  1. ETOPO 2022 at 15 arc-seconds (about 450 m) is mosaicked (gdal:buildvirtualraster) and
     projected onto the phase's frame three times (gdal:warpreproject, averaging): for the colour
     plate, for the terrain mesh and for the watersheds.
  2. The relief is shaded from several lights (gdal:hillshade, multidirectional).
  3. Natural Earth II's land cover (1:10m, without its relief or its modern waters) is projected
     onto the colour plate.
  4. GRASS r.watershed cuts the land into half-basins: the provinces, whose borders are crests and
     rivers, as the map rules want. GRASS r.water.outlet traces the named river basins the phase's
     polities are built from.
  5. The results are added to the project under "Controglobe · Solms <frame>", the provinces outlined
     over the shaded relief.

Results are cached in OUT; pass redo=True (or a list of step names) to redo them.
"""

import os
import pathlib


def _run(alg, params):
    import processing
    return processing.run(alg, params)


def solms_ground(FRAME, OUT, redo=False, show=True):
    import numpy as np
    from osgeo import gdal

    out = pathlib.Path(OUT)
    out.mkdir(parents=True, exist_ok=True)
    video = pathlib.Path(FRAME["video"])
    tiles = sorted((video / "cache" / "etopo" / "15s").glob("ETOPO_2022_v1_15s_*_surface.tif"))
    ne2 = video / "cache" / "naturalearth" / "NE2LC" / "NE2_HR_LC.tif"
    land_zip = video / "cache" / "naturalearth" / "ne_10m_land.zip"
    proj = FRAME["proj"]
    x0, y0, x1, y1 = FRAME["extent"]
    te = f"-te {x0:.3f} {y0:.3f} {x1:.3f} {y1:.3f}"
    crs = "PROJ4:" + proj
    log = []

    def want(name, path):
        return redo is True or (isinstance(redo, (list, tuple)) and name in redo) or not pathlib.Path(path).exists()

    vrt = out / "etopo15.vrt"
    if want("vrt", vrt):
        _run("gdal:buildvirtualraster", {"INPUT": [str(t) for t in tiles], "RESOLUTION": 1, "SEPARATE": False,
                                         "PROJ_DIFFERENCE": False, "ADD_ALPHA": False, "ASSIGN_CRS": None,
                                         "RESAMPLING": 0, "OUTPUT": str(vrt)})
        log.append(f"mosaicked {len(tiles)} ETOPO tiles")

    grids = {}
    for name, (w, h) in FRAME["grids"].items():
        path = out / f"dem_{name}.tif"
        if want("dem_" + name, path):
            _run("gdal:warpreproject", {"INPUT": str(vrt), "SOURCE_CRS": "EPSG:4326", "TARGET_CRS": crs,
                                        "RESAMPLING": 5, "DATA_TYPE": 6, "MULTITHREADING": True,
                                        "EXTRA": f"{te} -ts {w} {h}", "OUTPUT": str(path)})
            log.append(f"projected the relief to {w}x{h} for the {name}")
        grids[name] = path

    shade = out / "shade_tex.tif"
    if want("shade", shade):
        _run("gdal:hillshade", {"INPUT": str(grids["tex"]), "BAND": 1, "Z_FACTOR": FRAME.get("z_factor", 2.2),
                                "SCALE": 1.0, "AZIMUTH": 315.0, "ALTITUDE": 40.0, "COMPUTE_EDGES": True,
                                "ZEVENBERGEN": False, "COMBINED": False, "MULTIDIRECTIONAL": True,
                                "OUTPUT": str(shade)})
        log.append("shaded the relief (multidirectional)")

    cover = out / "landcover_tex.tif"
    if want("ne2", cover):
        w, h = FRAME["grids"]["tex"]
        _run("gdal:warpreproject", {"INPUT": str(ne2), "SOURCE_CRS": "EPSG:4326", "TARGET_CRS": crs,
                                    "RESAMPLING": 3, "DATA_TYPE": 1, "MULTITHREADING": True,
                                    "EXTRA": f"{te} -ts {w} {h}", "OUTPUT": str(cover)})
        log.append("projected Natural Earth II (land cover) onto the colour plate")

    # GRASS works on a longitude-latitude grid (as the atlases' tracer does): the half-basins and
    # the named basins are computed there and their polygons projected onto the frame after
    W, S, E, N = FRAME["ll_bbox"]
    res = FRAME.get("ws_res", 0.025)
    ll_region = f"{W},{E},{S},{N} [EPSG:4326]"
    dem_ll, land_ll = out / "dem_ll.tif", out / "dem_ll_land.tif"
    basins, drain, accum = out / "ll_basins.tif", out / "ll_drain.tif", out / "ll_accum.tif"
    if want("watershed", basins):
        _run("gdal:warpreproject", {"INPUT": str(vrt), "SOURCE_CRS": "EPSG:4326", "TARGET_CRS": "EPSG:4326",
                                    "RESAMPLING": 5, "TARGET_RESOLUTION": res, "TARGET_EXTENT": ll_region,
                                    "DATA_TYPE": 6, "OUTPUT": str(dem_ll)})
        land_mask = out / "land_ll.tif"
        _run("gdal:rasterize", {"INPUT": f"/vsizip/{land_zip.as_posix()}", "BURN": 1, "UNITS": 1,
                                "WIDTH": res, "HEIGHT": res, "EXTENT": ll_region, "NODATA": 0, "DATA_TYPE": 0,
                                "INIT": 0, "OUTPUT": str(land_mask)})
        _run("gdal:rastercalculator", {"INPUT_A": str(dem_ll), "BAND_A": 1, "INPUT_B": str(land_mask), "BAND_B": 1,
                                       "FORMULA": "where(B>0, A, -9999)", "NO_DATA": -9999, "RTYPE": 5,
                                       "OUTPUT": str(land_ll)})
        _run("grass:r.watershed", {"elevation": str(land_ll), "threshold": FRAME.get("threshold", 2400), "-s": True,
                                   "basin": str(basins), "drainage": str(drain), "accumulation": str(accum),
                                   "GRASS_REGION_PARAMETER": ll_region, "GRASS_REGION_CELLSIZE_PARAMETER": res})
        log.append(f"cut the land into half-basins (r.watershed, threshold {FRAME.get('threshold', 2400)} cells)")

    def project(src, dst, field):
        tmp = out / (dst.stem + "_ll.gpkg")
        for f in (tmp, dst):
            if f.exists():
                f.unlink()
        _run("gdal:polygonize", {"INPUT": str(src), "BAND": 1, "FIELD": field, "EIGHT_CONNECTEDNESS": False,
                                 "OUTPUT": str(tmp)})
        _run("native:reprojectlayer", {"INPUT": str(tmp), "TARGET_CRS": crs, "OUTPUT": str(dst)})
        try:
            tmp.unlink()
        except OSError:
            pass

    provinces = out / "provinces.gpkg"
    if want("provinces", provinces):
        project(basins, provinces, "basin")
        log.append("drew the provinces (gdal:polygonize) and projected them onto the frame")

    ds = gdal.Open(str(accum))
    acc = np.abs(ds.GetRasterBand(1).ReadAsArray().astype(float))
    gt = ds.GetGeoTransform()
    for name, (lon, lat, k) in FRAME["outlets"].items():
        vec = out / f"basin_{name}.gpkg"
        if not want("basin_" + name, vec):
            continue
        c, r = int((lon - gt[0]) / gt[1]), int((lat - gt[3]) / gt[5])
        win = acc[max(r - k, 0):r + k + 1, max(c - k, 0):c + k + 1]
        if win.size == 0 or not np.isfinite(win).any():
            log.append(f"{name}: no flow near its outlet; skipped")
            continue
        i, j = np.unravel_index(np.nanargmax(win), win.shape)
        px = gt[0] + (max(c - k, 0) + j + 0.5) * gt[1]
        py = gt[3] + (max(r - k, 0) + i + 0.5) * gt[5]
        ras = out / f"basin_{name}.tif"
        _run("grass:r.water.outlet", {"input": str(drain), "coordinates": f"{px},{py} [EPSG:4326]",
                                      "output": str(ras), "GRASS_REGION_PARAMETER": ll_region,
                                      "GRASS_REGION_CELLSIZE_PARAMETER": res})
        project(ras, vec, "v")
        log.append(f"traced the basin of the {name.replace('_', ' ')}")

    if show:
        _show(FRAME, out)
    print("\n".join(log) or "the ground is up to date")
    return log


def _show(FRAME, out):
    from qgis.core import (QgsFillSymbol, QgsProject, QgsRasterLayer, QgsSingleSymbolRenderer, QgsVectorLayer,
                           QgsCoordinateReferenceSystem)
    p = QgsProject.instance()
    group = f"Controglobe · Solms {FRAME['name']}"
    root = p.layerTreeRoot()
    grp = root.findGroup(group) or root.insertGroup(0, group)
    have = {l.source() for l in p.mapLayers().values()}

    def add(layer):
        if layer.isValid() and layer.source() not in have:
            p.addMapLayer(layer, False)
            grp.addLayer(layer)
        return layer

    prov = out / "provinces.gpkg"
    if prov.exists():
        lyr = add(QgsVectorLayer(str(prov), f"{FRAME['name']}: provinces (r.watershed)", "ogr"))
        lyr.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
            {"color": "0,0,0,0", "outline_color": "#7a1f12", "outline_width": "0.25"})))
    for f in ("shade_tex.tif", "landcover_tex.tif"):
        if (out / f).exists():
            add(QgsRasterLayer(str(out / f), f"{FRAME['name']}: {f.split('_')[0]}"))
    crs = QgsCoordinateReferenceSystem()
    crs.createFromProj(FRAME["proj"])
    p.setCrs(crs)
