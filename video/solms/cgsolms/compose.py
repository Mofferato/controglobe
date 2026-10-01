"""The HyperFrames composition of a phase: phaseN/script.yaml, cast.yaml and polities.yaml, made
into data for the engine (engine/engine.js), with the ground, the art and the fonts beside it.

    python solms.py compose 1     ->  build/solms/phase1/hf/  (index.html, data.js, engine.js, assets/)

Everything the engine draws is resolved here: places to plate pixels, dates to the composition's
seconds through each scene's clock, the map's states to merged shapes with their labels and areas,
the wars to armies, arrows, battles and numbers, the cast's lines to timed bubbles. The engine then
draws every frame as a pure function of time, which is what HyperFrames needs to render it.
"""

from __future__ import annotations

import json
import math
import re
import shutil

import numpy as np
import shapely
import yaml

from . import areas as AR
from . import frame as F
from .ground import Plate

ENGINE = F.SOLMS / "cgsolms" / "engine"
CACHE = F.VIDEO / "cache" / "solms"

MONTHS = {"01": 0, "02": 1, "03": 2, "04": 3, "05": 4, "06": 5, "07": 6, "08": 7, "09": 8, "10": 9, "11": 10, "12": 11}


# -- dates -------------------------------------------------------------------------------------

def astro(d) -> float:
    """A date as a continuous astronomical year: '26 BCE-03' -> -25 + 2/12; 272 -> 272.0; -150 -> -149.
    BCE years are written as such and there is no year 0; a number is the start of that year."""
    if isinstance(d, (int, float)):
        return float(d + 1 if d < 0 else d)
    s = str(d).strip()
    m = re.fullmatch(r"(\d+)\s*BCE(?:-(\d\d))?(?:-(\d\d))?", s)
    if m:
        y = -int(m.group(1)) + 1
        mo, dd = m.group(2), m.group(3)
    else:
        m = re.fullmatch(r"(-?\d+)(?:-(\d\d))?(?:-(\d\d))?", s)
        if not m:
            raise ValueError(f"cannot read the date {d!r}")
        y = int(m.group(1))
        if y < 0:
            y += 1
        mo, dd = m.group(2), m.group(3)
    f = 0.0
    if mo:
        f += MONTHS[mo] / 12.0
    if dd:
        f += (int(dd) - 1) / 365.25
    return y + f


# -- the composition ---------------------------------------------------------------------------

