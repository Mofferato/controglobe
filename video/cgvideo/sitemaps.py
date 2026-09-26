"""The encyclopedia's maps of al-Mashriq, drawn on the video's own borders.

Every map of al-Mashriq in the encyclopedia (ten of them, in both editions) shares one frame:
the video's projection, an azimuthal equal-area projection centred on 46.5E 25N, at 5.089 km a
pixel on a 920 x 620 canvas. `python build.py sitemaps` redraws the ground of each from the mesh
the video is drawn on: the sea by depth, the land, Natural Earth's shaded relief (projected by
QGIS), rivers and lakes, the map's coloured areas, the frontiers of the map's year and the coast.
So the encyclopedia and the video share one set of borders, and they follow rivers, wadis,
escarpments and the mesh's hand-drawn edges, never a ruled line.

What each map says (its arrows, battles, towns, labels, legend and footnote) is the page's own
and is kept as it is, in either language: only the ground under it is redrawn. The Arabic
edition's maps get the same ground under their Arabic labels.

config/sitemaps.yaml says, for each map, which year's frontiers it draws and which regions (or,
for the physical map, which mesh cells) take which of its legend's colours. `python build.py
sitemaps --bootstrap` wrote that file from the schematic maps by reading which colour covered
each region; the file is now the source, and a region can be moved between colours by hand.
"""

from __future__ import annotations

import base64
import io
import re
from collections import defaultdict

import geopandas as gpd
import numpy as np
import shapely
import yaml
from PIL import Image

from . import data as D
from .config import ROOT, paths

SITE = ROOT.parent
CONFIG = ROOT / "config" / "sitemaps.yaml"
PAGES = ("united-states-of-arabia.html", "history-of-the-united-states-of-arabia.html",
         "nabataean-unification.html")

# the frame every map of al-Mashriq shares (fitted to the pages' towns to under a pixel)
W, H = 920, 620
K, X0, Y0 = 1.96512669e-4, 388.884, 280.755
VIEW = shapely.box(-6, -6, W + 6, H + 6)
TOL = 0.5               # simplification, in map pixels (a pixel is 5 km)
RELIEF_SCALE = 1.5      # relief pixels per map pixel

INK = {
    "sea": "#e3eff5", "depths": {200: "#d7e8f1", 1000: "#cce1ed", 3000: "#c1d9e8", 5000: "#b7d1e3"},
    "land": "#ede7d8", "coast": "#3f4e55", "river": "#5a90bd", "lake": "#dbebf3",
    "frontier": "#262d31", "neighbour": "#8d8577", "inner": "#262d31", "category": "#ffffff",
    "names": "#5f7079",
}

