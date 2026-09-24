"""Controglobe in QGIS: open the mesh and the history, scrub through the years, draw precise
borders, and (optionally) export frames with QGIS cartography instead of matplotlib.

Run it once per QGIS session, either
  - by hand: Plugins > Python Console > Show Editor > open this file > Run Script, or
  - from Claude through the QGIS MCP server (jjsantos01/qgis_mcp), tool `execute_code`:
        exec(open(r"C:/path/to/controglobe/video/integrations/qgis/cg_qgis.py").read())

Then, in the same console (or further execute_code calls):
  cg_load()                       add every layer, styled, and zoom to the video frame
  cg_year(1776)                   show the map for one year
  cg_export(1760, 1870, r"C:/out", step=1, width=3840, height=2160)

Before running: `python build.py mesh` and `python build.py export-gis` in the video folder.
If the video folder is not found automatically, set CG_VIDEO_DIR (or edit VIDEO_DIR below).

Editing borders precisely (then re-run `python build.py mesh`):
  custom_lines  draw a line along a wadi, a watershed or an escarpment: cells split along it
                and regions stop at it. Snapping to the cells layer is switched on for you.
  overrides     draw a polygon and set its region_id: every cell whose centre falls inside
                is forced into that region. This is how a frontier is placed to the kilometre.
"""

import os
import pathlib

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFillSymbol,
    QgsLineSymbol,
    QgsMapRendererParallelJob,
    QgsMapSettings,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsProject,
    QgsProperty,
    QgsSingleSymbolRenderer,
    QgsSnappingConfig,
    QgsSymbolLayer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsTolerance,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor, QFont

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
    raise RuntimeError("set CG_VIDEO_DIR (or VIDEO_DIR in this script) to the controglobe/video folder")


def _iface():
    try:
        from qgis.utils import iface
        return iface
    except ImportError:
        return None


def _enum(owner, old_name, new_path):
    """QGIS 3.30+ moved many enums into scoped classes; accept either spelling."""
    if hasattr(owner, old_name):
        return getattr(owner, old_name)
    obj = owner
    for part in new_path.split("."):
        obj = getattr(obj, part)
    return obj


FILL_COLOR = _enum(QgsSymbolLayer, "PropertyFillColor", "Property.FillColor")
LABEL_SHOW = _enum(QgsPalLayerSettings, "Show", "Property.Show")

_LAYERS = {}


def _add(uri: str, name: str, provider: str = "ogr") -> QgsVectorLayer:
    layer = QgsVectorLayer(uri, name, provider)
    if not layer.isValid():
        raise RuntimeError(f"could not open {uri}")
    QgsProject.instance().addMapLayer(layer)
    _LAYERS[name] = layer
    return layer


def _labels(layer, field, size=9, bold=False, italic=False, show_expr=None):
    fmt = QgsTextFormat()
    font = QFont("Arial", size)
    font.setBold(bold)
    font.setItalic(italic)
    fmt.setFont(font)
    fmt.setSize(size)
    buf = QgsTextBufferSettings()
    buf.setEnabled(True)
    buf.setSize(1.0)
    buf.setColor(QColor("white"))
    fmt.setBuffer(buf)
    pal = QgsPalLayerSettings()
    pal.fieldName = field
    pal.setFormat(fmt)
    if show_expr:
        pal.dataDefinedProperties().setProperty(LABEL_SHOW, QgsProperty.fromExpression(show_expr))
    layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
    layer.setLabelsEnabled(True)