class Comp:
    def __init__(self, n: int):
        self.n = n
        self.dir = F.phase_dir(n)
        self.script = yaml.safe_load((self.dir / "script.yaml").read_text(encoding="utf8"))
        self.cast = yaml.safe_load((self.dir / "cast.yaml").read_text(encoding="utf8"))
        self.pol = yaml.safe_load((self.dir / "polities.yaml").read_text(encoding="utf8"))
        self.fr = F.frame(f"phase{n}")
        self.plate = Plate(self.fr, self.fr["grids"]["tex"])
        self.km_px = (self.fr["extent"][2] - self.fr["extent"][0]) / 1000.0 / self.plate.W
        self.out = F.build_dir(n) / "hf"
        self.scenes = []
        t = 0.0
        for sc in self.script["scenes"]:
            sc = dict(sc)
            sc["T"] = t
            sc["_clock"] = [(t + k[0], astro(k[1])) for k in sc["clock"]]
            self.scenes.append(sc)
            t += sc["dur"]
        self.duration = t

    # places
    def px(self, lon, lat):
        x, y = self.plate.ll(lon, lat)
        return [round(float(x), 1), round(float(y), 1)]

    def pts(self, ll):
        return [self.px(a, b) for a, b in ll]

    # the clock: a scene's dates to the composition's seconds
    def T(self, sc, d) -> float:
        a = astro(d) if not isinstance(d, float) else d
        keys = sc["_clock"]
        if len(keys) == 1:
            return keys[0][0]
        if a <= keys[0][1]:
            return keys[0][0]
        for (t0, a0), (t1, a1) in zip(keys, keys[1:]):
            if a0 <= a <= a1:
                return t0 if a1 == a0 else t0 + (a - a0) / (a1 - a0) * (t1 - t0)
        return keys[-1][0]

    def clock(self):
        out = []
        for sc in self.scenes:
            for t, a in sc["_clock"]:
                out.append([round(t, 3), round(a, 5)])
            if len(sc["_clock"]) == 1:
                out.append([round(sc["T"] + sc["dur"] - 1e-3, 3), round(sc["_clock"][0][1], 5)])
        return out

    # -- the map's states --------------------------------------------------------------------
    def map_states(self):
        """Every distinct state of the map over the phase, with the seconds each begins."""
        mp = json.loads((F.build_dir(self.n) / "map.json").read_text(encoding="utf8"))
        holds = {pid: [[astro(a), astro(b), ar, st] for a, b, ar, st in p.get("holds", [])]
                 for pid, p in self.pol["polities"].items()}
        bounds = sorted({v for h in holds.values() for a, b, _, _ in h for v in (a, b)})

        def state_at(a):
            own = {}
            for pid, hs in holds.items():
                for a0, a1, ar, st in hs:
                    if a0 <= a < a1:
                        own[ar] = (pid, st)
            return own

        geoms = {k: _parse_d(v["d"]) for k, v in mp["areas"].items()}
        states, keys, seen = [], [], {}
        clock = self.clock()
        # sample the state at every clock key and every boundary the clock crosses
        times = []
        for (t0, a0), (t1, a1) in zip(clock, clock[1:]):
            times.append((t0, a0))
            for b in bounds:
                if a0 < b <= a1 and a1 > a0:
                    times.append((t0 + (b - a0) / (a1 - a0) * (t1 - t0), b))
        times.append(tuple(clock[-1]))
        times.sort()
        for t, a in times:
            own = state_at(a + 1e-6)
            sig = json.dumps(sorted(own.items()))
            if sig not in seen:
                seen[sig] = len(states)
                states.append(self._state(own, geoms, mp))
            idx = seen[sig]
            if not keys or keys[-1][1] != idx:
                keys.append([round(t, 3), idx])
        return states, keys, mp

    def _state(self, own, geoms, mp):
        groups = {}
        for ar, (pid, st) in own.items():
            if ar not in geoms:
                continue
            groups.setdefault((pid, st), []).append(geoms[ar])
        regions = []
        for (pid, st), gs in groups.items():
            g = shapely.make_valid(shapely.union_all(gs)).buffer(0.6).buffer(-0.6)
            if g.is_empty:
                continue
            big = max(shapely.get_parts(g), key=lambda q: q.area)
            lp = __import__("shapely.ops").ops.polylabel(big, 2.0) if big.geom_type == "Polygon" else big.representative_point()
            km2 = g.area * self.km_px ** 2
            regions.append({"p": pid, "st": st, "d": AR.path_d(g.simplify(0.4)), "c": [round(lp.x, 1), round(lp.y, 1)],
                            "km2": round(km2), "w": round(math.sqrt(big.area), 1)})
        # a polity's whole ground, for its label and its frontier ribbon
        polities = {}
        for r in regions:
            polities.setdefault(r["p"], []).append(r)
        out = []
        for pid, rs in polities.items():
            g = shapely.union_all([_parse_d(r["d"]) for r in rs]).buffer(0.6).buffer(-0.6)
            big = max(shapely.get_parts(g), key=lambda q: q.area)
            lp = __import__("shapely.ops").ops.polylabel(big, 2.0) if big.geom_type == "Polygon" else big.representative_point()
            # the label's slant: the long axis of the ground, so a name runs along it
            mrr = big.minimum_rotated_rectangle
            c = np.asarray(mrr.exterior.coords)[:4]
            e1, e2 = c[1] - c[0], c[2] - c[1]
            long = e1 if np.hypot(*e1) >= np.hypot(*e2) else e2
            ang = math.degrees(math.atan2(long[1], long[0]))
            if ang > 90:
                ang -= 180
            if ang < -90:
                ang += 180
            out.append({"p": pid, "d": AR.path_d(g.simplify(0.4)), "c": [round(lp.x, 1), round(lp.y, 1)],
                        "km2": round(sum(r["km2"] for r in rs)), "w": round(math.sqrt(big.area), 1),
                        "ang": round(ang * 0.6, 1)})
        return {"regions": regions, "polities": out}

    # -- the modern map (the cold open and the premise) --------------------------------------
    def modern(self):
        import sys
        sys.path.insert(0, str(F.VIDEO))
        from cgvideo import frontiers as fr
        from pyproj import Transformer
        import csv
        store = F.VIDEO / "data" / "atlas"
        ne = F.VIDEO / "cache" / "naturalearth"
        import geopandas as gpd
        land = gpd.read_file(f"/vsizip/{(ne / 'ne_10m_land.zip').as_posix()}")
        land_ll = shapely.make_valid(shapely.union_all(list(land.cx[-130:-60, 10:60].geometry)))
        fwd = Transformer.from_crs("EPSG:4326", self.fr["proj"], always_xy=True)
        out = {"nations": [], "marches": []}
        for region, key in (("north-america", "nations"), ("solms-america", "marches")):
            try:
                held, _, rows, _ = fr.held_nations(region, land_ll, store)
            except Exception as e:                       # the atlas has not been traced on this machine
                print(f"  modern map: {region} unavailable ({e})")
                continue
            for r in rows:
                if r["key"] not in held:
                    continue
                g = shapely.transform(held[r["key"]], lambda c: np.column_stack(fwd.transform(c[:, 0], c[:, 1])))
                g = self.plate.geom(g).simplify(0.8)
                lx, ly = self.px(float(r["label_lon"]), float(r["label_lat"]))
                out[key].append({"k": r["key"], "name": r["name"], "twin": r.get("twin", ""), "ar": r.get("name_ar", ""),
                                 "twin_ar": r.get("twin_ar", ""), "colour": r["colour"], "d": AR.path_d(g),
                                 "c": [lx, ly], "size": r.get("size", "big")})
        return out

    # -- everything else --------------------------------------------------------------------
    def build(self, log=print):
        S = self.script
        states, skeys, mp = self.map_states()
        log(f"  {len(states)} states of the map over {self.duration:.0f} s")
        D = {"W": S["size"][0], "H": S["size"][1], "fps": S["fps"], "duration": round(self.duration, 3),
             "title": S["title"], "subtitle": S["subtitle"], "era": S["era"], "discord": S["discord"],
             "plate": {"src": "assets/plate.jpg", "w": self.plate.W, "h": self.plate.H},
             "terrain": json.loads((F.ground_dir(f"phase{self.n}") / "terrain.json").read_text()),
             "m_per_px": (self.fr["extent"][2] - self.fr["extent"][0]) / self.plate.W,
             "km_per_px": self.km_px, "clock": self.clock(), "states": states, "stateKeys": skeys,
             "provinces": mp["provinces"], "polities": {}, "scenes": [], "camera": [], "lines": [], "cards": [],
             "intros": [], "vignettes": [], "routes": [], "goods": S.get("goods", []), "places": [], "towns": {},
             "events": [], "wars": {}, "regions": REGIONS_LABELS, "peoples": PEOPLES, "lower": []}
        D["terrain"]["src"] = "assets/terrain.bin"
        for k in ("regions", "peoples"):
            D[k] = [dict(r, xy=self.px(*r["at"])) for r in D[k]]
        for pid, c in self.cast.items():
            names = c.get("names", {})
            D["polities"][pid] = {"colour": c.get("colour", "#888"), "names": names, "short": c.get("short") or names.get("en", pid),
                                  "twin": c.get("twin", ""), "personality": c.get("personality", "").strip(),
                                  "capital": c.get("capital")}
        D["polities"]["queen"]["colour"] = D["polities"]["houses"]["colour"]
        # scenes, camera, lines, cards
        for sc in self.scenes:
            T0 = sc["T"]
            D["scenes"].append({"id": sc["id"], "t0": T0, "t1": T0 + sc["dur"], "date": sc.get("date", "year"),
                                "chapter": sc.get("chapter", ""), "infobox": bool(sc.get("infobox")), "map": sc.get("map", "history"),
                                "marches": bool(sc.get("marches")), "regions": bool(sc.get("regions")),
                                "peoples": bool(sc.get("peoples")), "goods": bool(sc.get("show_goods")),
                                "war": sc.get("war"), "clip": sc.get("clip")})
            if sc.get("clip"):
                c = sc["clip"]
                D["scenes"][-1]["clip"] = {"src": c["src"], "t0": T0 + c["t0"], "t1": T0 + c["t1"], "fade": c.get("fade", 1.0),
                                           "fade_in": c.get("fade_in", 0.3)}
            for k in sc["camera"]:
                x, y = self.px(k[1], k[2])
                D["camera"].append([round(T0 + k[0], 3), x, y, round(k[3] / self.km_px, 1), k[4], k[5]])
            for ln in sc.get("lines", []):
                t, who, mood, text = ln[:4]
                opt = ln[4] if len(ln) > 4 else {}
                rec = {"t": round(T0 + t, 3), "dur": opt.get("dur", 3.2), "who": who, "mood": mood, "text": text}
                if "at" in opt:
                    rec["xy"] = self.px(*opt["at"])
                D["lines"].append(rec)
            for c in sc.get("cards", []):
                rec = dict(c)
                rec["t"] = round(T0 + c["t"], 3)
                D["cards"].append(rec)
            for t, who, dur in sc.get("intros", []):
                D["intros"].append({"t": round(T0 + t, 3), "dur": dur, "who": who})
            for v in sc.get("vignettes", []):
                D["vignettes"].append({"t": round(T0 + v["t"], 3), "dur": v["dur"], "id": v["id"]})
            if sc.get("discord_lower"):
                d = sc["discord_lower"]
                D["lower"].append({"t": round(T0 + d["t"], 3), "dur": d["dur"]})
            if sc.get("war"):
                D["wars"][sc["war"]] = self.war(sc, S["wars"][sc["war"]])
        # the road, the places, the towns, the events
        for r in S.get("routes", []):
            D["routes"].append({"id": r["id"], "from": astro(r["from"]), "pts": self.pts(r["pts"]), "name": r.get("name")})
        for p in S.get("places", []):
            D["places"].append({"id": p["id"], "name": p["name"], "xy": self.px(*p["at"]), "kind": p["kind"],
                                "from": astro(p["from"]), "to": astro(p["to"])})
        for name, keys in S.get("towns", {}).items():
            D["towns"][name] = [[astro(d), v] for d, v in keys]
        for d, text in S.get("events", []):
            D["events"].append([astro(d), _label(d), text])
        D["modern"] = self.modern()
        self.write(D, log)
        return D

    def war(self, sc, w):
        o = {"name": w["name"], "sides": w["sides"], "armies": [], "arrows": [], "battles": [], "sieges": [],
             "bignum": [], "attrition": [], "results": w.get("results"), "fleets": w.get("fleets", [])}
        for a in w.get("armies", []):
            keys = [[round(self.T(sc, k[0]), 3), *self.px(k[1], k[2]), k[3]] for k in a["keys"]]
            o["armies"].append({"id": a["id"], "side": a["side"], "name": a["name"], "kind": a.get("kind", "army"),
                                "litter": a.get("litter", False), "keys": keys})
        for ar in w.get("arrows", []):
            o["arrows"].append({"side": ar["side"], "t0": self.T(sc, ar["from"]), "t1": self.T(sc, ar["to"]),
                                "pts": self.pts(ar["pts"]), "retreat": ar.get("retreat", False),
                                "river": ar.get("river", False), "small": ar.get("small", False)})
        if w.get("shortcut"):
            s = w["shortcut"]
            o["shortcut"] = {"t0": self.T(sc, s["from"]), "t1": self.T(sc, s["to"]), "pts": self.pts(s["pts"]), "label": s["label"]}
        for b in w.get("battles", []):
            o["battles"].append({"name": b["name"], "xy": self.px(*b["at"]), "t": self.T(sc, b["date"]),
                                 "sides": b["sides"], "general_falls": b.get("general_falls")})
        for s in w.get("sieges", []):
            o["sieges"].append({"name": s["name"], "xy": self.px(*s["at"]), "t0": self.T(sc, s["from"]),
                                "t1": self.T(sc, s["to"]), "by": s["by"], "holds": s["holds"], "fails": s.get("fails", False)})
        for b in w.get("bignum", []):
            o["bignum"].append({"side": b["side"], "xy": self.px(*b["at"]), "t0": self.T(sc, b["from"]),
                                "t1": self.T(sc, b["to"]), "angle": b.get("angle", 0)})
        for d, lon, lat, n in w.get("attrition", []):
            o["attrition"].append({"t": self.T(sc, d), "xy": self.px(lon, lat), "n": n})
        for k in ("fever", "headgate", "viceroy_dies", "capture"):
            if w.get(k):
                v = w[k]
                rec = {"xy": self.px(*v["at"])}
                if "date" in v:
                    rec["t"] = self.T(sc, v["date"])
                if "from" in v:
                    rec["t0"], rec["t1"] = self.T(sc, v["from"]), self.T(sc, v["to"])
                if "text" in v:
                    rec["text"] = v["text"]
                o[k] = rec
        for f in o["fleets"]:
            f["burn"] = self.T(sc, f["burn"])
        return o

    def write(self, D, log):
        out = self.out
        (out / "assets").mkdir(parents=True, exist_ok=True)
        (out / "data.js").write_text("window.DATA = " + json.dumps(D, ensure_ascii=False, separators=(",", ":")) + ";\n",
                                     encoding="utf8")
        for f in ENGINE.iterdir():
            if f.is_file() and f.name != "index.template.html":
                shutil.copy2(f, out / f.name)
        from . import skin
        skin.build(out / "assets")
        clips = []
        for sc in D["scenes"]:
            c = sc.get("clip")
            if c and (out / "assets" / c["src"]).exists():
                clips.append(f'  <video class="clip sceneclip" data-start="{c["t0"]:.3f}" data-duration="{c["t1"] - c["t0"]:.3f}" '
                             f'data-t0="{c["t0"]:.3f}" data-t1="{c["t1"]:.3f}" data-fade="{c["fade"]}" data-fin="{c["fade_in"]}" '
                             f'src="assets/{c["src"]}" muted playsinline></video>')
        audio = ""
        for name in ("score_mix.wav", "score.wav"):
            if (out / "assets" / name).exists():
                audio = f'  <audio data-start="0" data-duration="{D["duration"]:.3f}" data-volume="1" src="assets/{name}"></audio>'
                break
        html = (ENGINE / "index.template.html").read_text(encoding="utf8")
        for k, v in {"{{TITLE}}": D["title"], "{{SKIN}}": self.script.get("skin", "marble"), "{{W}}": str(D["W"]),
                     "{{H}}": str(D["H"]), "{{DUR}}": f'{D["duration"]:.3f}', "{{CLIPS}}": chr(10).join(clips),
                     "{{AUDIO}}": audio}.items():
            html = html.replace(k, v)
        (out / "index.html").write_text(html, encoding="utf8")
        _fetch_vendor()
        for d in ("vendor", "fonts"):
            dst = out / d
            dst.mkdir(exist_ok=True)
            for f in (CACHE / d).iterdir():
                if not (dst / f.name).exists() or (dst / f.name).stat().st_size != f.stat().st_size:
                    shutil.copy2(f, dst / f.name)
        G = F.ground_dir(f"phase{self.n}")
        _link(G / "plate_marble.jpg", out / "assets" / "plate.jpg")
        _link(G / "terrain.bin", out / "assets" / "terrain.bin")
        log(f"  composition: {out / 'index.html'} ({self.duration / 60:.1f} min, {len(D['lines'])} lines, "
            f"{len(D['wars'])} wars)")