# the schematic maps' footnotes and captions, in both editions, now that their areas are drawn
TEXT_FIXES = [
    ("Schematic. Arabia is one of a small number", "Arabia is one of a small number"),
    ("Schematic constitutional reference map. Internal lines are indicative, not surveyed boundaries.",
     "Constitutional reference map of the twenty-four states and their boundaries."),
    ('aria-label="Schematic reference map of the', 'aria-label="Reference map of the'),
    ("<figcaption>Schematic map of the twenty-four states", "<figcaption>Map of the twenty-four states"),
    ("Schematic. The Interregnum had no single authority", "The Interregnum had no single authority"),
    ("Schematic; areas are drawn around reference points, not surveyed. Only the Hindustani",
     "Only the Hindustani"),
    ("Schematic. The Continental Army", "The Continental Army"),
    ("Schematic. Areas are drawn around each state&rsquo;s reference point and are not surveyed boundaries.",
     "Each area is shaded by the date it joined the Union."),
    ("Schematic. Areas are drawn around each state's reference point and are not surveyed boundaries.",
     "Each area is shaded by the date it joined the Union."),
    ("Schematic. Areas are drawn around each state’s reference point and are not surveyed boundaries.",
     "Each area is shaded by the date it joined the Union."),
    ("Schematic. Eleven states seceded", "Eleven states seceded"),
    ("Schematic, about 440&nbsp;BCE. No imperial power", "About 440&nbsp;BCE. No imperial power"),
    ("Schematic. Areas are drawn around reference points and are not surveyed frontiers. White circles",
     "White circles"),
    ("تخطيطية. العربية من البلدان القليلة", "العربية من البلدان القليلة"),
    ("خريطة دستورية مرجعية تخطيطية. والخطوط الداخلية إرشادية لا حدودًا مسّاحة.",
     "خريطة دستورية مرجعية للولايات الأربع والعشرين وحدودها."),
    ('aria-label="خريطة مرجعية تخطيطية لولايات', 'aria-label="خريطة مرجعية لولايات'),
    ("<figcaption>خريطة تخطيطية للولايات", "<figcaption>خريطة للولايات"),
    ("تخطيطية. لم تكن لحقبة الفترة", "لم تكن لحقبة الفترة"),
    ("تخطيطية؛ رُسمت المساحات حول نقاط مرجعية لا بالمساحة. ولم تُستوطن", "لم تُستوطن"),
    ("تخطيطية. لم يمسك الجيش القاري", "لم يمسك الجيش القاري"),
    ("تخطيطية. رُسمت المساحات حول نقطة مرجعية لكل ولاية وليست حدودًا مسّاحة.",
     "ظُلِّلت كل منطقة بحسب تاريخ انضمامها إلى الاتحاد."),
    ("تخطيطية. انفصلت إحدى عشرة ولاية", "انفصلت إحدى عشرة ولاية"),
    ("تخطيطية، نحو 440&nbsp;ق.م. لم تعد", "نحو 440&nbsp;ق.م. لم تعد"),
    ("تخطيطية. رُسمت المساحات حول نقاط مرجعية وليست حدودًا مسّاحة. والدوائر البيضاء",
     "الدوائر البيضاء"),
]

# what --bootstrap assumes about each schematic map (after that, config/sitemaps.yaml rules)
BOOT = {
    ("united-states-of-arabia.html", 0): {"id": "physical", "frontiers": 2026, "unit": "cell", "inner": None,
                                          "relief": 0.8, "fill_opacity": 0.72},
    ("united-states-of-arabia.html", 1): {"id": "states", "frontiers": 2026, "unit": "polity", "inner": "dashed"},
    ("united-states-of-arabia.html", 2): {"id": "energy", "frontiers": 2026, "unit": "polity", "inner": "solid",
                                          "keep": ["#f2c96b"]},
    ("history-of-the-united-states-of-arabia.html", 0): {"id": "interregnum", "frontiers": 1400, "unit": "polity"},
    ("history-of-the-united-states-of-arabia.html", 1): {"id": "colonial", "frontiers": 1750, "unit": "polity"},
    ("history-of-the-united-states-of-arabia.html", 2): {"id": "revolution", "frontiers": 1776, "unit": "polity"},
    ("history-of-the-united-states-of-arabia.html", 3): {"id": "growth", "frontiers": 1900, "unit": "region",
                                                         "inner": None, "category_lines": True},
    ("history-of-the-united-states-of-arabia.html", 4): {"id": "civil-war", "frontiers": 1862, "unit": "polity"},
    ("nabataean-unification.html", 0): {"id": "nabatu-440bce", "frontiers": -440, "unit": "polity"},
    ("nabataean-unification.html", 1): {"id": "nabataean-growth", "frontiers": -170, "unit": "region",
                                        "inner": None, "category_lines": True},
}

TAG = re.compile(r"<(/?)([a-zA-Z]+)([^>]*?)(/?)>")


# -- geometry to SVG ------------------------------------------------------------------------

def to_svg(geom):
    """Projected metres to the frame's pixels."""
    return shapely.affinity.affine_transform(geom, [K, 0, 0, -K, X0, Y0])


def _num(t: int) -> str:
    """A coordinate held in tenths of a pixel, written as short as SVG allows."""
    s = f"{t / 10:.1f}".rstrip("0").rstrip(".")
    if s in ("-0", ""):
        s = "0"
    return s.replace("0.", ".", 1) if s.startswith(("0.", "-0.")) else s


def _join(nums: list[str]) -> str:
    out = ""
    for n in nums:
        out += n if (not out or n.startswith("-") or out[-1] in "Mlz") else " " + n
    return out