def cg_load(year: int = 1776):
    """Add the mesh, the history and the editable border layers, styled like the video."""
    v = _video_dir()
    mesh, hist = v / "build" / "mesh.gpkg", v / "build" / "history.gpkg"
    if not mesh.exists() or not hist.exists():
        raise RuntimeError("run `python build.py mesh` and `python build.py export-gis` first")

    land = _add(f"{mesh}|layername=view_land", "land")
    land.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
        {"color": "#e9e2cf", "outline_color": "#101c27", "outline_width": "0.2"})))

    pol = _add(f"{hist}|layername=polities", "polities (this year)")
    sym = QgsFillSymbol.createSimple({"color": "#cccccc", "outline_color": "#2e2a26", "outline_width": "0.35"})
    sym.symbolLayer(0).setDataDefinedProperty(FILL_COLOR, QgsProperty.fromField("color"))
    pol.setRenderer(QgsSingleSymbolRenderer(sym))
    _labels(pol, "name", size=10, bold=True, show_expr='"parent" = \'\' OR "parent" IS NULL')

    rivers = _add(f"{mesh}|layername=view_rivers", "rivers")
    rivers.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#4a7ba3", "width": "0.3"})))

    cells = _add(f"{mesh}|layername=cells", "cells (snap target)")
    cells.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
        {"style": "no", "outline_color": "#80808060", "outline_width": "0.1"})))
    regions = _add(f"{mesh}|layername=regions", "regions")
    regions.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
        {"style": "no", "outline_color": "#7a2a8a", "outline_width": "0.4"})))
    _labels(regions, "region_id", size=8, italic=True)
    seeds = _add(f"{mesh}|layername=region_seeds", "region seeds")
    seeds.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple(
        {"name": "circle", "color": "#7a2a8a", "size": "1.6"})))

    lines = _add(str(v / "data" / "custom_lines.geojson"), "custom_lines (edit me)")
    lines.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#d7191c", "width": "0.8"})))
    ov = _add(str(v / "data" / "overrides.geojson"), "overrides (edit me)")
    ov.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
        {"color": "#fdae6140", "outline_color": "#e66101", "outline_width": "0.6", "style": "b_diagonal"})))

    frame = _add(f"{hist}|layername=frame", "video frame")
    frame.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
        {"style": "no", "outline_color": "#000000", "outline_width": "0.6", "outline_style": "dash"})))

    proj = QgsProject.instance()
    proj.setCrs(QgsCoordinateReferenceSystem(pol.crs()))
    try:
        _snapping(proj, (cells, regions, lines))
    except Exception as exc:  # snapping is a convenience; the layers are usable without it
        print(f"snapping not configured ({exc}); enable it from the Snapping toolbar")

    cg_year(year)
    iface = _iface()
    if iface:
        iface.mapCanvas().setExtent(frame.extent())
        iface.mapCanvas().refresh()
    print("Controglobe layers loaded. Edit 'custom_lines' or 'overrides', save, then `python build.py mesh`.")


def _snapping(proj, layers):
    try:
        from qgis.core import Qgis
        kind = Qgis.SnappingType.Vertex | Qgis.SnappingType.Segment
        mode = Qgis.SnappingMode.AdvancedConfiguration
    except AttributeError:
        kind = QgsSnappingConfig.VertexFlag | QgsSnappingConfig.SegmentFlag
        mode = QgsSnappingConfig.AdvancedConfiguration
    snap = proj.snappingConfig()
    snap.setEnabled(True)
    snap.setMode(mode)
    for layer in layers:
        snap.setIndividualLayerSettings(
            layer, QgsSnappingConfig.IndividualLayerSettings(True, kind, 12, QgsTolerance.Pixels, 0.0, 0.0))
    proj.setSnappingConfig(snap)


def cg_year(year: int):
    """Show the polities of one year (negative = BCE)."""
    layer = _LAYERS.get("polities (this year)")
    if layer is None:
        raise RuntimeError("run cg_load() first")
    layer.setSubsetString(f'"year_from" <= {int(year)} AND "year_to" >= {int(year)}')
    iface = _iface()
    if iface:
        iface.mapCanvas().refreshAllLayers()
    return layer.featureCount()


def cg_export(first: int, last: int, out_dir: str, step: int = 1, width: int = 3840, height: int = 2160):
    """Render years with QGIS's own renderer: an alternative to `build.py render`, useful when
    you want QGIS cartography (a hillshade underlay, blending modes) in the frames."""
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    order = ["polities (this year)", "rivers", "land"]
    layers = [_LAYERS[n] for n in order if n in _LAYERS]
    extent = _LAYERS["video frame"].extent()
    for y in range(first, last + 1, step):
        if y == 0:
            continue
        cg_year(y)
        ms = QgsMapSettings()
        ms.setLayers(layers)
        ms.setDestinationCrs(_LAYERS["polities (this year)"].crs())
        ms.setOutputSize(QSize(width, height))
        ms.setExtent(extent)
        ms.setBackgroundColor(QColor("#22364a"))
        job = QgsMapRendererParallelJob(ms)
        job.start()
        job.waitForFinished()
        name = f"{-y}BCE" if y < 0 else str(y)
        job.renderedImage().save(str(out / f"qgis_{name}.png"), "png")
    print(f"exported {first}..{last} to {out}")


print("cg_qgis ready: cg_load(), cg_year(year), cg_export(first, last, out_dir)")
