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

def _draw_layers(ax, scene: Scene, polities: dict, tops: dict, s: float, clip=None):
    st = scene.cfg["style"]
    land = scene.land if clip is None else scene.land.intersection(clip)
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
    lakes = scene.lakes if clip is None else scene.lakes.intersection(clip)
    lp = geom_path(lakes)
    if lp is not None:
        ax.add_patch(PathPatch(lp, facecolor=st["ocean"], edgecolor=st["coast"], linewidth=0.6 * s, zorder=3))
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


def _place_labels(fig, ax, scene: Scene, polities: dict, tops: dict, W: int, H: int, extent,
                  placed: list, which: str, scale: float | None = None) -> list:
    """Country labels (which="top") or state and colony labels (which="sub"), largest first.

    A label that would overlap one already placed is dropped. A union or empire is labelled on
    its largest piece, and again only on pieces at least 15% that size (an exclave the size of
    Adharbaijan carries its own state label instead).
    """
    st = scene.cfg["style"]
    x0, x1, y0, y1 = extent
    px_per_m = W / (x1 - x0)
    s = scale or H / 2160
    renderer = fig.canvas.get_renderer()

    def try_label(geom, text, px, weight, style, alpha):
        parts = sorted(shapely.get_parts(geom), key=lambda g: -g.area)[:3]
        for n, part in enumerate(parts):
            if n and part.area < 0.15 * parts[0].area:
                break
            bx0, by0, bx1, by1 = part.bounds
            width_px = (bx1 - bx0) * px_per_m
            lines = text.split("\n")
            size = px
            longest = max(len(line) for line in lines)
            if 0.62 * size * longest > 0.9 * width_px and " " in lines[0] and len(lines) == 1:
                words = lines[0].split(" ")
                cut = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
                lines = [" ".join(words[:cut]), " ".join(words[cut:])]
                longest = max(len(line) for line in lines)
            if 0.62 * size * longest > 0.9 * width_px:
                size = 0.9 * width_px / (0.62 * longest)
            if size < 14 * s:
                continue
            try:
                pt = polylabel(part, tolerance=max(part.length / 400, 1000))
            except Exception:
                pt = part.representative_point()
            if not (x0 < pt.x < x1 and y0 < pt.y < y1):
                continue
            t = ax.text(pt.x, pt.y, "\n".join(lines), ha="center", va="center", fontsize=size * 72 / fig.dpi,
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
            try_label(g, _label_text(scene, t, True), px, "bold", "normal", 0.92)
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


def render_map(scene: Scene, row: np.ndarray, W: int, H: int, places: list[dict] | None = None,
               extent=None, px_scale: float | None = None, insets: bool = True) -> Image.Image:
    """One map. By default the configured frame; the motion pass passes a larger `extent`
    (a plate the camera moves over) and `px_scale` so text and lines keep their screen size."""
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

    def in_box(p, bb):
        return bb[0] <= p["lon"] <= bb[2] and bb[1] <= p["lat"] <= bb[3]

    _draw_layers(ax, scene, polities, tops, s)
    placed = _place_labels(fig, ax, scene, polities, tops, W, H, extent, [], "top", s)
    if show_places:
        main = [p for p in places if not any(in_box(p, i["bbox"]) for i in cfg.get("insets", []))]
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
            mine = [p for p in places if in_box(p, ins["bbox"])]
            _draw_places(fig, iax, scene, mine, [title.get_window_extent(fig.canvas.get_renderer())], s)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    img = Image.open(buf).convert("RGB")
    if img.size != (W, H):
        img = img.resize((W, H), Image.LANCZOS)
    return img


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
    scene_places = Scene(cfg, data).places if slots else []
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
