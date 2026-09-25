"""Draw the frames.

Two layers, so 2,500 years render in minutes rather than hours:
  map  one matplotlib drawing per distinct border state (a few hundred), cached in build/maps
  HUD  per year, drawn with Pillow over the cached map: year counter, era, captions
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import pathlib
import textwrap
from concurrent.futures import ProcessPoolExecutor

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import shapely  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.collections import LineCollection, PatchCollection  # noqa: E402
from matplotlib.patches import PathPatch  # noqa: E402
from matplotlib.path import Path as MPath  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from shapely.ops import polylabel  # noqa: E402

from . import data as D  # noqa: E402
from . import geo  # noqa: E402
from . import years as Y  # noqa: E402
from .config import paths  # noqa: E402

LIGHT_KINDS = {"territory", "protectorate"}
HATCH_KINDS = {"confederation"}


# -- colour and geometry helpers ----------------------------------------------------

def hex_rgb(c: str) -> tuple[float, float, float]:
    c = c.lstrip("#")
    return tuple(int(c[i : i + 2], 16) / 255 for i in (0, 2, 4))


def mix(c, other, t: float):
    a, b = hex_rgb(c) if isinstance(c, str) else c, hex_rgb(other) if isinstance(other, str) else other
    return tuple(x * (1 - t) + y * t for x, y in zip(a, b))


def geom_path(geom) -> MPath | None:
    verts, codes = [], []
    for poly in shapely.get_parts(geom):
        if poly.geom_type != "Polygon" or poly.is_empty:
            continue
        for ring in (poly.exterior, *poly.interiors):
            c = np.asarray(ring.coords)
            if len(c) < 4:
                continue
            verts.append(c)
            codes.append(np.array([MPath.MOVETO] + [MPath.LINETO] * (len(c) - 2) + [MPath.CLOSEPOLY]))
    if not verts:
        return None
    return MPath(np.vstack(verts), np.concatenate(codes))


def line_arrays(geom) -> list[np.ndarray]:
    out = []
    for part in shapely.get_parts(geom):
        if part.geom_type == "LineString" and not part.is_empty:
            out.append(np.asarray(part.coords))
        elif part.geom_type in ("MultiLineString", "GeometryCollection"):
            out.extend(line_arrays(part))
        elif part.geom_type in ("Polygon", "MultiPolygon"):
            out.extend(line_arrays(part.boundary))
    return out


def font_path(cfg: dict, bold: bool = False) -> str:
    hud = cfg["style"].get("hud", {})
    custom = hud.get("font_bold" if bold else "font")
    if custom and pathlib.Path(custom).exists():
        return custom
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return str(pathlib.Path(matplotlib.get_data_path()) / "fonts" / "ttf" / name)


def style_key(cfg: dict, data: D.Data) -> str:
    h = hashlib.sha1()
    h.update(json.dumps({k: cfg[k] for k in ("style", "view", "frame", "insets", "projection") if k in cfg},
                        sort_keys=True, default=str).encode())
    h.update(json.dumps(data.polities, sort_keys=True).encode())
    mesh = paths(cfg).mesh
    if mesh.exists():
        h.update(str(mesh.stat().st_mtime_ns).encode())
    return h.hexdigest()[:10]


# -- the scene: everything a map drawing needs, loaded once per process ----------------

class Scene:
    def __init__(self, cfg: dict, data: D.Data):
        self.cfg, self.data = cfg, data
        mesh = paths(cfg).mesh
        if not mesh.exists():
            raise SystemExit("no build/mesh.gpkg: run `python build.py mesh` first")
        regions = gpd.read_file(mesh, layer="regions")
        self.region_geom = dict(zip(regions["region_id"], regions.geometry))
        self.land = gpd.read_file(mesh, layer="view_land").geometry.iloc[0]
        self.lakes = gpd.read_file(mesh, layer="view_lakes").geometry.iloc[0]
        self.rivers = gpd.read_file(mesh, layer="view_rivers").geometry.iloc[0]
        self._coast_buf = None  # built on first use: only map drawing needs it, and it is heavy
        self.bathy = []         # (depth in metres, sea deeper than that), shallow first
        try:
            b = gpd.read_file(mesh, layer="view_bathy")
            self.bathy = sorted(zip((int(v) for v in b["depth"]), b.geometry), key=lambda t: t[0])
        except Exception:
            pass
        self._relief = {}
        # realms that never hold ground on the map themselves, only through possessions
        # (Ifriqiya, whose home is off the map, holding Qubrus)
        held = {data.polity_ids[int(p)] for p in np.unique(data.matrix) if p >= 0}
        self.offmap_realms = {p["polity_id"] for p in data.polities
                              if not p.get("parent") and p["polity_id"] not in held}
        self.places = []
        for p in data.places:
            x, y = geo.project_points(cfg, [float(p["lon"])], [float(p["lat"])])
            self.places.append({**p, "x": float(x[0]), "y": float(y[0]), "lon": float(p["lon"]),
                                "lat": float(p["lat"]), "start": Y.parse(p["start"]), "end": Y.parse(p["end"])})
        st = cfg["style"]
        self.fill: dict[str, tuple] = {}
        for p in data.polities:
            pid = p["polity_id"]
            color, cur, seen = p.get("color"), pid, set()
            while not color and data.polity[cur].get("parent") and cur not in seen:
                seen.add(cur)
                cur = data.polity[cur]["parent"]
                color = data.polity.get(cur, {}).get("color")
            color = color or "#bbbbbb"
            rgb = hex_rgb(color)
            if p.get("kind") in LIGHT_KINDS:
                rgb = mix(rgb, "#ffffff", float(st.get("territory_lighten", 0.45)))
            self.fill[pid] = rgb

    def relief_overlay(self, extent, W: int, H: int):
        """The shaded relief for this exact frame as an RGBA overlay (see cgvideo/relief.py),
        or None when style.relief is off or its source is missing."""
        rs = self.cfg["style"].get("relief") or {}
        if not float(rs.get("strength", 0)):
            return None
        key = (tuple(round(v) for v in extent), W, H)
        if key not in self._relief:
            from . import relief
            try:
                shade = relief.relief(self.cfg, extent, W, H)
            except SystemExit as exc:
                print(f"    no relief: {exc}")
                self._relief[key] = None
                return None
            self._relief = {key: relief.overlay(shade, float(rs.get("strength", 0.5)), float(rs.get("highlight", 0.2)))}
        return self._relief[key]

    @property
    def coast_buf(self):
        """The coastline widened a little, to keep country borders from being drawn along it."""
        if self._coast_buf is None:
            self._coast_buf = self.land.boundary.buffer(600)
            shapely.prepare(self._coast_buf)
        return self._coast_buf

    def places_for(self, year: int) -> list[dict]:
        return [p for p in self.places if p["start"] <= year <= p["end"]]

    def state(self, row: np.ndarray):
        """Polity geometries and top-level (union/empire) geometries for one map state."""
        members: dict[str, list] = {}
        for k, region_id in enumerate(self.data.region_ids):
            p = int(row[k])
            if p == D.UNCLAIMED or region_id not in self.region_geom:
                continue
            members.setdefault(self.data.polity_ids[p], []).append(self.region_geom[region_id])
        polities = {pid: shapely.union_all(gs) for pid, gs in members.items()}
        tops: dict[str, list] = {}
        for pid, g in polities.items():
            tops.setdefault(self.data.top(pid), []).append(g)
        tops = {t: shapely.union_all(gs) for t, gs in tops.items()}
        return polities, tops


# -- map layer ---------------------------------------------------------------------

def _draw_layers(ax, scene: Scene, polities: dict, tops: dict, s: float, clip=None, relief=None, extent=None):
    st = scene.cfg["style"]
    land = scene.land if clip is None else scene.land.intersection(clip)
    # the sea: a lighter shelf stepping down to a darker abyss
    tints = {int(k): v for k, v in (st.get("bathymetry") or {}).items()}
    for n, (depth, geom) in enumerate(scene.bathy):
        if depth in tints:
            bp = geom_path(geom if clip is None else geom.intersection(clip))
            if bp is not None:
                ax.add_patch(PathPatch(bp, facecolor=tints[depth], edgecolor="none", zorder=0.5 + n * 0.01))
    # a soft glow on the sea side of every coast (the land drawn next covers the inland half)
    glow = st.get("coast_glow") or {}
    if float(glow.get("alpha", 0)):
        coast = line_arrays(land.boundary)
        for wmul, amul in ((1.0, 1.0), (0.45, 1.4)):
            ax.add_collection(LineCollection(coast, colors=glow.get("color", "#7fc4e6"),
                                             linewidths=float(glow.get("width", 10)) * wmul * s,
                                             alpha=min(1.0, float(glow["alpha"]) * amul), zorder=0.9,
                                             joinstyle="round", capstyle="round"))
    p = geom_path(land)
    if p is not None:
        ax.add_patch(PathPatch(p, facecolor=st["land"], edgecolor="none", zorder=1))
    patches, colors, hatched = [], [], []
    for pid, g in polities.items():
        g = g if clip is None else g.intersection(clip)
        path = geom_path(g)
        if path is None:
            continue
        kind = scene.data.polity[pid].get("kind")
        if kind in HATCH_KINDS:
            hatched.append((path, scene.fill[pid]))
        else:
            patches.append(PathPatch(path))
            colors.append(scene.fill[pid])
    if patches:
        ax.add_collection(PatchCollection(patches, facecolors=colors, edgecolors="none", zorder=2))
    for path, rgb in hatched:
        ax.add_patch(PathPatch(path, facecolor=rgb, edgecolor=mix(rgb, "#000000", 0.3),
                               hatch="///", linewidth=0, zorder=2))
    if relief is not None and extent is not None:
        # terrain over the colours: shaded slopes darken, lit ones brighten, the flat stays clear
        ax.imshow(relief, extent=(extent[0], extent[1], extent[2], extent[3]), origin="upper",
                  interpolation="nearest", zorder=2.5)
        ax.set_xlim(extent[0], extent[1])
        ax.set_ylim(extent[2], extent[3])
    lakes = scene.lakes if clip is None else scene.lakes.intersection(clip)
    lp = geom_path(lakes)
    if lp is not None:
        lake = tints.get(0, st["ocean"])
        ax.add_patch(PathPatch(lp, facecolor=lake, edgecolor=st["coast"], linewidth=0.6 * s, zorder=3))
    rivers = scene.rivers if clip is None else scene.rivers.intersection(clip)
    ax.add_collection(LineCollection(line_arrays(rivers), colors=st["river"],
                                     linewidths=st["river_width"] * s, zorder=3, capstyle="round"))
    inner, outer = [], []
    for g in polities.values():
        inner.extend(line_arrays(g.boundary.difference(scene.coast_buf)))
    for g in tops.values():
        outer.extend(line_arrays(g.boundary.difference(scene.coast_buf)))
    if clip is not None:
        inner = line_arrays(shapely.intersection(shapely.MultiLineString(inner), clip)) if inner else []
        outer = line_arrays(shapely.intersection(shapely.MultiLineString(outer), clip)) if outer else []
    ax.add_collection(LineCollection(inner, colors=st["border"], linewidths=st["inner_border_width"] * s,
                                     alpha=0.55, zorder=4, joinstyle="round"))
    shadow = st.get("border_shadow") or {}
    if float(shadow.get("alpha", 0)):
        # a soft dark bed under each national frontier, so borders read as raised edges
        ax.add_collection(LineCollection(outer, colors="#000000",
                                         linewidths=st["border_width"] * float(shadow.get("width", 3)) * s,
                                         alpha=float(shadow["alpha"]), zorder=4.8, joinstyle="round",
                                         capstyle="round"))
    ax.add_collection(LineCollection(outer, colors=st["border"], linewidths=st["border_width"] * s,
                                     zorder=5, joinstyle="round", capstyle="round"))
    ax.add_collection(LineCollection(line_arrays(land.boundary), colors=st["coast"],
                                     linewidths=st["coast_width"] * s, zorder=5, joinstyle="round"))


def _label_text(scene: Scene, pid: str, top: bool) -> str:
    p = scene.data.polity[pid]
    text = p.get("short") or p["name"]
    text = text.upper() if top else text
    if scene.cfg["style"].get("arabic_labels") and p.get("name_ar"):
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display
            text += "\n" + get_display(arabic_reshaper.reshape(p["name_ar"]))
        except ImportError:
            pass
    return text


def _visible_piece(part, visible):
    """The piece of a polygon to put its label on in a moving shot, and the region its label
    must stay inside. `visible` is (always, anywhere): what every frame showing this map sees
    clear of the panel and the inset, and what at least one frame sees. The label goes where
    it is always seen if enough of the polygon is there, else where it is seen at all;
    (None, None) when no frame shows the polygon."""
    always, anywhere = visible
    for region, share in ((always, 0.2), (anywhere, 0.0)):
        if region is None or region.is_empty:
            continue
        piece = part.intersection(region)
        polys = [g for g in shapely.get_parts(piece) if g.geom_type == "Polygon" and not g.is_empty]
        if not polys:
            continue
        best = max(polys, key=lambda g: g.area)
        if best.area >= min(share * part.area, 6e10) and best.area > 0:
            return best, region
    return None, None


def _fit_label(pt, piece, region, land, size, wps, hps, px_per_m, min_size):
    """Place and size a label so that its whole box lies inside `region`, on its own polygon
    or on water rather than on its neighbours: (x, y, size), or None. wps and hps are the
    label's drawn width and height per pixel of font size. The largest size that has a good
    place wins; among places, the one most on its country and nearest the pole. A long name
    centred where its country is widest can otherwise run on under the infobox."""
    shapely.prepare(region)
    simple = piece.simplify(max(2000.0, 2.0 / px_per_m))
    shapely.prepare(simple)
    bx0, by0, bx1, by1 = piece.bounds
    diag = math.hypot(bx1 - bx0, by1 - by0) or 1.0
    cands = [(pt.x, pt.y)]
    for fy in (0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8):
        for fx in (0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8):
            cands.append((bx0 + (bx1 - bx0) * fx, by0 + (by1 - by0) * fy))
    cands = [c for k, c in enumerate(cands) if k == 0 or simple.contains(shapely.Point(c))]
    gx, gy = np.meshgrid(np.linspace(-0.46, 0.46, 11), np.linspace(-0.38, 0.38, 3))
    gx, gy = gx.ravel(), gy.ravel()
    best_any = None
    sz = size
    while sz >= min_size:
        w = wps * sz * 1.08 / px_per_m      # the halo and the collision margin
        h = hps * sz * 1.2 / px_per_m
        best = None
        for k, (x, y) in enumerate(cands):
            if not region.contains(shapely.box(x - w / 2, y - h / 2, x + w / 2, y + h / 2)):
                continue
            X, Y = x + gx * w, y + gy * h
            own = shapely.contains_xy(simple, X, Y).mean()
            wet = 1.0 - shapely.contains_xy(land, X, Y).mean() if land is not None else 0.0
            good = min(1.0, own + wet)
            score = own + 0.6 * wet - 0.35 * math.hypot(x - pt.x, y - pt.y) / diag + (0.05 if k == 0 else 0.0)
            if best is None or score > best[0]:
                best = (score, good, x, y, sz)
        if best is not None:
            if best[1] >= 0.7:
                return best[2:]
            if best_any is None or best[1] > best_any[1] + 0.1:
                best_any = best
        sz *= 0.9
    return best_any[2:] if best_any is not None and best_any[1] >= 0.45 else None


def _place_labels(fig, ax, scene: Scene, polities: dict, tops: dict, W: int, H: int, extent,
                  placed: list, which: str, scale: float | None = None, visible=None) -> list:
    """Country labels (which="top") or state and colony labels (which="sub"), largest first.

    A label that would overlap one already placed is dropped. A union or empire is labelled on
    its largest piece, and again only on pieces at least 15% that size (an exclave the size of
    Adharbaijan carries its own state label instead). With `visible` (see _visible_piece) each
    label is placed on the part of its polygon that the moving camera actually shows.
    """
    st = scene.cfg["style"]
    x0, x1, y0, y1 = extent
    px_per_m = W / (x1 - x0)
    s = scale or H / 2160
    renderer = fig.canvas.get_renderer()
    land = None
    if visible is not None:   # labels may lie over water, but not over their neighbours
        land = scene.land
        shapely.prepare(land)

    def measure(lines, weight, style):
        """A label's drawn width and height per pixel of font size (probed at 100 px)."""
        probe = ax.text(0, 0, "\n".join(lines), fontsize=100 * 72 / fig.dpi, fontweight=weight,
                        fontstyle=style, linespacing=1.0)
        e = probe.get_window_extent(renderer)
        probe.remove()
        return e.width / 100, e.height / 100

    def try_label(geom, text, px, weight, style, alpha, track=False):
        # tracked (letter-spaced) capitals for countries, the cartographer's convention for
        # large areas: hair spaces between the letters, about a quarter wider in all
        widen = 1.25 if track else 1.0
        parts = sorted(shapely.get_parts(geom), key=lambda g: -g.area)[:3]
        for n, part in enumerate(parts):
            if n and part.area < 0.15 * parts[0].area:
                break
            region = None
            if visible is not None:
                part, region = _visible_piece(part, visible)
                if part is None:
                    continue
            bx0, by0, bx1, by1 = part.bounds
            width_px = (bx1 - bx0) * px_per_m
            lines = text.split("\n")
            size = px
            longest = max(len(line) for line in lines) * widen
            split = None
            if " " in lines[0] and len(lines) == 1:
                words = lines[0].split(" ")
                cut = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
                split = [" ".join(words[:cut]), " ".join(words[cut:])]
            if 0.62 * size * longest > 0.9 * width_px and split:
                lines, split = split, None
                longest = max(len(line) for line in lines) * widen
            if 0.62 * size * longest > 0.9 * width_px:
                size = 0.9 * width_px / (0.62 * longest)
            if size < 14 * s:
                continue
            try:
                pt = polylabel(part, tolerance=max(part.length / 400, 1000))
            except Exception:
                pt = part.representative_point()
            lx, ly = pt.x, pt.y
            if track:
                lines = [" ".join(line) for line in lines]
                split = [" ".join(line) for line in split] if split else None
            if region is not None:
                # the whole label inside what the camera shows: slide or shrink it, or break a
                # one-line name in two, rather than let it run on under the infobox
                fit = _fit_label(pt, part, region, land, size, *measure(lines, weight, style), px_per_m, 14 * s)
                if fit is None and split:
                    fit = _fit_label(pt, part, region, land, size, *measure(split, weight, style), px_per_m, 14 * s)
                    if fit is not None:
                        lines = split
                if fit is None:
                    continue
                lx, ly, size = fit
            if not (x0 < lx < x1 and y0 < ly < y1):
                continue
            t = ax.text(lx, ly, "\n".join(lines), ha="center", va="center", fontsize=size * 72 / fig.dpi,
                        fontweight=weight, fontstyle=style, color=st["label_color"], alpha=alpha,
                        linespacing=1.0, zorder=8,
                        path_effects=[pe.withStroke(linewidth=max(2.5, size / 6) * 72 / fig.dpi * 1.5,
                                                    foreground=st["label_halo"], alpha=0.85)])
            bb = t.get_window_extent(renderer).expanded(1.04, 1.1)
            if any(bb.overlaps(o) for o in placed):
                t.remove()
                continue
            placed.append(bb)

    if which == "top":
        for t, g in sorted(tops.items(), key=lambda kv: -kv[1].area):
            area = g.area / 1e6
            if area < float(st["label_min_area_km2"]):
                continue
            px = min(92 * s, max(24 * s, 0.045 * math.sqrt(area) * s))
            text = _label_text(scene, t, True)
            kids = [pid for pid in polities if pid != t and scene.data.top(pid) == t]
            if t in scene.offmap_realms and len(kids) == 1:
                # a realm whose own land is off the map, seen through one possession, is named
                # by it with the realm in brackets, as a map writes "Greenland (Denmark)"
                text = f"{_label_text(scene, kids[0], True)} ({text})"
            try_label(g, text, px, "bold", "normal", 0.92, track=bool(st.get("label_tracking", True)))
    elif st.get("show_sub_labels", True):
        subs = [(pid, g) for pid, g in polities.items() if scene.data.top(pid) != pid]
        for pid, g in sorted(subs, key=lambda kv: -kv[1].area):
            area = g.area / 1e6
            if area < float(st["sub_label_min_area_km2"]):
                continue
            px = min(34 * s, max(17 * s, 0.028 * math.sqrt(area) * s))
            try_label(g, _label_text(scene, pid, False), px, "normal", "italic", 0.85)
    return placed


