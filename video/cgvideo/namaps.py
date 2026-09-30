"""The maps of North America, which carries the Middle East, and of the Kingdom of Solms-America.

North America's frontiers are data, like the atlases': data/atlas/north-america-frontiers.yaml
says what each follows on the ground, QGIS traces it (integrations/qgis/cg_frontiers.py, with
GRASS's river basins) into north-america-frontiers.geojson, and north-america-nations.csv gives
each nation its seed, colour and names. The thirteen marches of Solms-America are cut out of the
kingdom the same way (solms-america-*). The continent's map descends from "A More Fractured
Union" (Bemon and Body25, 2023): the same states in the same places, with its non-state actors
laid over them, on frontiers moved from state lines onto rivers, watersheds and crests.

`python build.py namaps` draws four maps and sets each wherever a page carries its markers,
`<!-- cg-na:NAME -->` ... `<!-- /cg-na:NAME -->`, in both editions:

  political    North America at the end of 2023: the states, the self-governing and occupied
               territories, and the ground held by non-state actors, numbered to a key
  marches      the kingdom: its thirteen marches, their seats, the holy cities and the oilfields
  unification  the same ground, coloured by the years in which the House of Solms took it
  locator      the kingdom on the continent, for the infobox

Everything stands on ETOPO 2022, projected and shaded by QGIS and finished in GIMP (terrain.py),
with GIMP's ribbons along the frontiers, as the atlases do.
"""

from __future__ import annotations

import html
import math
import re

import numpy as np
import shapely

from . import frontiers as fr
from . import geo, terrain
from .atlas import INK, LABELS, Frame, _to, graticule, real_land_ll
from .config import paths
from .sitemaps import SITE, path_d

PAGES = ("kingdom-of-solms-america.html", "timeline-of-the-global-swap.html", "united-states-of-arabia.html",
         "index.html")

CONTINENT = {
    "proj": "+proj=laea +lat_0=36 +lon_0=-97 +datum=WGS84 +units=m +no_defs",
    "extent": (-2450e3, -1760e3, 2450e3, 1861.7e3),        # x0, y0, x1, y1 in metres
    "area": (0, 0, 920, 680), "bbox": (-140, 7, -52, 62), "margin": 0,
}
KINGDOM = {
    "proj": "+proj=laea +lat_0=33.5 +lon_0=-103.5 +datum=WGS84 +units=m +no_defs",
    "extent": (-1230e3, -930e3, 1170e3, 896e3),
    "area": (0, 0, 920, 700), "bbox": (-124, 20, -84, 47), "margin": 0,
}

# -- what the maps say, in each edition -------------------------------------------------------

# non-state actors and unrecognised administrations at the end of 2023: number, place (lon, lat)
ACTORS = [
    (1, -122.4, 47.75, "Pacific Liberation Committee", "لجنة تحرير المحيط الهادئ"),
    (2, -117.8, 48.85, "Free Cascadian Army", "الجيش الكاسكادي الحر"),
    (3, -106.2, 48.35, "Wiyohiyanpa (East Cascadia)", "ويوهيانبا (شرق كاسكاديا)"),
    (4, -100.8, 46.85, "Bismarck Garrisons", "حاميات بسمارك"),
    (5, -102.0, 44.45, "Kingdom of Heaven on Earth", "مملكة السماء على الأرض"),
    (6, -108.25, 43.65, "Thermopolis Garrison", "حامية ثيرموبوليس"),
    (7, -123.3, 42.75, "God's Faction", "فصيل الله"),
    (8, -111.66, 40.3, "C.L.O.–Victory", "منظمة التحرير الكاليفورنية – النصر"),
    (9, -118.3, 34.0, "Armov", "أرموف"),
    (10, -106.65, 35.1, "God's Faction in Deseret", "فصيل الله في ديزرت"),
    (11, -101.5, 26.35, "The Huastecas", "الهواستيكاس"),
    (12, -98.75, 23.4, "Southern Transition Council", "المجلس الانتقالي الجنوبي"),
    (13, -98.15, 24.85, "The Base in Mexico", "تنظيم «الأساس» في المكسيك"),
    (14, -106.35, 23.3, "Santo Templo", "أنصار الهيكل المقدس"),
    (15, -89.4, 30.85, "A.S.M.L.F. and N.L.O.F. (Florida)", "حركتا تحرير فلوريدا"),
    (16, -90.1, 29.95, "People's Knights", "فرسان الشعب"),
]

WATERS = [
    (-123.6, 27.6, "Pacific Ocean", "المحيط الهادئ", -62),
    (-73.2, 31.6, "Atlantic Ocean", "المحيط الأطلسي", 60),
    (-90.3, 24.6, "Gulf of Mexico", "خليج المكسيك", 0),
]
CONTINENT_NOTES = [                                   # ground outside the swap's North America
    (-79.0, 21.4, "Cuba", "كوبا"),
    (-88.4, 15.6, "Central America", "أمريكا الوسطى"),
]
TERRITORIES = [                                       # parts of a nation named on the map
    (-118.8, 32.35, "L.A. Strip", "شريط لوس أنجلوس", "end", 0, None, None),
    (-112.55, 38.7, "East Basin", "الحوض الشرقي", "middle", 0, None, None),
    (-120.55, 42.62, "Fremont Forests", "غابات فريمونت", "middle", 0, None, None),
]

KEY = {
    "en": {"occupied": "occupied territory", "held": "held by a non-state actor", "presence": "non-state actor present",
           "auto": "self-governing region", "capital": "capital", "seat": "seat of a march", "holy": "holy city",
           "oil": "oilfield", "port": "port", "inset": "Puerto Rico (Bahrain)",
           "frontier": "frontier of the kingdom", "march": "frontier of a march"},
    "ar": {"occupied": "أرض محتلة", "held": "تسيطر عليها جهة غير حكومية", "presence": "وجود لجهة غير حكومية",
           "auto": "إقليم يتمتع بالحكم الذاتي", "capital": "العاصمة", "seat": "مقر المارك", "holy": "مدينة مقدسة",
           "oil": "حقل نفط", "port": "ميناء", "inset": "بورتوريكو (البحرين)",
           "frontier": "حدود المملكة", "march": "حدود المارك"},
}