def _ring_d(coords, closed: bool) -> str:
    pts = np.round(np.asarray(coords)[:, :2] * 10).astype(np.int64)
    if len(pts) > 1:
        keep = np.ones(len(pts), bool)
        keep[1:] = np.any(pts[1:] != pts[:-1], axis=1)
        pts = pts[keep]
    if closed and len(pts) > 1 and (pts[0] == pts[-1]).all():
        pts = pts[:-1]
    if len(pts) < (3 if closed else 2):
        return ""
    d = np.diff(pts, axis=0)
    s = "M" + _join([_num(pts[0][0]), _num(pts[0][1])]) + "l" + _join([_num(v) for v in d.ravel()])
    return s + ("z" if closed else "")


def path_d(geom) -> str:
    """Any shapely geometry as compact relative SVG path data."""
    parts = []
    for g in shapely.get_parts(geom) if geom is not None and not geom.is_empty else []:
        if g.geom_type == "Polygon":
            parts.append(_ring_d(g.exterior.coords, True))
            parts.extend(_ring_d(r.coords, True) for r in g.interiors)
        elif g.geom_type in ("LineString", "LinearRing"):
            parts.append(_ring_d(g.coords, False))
        elif g.geom_type.startswith("Multi") or g.geom_type == "GeometryCollection":
            parts.append(path_d(g))
    return "".join(p for p in parts if p)


def _clean(geom, tol=TOL, min_area=0.6):
    """Clip to the frame, simplify and drop specks too small to see."""
    geom = shapely.intersection(shapely.make_valid(geom), VIEW)
    geom = shapely.simplify(geom, tol, preserve_topology=True)
    if geom.geom_type in ("Polygon", "MultiPolygon", "GeometryCollection"):
        polys = [p for p in shapely.get_parts(geom) if p.geom_type == "Polygon" and p.area >= min_area]
        return shapely.MultiPolygon(polys) if polys else shapely.Polygon()
    return geom


# -- the pages ------------------------------------------------------------------------------

def _children(svg: str):
    """Top-level children of an <svg> element: (tag, attrs, text)."""
    inner = svg[svg.index(">") + 1: svg.rindex("</svg>")]
    out, depth, start, cur = [], 0, None, None
    for m in TAG.finditer(inner):
        close, tag, attrs, selfc = m.groups()
        if not close:
            if depth == 0:
                start, cur = m.start(), (tag, attrs)
            if selfc:
                if depth == 0:
                    out.append((cur[0], cur[1], inner[start:m.end()]))
            else:
                depth += 1
        else:
            depth -= 1
            if depth == 0:
                out.append((cur[0], cur[1], inner[start:m.end()]))
    return out


def _maps(text: str):
    """Spans of every map of al-Mashriq on a page, in order: (start, end) of its <svg>.
    The map of every year (figure.cg-years) is drawn by year_map() and is not one of them."""
    spans = []
    for fig in re.finditer(r"<figure\b[^>]*>.*?</figure>", text, re.S):
        if "cg-years" in fig.group(0)[:120]:
            continue
        m = re.search(r'<svg\b[^>]*viewBox="0 0 920 620"[^>]*>.*?</svg>', fig.group(0), re.S)
        if m:
            spans.append((fig.start() + m.start(), fig.start() + m.end()))
    return spans


def _is_region_group(tag, attrs, full) -> bool:
    """A schematic map's coloured areas: a bare <g> holding nothing but filled shapes."""
    if tag != "g" or attrs.strip():
        return False
    inner = full[full.index(">") + 1: full.rindex("</g>")]
    tags = set(re.findall(r"<([a-zA-Z]+)\b", inner))
    return bool(tags) and tags <= {"path", "polygon"} and "fill=" in inner