MARKERS = {  # kind: (matplotlib marker, face colour, size in px at 4K)
    "capital": ("s", "#a0141e", 17),
    "city": ("o", "#1d1d1d", 14),
    "fort": ("^", "#1d1d1d", 18),
    "district": ("*", "#d4aa32", 30),
    "battle": ("X", "#a0141e", 20),
}


def _draw_places(fig, ax, scene: Scene, places: list[dict], placed: list, s: float):
    """Markers always show; a label takes its preferred side, else the other, else is dropped."""
    st = scene.cfg["style"]
    renderer = fig.canvas.get_renderer()
    for p in places:
        marker, color, size = MARKERS.get(p["kind"], MARKERS["city"])
        (dot,) = ax.plot([p["x"]], [p["y"]], marker=marker, markersize=size * s * 72 / fig.dpi, color=color,
                         markeredgecolor="white", markeredgewidth=2.2 * s * 72 / fig.dpi, zorder=9,
                         linestyle="none")
        placed.append(dot.get_window_extent(renderer))
    for p in places:
        bold = p["kind"] in ("capital", "district")
        sides = ["right", "left"] if p.get("side", "right") != "left" else ["left", "right"]
        for side in sides:
            dx = 16 * s if side == "right" else -16 * s
            t = ax.annotate(p["name"], (p["x"], p["y"]), xytext=(dx * 72 / fig.dpi, 0), textcoords="offset points",
                            ha="left" if side == "right" else "right", va="center",
                            fontsize=24 * s * 72 / fig.dpi, fontweight="bold" if bold else "normal",
                            color="#161616", zorder=10,
                            path_effects=[pe.withStroke(linewidth=4.5 * s * 72 / fig.dpi * 1.5,
                                                        foreground=st["label_halo"], alpha=0.9)])
            bb = t.get_window_extent(renderer)
            if any(bb.overlaps(o) for o in placed):
                t.remove()
                continue
            placed.append(bb)
            break