def _link(src, dst):
    if dst.exists() and dst.stat().st_size == src.stat().st_size:
        return
    if dst.exists():
        dst.unlink()
    try:
        import os
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _fetch_vendor():
    """three.js, GSAP and the skins' open fonts, downloaded once into cache/solms."""
    import urllib.request
    want = {
        "vendor/three.module.min.js": "https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.min.js",
        "vendor/gsap.min.js": "https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/gsap.min.js",
    }
    G = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
    for f in ("cinzel/Cinzel%5Bwght%5D.ttf", "cinzeldecorative/CinzelDecorative-Bold.ttf",
              "cormorantgaramond/CormorantGaramond%5Bwght%5D.ttf", "cormorantgaramond/CormorantGaramond-Italic%5Bwght%5D.ttf",
              "amiri/Amiri-Regular.ttf", "amiri/Amiri-Bold.ttf", "unifrakturmaguntia/UnifrakturMaguntia-Book.ttf"):
        want["fonts/" + f.split("/")[-1].replace("%5B", "[").replace("%5D", "]")] = G + f
    for rel, url in want.items():
        p = CACHE / rel
        if p.exists() and p.stat().st_size > 1000:
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, p)


def _parse_d(d):
    polys = []
    for ring in re.findall(r"M([^Z]+)Z", d):
        pts = [tuple(float(v) for v in pt.split(",")) for pt in ring.split("L")]
        if len(pts) > 2:
            polys.append(shapely.Polygon(pts))
    # rings are exteriors and holes in turn; even-odd by symmetric difference
    g = shapely.Polygon()
    for p in polys:
        g = g.symmetric_difference(shapely.make_valid(p))
    return shapely.make_valid(g)