def _is_base(tag, attrs, full) -> bool:
    a = attrs
    return ('class="cg-base"' in a or 'class="cg-shared"' in a
            or tag == "rect" and 'width="920"' in a and 'height="620"' in a
            or tag == "path" and ('fill="#e7e2d7"' in a or 'fill="#e8dfc6"' in a or 'stroke="#9fb6c2"' in a)
            or tag == "path" and 'fill="none"' in a and 'stroke="#3d4a50"' in a and 'stroke-width="1.1"' in a
            or tag == "g" and 'stroke="#3d4a50"' in a and 'stroke-width="1.6"' in a
            or tag == "g" and 'stroke-dasharray="5 3"' in a and 'stroke="#8c9aa1"' in a
            or tag == "g" and 'stroke="#3b7fb5"' in a
            or _is_region_group(tag, attrs, full))


def _poly_from_svg(el: str):
    """A schematic map's filled shape (M/L/Z path data or polygon points) as a shapely polygon."""
    m = re.search(r'\bpoints="([^"]+)"', el)
    if m:
        nums = [float(v) for v in re.findall(r"-?\d*\.?\d+", m.group(1))]
        rings = [list(zip(nums[0::2], nums[1::2]))]
    else:
        d = re.search(r'\bd="([^"]+)"', el).group(1)
        rings, x, y, cmd = [], 0.0, 0.0, "M"
        toks = re.findall(r"[MmLlHhVvZz]|-?\d*\.?\d+(?:e-?\d+)?", d)
        i, ring = 0, []
        while i < len(toks):
            t = toks[i]
            if t in "MmLlHhVvZz":
                cmd = t
                i += 1
                if t in "Zz":
                    if len(ring) >= 3:
                        rings.append(ring)
                    ring = []
                continue
            if cmd in "Mm":
                if ring and len(ring) >= 3:
                    rings.append(ring)
                x, y = (float(toks[i]), float(toks[i + 1])) if cmd == "M" else (x + float(toks[i]), y + float(toks[i + 1]))
                ring = [(x, y)]
                i += 2
                cmd = "L" if cmd == "M" else "l"
            elif cmd in "Ll":
                x, y = (float(toks[i]), float(toks[i + 1])) if cmd == "L" else (x + float(toks[i]), y + float(toks[i + 1]))
                ring.append((x, y))
                i += 2
            elif cmd in "Hh":
                x = float(toks[i]) if cmd == "H" else x + float(toks[i])
                ring.append((x, y))
                i += 1
            elif cmd in "Vv":
                y = float(toks[i]) if cmd == "V" else y + float(toks[i])
                ring.append((x, y))
                i += 1
            else:
                i += 1
        if len(ring) >= 3:
            rings.append(ring)
    polys = [shapely.make_valid(shapely.Polygon(r)) for r in rings if len(r) >= 3]
    return shapely.union_all(polys) if polys else shapely.Polygon()


def _old_categories(svg: str):
    """(colour, polygon) of a schematic map's coloured areas, merged per colour."""
    by = defaultdict(list)
    for tag, attrs, full in _children(svg):
        if _is_region_group(tag, attrs, full) or tag == "path" and 'fill="#e8dfc6"' in attrs:
            for el in re.findall(r"<(?:path|polygon)\b[^>]*>", full):
                colour = re.search(r'fill="([^"]+)"', el).group(1)
                by[colour].append(_poly_from_svg(el))
    return {c: shapely.union_all(ps) for c, ps in by.items()}


# -- the ground -----------------------------------------------------------------------------