def _inset_extent(cfg: dict, ins: dict, W: int, H: int):
    """The projected window of an inset, widened to the aspect of its rectangle."""
    bx0, by0, bx1, by1 = geo.bbox_polygon(cfg, ins["bbox"]).bounds
    rect = ins["rect"]
    want = (rect[2] * W) / (rect[3] * H)
    w_m, h_m = bx1 - bx0, by1 - by0
    if w_m / h_m < want:
        w_m = h_m * want
    else:
        h_m = w_m / want
    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
    return cx - w_m / 2, cx + w_m / 2, cy - h_m / 2, cy + h_m / 2


def _in_box(p, bb):
    return bb[0] <= p["lon"] <= bb[2] and bb[1] <= p["lat"] <= bb[3]


def render_map(scene: Scene, row: np.ndarray, W: int, H: int, places: list[dict] | None = None,
               extent=None, px_scale: float | None = None, insets: bool = True, labels: bool = True) -> Image.Image:
    """One map. By default the configured frame; the motion pass passes a larger `extent`
    (a plate the camera moves over) and `px_scale` so text and lines keep their screen size,
    and labels=False, because it draws the labels on a layer of their own (render_labels)."""
    cfg = scene.cfg
    st = cfg["style"]
    s = px_scale or H / 2160
    dpi = 100
    fig = plt.figure(figsize=(W / dpi, H / dpi), dpi=dpi)
    fig.patch.set_facecolor(st["ocean"])
    ax = fig.add_axes([0, 0, 1, 1])
    extent = extent or geo.view_extent(cfg, W, H)
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal")
    ax.axis("off")
    plt.rcParams["hatch.linewidth"] = 0.8 * s
    polities, tops = scene.state(row)
    places = places or []
    show_places = st.get("show_places", True)

    _draw_layers(ax, scene, polities, tops, s, relief=scene.relief_overlay(extent, W, H), extent=extent)
    if labels:
        placed = _place_labels(fig, ax, scene, polities, tops, W, H, extent, [], "top", s)
        if show_places:
            main = [p for p in places if not any(_in_box(p, i["bbox"]) for i in cfg.get("insets", []))]
            _draw_places(fig, ax, scene, main, placed, s)
        _place_labels(fig, ax, scene, polities, tops, W, H, extent, placed, "sub", s)
    for ins in (cfg.get("insets", []) if insets else []):
        ex0, ex1, ey0, ey1 = _inset_extent(cfg, ins, W, H)
        iax = fig.add_axes(ins["rect"])
        iax.set_xlim(ex0, ex1)
        iax.set_ylim(ey0, ey1)
        iax.set_facecolor(st["ocean"])
        iax.set_xticks([])
        iax.set_yticks([])
        for sp in iax.spines.values():
            sp.set_edgecolor(st["border"])
            sp.set_linewidth(2 * s)
        _draw_layers(iax, scene, polities, tops, s * 1.4, clip=shapely.box(ex0, ey0, ex1, ey1))
        title = iax.text(0.04, 0.94, ins["name"], transform=iax.transAxes, ha="left", va="top",
                         fontsize=26 * s * 72 / dpi, fontweight="bold", color=st["label_color"],
                         path_effects=[pe.withStroke(linewidth=4 * s, foreground=st["label_halo"])])
        if show_places:
            mine = [p for p in places if _in_box(p, ins["bbox"])]
            _draw_places(fig, iax, scene, mine, [title.get_window_extent(fig.canvas.get_renderer())], s)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    img = Image.open(buf).convert("RGB")
    if img.size != (W, H):
        img = img.resize((W, H), Image.LANCZOS)
    return img