def _label(d):
    s = str(d)
    return s if "BCE" in s or not s.startswith("-") else f"{s[1:]} BCE"


# geographic names for the tour of the land: English, American, Arabic (and the role they carry)
REGIONS_LABELS = [
    {"en": "The Staked Plain", "de": "Hochebene", "ar": "السهل الموتَّد", "at": [-102.4, 33.9], "size": 1.0},
    {"en": "The Caprock", "de": "Caprock", "ar": "جرف كابروك", "at": [-101.0, 33.2], "size": 0.6},
    {"en": "Sierra Madre", "de": "Sierra Madre", "ar": "سييرا مادري", "at": [-107.3, 27.3], "size": 1.0, "ang": -55},
    {"en": "The Sonoran Desert", "de": "Sonora-Wüste", "ar": "صحراء سونورا", "at": [-112.4, 31.4], "size": 0.9},
    {"en": "Rio Grande", "de": "Rio Grande", "ar": "ريو غراندي", "at": [-106.9, 33.4], "size": 0.7, "ang": -80},
    {"en": "The basin of Paquimé", "de": "Becken von Paquimé", "ar": "حوض باكيمي", "at": [-107.9, 30.75], "size": 0.75},
    {"en": "Gulf of California", "de": "Golf von Kalifornien", "ar": "خليج كاليفورنيا", "at": [-111.6, 27.9], "size": 0.9,
     "twin": "the Red Sea", "ang": -50, "water": True},
    {"en": "Gulf of Mexico", "de": "Golf von Mexiko", "ar": "خليج المكسيك", "at": [-91.5, 25.6], "size": 1.2,
     "twin": "the Gulf", "water": True},
    {"en": "The pine woods", "de": "Ostmark", "ar": "أوستمارك", "at": [-94.6, 31.6], "size": 0.75},
    {"en": "The black prairie", "de": "Schwarze Prärie", "ar": "البراري السوداء", "at": [-97.1, 31.4], "size": 0.75},
    {"en": "The Chihuahuan Desert", "de": "Chihuahua-Wüste", "ar": "صحراء تشيواوا", "at": [-104.8, 29.0], "size": 0.85},
    {"en": "The Red River plains", "de": "Rotland", "ar": "روتلاند", "at": [-98.2, 34.5], "size": 0.75},
]