class Ground:
    """Everything the maps share, in the frame's pixels, loaded once."""

    def __init__(self, cfg: dict, data: D.Data):
        self.cfg, self.data = cfg, data
        mesh = paths(cfg).mesh
        regions = gpd.read_file(mesh, layer="regions")
        ids = list(regions["region_id"])
        simple = shapely.coverage_simplify(np.array([to_svg(g) for g in regions.geometry]), TOL)
        self.region = {rid: g for rid, g in zip(ids, simple) if not g.is_empty}
        self.limit = shapely.union_all(list(self.region.values()))        # where the mesh ends
        self.land = to_svg(gpd.read_file(mesh, layer="view_land").geometry.iloc[0])
        self.land = _clean(self.land)
        self.lakes = _clean(to_svg(gpd.read_file(mesh, layer="view_lakes").geometry.iloc[0]), min_area=1.5)
        rivers = to_svg(gpd.read_file(mesh, layer="view_rivers").geometry.iloc[0])
        self.rivers = shapely.simplify(shapely.intersection(rivers, VIEW), TOL * 1.4)
        b = gpd.read_file(mesh, layer="view_bathy")
        self.depths = {int(d): _clean(to_svg(g), tol=0.9, min_area=4) for d, g in zip(b["depth"], b.geometry)
                       if int(d) in INK["depths"]}
        self.coast_buf = self.land.boundary.buffer(0.7)
        self.edge_buf = self.limit.boundary.buffer(0.7)
        self._cells = None

    @property
    def cells(self):
        if self._cells is None:
            c = gpd.read_file(paths(self.cfg).mesh, layer="cells")
            simple = shapely.coverage_simplify(np.array([to_svg(g) for g in c.geometry]), TOL)
            self._cells = {str(cid): g for cid, g in zip(c["cell_id"], simple) if not g.is_empty}
        return self._cells

    # the year's political state
    def holders(self, year: int) -> dict[str, str]:
        row = self.data.matrix[self.data.year_index(year)]
        out = {}
        for k, rid in enumerate(self.data.region_ids):
            p = int(row[k])
            if p != D.UNCLAIMED and rid in self.region:
                out[rid] = self.data.polity_ids[p]
        return out

    def joined(self, top: str, first: int, last: int) -> dict[str, int]:
        """The year each region first comes under `top` (a union or kingdom) between two years."""
        m = self.data.matrix[self.data.year_index(first): self.data.year_index(last) + 1]
        under = np.array([self.data.top(p) == top for p in self.data.polity_ids] + [False])
        hit = under[m]                                   # UNCLAIMED (-1) reads the trailing False
        years = [y for y in self.data.year_list if first <= y <= last]
        out = {}
        for k, rid in enumerate(self.data.region_ids):
            rows = np.flatnonzero(hit[:, k])
            if rows.size and rid in self.region:
                out[rid] = years[rows[0]]
        return out

    def lines(self, year: int):
        """(frontiers, inner lines) for a year: frontiers between powers, inner lines between the
        states, colonies or territories of one power. Never along a coast or the mesh's edge."""
        held = self.holders(year)
        by_top, by_pol = defaultdict(list), defaultdict(list)
        for rid, g in self.region.items():
            pid = held.get(rid)
            by_top[self.data.top(pid) if pid else "-"].append(g)
            by_pol[pid or "-"].append(g)
        tops = [shapely.union_all(gs) for gs in by_top.values()]
        front = shapely.union_all([t.boundary for t in tops])
        pols = [shapely.union_all(gs) for gs in by_pol.values()]
        inner = shapely.union_all([p.boundary for p in pols])
        cut = shapely.union(self.coast_buf, self.edge_buf)
        front = shapely.line_merge(shapely.difference(front, cut))
        inner = shapely.line_merge(shapely.difference(shapely.difference(inner, front.buffer(0.4)), cut))
        return front, inner


def relief_image(cfg: dict) -> str:
    """Natural Earth's shaded relief for exactly this frame, projected by QGIS (see relief.py),
    as a greyscale WebP to multiply over the map: white on the flat, darker on shaded slopes."""
    from . import relief
    w, h = int(W * RELIEF_SCALE), int(H * RELIEF_SCALE)
    extent = ((0 - X0) / K, (W - X0) / K, (Y0 - H) / K, Y0 / K)
    shade = relief.relief(cfg, extent, w, h).astype(np.float32)
    flat = float(np.argmax(np.bincount(shade.astype(np.uint8).ravel(), minlength=256)))
    tone = 255 - np.clip((flat - shade) * 1.15, 0, 255)
    buf = io.BytesIO()
    Image.fromarray(tone.astype(np.uint8), "L").convert("RGB").save(buf, "WEBP", quality=48, method=6)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()