def render_labels(scene: Scene, row: np.ndarray, W: int, H: int, places: list[dict] | None = None,
                  extent=None, px_scale: float | None = None, visible=None):
    """The labels of one map on a transparent layer of their own, for the motion cut: country
    and state names, and the place markers with their names. Returns (RGBA image, boxes), a box
    per label or marker as [x0, y0, x1, y1] in pixels from the top left, so each one can be
    faded on its own where the infobox, an inset or the frame edge would cut it. `visible`
    steers each label onto the part of its polygon the camera shows (see _visible_piece)."""
    cfg = scene.cfg
    st = cfg["style"]
    s = px_scale or H / 2160
    dpi = 100
    fig = plt.figure(figsize=(W / dpi, H / dpi), dpi=dpi)
    fig.patch.set_alpha(0.0)
    ax = fig.add_axes([0, 0, 1, 1])
    extent = extent or geo.view_extent(cfg, W, H)
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal")
    ax.axis("off")
    polities, tops = scene.state(row)
    placed = _place_labels(fig, ax, scene, polities, tops, W, H, extent, [], "top", s, visible=visible)
    if st.get("show_places", True) and places:
        main = [p for p in places if not any(_in_box(p, i["bbox"]) for i in cfg.get("insets", []))]
        _draw_places(fig, ax, scene, main, placed, s)
    _place_labels(fig, ax, scene, polities, tops, W, H, extent, placed, "sub", s, visible=visible)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, transparent=True)
    plt.close(fig)
    buf.seek(0)
    img = Image.open(buf).convert("RGBA")
    sx, sy = W / img.width, H / img.height
    if img.size != (W, H):
        img = img.resize((W, H), Image.LANCZOS)
    fh = fig.get_figheight() * dpi
    boxes = [[b.x0 * sx, (fh - b.y1) * sy, b.x1 * sx, (fh - b.y0) * sy] for b in placed]
    return img, boxes