# the kingdom's towns: lon, lat, name, Arabic name, kind, side of the dot the label takes (dx, dy, anchor)
TOWNS = [
    (-96.80, 32.78, "Dreifurt", "درايفورت", "capital", 7, 3.5, "start"),
    (-97.13, 33.2, "Braunfels", "براونفيلس", "town", -6, 2, "end"),
    (-94.10, 30.08, "Neches", "نيتشيس", "seat", 6, -5, "start"),
    (-97.15, 31.55, "Waco", "واكو", "town", 6, 3.5, "start"),
    (-97.13, 34.17, "Waschita", "واشيتا", "seat", 6, 3.5, "start"),
    (-97.34, 37.69, "Wichita", "ويتشيتا", "seat", 6, 3.5, "start"),
    (-95.68, 39.05, "Topeka", "توبيكا", "seat", -6, -4, "end"),
    (-94.61, 39.11, "Kawsmund", "كاوسموند", "town", 6, -3, "start"),
    (-101.85, 33.58, "Gelbhaus", "غيلبهاوس", "seat", 6, 3.5, "start"),
    (-103.49, 31.42, "Pecos", "بيكوس", "seat", 6, 3.5, "start"),
    (-105.94, 35.69, "Tewa", "تيوا", "seat", 6, 3.5, "start"),
    (-106.49, 31.76, "Nordpass", "نوردباس", "town", 6, -4, "start"),
    (-106.08, 28.63, "Chihuahua", "تشيواوا", "seat", 6, 3.5, "start"),
    (-107.95, 30.37, "Paquimé", "باكيمي", "holy", 7, 3.5, "start"),
    (-110.97, 32.22, "Chukson", "تشوكسون", "holy", 7, 3.5, "start"),
    (-110.90, 27.92, "Waimas", "وايماس", "port", -6, 3.5, "end"),
    (-110.97, 29.07, "Pitic", "بيتيك", "town", -6, 3.5, "end"),
    (-107.50, 28.55, "Papigochi", "بابيغوتشي", "seat", -6, 10, "end"),
]
OILFIELDS = [
    (-94.87, 32.39, "Großfeld", "الحقل الكبير", 6, 3.5, "start"),
    (-102.2, 31.95, "Pecosbecken", "حوض بيكوس", 6, 3.5, "start"),
    (-94.07, 29.85, "Küstenfeld", "حقل الساحل", 5, 11, "start"),
]
KINGDOM_WATERS = [
    (-93.0, 28.2, "Gulf of Mexico", "خليج المكسيك", 0),
    (-112.6, 27.6, "Gulf of California", "خليج كاليفورنيا", -52),
]
# neighbours named on the kingdom's maps, faint, on their own ground: key, lon, lat
NEIGHBOURS = [("mississippi", -92.6, 36.8), ("colorado", -109.3, 36.4), ("aztlan", -115.6, 35.3),
              ("mexico", -105.6, 25.6), ("nuevoleon", -101.0, 26.5), ("riogrande", -99.4, 28.2),
              ("counties", -97.6, 29.55), ("ludwigsland", -92.4, 30.6), ("karankawa", -95.4, 29.6)]

# the unification: the year each march came under the House of Solms, in five steps of one hue,
# dark for the oldest ground
UNIFICATION = [
    ("1902–1906", "#1f4e79", ("dreifurt", "rotland")),
    ("1913", "#3f76aa", ("ostmark",)),
    ("1919–1922", "#6f9fcc", ("wichita", "kansa", "hochebene", "bergland")),
    ("1924–1926", "#a3c3e0", ("paquime", "chukson", "kuestenland", "oberland", "pecos")),
    ("1934", "#d3e1ef", ("chihuahua",)),
]
UNIFICATION_TITLE = {"en": "Taken by the House of Solms in", "ar": "ضمّها آل زولمس في"}


# -- ground -----------------------------------------------------------------------------------

def _pt(proj, lon, lat):
    p = _to(proj, [shapely.Point(lon, lat)])[0]
    return np.array([p.x, p.y])


class Ground:
    """One frame's ground: the land, the nations and their frontiers in the map's pixels, the
    rivers and lakes, and the relief and sea from terrain.py."""

    def __init__(self, cfg, A, name, continent, marches=None, river_rank=5, focus=None, relief=True):
        self.cfg, self.A, self.name = cfg, A, name
        proj = A["proj"]
        self.F = F = Frame(A, A["extent"])
        held, unclaimed, rows, spec, land_ll = continent
        self.spec = spec
        self.rows = [r for r in rows if r["key"] in held]
        view_ll = real_land_ll(cfg, A)
        box_m = F.ground_box_m().buffer(150_000)
        land = shapely.make_valid(shapely.intersection(shapely.make_valid(_to(proj, [view_ll])[0]), box_m))
        self.held_ll = held
        nat_m = {r["key"]: shapely.intersection(shapely.make_valid(_to(proj, [held[r["key"]]])[0]), box_m)
                 for r in self.rows}
        keep = [r for r in self.rows if not nat_m[r["key"]].is_empty]
        geoms = [F.g(nat_m[r["key"]], tol=0.0, min_area=0.0) for r in keep]
        self.march_rows, march_geoms = [], []
        if marches is not None:
            mheld, _, mrows, _ = marches
            self.march_rows = [r for r in mrows if r["key"] in mheld]
            march_geoms = [F.g(shapely.make_valid(_to(proj, [mheld[r["key"]]])[0]), tol=0.0, min_area=0.0)
                           for r in self.march_rows]
            # the marches stand in for the kingdom in the coverage, so every edge is shared once
            k = [i for i, r in enumerate(keep) if r["key"] == "solms"][0]
            keep, geoms = keep[:k] + keep[k + 1:], geoms[:k] + geoms[k + 1:]
        cover = list(shapely.coverage_simplify(np.array(geoms + march_geoms), 0.35))
        self.nations = dict(zip([r["key"] for r in keep], cover[:len(keep)]))
        self.marches = dict(zip([r["key"] for r in self.march_rows], cover[len(keep):]))
        self.nation_rows = keep
        if self.marches:
            self.nations["solms"] = shapely.union_all(list(self.marches.values()))
        swap = shapely.union_all(list(self.nations.values()))
        self.body = swap
        self.other = F.g(shapely.difference(land, _unpx(F, swap).buffer(1500)), tol=0.4, min_area=1.0)
        coast = shapely.union_all([p.boundary for p in shapely.get_parts(shapely.union(swap, self.other.buffer(0.2)))])
        # sovereign frontiers: a self-governing region is inside its parent
        units = {}
        for r in keep + ([{"key": "solms", "parent": ""}] if self.marches else []):
            units.setdefault(r.get("parent") or r["key"], []).append(self.nations[r["key"]])
        units = {k: shapely.union_all(v) for k, v in units.items()}
        self.units = units
        edges = shapely.union_all([g.boundary for g in units.values()])
        self.frontiers = _lines(shapely.difference(edges, coast.buffer(0.3)))
        inner = [shapely.intersection(self.nations[r["key"]].boundary, self.nations[r["parent"]].boundary)
                 for r in keep if r.get("parent") and r["parent"] in self.nations]
        self.inner = _lines(shapely.union_all(inner)) if inner else shapely.LineString()
        if self.marches:
            medges = shapely.union_all([g.boundary for g in self.marches.values()])
            self.march_lines = _lines(shapely.difference(medges, self.nations["solms"].boundary.buffer(0.3)))
        lk = geo.read_ne(cfg, "ne_10m_lakes", bbox_ll=A["bbox"])
        lk = lk[lk["scalerank"].fillna(99) <= 3]
        self.lakes = F.g(shapely.union_all(_to(proj, lk.geometry)), tol=0.4, min_area=1.5)
        rv = geo.read_ne(cfg, "ne_10m_rivers_lake_centerlines", bbox_ll=A["bbox"])
        rv = rv[rv["scalerank"].fillna(99) <= river_rank]
        on = shapely.make_valid(_to(proj, [shapely.union_all(list(held.values()))])[0]) if focus is None else \
            shapely.make_valid(_to(proj, [held[focus]])[0]).buffer(60_000)
        self.rivers = F.g(shapely.intersection(shapely.union_all(_to(proj, rv.geometry)), on), tol=0.5, lines=True)
        self.grat = graticule(A, F)
        self.relief = self.sea = None
        if relief:
            x0, y0, w, h = F.area
            k = 1.5
            land_px = shapely.affinity.affine_transform(shapely.union(swap, self.other), [k, 0, 0, k, -x0 * k, -y0 * k])
            metres = 1 / (F.k * k)
            self.relief, self.sea = terrain.images(cfg, name, proj, F.extent_m(), int(w * k), int(h * k), land_px,
                                                   z=round(6 * math.sqrt(metres / 3393), 1), floor=0.2)

    def xy(self, lon, lat):
        q = self.F.xy(_pt(self.A["proj"], lon, lat)[None])[0]
        return float(q[0]), float(q[1])

    def overlay(self, ring, within):
        """A lon/lat ring, clipped to the nation it lies in, in the map's pixels."""
        g = shapely.intersection(shapely.make_valid(shapely.Polygon(ring)), self.held_ll[within])
        if g.is_empty:
            return shapely.Polygon()
        return self.F.g(shapely.make_valid(_to(self.A["proj"], [g])[0]), tol=0.3, min_area=0.5)


