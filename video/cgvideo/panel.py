"""The infobox: the dark panel on the right of every frame of the motion cut.

Top to bottom: the year and the era, the flag (and for the Union its Great Seal) and name of
the power that holds most of Arabia that year, its head of state with portrait, title, term and
party, the events of the year, an election result in election years, the population and the
largest cities from the first census on; and, in years with no known ruler, the leading powers
on the map with their colours. Everything is drawn with Pillow from the data tables.
"""

from __future__ import annotations

import bisect
import math
import pathlib
import textwrap

import matplotlib
from PIL import Image, ImageDraw, ImageFont

from . import assets
from . import years as Y


def _fontfile(name: str) -> str:
    return str(pathlib.Path(matplotlib.get_data_path()) / "fonts" / "ttf" / name)


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def hexrgb(c: str, a: int = 255):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


class Panel:
    def __init__(self, cfg, data, scene, W: int, H: int):
        self.cfg, self.data, self.scene, self.W, self.H = cfg, data, scene, W, H
        self.s = H / 1080
        self.x0 = int(W * float(cfg.get("motion", {}).get("panel_x", 0.655)))
        self.w = W - self.x0
        self._fonts = {}
        self.parties = {p["party"]: p for p in data.parties}
        self.rulers = sorted(data.rulers, key=lambda r: int(r["start"]))
        self.elections = {int(e["year"]): e for e in data.elections}
        pop = sorted((int(p["year"]), float(p["millions"])) for p in data.population)
        self.pop_years = [p[0] for p in pop]
        self.pop_vals = [p[1] for p in pop]
        self.region_area = {rid: g.area / 1e6 for rid, g in scene.region_geom.items()}
        self.arabia = set(data.expand("@arabia")) if "arabia" in data.groups else set(data.region_ids)
        self._focus_cache = {}
        self._img_cache = {}

    # -- small helpers ---------------------------------------------------------------
    def font(self, size, bold=False, serif=False):
        name = ("DejaVuSerif" if serif else "DejaVuSans") + ("-Bold" if bold else "") + ".ttf"
        key = (name, round(size))
        if key not in self._fonts:
            self._fonts[key] = ImageFont.truetype(_fontfile(name), max(8, round(size)))
        return self._fonts[key]

    def image(self, kind, key, w, *args):
        k = (kind, key, w)
        if k not in self._img_cache:
            if kind == "flag":
                img = assets.flag(self.cfg, self.data.polity[key], 300)
            elif kind == "seal":
                img = assets.union_seal(self.cfg, 400)
            else:
                img = assets.portrait(self.cfg, key, args[0], 240, args[1] if len(args) > 1 else "#8a6d3b")
            h = round(w * img.height / img.width)
            self._img_cache[k] = img.resize((max(1, w), max(1, h)), Image.LANCZOS)
        return self._img_cache[k]

    # -- what the panel is about -----------------------------------------------------
    def focus(self, year: int) -> str | None:
        """The top-level polity holding the most of Arabia's area this year."""
        if year in self._focus_cache:
            return self._focus_cache[year]
        row = self.data.matrix[self.data.year_index(year)]
        area = {}
        for k, rid in enumerate(self.data.region_ids):
            if rid not in self.arabia or row[k] < 0:
                continue
            top = self.data.top(self.data.polity_ids[row[k]])
            area[top] = area.get(top, 0) + self.region_area.get(rid, 0)
        best = max(area, key=area.get) if area else None
        for pid in (self.cfg.get("motion") or {}).get("focus_priority", ["usa"]):
            if pid in area:
                best = pid
                break
        self._focus_cache[year] = best
        return best

    def leaders(self, year: int, count=5):
        row = self.data.matrix[self.data.year_index(year)]
        area = {}
        for k, rid in enumerate(self.data.region_ids):
            if row[k] < 0:
                continue
            top = self.data.top(self.data.polity_ids[row[k]])
            area[top] = area.get(top, 0) + self.region_area.get(rid, 0)
        return sorted(area.items(), key=lambda kv: -kv[1])[:count]

    def ruler(self, year: int, focus: str | None):
        if not focus:
            return None
        hits = [r for r in self.rulers if int(r["start"]) <= year <= int(r["end"])
                and (r["polity"] == focus or self.data.top(r["polity"]) == focus
                     or r["polity"] in self._children(focus))]
        return hits[-1] if hits else None

    def _children(self, pid):
        return {p["polity_id"] for p in self.data.polities if p.get("parent") == pid}

    def population(self, year: float) -> float | None:
        if not self.pop_years or year < self.pop_years[0]:
            return None
        i = bisect.bisect_right(self.pop_years, year) - 1
        if i >= len(self.pop_years) - 1:
            return self.pop_vals[-1] * 1e6
        y0, y1 = self.pop_years[i], self.pop_years[i + 1]
        v0, v1 = self.pop_vals[i], self.pop_vals[i + 1]
        t = (year - y0) / (y1 - y0)
        return math.exp(math.log(v0) + t * (math.log(v1) - math.log(v0))) * 1e6

    def cities(self, year: int, focus: str | None, count=5):
        if focus != "usa" or year < 1790:
            return []
        nat = self.population(year)
        nat25 = self.pop_vals[-1] * 1e6
        out = []
        for c in self.data.cities:
            pop = float(c["pop2025"]) * (nat / nat25) ** float(c["growth"])
            if pop >= 30000:
                out.append((c["name"], c["state"], pop))
        return sorted(out, key=lambda t: -t[2])[:count]

    # -- drawing -------------------------------------------------------------------------
    def draw(self, img: Image.Image, slot: dict, t_in_slot: float) -> None:
        """Draw onto img (RGBA) for this slot; t_in_slot is seconds since the slot began."""
        s, x0, W, H = self.s, self.x0, self.W, self.H
        cfg = self.cfg
        hud = cfg["style"]["hud"]
        over = Image.new("RGBA", (self.w, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(over)
        panel = hexrgb(hud["panel"])
        # the panel fades in from the map over a soft left edge
        edge = int(40 * s)
        for i in range(edge):
            d.line([(i, 0), (i, H)], fill=panel[:3] + (int(235 * (i / edge) ** 1.5),))
        d.rectangle([edge, 0, self.w, H], fill=panel[:3] + (235,))
        text, accent, muted = hexrgb(hud["text"]), hexrgb(hud["accent"]), (170, 176, 184, 255)
        pad = int(46 * s)
        x = pad
        y = int(30 * s)
        year = slot["year"]
        grow = ease(t_in_slot / 0.6)

        # year and era
        d.text((x, y), slot["label"], font=self.font(78 * s, bold=True, serif=True), fill=text)
        y += int(92 * s)
        d.text((x, y), slot["era_name"].upper(), font=self.font(17 * s, bold=True), fill=accent)
        y += int(38 * s)

        focus = self.focus(year)
        if focus:
            fl = self.image("flag", focus, int(170 * s))
            over.alpha_composite(fl, (x, y))
            if focus == "usa":
                seal = self.image("seal", "usa", int(fl.height * 1.05))
                over.alpha_composite(seal, (x + fl.width + int(24 * s), y - int(4 * s)))
            y += fl.height + int(14 * s)
            name = self.data.polity[focus]["name"]
            f = self.font(30 * s, serif=True)
            for line in textwrap.wrap(name, 26):
                d.text((x, y), line, font=f, fill=text)
                y += int(36 * s)
            kind = self.data.polity[focus].get("kind", "")
            d.text((x, y), kind.capitalize(), font=self.font(15 * s), fill=muted)
            y += int(34 * s)

        r = self.ruler(year, focus)
        if r:
            party = self.parties.get(r.get("party", ""), {})
            accent_c = party.get("color", "#8a6d3b")
            d.text((x, y), "HEAD OF STATE", font=self.font(15 * s, bold=True), fill=muted)
            y += int(24 * s)
            pw = int(104 * s)
            por = self.image("portrait", r["portrait"], pw, r["name"], accent_c)
            over.alpha_composite(por, (x, y))
            tx = x + pw + int(18 * s)
            ty = y + int(4 * s)
            for line in textwrap.wrap(r["name"], 20):
                d.text((tx, ty), line, font=self.font(24 * s, bold=True, serif=True), fill=text)
                ty += int(29 * s)
            d.text((tx, ty), r["title"], font=self.font(15 * s), fill=muted)
            ty += int(22 * s)
            term = f"{Y.label(int(r['start']))} - {Y.label(int(r['end']))}" if int(r["end"]) < 2026 else f"since {Y.label(int(r['start']))}"
            d.text((tx, ty), term, font=self.font(15 * s), fill=muted)
            ty += int(28 * s)
            if party:
                rr = int(13 * s)
                cx, cy = tx + rr, ty + rr
                d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=hexrgb(party["color"]), outline=(255, 255, 255, 255), width=max(1, int(2 * s)))
                d.ellipse([cx - rr // 2.4, cy - rr // 2.4, cx + rr // 2.4, cy + rr // 2.4], fill=(255, 255, 255, 255))
                d.text((cx + rr + int(10 * s), cy - int(11 * s)), r["party"].upper(), font=self.font(17 * s, bold=True), fill=hexrgb(party["color"])[:3] + (255,) if sum(hexrgb(party["color"])[:3]) > 250 else text)
                ty += int(30 * s)
                for line in textwrap.wrap(party.get("ideology", ""), 30)[:2]:
                    d.text((tx, ty), line, font=self.font(13 * s), fill=muted)
                    ty += int(18 * s)
            y = max(y + por.height, ty) + int(18 * s)
        else:
            d.text((x, y), "LEADING POWERS", font=self.font(15 * s, bold=True), fill=muted)
            y += int(26 * s)
            for pid, area in self.leaders(year, 4):
                sw = int(18 * s)
                col = self.scene.fill[pid]
                d.rectangle([x, y + 3 * s, x + sw, y + 3 * s + sw], fill=tuple(int(v * 255) for v in col) + (255,), outline=(255, 255, 255, 180))
                d.text((x + sw + int(12 * s), y), self.data.polity[pid]["name"], font=self.font(19 * s), fill=text)
                d.text((self.w - pad, y), f"{area / 1e6:,.2f}M km²".replace("M km²", " M km²"), font=self.font(15 * s), fill=muted, anchor="ra")
                y += int(30 * s)
            y += int(14 * s)

        # election
        e = self.elections.get(year)
        if e and y < H - 300 * s:
            d.text((x, y), f"PRESIDENTIAL ELECTION {year}", font=self.font(15 * s, bold=True), fill=muted)
            y += int(26 * s)
            bw = self.w - 2 * pad - int(150 * s)
            for part in e["results"].split("|")[:4]:
                label, _, pct = part.rpartition(" ")
                pct = float(pct)
                base = label.split(" (")[0]
                col = hexrgb(self.parties.get(base, {}).get("color", "#8a8f94"))
                d.text((x, y), label, font=self.font(16 * s), fill=text)
                by = y + int(22 * s)
                d.rectangle([x, by, x + bw, by + int(10 * s)], fill=(255, 255, 255, 30))
                d.rectangle([x, by, x + int(bw * pct / 100 * grow), by + int(10 * s)], fill=col)
                d.text((x + bw + int(12 * s), y + int(8 * s)), f"{pct * grow:.1f}%", font=self.font(18 * s, bold=True), fill=text)
                y += int(42 * s)
            y += int(8 * s)

        # events
        caps = slot.get("captions", [])[:3]
        if caps and y < H - 200 * s:
            d.text((x, y), "EVENTS", font=self.font(15 * s, bold=True), fill=muted)
            y += int(24 * s)
            for n, c in enumerate(caps):
                alpha = 255 if n == 0 else 150
                for line in textwrap.wrap("- " + c["text"], 40)[:3]:
                    if y > H - 150 * s:
                        break
                    d.text((x, y), line, font=self.font(18 * s), fill=text[:3] + (alpha,))
                    y += int(24 * s)
                y += int(8 * s)
            y += int(6 * s)

        # population and cities
        pop = self.population(year) if focus == "usa" else None
        if pop and y < H - 120 * s:
            prev = self.population(year - 1) or pop
            shown = prev + (pop - prev) * grow
            d.text((x, y), "POPULATION", font=self.font(15 * s, bold=True), fill=muted)
            d.text((self.w - pad, y - int(6 * s)), f"{shown:,.0f}", font=self.font(26 * s, bold=True, serif=True), fill=text, anchor="ra")
            y += int(34 * s)
            cities = self.cities(year, focus, 5)
            if cities and y < H - 110 * s:
                d.text((x, y), "LARGEST CITIES", font=self.font(15 * s, bold=True), fill=muted)
                y += int(24 * s)
                for n, (name, state, cp) in enumerate(cities, 1):
                    if y > H - 40 * s:
                        break
                    d.text((x, y), f"{n}. {name}", font=self.font(17 * s), fill=text)
                    d.text((x + int(210 * s), y + int(2 * s)), state, font=self.font(14 * s), fill=muted)
                    d.text((self.w - pad, y), f"{cp:,.0f}", font=self.font(17 * s), fill=text, anchor="ra")
                    y += int(24 * s)

        img.alpha_composite(over, (x0, 0))