# -- HUD layer ---------------------------------------------------------------------

class Hud:
    """Year counter, era, captions, era title cards and the watermark, drawn over a map."""

    def __init__(self, cfg: dict, W: int, H: int):
        self.cfg, self.W, self.H = cfg, W, H
        self.s = W / 3840
        self.reg = font_path(cfg)
        self.bold = font_path(cfg, bold=True)
        self._fonts = {}

    def font(self, size: float, bold: bool = False):
        key = (round(size), bold)
        if key not in self._fonts:
            self._fonts[key] = ImageFont.truetype(self.bold if bold else self.reg, max(8, round(size)))
        return self._fonts[key]

    def draw(self, base: Image.Image, slot: dict) -> Image.Image:
        cfg, s = self.cfg, self.s
        hud = cfg["style"]["hud"]
        img = base.convert("RGBA")
        over = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(over)
        panel = tuple(int(v * 255) for v in hex_rgb(hud["panel"])) + (int(255 * float(hud["panel_alpha"])),)
        text = tuple(int(v * 255) for v in hex_rgb(hud["text"])) + (255,)
        accent = tuple(int(v * 255) for v in hex_rgb(hud["accent"])) + (255,)
        # year and era, top left
        pad = 40 * s
        fy = self.font(170 * s, bold=True)
        fe = self.font(40 * s)
        ylabel = slot["label"]
        yw = d.textlength(ylabel, font=fy)
        ew = d.textlength(slot["era_name"], font=fe)
        bw = max(yw, ew, 520 * s) + 2 * pad
        d.rounded_rectangle([pad, pad, pad + bw, pad + 290 * s], radius=int(24 * s), fill=panel)
        d.text((2 * pad, pad + 20 * s), ylabel, font=fy, fill=text)
        d.text((2 * pad, pad + 222 * s), slot["era_name"], font=fe, fill=accent)

        # captions, bottom left, newest on top
        caps = slot.get("captions", [])
        if caps:
            fd, ft = self.font(30 * s, bold=True), self.font(36 * s)
            width = 900 * s
            blocks = []
            for c in caps:
                lines = textwrap.wrap(c["text"], width=40)
                blocks.append((c["date"], lines))
            h = sum(60 * s + 46 * s * len(lines) for _, lines in blocks) + 20 * s * (len(blocks) - 1) + 2 * pad
            top = self.H - 150 * s - h
            d.rounded_rectangle([pad, top, pad + width, top + h], radius=int(24 * s), fill=panel)
            y = top + pad
            for n, (date, lines) in enumerate(blocks):
                fade = 255 if n == 0 else 170
                d.text((2 * pad, y), date.upper(), font=fd, fill=accent[:3] + (fade,))
                y += 48 * s
                for line in lines:
                    d.text((2 * pad, y), line, font=ft, fill=text[:3] + (fade,))
                    y += 46 * s
                y += 32 * s

        # era title card
        if slot.get("era_start"):
            ft, fs = self.font(96 * s, bold=True), self.font(46 * s)
            era = slot["era_name"].upper()
            tw = d.textlength(era, font=ft)
            bw = tw + 160 * s
            cx = self.W / 2
            d.rounded_rectangle([cx - bw / 2, 60 * s, cx + bw / 2, 300 * s], radius=int(30 * s), fill=panel)
            d.text((cx, 150 * s), era, font=ft, fill=text, anchor="mm")
            d.text((cx, 245 * s), f"from {slot['label']}", font=fs, fill=accent, anchor="mm")

        # watermark
        fw = self.font(40 * s, bold=True)
        d.text((self.W - pad, self.H - pad), cfg.get("watermark", ""), font=fw, fill=(255, 255, 255, 170),
               anchor="rd", stroke_width=max(1, round(2 * s)), stroke_fill=(0, 0, 0, 120))
        fc = self.font(20 * s)
        d.text((self.W - pad, self.H - pad - 52 * s), "Coastlines and rivers: Natural Earth", font=fc,
               fill=(255, 255, 255, 150), anchor="rd")
        out = Image.alpha_composite(img, over).convert("RGB")
        return self.postfx(out)

    def postfx(self, img: Image.Image) -> Image.Image:
        """Optional vignette and grain (style.postfx); GIMP can do heavier finishing later."""
        fx = self.cfg["style"].get("postfx") or {}
        vig, grain = float(fx.get("vignette", 0)), float(fx.get("grain", 0))
        if not vig and not grain:
            return img
        a = np.asarray(img).astype(np.float32)
        if vig:
            if getattr(self, "_vig", None) is None or self._vig.shape[:2] != a.shape[:2]:
                yy, xx = np.mgrid[0 : a.shape[0], 0 : a.shape[1]]
                r = np.hypot((xx - a.shape[1] / 2) / (a.shape[1] / 2), (yy - a.shape[0] / 2) / (a.shape[0] / 2))
                self._vig = (1 - vig * np.clip(r - 0.55, 0, None) ** 1.6)[..., None].astype(np.float32)
            a *= self._vig
        if grain:
            rng = np.random.default_rng()
            a += rng.normal(0, 255 * grain, a.shape[:2])[..., None]
        return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