def shared_defs(g: Ground, relief_uri: str) -> str:
    sea = [f'<rect width="{W}" height="{H}" fill="{INK["sea"]}"/>']
    for depth in sorted(g.depths):
        d = path_d(g.depths[depth])
        if d:
            sea.append(f'<path fill="{INK["depths"][depth]}" d="{d}"/>')
    water = [f'<path fill="{INK["lake"]}" stroke="{INK["coast"]}" stroke-width=".5" d="{path_d(g.lakes)}"/>',
             f'<path fill="none" stroke="{INK["river"]}" stroke-width=".9" stroke-linecap="round" '
             f'stroke-linejoin="round" d="{path_d(g.rivers)}"/>']
    return ('<defs class="cg-shared">'
            f'<g id="cgm-sea">{"".join(sea)}</g>'
            f'<path id="cgm-land" d="{path_d(g.land)}"/>'
            f'<image id="cgm-relief" width="{W}" height="{H}" preserveAspectRatio="none" href="{relief_uri}"/>'
            f'<g id="cgm-water">{"".join(water)}</g>'
            "</defs>")


def base_group(g: Ground, spec: dict) -> str:
    """One map's ground, drawn from the shared layers and the map's own fills and frontiers.
    Frontiers that touch the map's coloured areas are drawn dark over a white halo; those between
    neighbours further off, lighter, so the eye stays on the map's subject."""
    unit = spec.get("unit", "polity")
    pieces = g.cells if unit == "cell" else g.region
    colour_of = {str(m): c for c, members in (spec.get("fills") or {}).items() for m in members}
    j = spec.get("joined")
    if j:
        # a map of growth: each region shaded by the period in which it joined, from the data
        for rid, year in g.joined(j["top"], int(j["from"]), int(j["until"])).items():
            colour = (j.get("regions") or {}).get(rid) or (j.get("years") or {}).get(year)
            if colour:
                colour_of[rid] = colour
            else:
                print(f"    ! {spec.get('id')}: {rid} joined in {year}, a year the map has no colour for")
    by_colour = defaultdict(list)
    for m, c in colour_of.items():
        if m in pieces:
            by_colour[c].append(pieces[m])
    fills = []
    for colour in dict.fromkeys(list((spec.get("fills") or {})) + list(by_colour)):
        geom = _clean(shapely.union_all(by_colour.get(colour, [])), tol=0.05, min_area=0.3)
        if not geom.is_empty:
            fills.append((colour, geom))
    key = spec.get("id", "map")
    out = [f'<g class="cg-base" data-frontiers="{spec.get("frontiers", "")}" aria-hidden="true">',
           '<use href="#cgm-sea"/>', f'<use href="#cgm-land" fill="{INK["land"]}"/>']
    op = spec.get("fill_opacity")
    out.append('<g fill-rule="evenodd"' + (f' fill-opacity="{op}"' if op else "") + ">"
               + "".join(f'<path fill="{c}" d="{path_d(geom)}"/>' for c, geom in fills) + "</g>")
    out.append(f'<use href="#cgm-relief" opacity="{spec.get("relief", 0.55)}" style="mix-blend-mode:multiply"/>')
    out.append('<use href="#cgm-water"/>')
    subject = shapely.union_all([geom for _, geom in fills]).buffer(1.2) if fills else shapely.Polygon()
    if spec.get("category_lines") and len(fills) > 1:
        cat = shapely.union_all([geom.boundary for _, geom in fills])
        cat = shapely.difference(cat, shapely.union(g.coast_buf, g.edge_buf))
        out.append(f'<path fill="none" stroke="{INK["category"]}" stroke-width="1.1" stroke-opacity=".85" '
                   f'stroke-linejoin="round" d="{path_d(shapely.line_merge(cat))}"/>')
    year = spec.get("frontiers")
    if year is not None:
        front, inner = g.lines(int(year))
        near = shapely.line_merge(shapely.intersection(front, subject))
        far = shapely.simplify(shapely.line_merge(shapely.difference(front, subject)), TOL * 1.6)
        inner = shapely.intersection(inner, subject)
        if not far.is_empty:
            out.append(f'<path fill="none" stroke="{INK["neighbour"]}" stroke-width=".8" stroke-linejoin="round" '
                       f'd="{path_d(far)}"/>')
        style = spec.get("inner", "solid")
        if style and not inner.is_empty:
            dash = ' stroke-dasharray="4 2.5"' if style == "dashed" else ""
            out.append(f'<path fill="none" stroke="{INK["inner"]}" stroke-width=".7" stroke-opacity=".55"{dash} '
                       f'stroke-linejoin="round" d="{path_d(inner)}"/>')
        if not near.is_empty:
            out.append(f'<defs><path id="cgm-front-{key}" d="{path_d(near)}"/></defs>'
                       f'<g fill="none" stroke-linejoin="round" stroke-linecap="round">'
                       f'<use href="#cgm-front-{key}" stroke="#fff" stroke-width="3" stroke-opacity=".6"/>'
                       f'<use href="#cgm-front-{key}" stroke="{INK["frontier"]}" stroke-width="1.35"/></g>')
    out.append(f'<use href="#cgm-land" fill="none" stroke="{INK["coast"]}" stroke-width=".8" stroke-linejoin="round"/>')
    out.append("</g>")
    return "".join(out)