# the peoples of 500 BCE
PEOPLES = [
    {"en": "The Nahua of the lake", "de": "Die Nahua am See", "ar": "ناهوا البحيرة", "at": [-111.9, 40.3], "p": "nahua", "t": 4.4},
    {"en": "Canal farmers of the Gila", "de": "Kanalbauern am Gila", "ar": "مزارعو القنوات على نهر غيلا", "at": [-111.6, 32.9], "p": "canal", "t": 6.4},
    {"en": "Villages of the San Juan", "de": "Dörfer am San Juan", "ar": "قرى سان خوان", "at": [-108.4, 36.6], "p": "houses", "t": 8.4},
    {"en": "Pueblos of the Rio Grande", "de": "Pueblos am Rio Grande", "ar": "قرى ريو غراندي", "at": [-105.7, 34.6], "p": None, "t": 10.4},
    {"en": "Foragers of the grassland", "de": "Sammler des Graslands", "ar": "جامعو القوت في المرعى", "at": [-101.0, 33.4], "p": "bison", "t": 13.0},
    {"en": "Mound farmers of the east", "de": "Hügelbauern des Ostens", "ar": "بناة التلال في الشرق", "at": [-94.6, 32.4], "p": "caddo", "t": 18.0},
    {"en": "Fire-keepers of the eastern woods", "de": "Feuerhüter der Ostwälder", "ar": "حفظة النار في الغابات الشرقية", "at": [-87.5, 36.8], "p": "fire", "t": 20.0},
    {"en": "Towns of the Valley of Mexico", "de": "Städte im Tal von Mexiko", "ar": "مدن وادي المكسيك", "at": [-99.2, 20.4], "p": "city", "t": 24.6},
]


def build(n: int, log=print):
    from . import areas
    areas.build(n, log=lambda *a: None)
    from . import cast
    cast.build(n, sheet=False, log=log)
    return Comp(n).build(log)