# -- orchestration -------------------------------------------------------------------

_G: dict = {}


def _init(cfg_path, W, H):
    from .config import load_config
    cfg = load_config(cfg_path)
    data = D.load(cfg)
    _G.update(cfg=cfg, data=data, scene=Scene(cfg, data), hud=Hud(cfg, W, H), W=W, H=H,
              key=style_key(cfg, data))


def _map_path(cfg, key, sig, W, H) -> pathlib.Path:
    return paths(cfg).maps / f"{W}x{H}_{key}_{sig}.png"


def map_signature(data: D.Data, places: list[dict], slot: dict) -> str:
    """The borders plus the places on show: equal signatures share one cached map."""
    names = "|".join(p["name"] for p in places)
    return data.state_signature(data.matrix[slot["index"]]) + hashlib.sha1(names.encode()).hexdigest()[:6]


def _job_map(slot: dict) -> str:
    cfg, data, scene = _G["cfg"], _G["data"], _G["scene"]
    row = data.matrix[slot["index"]]
    places = scene.places_for(slot["year"])
    out = _map_path(cfg, _G["key"], map_signature(data, places, slot), _G["W"], _G["H"])
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        img = render_map(scene, row, _G["W"], _G["H"], places)
        tmp = out.with_suffix(".tmp.png")
        img.save(tmp)
        os.replace(tmp, out)
    return str(out)