def _unpx(F: Frame, g):
    return shapely.affinity.affine_transform(g, [1 / F.k, 0, 0, -1 / F.k, -F.tx / F.k, F.ty / F.k])


def _lines(g):
    parts = [p for p in shapely.get_parts(g) if p.geom_type == "LineString" and p.length > 0.6]
    return shapely.line_merge(shapely.union_all(parts)) if parts else shapely.LineString()


def _deep(colour: str, l=0.62, s=1.25) -> str:
    import colorsys
    r, g, b = (int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    return "#%02x%02x%02x" % tuple(int(v * 255) for v in colorsys.hls_to_rgb(hh, ll * l, min(1.0, ss * s)))


def _pale(colour: str, t=0.6) -> str:
    r, g, b = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
    base = [int(INK["base"][i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(c + (p - c) * t) for c, p in zip((r, g, b), base))


# -- drawing ----------------------------------------------------------------------------------

def _style(ed):
    L = LABELS[ed]
    return (f"font-family='{L['font']}' paint-order=\"stroke\" stroke=\"rgba(255,255,255,.78)\" "
            f"stroke-linejoin=\"round\"")


def _anchored(ed, anchor):
    """A label keeps to the side of its dot that the English gives it; Arabic reads right to left."""
    if anchor == "middle":
        return ' text-anchor="middle"' + (' direction="rtl"' if ed == "ar" else "")
    if ed == "en":
        return f' text-anchor="{anchor}"'
    return ' direction="rtl" text-anchor="%s"' % ("end" if anchor == "start" else "start")


def _base(G: Ground, tag: str, fills: str, ribbons: str, extra_lines: str = "", relief_opacity=".55", share=None) -> str:
    """The ground of a map, up to its frontiers. `share` lets two maps of one frame on one page
    carry the sea and the relief once: ("define", id) puts them in this map's <defs>, ("use", id)
    draws the other map's."""
    x0, y0, w, h = G.F.area
    img = lambda href, more="": (f'<image x="{x0}" y="{y0}" width="{w}" height="{h}" preserveAspectRatio="none" '
                                 f'href="{href}"{more}/>')
    blend = f' opacity="{relief_opacity}" style="mix-blend-mode:multiply"'
    shared = ""
    if share:
        sea, relief = f'<use href="#{share[1]}-sea"/>', f'<use href="#{share[1]}-relief"{blend}/>'
        if share[0] == "define":
            shared = img(G.sea, f' id="{share[1]}-sea"') + img(G.relief, f' id="{share[1]}-relief"')
    else:
        sea = img(G.sea) if G.sea else f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="#dbe8ef"/>'
        relief = img(G.relief, blend) if G.relief else ""
    return (
        f'<defs><clipPath id="{tag}-frame"><rect x="{x0}" y="{y0}" width="{w}" height="{h}"/></clipPath>{shared}'
        f'<path id="{tag}-frontiers" d="{path_d(G.frontiers)}"/>'
        f'<pattern id="{tag}-held" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        f'<rect width="2" height="5" fill="#b0353f" fill-opacity=".62"/></pattern>'
        f'<pattern id="{tag}-occ" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">'
        f'<rect width="2.2" height="5" fill="#b8563f" fill-opacity=".7"/></pattern>'
        f'<pattern id="{tag}-auto" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        f'<rect width="1.2" height="6" fill="#4f6f86" fill-opacity=".5"/></pattern></defs>'
        f'<g clip-path="url(#{tag}-frame)">'
        + sea
        + f'<path d="{path_d(G.grat)}" fill="none" stroke="#8fa7b3" stroke-width=".6" stroke-opacity=".45"/>'
        f'<path d="{path_d(G.other)}" fill="{INK["other"]}"/>'
        f'<g fill-rule="evenodd">{fills}</g>'
        + (img(ribbons) if ribbons else "")
        + relief
        + f'<path d="{path_d(G.lakes)}" fill="#dcebf2" stroke="{INK["coast"]}" stroke-width=".4"/>'
        f'<path d="{path_d(G.rivers)}" fill="none" stroke="#6a9ac0" stroke-width=".6" stroke-linejoin="round" '
        f'stroke-linecap="round"/>'
        + extra_lines
        + f'<use href="#{tag}-frontiers" fill="none" stroke="#fff" stroke-width="1.7" stroke-opacity=".7" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<use href="#{tag}-frontiers" fill="none" stroke="{INK["frontier"]}" stroke-width=".75" '
        f'stroke-dasharray="3.2 1.3 .9 1.3" stroke-linejoin="round"/>'
        f'<path d="{path_d(shapely.union(G.body, G.other))}" fill="none" stroke="{INK["coast"]}" stroke-width=".7" '
        f'stroke-linejoin="round"/>')


def _waters(G, ed, waters, size=11.5):
    out = ""
    for lon, lat, en, ar, turn in waters:
        x, y = G.xy(lon, lat)
        out += (f'<text x="{x:.1f}" y="{y:.1f}" transform="rotate({turn} {x:.1f} {y:.1f})" text-anchor="middle"'
                + (' direction="rtl"' if ed == "ar" else ' letter-spacing="2.4"')
                + f'>{html.escape(ar if ed == "ar" else en)}</text>')
    L = LABELS[ed]
    return (f"<g font-family='{L['font']}' font-size=\"{size}\" font-style=\"italic\" fill=\"#5d7f95\" "
            f'fill-opacity=".85">{out}</g>')


def _legend_row(ed, W, items, y, pad=14):
    """Swatch-and-word entries in one row, left to right (right to left in Arabic)."""
    out, x = "", pad
    for swatch, word in items:
        tw = 0.58 * 10 * len(word) + 8
        if ed == "en":
            out += (f'<g transform="translate({x:.1f} {y})">{swatch}</g>'
                    f'<text x="{x + 20:.1f}" y="{y + 3.6}">{html.escape(word)}</text>')
        else:
            # a run of years reads left to right even in an Arabic key: it is anchored at its end
            way = ('direction="ltr" text-anchor="end"' if re.fullmatch(r"[\d– ]+", word)
                   else 'direction="rtl" text-anchor="start"')
            out += (f'<g transform="translate({W - x - 14:.1f} {y})">{swatch}</g>'
                    f'<text x="{W - x - 20:.1f}" y="{y + 3.6}" {way}>{html.escape(word)}</text>')
        x += 20 + tw + 14
    return out


def political(cfg, continent, ed: str) -> str:
    """North America at the end of 2023: states, territories, non-state actors, and their key."""
    A = CONTINENT
    G = _ground(cfg, "political", A, continent)
    x0, y0, w, h = G.F.area
    tag = "nap"
    rows = G.nation_rows
    colour = {r["key"]: r["colour"] for r in G.rows}
    fills = "".join(f'<path d="{path_d(G.nations[r["key"]])}" fill="{r["colour"]}"/>' for r in rows)
    ribbons = terrain.ribbons(cfg, "North America political", G.F.area, [(G.nations[r["key"]], r["colour"]) for r in rows],
                              shapely.union(G.frontiers, G.inner))
    zones = ""
    for key, o in (G.spec.get("overlays") or {}).items():
        g = G.overlay(o["ring"], o["within"])
        if g.is_empty:
            continue
        if o["kind"] == "presence":
            zones += (f'<path d="{path_d(g)}" fill="none" stroke="#b0353f" stroke-width="1.1" '
                      f'stroke-dasharray="3.4 2.2" stroke-linejoin="round"/>')
        else:
            pat = "occ" if o["kind"] == "occupied" else "held"
            zones += (f'<path d="{path_d(g)}" fill="url(#{tag}-{pat})" stroke="#9a3a3a" stroke-width=".5" '
                      f'stroke-opacity=".55"/>')
    # a self-governing region: hatched lightly, behind a lighter frontier
    auto = "".join(f'<path d="{path_d(G.nations[r["key"]])}" fill="url(#{tag}-auto)"/>' for r in rows if r.get("parent"))
    inner = (f'<path d="{path_d(G.inner)}" fill="none" stroke="#fff" stroke-width="1.5" stroke-opacity=".6"/>'
             f'<path d="{path_d(G.inner)}" fill="none" stroke="#5b6b76" stroke-width=".7" stroke-dasharray="2 1.6"/>')
    ground = _base(G, tag, fills, ribbons, auto + zones + inner) + "</g>"

    L, st = LABELS[ed], _style(ed)
    big_n, big_t, small_n, small_t, leads = [], [], [], [], []
    for r in rows:
        name = r["name_ar"] if ed == "ar" else r["name"]
        twin = r["twin_ar"] if ed == "ar" else r["twin"]
        cx, cy = G.xy(r["label_lon"], r["label_lat"])
        if not (x0 - 40 < cx < x0 + w + 40 and y0 < cy < y0 + h):
            continue
        if r["size"] == "big":
            shown = name if ed == "ar" else name.upper()
            big_n.append(f'<text x="{cx:.1f}" y="{cy - 1.5:.1f}">{html.escape(shown)}</text>')
            big_t.append(f'<text x="{cx:.1f}" y="{cy + 10.5:.1f}">{html.escape(twin)}</text>')
        else:
            small_n.append(f'<text x="{cx:.1f}" y="{cy:.1f}">{html.escape(name)}</text>')
            small_t.append(f'<text x="{cx:.1f}" y="{cy + 9.5:.1f}">{html.escape(twin)}</text>')
        if r["lead"]:
            sx, sy = G.xy(r["seed_lon"], r["seed_lat"])
            dx, dy = sx - cx, sy - cy
            n = math.hypot(dx, dy) or 1
            ax_, ay_ = cx + dx / n * 17, cy + 4 + dy / n * 10
            leads.append(f'<path d="M{ax_:.1f} {ay_:.1f}L{sx - dx / n * 2:.1f} {sy - dy / n * 2:.1f}"/>')
    terr = ""
    for lon, lat, en, ar, anchor, dx, llon, llat in TERRITORIES:
        tx, ty = G.xy(lon, lat)
        if llon is not None:
            lx, ly = G.xy(llon, llat)
            leads.append(f'<path d="M{lx + 2:.1f} {ly - 5:.1f}L{tx:.1f} {ty:.1f}"/>')
            tx, ty, anchor = lx, ly, "middle"
        terr += f'<text x="{tx + dx:.1f}" y="{ty:.1f}"{_anchored(ed, anchor)}>{html.escape(ar if ed == "ar" else en)}</text>'
    notes = "".join(f'<text x="{G.xy(lon, lat)[0]:.1f}" y="{G.xy(lon, lat)[1]:.1f}" text-anchor="middle"'
                    + (' direction="rtl"' if ed == "ar" else "") + f'>{html.escape(ar if ed == "ar" else en)}</text>'
                    for lon, lat, en, ar in CONTINENT_NOTES)
    dx_, dy_ = G.xy(-96.80, 32.78)
    capital = (f'<circle cx="{dx_:.1f}" cy="{dy_:.1f}" r="3.1" fill="#fff" stroke="#1d2a33" stroke-width="1.1"/>'
               f'<circle cx="{dx_:.1f}" cy="{dy_:.1f}" r="1.2" fill="#1d2a33"/>'
               f'<text x="{dx_ + 6:.1f}" y="{dy_ + 3.2:.1f}" {st} stroke-width="2.2" font-size="9.2" font-weight="600" '
               f'fill="#1d2a33"{_anchored(ed, "start")}>{"درايفورت" if ed == "ar" else "Dreifurt"}</text>')
    badges = ""
    for n, lon, lat, en, ar in ACTORS:
        bx, by = G.xy(lon, lat)
        badges += (f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="6.4" fill="#2c3943" stroke="#fff" stroke-width="1.1"/>'
                   f'<text x="{bx:.1f}" y="{by + 2.7:.1f}">{n}</text>')
    # Puerto Rico, off the frame to the south-east, in a box of its own
    ix, iy, iw, ih = x0 + w - 122, y0 + h - 232, 108, 62
    pr = shapely.make_valid(_to(A["proj"], [G.held_ll["puertorico"]])[0])
    c = pr.centroid
    kk = 0.00019
    prpx = shapely.affinity.affine_transform(pr, [kk, 0, 0, -kk, ix + iw / 2 - kk * c.x, iy + ih / 2 + 4 + kk * c.y])
    prpx = shapely.intersection(shapely.simplify(prpx, 0.2), shapely.box(ix + 1, iy + 1, ix + iw - 1, iy + ih - 1))
    K = KEY[ed]
    inset = (f'<rect x="{ix}" y="{iy}" width="{iw}" height="{ih}" fill="#e3eef4" stroke="#55646d" stroke-width=".8"/>'
             f'<path d="{path_d(prpx)}" fill="{colour["puertorico"]}" stroke="{INK["coast"]}" stroke-width=".6"/>'
             f'<text x="{ix + iw / 2:.1f}" y="{iy + 11:.1f}" text-anchor="middle" font-family=\'{L["font"]}\' font-size="8.6" '
             f'font-weight="700" fill="#1f2a30"' + (' direction="rtl"' if ed == "ar" else "") + f'>{html.escape(K["inset"])}</text>')
    overlay = (
        _waters(G, ed, WATERS)
        + f"<g font-family='{L['font']}' font-size=\"9\" font-style=\"italic\" fill=\"#6b6b66\">{notes}</g>"
        + f'<g stroke="#333" stroke-width=".8" fill="none" opacity=".6">{"".join(leads)}</g>'
        + f'<g {st} text-anchor="middle" font-size="12.5" fill="#141414" font-weight="700" stroke-width="2.4"'
        + (' direction="rtl"' if ed == "ar" else ' letter-spacing="1.1"') + f'>{"".join(big_n)}</g>'
        + f'<g {st} text-anchor="middle" font-size="9.2" fill="#2b2b2b" font-style="italic" font-weight="600" stroke-width="2.2"'
        + (' direction="rtl"' if ed == "ar" else "") + f'>{"".join(big_t)}</g>'
        + f'<g {st} text-anchor="middle" font-size="9.6" fill="#141414" font-weight="700" stroke-width="2.4"'
        + (' direction="rtl"' if ed == "ar" else "") + f'>{"".join(small_n)}</g>'
        + f'<g {st} text-anchor="middle" font-size="8.2" fill="#2b2b2b" font-style="italic" font-weight="600" stroke-width="2.1"'
        + (' direction="rtl"' if ed == "ar" else "") + f'>{"".join(small_t)}</g>'
        + f'<g {st} font-size="8.4" fill="#5a2a2a" font-style="italic" font-weight="600" stroke-width="2.1">{terr}</g>'
        + capital
        + f"<g font-family='{L['font']}' font-size=\"7.6\" font-weight=\"700\" fill=\"#fff\" text-anchor=\"middle\">{badges}</g>"
        + inset)
    # the key: the hatches, then the numbered actors in three columns
    band_y = y0 + h
    sw = lambda fill, stroke="#9a3a3a", dash="": (f'<rect x="0" y="-5" width="14" height="10" rx="1.5" fill="{fill}" '
                                                 f'stroke="{stroke}" stroke-width=".7"{dash}/>')
    items = [(sw(f"url(#{tag}-occ)"), K["occupied"]), (sw(f"url(#{tag}-held)"), K["held"]),
             (sw("none", "#b0353f", ' stroke-dasharray="3 2"'), K["presence"]),
             (sw(f"url(#{tag}-auto)", "#5b6b76"), K["auto"]),
             ('<circle cx="7" cy="0" r="3.1" fill="#fff" stroke="#1d2a33" stroke-width="1.1"/>'
              '<circle cx="7" cy="0" r="1.2" fill="#1d2a33"/>', K["capital"])]
    cols, per = 3, math.ceil(len(ACTORS) / 3)
    colw = (w - 28) / cols
    key = ""
    for i, (n, lon, lat, en, ar) in enumerate(ACTORS):
        cx_ = 14 + (i // per) * colw
        cy_ = band_y + 42 + (i % per) * 15.5
        word = ar if ed == "ar" else en
        if ed == "en":
            key += (f'<circle cx="{cx_ + 6:.1f}" cy="{cy_:.1f}" r="6" fill="#2c3943"/>'
                    f'<text x="{cx_ + 6:.1f}" y="{cy_ + 2.7:.1f}" text-anchor="middle" font-size="7.6" font-weight="700" '
                    f'fill="#fff">{n}</text><text x="{cx_ + 17:.1f}" y="{cy_ + 3.4:.1f}">{html.escape(word)}</text>')
        else:
            rx = w - cx_
            key += (f'<circle cx="{rx - 6:.1f}" cy="{cy_:.1f}" r="6" fill="#2c3943"/>'
                    f'<text x="{rx - 6:.1f}" y="{cy_ + 2.7:.1f}" text-anchor="middle" font-size="7.6" font-weight="700" '
                    f'fill="#fff">{n}</text><text x="{rx - 17:.1f}" y="{cy_ + 3.4:.1f}" direction="rtl" '
                    f'text-anchor="start">{html.escape(word)}</text>')
    band_h = 42 + per * 15.5 + 6
    band = (f'<rect x="{x0}" y="{band_y}" width="{w}" height="{band_h:.0f}" fill="#fff"/>'
            f'<path d="M{x0} {band_y}H{x0 + w}" stroke="#c9c4b8" stroke-width="1"/>'
            f"<g font-family='{L['font']}' font-size=\"10\" fill=\"#22292e\">"
            + _legend_row(ed, w, items, band_y + 16) + key + "</g>")
    return ground + overlay + band, f"{x0} {y0} {w} {h + band_h:.0f}"


def _towns(G, ed, st):
    dots, names = "", ""
    for lon, lat, en, ar, kind, dx, dy, anchor in TOWNS:
        x, y = G.xy(lon, lat)
        if kind == "capital":
            dots += (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#fff" stroke="#1d2a33" stroke-width="1.3"/>'
                     f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.6" fill="#1d2a33"/>')
        elif kind == "holy":
            dots += (f'<path d="M{x:.1f} {y - 5:.1f}l1.5 3.5 3.5 1.5-3.5 1.5-1.5 3.5-1.5-3.5-3.5-1.5 3.5-1.5z" '
                     f'fill="#1d6b3a" stroke="#fff" stroke-width=".8"/>')
        elif kind == "port":
            dots += f'<rect x="{x - 2.6:.1f}" y="{y - 2.6:.1f}" width="5.2" height="5.2" fill="#1d2a33" stroke="#fff" stroke-width=".8"/>'
        elif kind == "seat":
            dots += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="#1d2a33" stroke="#fff" stroke-width=".9"/>'
        else:
            dots += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.9" fill="#fff" stroke="#1d2a33" stroke-width=".9"/>'
        weight = ' font-weight="700"' if kind in ("capital", "holy") else ""
        size = ' font-size="10.6"' if kind == "capital" else ""
        names += (f'<text x="{x + dx:.1f}" y="{y + dy:.1f}"{_anchored(ed, anchor)}{weight}{size}>'
                  f'{html.escape(ar if ed == "ar" else en)}</text>')
    return dots + f'<g {st} font-size="9.2" fill="#1d2a33" stroke-width="2.3">{names}</g>'


def _oil(G, ed, st):
    marks, names = "", ""
    for lon, lat, en, ar, dx, dy, anchor in OILFIELDS:
        x, y = G.xy(lon, lat)
        marks += f'<path d="M{x:.1f} {y - 4.2:.1f}l3.8 7.2h-7.6z" fill="#3a2f23" stroke="#fff" stroke-width=".8"/>'
        names += (f'<text x="{x + dx:.1f}" y="{y + dy:.1f}"{_anchored(ed, anchor)}>'
                  f'{html.escape(ar if ed == "ar" else en)}</text>')
    return marks + f'<g {st} font-size="8.4" font-style="italic" fill="#3a2f23" stroke-width="2.1">{names}</g>'


def _neighbours(G, ed):
    L = LABELS[ed]
    by = {r["key"]: r for r in G.rows}
    out = ""
    for key, lon, lat in NEIGHBOURS:
        x, y = G.xy(lon, lat)
        out += (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle"' + (' direction="rtl"' if ed == "ar" else "")
                + f'>{html.escape(by[key]["name_ar"] if ed == "ar" else by[key]["name"])}</text>')
    return (f"<g font-family='{L['font']}' font-size=\"9.6\" font-style=\"italic\" fill=\"#55524a\" "
            f'fill-opacity=".8">{out}</g>')


def _kingdom(cfg, G: Ground, tag: str, ed: str, march_fill: dict, ribbon_name: str, legend: str, band_h: float,
             twins: bool, strength: float = 0.42, share=None) -> tuple[str, str]:
    x0, y0, w, h = G.F.area
    fills = "".join(f'<path d="{path_d(G.nations[r["key"]])}" fill="{_pale(r["colour"])}"/>'
                    for r in G.nation_rows if r["key"] != "solms")
    fills += "".join(f'<path d="{path_d(G.marches[r["key"]])}" fill="{march_fill[r["key"]]}"/>' for r in G.march_rows)
    nations = [(G.nations[r["key"]], _pale(r["colour"])) for r in G.nation_rows if r["key"] != "solms"]
    nations += [(G.marches[r["key"]], march_fill[r["key"]]) for r in G.march_rows]
    ribbons = terrain.ribbons(cfg, ribbon_name, G.F.area, nations, shapely.union(G.frontiers, G.march_lines),
                              strength=strength)
    edge = G.nations["solms"].boundary
    inland = _lines(shapely.difference(edge, shapely.union_all(
        [p.boundary for p in shapely.get_parts(shapely.union(G.body, G.other.buffer(0.2)))]).buffer(0.3)))
    lines = (f'<path d="{path_d(G.march_lines)}" fill="none" stroke="#fff" stroke-width="1.5" stroke-opacity=".65" '
             f'stroke-linejoin="round"/>'
             f'<path d="{path_d(G.march_lines)}" fill="none" stroke="#5b5b5b" stroke-width=".7" stroke-dasharray="2.2 1.6" '
             f'stroke-linejoin="round"/>')
    # the kingdom's own frontier, over the neighbours' dash-dot lines
    edge_line = (f'<path d="{path_d(inland)}" fill="none" stroke="#fff" stroke-width="3.2" stroke-opacity=".8" '
                 f'stroke-linejoin="round"/>'
                 f'<path d="{path_d(inland)}" fill="none" stroke="#2a2f33" stroke-width="1.3" stroke-linejoin="round"/>')
    ground = _base(G, tag, fills, ribbons, lines, share=share) + edge_line + "</g>"
    L, st = LABELS[ed], _style(ed)
    names, under = "", ""
    for r in G.march_rows:
        cx, cy = G.xy(r["label_lon"], r["label_lat"])
        name = r["name_ar"] if ed == "ar" else r["name"].upper()
        names += f'<text x="{cx:.1f}" y="{cy:.1f}">{html.escape(name)}</text>'
        if twins:
            under += f'<text x="{cx:.1f}" y="{cy + 10.5:.1f}">{html.escape(r["twin_ar"] if ed == "ar" else r["twin"])}</text>'
    overlay = (
        _waters(G, ed, KINGDOM_WATERS, 11)
        + _neighbours(G, ed)
        + f'<g {st} text-anchor="middle" font-size="11" fill="#141414" font-weight="700" stroke-width="2.4"'
        + (' direction="rtl"' if ed == "ar" else ' letter-spacing=".9"') + f'>{names}</g>'
        + f'<g {st} text-anchor="middle" font-size="8.6" fill="#2b2b2b" font-style="italic" font-weight="600" stroke-width="2.1"'
        + (' direction="rtl"' if ed == "ar" else "") + f'>{under}</g>')
    band = (f'<rect x="{x0}" y="{y0 + h}" width="{w}" height="{band_h}" fill="#fff"/>'
            f'<path d="M{x0} {y0 + h}H{x0 + w}" stroke="#c9c4b8" stroke-width="1"/>'
            f"<g font-family='{L['font']}' font-size=\"10\" fill=\"#22292e\">{legend}</g>")
    return ground + overlay, band


def marches(cfg, continent, provinces, ed: str, shared: bool = False) -> tuple[str, str]:
    """The kingdom: thirteen marches, their seats, the holy cities, the oilfields."""
    G = _ground(cfg, "kingdom", KINGDOM, continent, provinces)
    x0, y0, w, h = G.F.area
    st, K = _style(ed), KEY[ed]
    fill = {r["key"]: r["colour"] for r in G.march_rows}
    items = [('<circle cx="7" cy="0" r="4" fill="#fff" stroke="#1d2a33" stroke-width="1.3"/><circle cx="7" cy="0" r="1.6" fill="#1d2a33"/>', K["capital"]),
             ('<circle cx="7" cy="0" r="2.6" fill="#1d2a33"/>', K["seat"]),
             ('<path d="M7 -5l1.5 3.5 3.5 1.5-3.5 1.5-1.5 3.5-1.5-3.5-3.5-1.5 3.5-1.5z" fill="#1d6b3a"/>', K["holy"]),
             ('<rect x="4.4" y="-2.6" width="5.2" height="5.2" fill="#1d2a33"/>', K["port"]),
             ('<path d="M7 -4.2l3.8 7.2h-7.6z" fill="#3a2f23"/>', K["oil"]),
             ('<path d="M0 0H14" stroke="#2a2f33" stroke-width="1.25"/>', K["frontier"]),
             ('<path d="M0 0H14" stroke="#5b5b5b" stroke-width=".8" stroke-dasharray="2.2 1.6"/>', K["march"])]
    body, band = _kingdom(cfg, G, "nam", ed, fill, "Solms-America marches", _legend_row(ed, w, items, y0 + h + 15), 30, True,
                          share=("define", "nak") if shared else None)
    return body + _oil(G, ed, st) + _towns(G, ed, st) + band, f"{x0} {y0} {w} {h + 30}"


def unification(cfg, continent, provinces, ed: str, shared: bool = False) -> tuple[str, str]:
    """The same ground, coloured by the years in which the House of Solms took each march."""
    G = _ground(cfg, "kingdom", KINGDOM, continent, provinces)
    x0, y0, w, h = G.F.area
    st = _style(ed)
    fill = {k: colour for _, colour, keys in UNIFICATION for k in keys}
    items = [(f'<rect x="0" y="-5" width="14" height="10" rx="1.5" fill="{colour}" stroke="#55646d" stroke-width=".6"/>', span)
             for span, colour, _ in UNIFICATION]
    title = UNIFICATION_TITLE[ed]
    tw = 0.56 * 10 * len(title) + 22
    if ed == "en":
        legend = (f'<text x="14" y="{y0 + h + 18.6}" font-weight="700">{html.escape(title)}</text>'
                  f'<g transform="translate({tw:.0f} 0)">' + _legend_row(ed, w, items, y0 + h + 15, 0) + "</g>")
    else:
        legend = (f'<text x="{w - 14}" y="{y0 + h + 18.6}" font-weight="700" direction="rtl" text-anchor="start">{html.escape(title)}</text>'
                  f'<g transform="translate({-tw:.0f} 0)">' + _legend_row(ed, w, items, y0 + h + 15, 0) + "</g>")
    body, band = _kingdom(cfg, G, "nau", ed, fill, "Solms-America unification", legend, 30, False, strength=0.2,
                          share=("use", "nak") if shared else None)
    # the years, set under each march's name, so the map does not rest on colour alone
    L = LABELS[ed]
    years = ""
    when = {k: span for span, _, keys in UNIFICATION for k in keys}
    for r in G.march_rows:
        cx, cy = G.xy(r["label_lon"], r["label_lat"])
        years += f'<text x="{cx:.1f}" y="{cy + 10.5:.1f}">{when[r["key"]]}</text>'
    years = (f'<g {st} text-anchor="middle" font-size="8.8" fill="#1d2a33" font-weight="600" stroke-width="2.2">{years}</g>')
    keep = [t for t in TOWNS if t[4] in ("capital", "holy") or t[2] in ("Braunfels", "Wichita", "Neches", "Waimas")]
    dots = ""
    names = ""
    for lon, lat, en, ar, kind, dx, dy, anchor in keep:
        x, y = G.xy(lon, lat)
        dots += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.3" fill="#fff" stroke="#1d2a33" stroke-width="1"/>'
        names += f'<text x="{x + dx:.1f}" y="{y + dy:.1f}"{_anchored(ed, anchor)}>{html.escape(ar if ed == "ar" else en)}</text>'
    towns = dots + f'<g {st} font-size="9" fill="#1d2a33" stroke-width="2.3">{names}</g>'
    return body + years + towns + band, f"{x0} {y0} {w} {h + 30}"


def locator(cfg, continent, ed: str) -> tuple[str, str]:
    """The kingdom on the continent, small, for the infobox: no relief, the kingdom alone in colour."""
    A = {**CONTINENT, "area": (0, 0, 330, 243.9)}
    G = _ground(cfg, "locator", A, continent, relief=False, river_rank=2)
    x0, y0, w, h = G.F.area
    simp = lambda g, t=0.5: shapely.simplify(g, t)
    fills = "".join(f'<path d="{path_d(simp(G.nations[r["key"]]))}" fill="{"#1d6b78" if r["key"] == "solms" else "#ece8dd"}"/>'
                    for r in G.nation_rows)
    body = (f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="#dbe8ef"/>'
            f'<path d="{path_d(simp(G.other))}" fill="#e2ded3"/>{fills}'
            f'<path d="{path_d(simp(G.lakes))}" fill="#dbe8ef"/>'
            f'<path d="{path_d(simp(G.frontiers, 0.4))}" fill="none" stroke="#9b978c" stroke-width=".5"/>'
            f'<path d="{path_d(simp(shapely.union(G.body, G.other)))}" fill="none" stroke="#7d8a90" stroke-width=".5"/>')
    return body, f"{x0} {y0} {w} {h:.0f}"


_GROUNDS: dict = {}


def _ground(cfg, name, A, continent, provinces=None, **kw) -> Ground:
    key = (name, A["area"])
    if key not in _GROUNDS:
        label = {"political": "North America", "kingdom": "Solms-America", "locator": "North America locator"}[name]
        _GROUNDS[key] = Ground(cfg, A, label, continent, provinces,
                               focus="solms" if name == "kingdom" else None,
                               river_rank=kw.pop("river_rank", 6 if name == "kingdom" else 4), **kw)
    return _GROUNDS[key]


# -- the pages --------------------------------------------------------------------------------

ARIA = {
    "political": {
        "en": "Map of North America at the end of 2023: Solms-America in the centre, with Mississippi and Atlantica to the east, Cascadia, Oregon, Aztlan, California and Colorado to the west, Mexico, Nuevo León, Río Grande, the Counties, Karankawa and Ludwigsland around the Gulf, and Canada to the north; occupied territories and the ground held by sixteen non-state actors are hatched and numbered.",
        "ar": "خريطة أمريكا الشمالية في نهاية عام 2023: زولمس-أمريكا في الوسط، والمسيسيبي وأتلانتيكا شرقًا، وكاسكاديا وأوريغون وأزتلان وكاليفورنيا وكولورادو غربًا، والمكسيك ونويفو ليون وريو غراندي والمقاطعات وكارانكاوا ولودفيغسلاند حول الخليج، وكندا شمالًا؛ والأراضي المحتلة والمناطق التي تسيطر عليها ست عشرة جهة غير حكومية مظللة ومرقّمة."},
    "marches": {
        "en": "Map of the Kingdom of Solms-America and its thirteen marches, from Kansa and Wichita in the north through Dreifurt, Rotland and the Ostmark to the Gulf of Mexico, and west across the Hochebene, Pecos, Oberland and Chihuahua to the holy marches of Paquimé and Chukson, Bergland and the Küstenland on the Gulf of California.",
        "ar": "خريطة مملكة زولمس-أمريكا وماركاتها الثلاث عشرة، من كانسا وويتشيتا شمالًا عبر درايفورت وروتلاند وأوستمارك إلى خليج المكسيك، وغربًا عبر هوخ إيبنه وبيكوس وأوبرلاند وتشيواوا إلى المارْكتين المقدستين باكيمي وتشوكسون وبيرغلاند وكوستنلاند على خليج كاليفورنيا."},
    "unification": {
        "en": "Map of the unification of Solms-America: Dreifurt and Rotland taken in 1902 to 1906, the Ostmark in 1913, Wichita, Kansa, the Hochebene and Bergland in 1919 to 1922, the holy marches, the Küstenland, Oberland and Pecos in 1924 to 1926, and Chihuahua in 1934.",
        "ar": "خريطة توحيد زولمس-أمريكا: درايفورت وروتلاند بين 1902 و1906، وأوستمارك عام 1913، وويتشيتا وكانسا وهوخ إيبنه وبيرغلاند بين 1919 و1922، والمارْكتان المقدستان وكوستنلاند وأوبرلاند وبيكوس بين 1924 و1926، وتشيواوا عام 1934."},
    "locator": {
        "en": "Locator map: the Kingdom of Solms-America, in teal, in the south-centre of North America between the Gulf of Mexico and the Gulf of California.",
        "ar": "خريطة الموقع: مملكة زولمس-أمريكا، بالأزرق المخضرّ، في وسط جنوب أمريكا الشمالية بين خليج المكسيك وخليج كاليفورنيا."},
}


def build(cfg: dict, only=None, dump=None) -> list[str]:
    """Draw the maps and set each where a page carries its markers. Returns the pages changed.
    With `dump` (a folder), every map is also written there as an SVG file of its own, to look at."""
    store = paths(cfg).data / "atlas"
    land_ll = real_land_ll(cfg, {"bbox": fr.NORTH_AMERICA_BBOX})
    held, unclaimed, rows, spec = fr.held_nations("north-america", land_ll, store)
    continent = (held, unclaimed, rows, spec, land_ll)
    provinces = fr.held_nations("solms-america", land_ll, store)
    print(f"    {len(held)} nations cut by {len(spec['frontiers'])} frontiers; {len(provinces[0])} marches")
    draw = {"political": lambda ed, shared=False: political(cfg, continent, ed),
            "marches": lambda ed, shared=False: marches(cfg, continent, provinces, ed, shared),
            "unification": lambda ed, shared=False: unification(cfg, continent, provinces, ed, shared),
            "locator": lambda ed, shared=False: locator(cfg, continent, ed)}
    done, changed = {}, []
    if dump:
        import pathlib
        pathlib.Path(dump).mkdir(parents=True, exist_ok=True)
        for name in draw:
            if only and name not in only:
                continue
            for ed in ("en", "ar"):
                print(f"    drawing {name} ({ed})")
                done[(name, ed, False)] = body, vb = draw[name](ed)
                (pathlib.Path(dump) / f"{name}.{ed}.svg").write_text(
                    f'<svg viewBox="{vb}" xmlns="http://www.w3.org/2000/svg">{body}</svg>', encoding="utf8")
    for page in PAGES:
        for p in (page, "ar/" + page):
            f = SITE / p
            if not f.exists():
                continue
            with open(f, encoding="utf8", newline="") as fh:
                text = fh.read()
            ed = "ar" if p.startswith("ar/") else "en"
            new = text
            marks = list(re.finditer(r"<!-- cg-na:([a-z]+) -->(.*?)<!-- /cg-na:\1 -->", text, re.S))
            # a page with both maps of the kingdom carries their sea and relief once
            both = {"marches", "unification"} <= {m.group(1) for m in marks}
            for m in marks[::-1]:
                name = m.group(1)
                if name not in draw or (only and name not in only):
                    continue
                shared = both and name in ("marches", "unification")
                if (name, ed, shared) not in done:
                    print(f"    drawing {name} ({ed})")
                    done[(name, ed, shared)] = draw[name](ed, shared)
                body, vb = done[(name, ed, shared)]
                cls = ' class="locator"' if name == "locator" else ""
                ltr = ' direction="ltr"' if ed == "ar" else ""      # the page's right-to-left is not the map's
                svg = (f'<svg{cls} viewBox="{vb}" xmlns="http://www.w3.org/2000/svg"{ltr} role="img" '
                       f'aria-label="{html.escape(ARIA[name][ed], quote=True)}">{body}</svg>')
                new = new[:m.start(2)] + svg + new[m.end(2):]
            if new != text:
                with open(f, "w", encoding="utf8", newline="") as fh:
                    fh.write(new)
                changed.append(p)
    return changed