def rebuild(svg: str, base: str, defs: str | None, keep: list[str]) -> str:
    """The map with its ground replaced and everything it says kept, in order."""
    head = svg[: svg.index(">") + 1]
    kids = _children(svg)
    kept, placed, extra = [], False, []
    for tag, attrs, full in kids:
        if _is_region_group(tag, attrs, full) and keep:
            for el in re.findall(r"<(?:path|polygon)\b[^>]*>(?:\s*</(?:path|polygon)>)?", full):
                if re.search(r'fill="([^"]+)"', el).group(1) in keep:
                    extra.append(el)
        if _is_base(tag, attrs, full):
            if not placed:
                kept.append("\0BASE\0")
                placed = True
            continue
        if tag == "g" and 'font-style="italic"' in attrs and re.search(r'fill="#(cfd8dc|8c9aa1)"', attrs):
            # the neighbours' and seas' names, pale on the old flat plate: dark enough to read now
            head_tag = full[: full.index(">") + 1]
            new_tag = re.sub(r'fill="#[0-9a-f]{6}"', f'fill="{INK["names"]}"', head_tag)
            new_tag = re.sub(r'opacity="[^"]*"', 'opacity=".75"', new_tag)
            full = new_tag + full[len(head_tag):]
        kept.append(full)
    if not placed:
        kept.insert(0, "\0BASE\0")
    ground = (defs or "") + base + (f'<g class="cg-keep">{"".join(extra)}</g>' if extra else "")
    i = kept.index("\0BASE\0")
    # anything the old base carried that the map still refers to (arrow markers live in <defs>)
    kept[i] = ground
    # a map's own <defs> go first, so markers stay defined before use
    defs_first = [k for k in kept if k.startswith("<defs") and 'class="cg-shared"' not in k]
    rest = [k for k in kept if k not in defs_first]
    return head + "".join(defs_first) + "".join(rest) + "</svg>"


# -- bootstrap: read the schematic maps once ------------------------------------------------