def _job_frame(args) -> str:
    slot, dest = args
    cfg, data, scene = _G["cfg"], _G["data"], _G["scene"]
    sig = map_signature(data, scene.places_for(slot["year"]), slot)
    base = Image.open(_map_path(cfg, _G["key"], sig, _G["W"], _G["H"]))
    _G["hud"].draw(base, slot).save(dest, compress_level=3)
    return dest


def frame_name(slot: dict) -> str:
    return f"{slot['index']:05d}_{slot['label'].replace(' ', '')}.png"


def render(cfg: dict, cfg_path, slots: list[dict], out_dir: pathlib.Path, scale: float = 1.0,
           workers: int | None = None) -> list[str]:
    W = int(round(cfg["frame"]["width"] * scale / 2) * 2)
    H = int(round(cfg["frame"]["height"] * scale / 2) * 2)
    out_dir.mkdir(parents=True, exist_ok=True)
    data = D.load(cfg)
    scene = Scene(cfg, data) if slots else None
    scene_places = scene.places if scene else []
    if scene:  # project the terrain once, here, before the workers each want it
        scene.relief_overlay(geo.view_extent(cfg, W, H), W, H)
    firsts = {}
    for s in slots:
        active = [p for p in scene_places if p["start"] <= s["year"] <= p["end"]]
        firsts.setdefault(map_signature(data, active, s), s)
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    print(f"  {len(firsts)} distinct maps for {len(slots)} years at {W}x{H}, {workers} workers")
    jobs = [(s, str(out_dir / frame_name(s))) for s in slots]
    if workers == 1:
        _init(str(cfg_path), W, H)
        for i in firsts.values():
            _job_map(i)
        return [_job_frame(j) for j in jobs]
    with ProcessPoolExecutor(workers, initializer=_init, initargs=(str(cfg_path), W, H)) as ex:
        for n, _ in enumerate(ex.map(_job_map, list(firsts.values())), 1):
            if n % 25 == 0 or n == len(firsts):
                print(f"    maps {n}/{len(firsts)}")
        done = []
        for n, p in enumerate(ex.map(_job_frame, jobs, chunksize=8), 1):
            done.append(p)
            if n % 250 == 0 or n == len(jobs):
                print(f"    frames {n}/{len(jobs)}")
        return done


def contact_sheet(frames: list[str], dest: pathlib.Path, cols: int = 4, thumb_w: int = 640) -> None:
    imgs = [Image.open(f) for f in frames]
    if not imgs:
        return
    tw = thumb_w
    th = round(imgs[0].height * tw / imgs[0].width)
    rows = math.ceil(len(imgs) / cols)
    sheet = Image.new("RGB", (cols * tw, rows * th), (20, 20, 20))
    for k, im in enumerate(imgs):
        sheet.paste(im.resize((tw, th), Image.LANCZOS), ((k % cols) * tw, (k // cols) * th))
    dest.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dest)