def bootstrap(cfg: dict, data: D.Data) -> None:
    g = Ground(cfg, data)
    maps = []
    for page in PAGES:
        text = (SITE / page).read_text(encoding="utf8")
        for n, (a, b) in enumerate(_maps(text)):
            svg = text[a:b]
            if 'class="cg-base"' in svg:
                raise SystemExit(f"{page} map {n} is already redrawn: --bootstrap reads the schematic maps")
            boot = dict(BOOT[(page, n)])
            cats = _old_categories(svg)
            cats.pop("#efe6d2" if boot["id"] == "energy" else "", None)   # the Union, drawn from the year below
            for c in boot.get("keep", []):
                cats.pop(c, None)
            unit = boot["unit"]
            pieces = g.cells if unit == "cell" else g.region
            tree = [(c, shapely.make_valid(p)) for c, p in cats.items()]
            vote = {}
            for pid_, geom in pieces.items():
                if geom.area <= 0:
                    continue
                shares = [(shapely.intersection(geom, p).area / geom.area, c) for c, p in tree]
                best = max(shares, default=(0, None))
                if best[0] >= 0.5:
                    vote[pid_] = best[1]
            if unit == "polity":
                held = g.holders(boot["frontiers"])
                members = defaultdict(list)
                for rid, pid in held.items():
                    members[pid].append(rid)
                for pid, rids in members.items():
                    area = defaultdict(float)
                    total = sum(g.region[r].area for r in rids)
                    for r in rids:
                        if r in vote:
                            area[vote[r]] += g.region[r].area
                    if area:
                        colour, a2 = max(area.items(), key=lambda t: t[1])
                        if a2 >= 0.5 * total:
                            for r in rids:
                                vote[r] = colour
            if boot["id"] == "states" or boot["id"] == "energy":
                held = g.holders(2026)
                union = "#e8dfc6" if boot["id"] == "states" else "#efe6d2"
                vote = {r: union for r, pid in held.items() if data.top(pid) == "usa"}
            fills = defaultdict(list)
            for pid_, c in vote.items():
                fills[c].append(pid_)
            spec = {k: v for k, v in boot.items() if k not in ("unit",)}
            spec = {"id": boot["id"], "page": page, "map": n, "unit": unit, **{k: v for k, v in spec.items() if k != "id"}}
            spec["fills"] = {c: sorted(v, key=str) for c, v in sorted(fills.items())}
            maps.append(spec)
            print(f"  {page} map {n} ({boot['id']}): {sum(len(v) for v in fills.values())} {unit}s in "
                  f"{len(fills)} colours")
    header = ("# The encyclopedia's maps of al-Mashriq, redrawn on the video's borders by `python build.py sitemaps`.\n"
              "# Written once by --bootstrap from the schematic maps; edit it by hand from now on.\n"
              "# id: a name; page and map: which map of al-Mashriq on which page (0 is the first; the\n"
              "#   Arabic edition's page of the same name gets the same ground); frontiers: the year whose\n"
              "#   frontiers are drawn; inner: solid, dashed or null for the lines between one power's states,\n"
              "#   colonies or territories; unit: what the fills list (region ids, or mesh cell ids for\n"
              "#   unit: cell); fills: legend colour -> the regions or cells it covers; keep: colours of the\n"
              "#   schematic map's own shapes kept above the ground (the energy map's solar arrays);\n"
              "#   category_lines: white lines between the fill colours; relief and fill_opacity: strengths.\n")
    CONFIG.write_text(header + yaml.safe_dump({"maps": maps}, sort_keys=False, allow_unicode=True, width=110,
                                              default_flow_style=None), encoding="utf8")
    print(f"  wrote {CONFIG}")


# -- build ----------------------------------------------------------------------------------

def build(cfg: dict, data: D.Data) -> list[str]:
    specs = yaml.safe_load(CONFIG.read_text(encoding="utf8"))["maps"]
    by_page = defaultdict(dict)
    for s in specs:
        by_page[s["page"]][int(s["map"])] = s
    g = Ground(cfg, data)
    defs = shared_defs(g, relief_image(cfg))
    bases = {(p, n): base_group(g, s) for p, maps in by_page.items() for n, s in maps.items()}
    changed = []
    for page, maps in by_page.items():
        for path in (SITE / page, SITE / "ar" / page):
            if not path.exists():
                continue
            with open(path, encoding="utf8", newline="") as fh:
                text = fh.read()
            spans = _maps(text)
            if len(spans) != len(maps):
                print(f"  ! {path.name}: {len(spans)} maps of al-Mashriq on the page, {len(maps)} in the config")
            out, last = [], 0
            for n, (a, b) in enumerate(spans):
                if n not in maps:
                    continue
                svg = rebuild(text[a:b], bases[(page, n)], defs if n == min(maps) else None,
                              maps[n].get("keep") or [])
                out.append(text[last:a] + svg)
                last = b
            out.append(text[last:])
            new = "".join(out)
            for old, fixed in TEXT_FIXES:
                new = new.replace(old, fixed)
            if new != text:
                with open(path, "w", encoding="utf8", newline="") as fh:
                    fh.write(new)
                changed.append(path.relative_to(SITE).as_posix())
    from . import yearmap
    for page in yearmap.install(cfg, data, g):
        if page not in changed:
            changed.append(page)
    return changed
