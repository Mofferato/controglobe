"""The closing: Arabia in 2025 by the numbers, then the end card.

  1 population by state     choropleth with each state's figure; the national count runs up
  2 religion by county      every mesh cell stands for a group of muhafazat (the county tier):
                            coloured by its plurality faith, shaded by how strong it is
  3 ancestry by county      the same, for the federal categories
  4 largest cities          metropolitan bubbles grow in rank order over the dimmed map
  5 end card

National figures are canon (united-states-of-arabia, Demographics); the state split in
data/demographics.csv and the county pattern drawn from it are inferred to fit them. Each map
is revealed by a circular wipe from the centre of the country while the panel counts up. The
four maps are one continuous shot: it opens on the frame the close (motion.outro_frame) ends
on, the camera pushes in slowly throughout, and between maps only the figures fade.
"""

from __future__ import annotations

import math

import numpy as np
import geopandas as gpd
import shapely
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import geo
from .config import paths
from .panel import _fontfile, ease, hexrgb

RELIGION = [("sunni", "Sunni Islam", "#3f8f4f", 51), ("shia", "Shia Islam", "#1d6f86", 15),
            ("ibadi", "Ibadi Islam", "#9ab83c", 1), ("zaydi", "Zaydi Islam", "#6d8a2a", 1),
            ("christian", "Christianity", "#b8452f", 11), ("jewish", "Judaism", "#3a5fb0", 3),
            ("hindu_buddhist", "Hinduism and Buddhism", "#e0922e", 2), ("none", "No affiliation", "#9aa0a6", 14)]
ANCESTRY = [("brown", "Brown", "#a8743f", 64), ("european", "White (European Arabian)", "#5b86c9", 13),
            ("masri", "Masri origin", "#5fa35a", 11), ("asian", "Asian Arabian", "#e3b23c", 6),
            ("african", "African Arabian", "#7a4a8f", 4), ("indigenous", "Indigenous Mashriqi", "#c2413c", 2.3),
            ("caucasian", "Caucasian Arabian", "#3fa39b", 1.8), ("islander", "Islander", "#2f86c7", 0.9)]
SEGMENTS = ["population", "religion", "ancestry", "cities"]


def _font(size, bold=False, serif=False):
    name = ("DejaVuSerif" if serif else "DejaVuSans") + ("-Bold" if bold else "") + ".ttf"
    return ImageFont.truetype(_fontfile(name), max(8, int(size)))


class Finale:
    @staticmethod
    def length(cfg, fps):
        from .motion import mcfg
        m = mcfg(cfg)
        return int(round((len(SEGMENTS) * m["finale_seconds"] + m["end_card_seconds"]) * fps))

    def __init__(self, r):
        self.r = r
        self.cfg, self.data, self.scene = r.cfg, r.data, r.scene
        self.W, self.H, self.fps, self.s = r.W, r.H, r.fps, r.H / 1080
        self.seg = int(round(r.m["finale_seconds"] * self.fps))
        last = r.slots[-1]
        self.last_slot = last
        self.cam = r.outro_cam        # where the close leaves the camera
        self.row = self.data.matrix[last["index"]]
        self.map_only = r.map_view(r.sigs[-1], self.cam, (0.0, 0.0), [r.panel_hide()])
        self.map_dim = Image.blend(self.map_only, Image.new("RGB", self.map_only.size, (10, 12, 16)), 0.45)
        self._layers = {}
        self._cities = None
        self._load_tables()

    # -- data --------------------------------------------------------------------------
    def _load_tables(self):
        rows = self.data.demographics
        total = 424.6
        states = [r for r in rows if r["state"] != "dc"]
        dc = next((float(r["pop_m"]) for r in rows if r["state"] == "dc"), 0.0)
        raw = sum(float(r["pop_m"]) for r in states)
        k = (total - dc) / raw if raw else 1
        self.demo = {r["state"]: r for r in rows}
        self.pop = {r["state"]: float(r["pop_m"]) * k for r in states}
        self.state_of_region = {}
        for j, rid in enumerate(self.data.region_ids):
            p = self.row[j]
            if p >= 0:
                pid = self.data.polity_ids[p]
                if pid in self.pop:
                    self.state_of_region[rid] = pid
        mesh = paths(self.cfg).mesh
        cells = gpd.read_file(mesh, layer="cells")
        cells = cells[cells["region_id"].isin(self.state_of_region)]
        self.cells = list(zip(cells["cell_id"], cells["region_id"], cells.geometry))
        xs, ys = geo.project_points(self.cfg, [float(c["lon"]) for c in self.data.cities],
                                    [float(c["lat"]) for c in self.data.cities])
        self.city_xy = np.column_stack([xs, ys])

    # -- drawing helpers ---------------------------------------------------------------
    def _poly_px(self, geom, scale=1):
        from .motion import world_to_screen
        out = []
        for poly in shapely.get_parts(geom):
            if poly.geom_type != "Polygon":
                continue
            x, y = np.asarray(poly.exterior.coords).T
            u, v = world_to_screen(x, y, self.cam, self.W, self.H, self.r.m["anchor"])
            out.append(list(zip(u * scale, v * scale)))
        return out

    def _layer(self, kind) -> Image.Image:
        if kind in self._layers:
            return self._layers[kind]
        ss = 2
        img = Image.new("RGBA", (self.W * ss, self.H * ss), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        if kind == "population":
            polities, _ = self.scene.state(self.row)
            vals = {p: v for p, v in self.pop.items() if p in polities}
            lo, hi = math.log(min(vals.values())), math.log(max(vals.values()))
            ramp = [(255, 243, 196), (253, 196, 110), (240, 126, 60), (200, 58, 44), (122, 18, 40)]
            for pid, v in vals.items():
                t = (math.log(v) - lo) / (hi - lo or 1)
                i = min(len(ramp) - 2, int(t * (len(ramp) - 1)))
                f = t * (len(ramp) - 1) - i
                col = tuple(int(ramp[i][c] + (ramp[i + 1][c] - ramp[i][c]) * f) for c in range(3))
                for ring in self._poly_px(polities[pid], ss):
                    d.polygon(ring, fill=col + (255,), outline=(20, 20, 20, 255))
            self._labels = []
            from shapely.ops import polylabel
            for pid, v in vals.items():
                g = polities[pid]
                part = max(shapely.get_parts(g), key=lambda p: p.area)
                if part.area / 1e6 < 25000:
                    continue
                pt = polylabel(part, tolerance=2000)
                from .motion import world_to_screen
                u, vv = world_to_screen([pt.x], [pt.y], self.cam, self.W, self.H, self.r.m["anchor"])
                self._labels.append((float(u[0]), float(vv[0]), self.data.polity[pid]["name"], v))
        else:
            table = RELIGION if kind == "religion" else ANCESTRY
            keys = [k for k, *_ in table]
            colors = {k: hexrgb(c)[:3] for k, _, c, _ in table}
            for cid, rid, geom in self.cells:
                st = self.demo[self.state_of_region[rid]]
                w = np.array([float(st[k]) for k in keys], float) + 0.01
                rng = np.random.default_rng(int(cid) * 31 + (7 if kind == "religion" else 11))
                w = w * np.exp(rng.normal(0, 0.85, len(w)))
                c = shapely.centroid(geom)
                dmin = np.min(np.hypot(self.city_xy[:, 0] - c.x, self.city_xy[:, 1] - c.y))
                if dmin < 70_000:
                    boost = {"none": 1.9, "christian": 1.2, "hindu_buddhist": 1.6, "jewish": 1.3,
                             "asian": 1.8, "masri": 1.4, "european": 1.2, "african": 1.3}
                    w = w * np.array([boost.get(k, 1.0) for k in keys])
                k = int(np.argmax(w))
                share = w[k] / w.sum()
                base = np.array(colors[keys[k]], float)
                shade = 0.35 + 0.65 * min(1.0, (share - 0.25) / 0.5)
                col = tuple(int(v) for v in base * shade + np.array([245, 240, 230]) * (1 - shade))
                for ring in self._poly_px(geom, ss):
                    d.polygon(ring, fill=col + (255,), outline=(30, 30, 30, 120))
        img = img.resize((self.W, self.H), Image.LANCZOS)
        self._layers[kind] = img
        return img

    def _wipe(self, layer, t):
        """Reveal a layer with a circle growing from the country's centre."""
        k = ease(t / 1.6)
        if k >= 1:
            return layer
        cx, cy = self.r.m["anchor"][0] * self.W, self.r.m["anchor"][1] * self.H
        R = k * math.hypot(self.W, self.H)
        mask = Image.new("L", layer.size, 0)
        ImageDraw.Draw(mask).ellipse([cx - R, cy - R, cx + R, cy + R], fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(12 * self.s))
        out = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        out.paste(layer, (0, 0), Image.composite(layer.getchannel("A"), Image.new("L", layer.size, 0), mask))
        return out

    def _city_layout(self):
        """Bubbles at their full size and a name beside each, on the first side that is clear
        of the names and bubbles already placed (right, left, below, above), largest first."""
        if self._cities is not None:
            return self._cities
        from .motion import world_to_screen
        s = self.s
        u, v = world_to_screen(self.city_xy[:, 0], self.city_xy[:, 1], self.cam, self.W, self.H, self.r.m["anchor"])
        order = sorted(range(len(self.data.cities)), key=lambda i: -float(self.data.cities[i]["pop2025"]))
        font = _font(15 * s, bold=True)
        probe = ImageDraw.Draw(Image.new("L", (1, 1)))
        taken, out = [], []

        def clear(b):
            return all(b[2] <= o[0] or b[0] >= o[2] or b[3] <= o[1] or b[1] >= o[3] for o in taken)

        for i in order:
            R = math.sqrt(float(self.data.cities[i]["pop2025"])) / 55 * s
            x, y = float(u[i]), float(v[i])
            name = self.data.cities[i]["name"]
            w, h = probe.textlength(name, font=font), 16 * s
            g = 5 * s
            cands = [((x + R + g, y), "lm", (x + R + g, y - h / 2, x + R + g + w, y + h / 2)),
                     ((x - R - g, y), "rm", (x - R - g - w, y - h / 2, x - R - g, y + h / 2)),
                     ((x, y + R + g + h / 2), "mm", (x - w / 2, y + R + g, x + w / 2, y + R + g + h)),
                     ((x, y - R - g - h / 2), "mm", (x - w / 2, y - R - g - h, x + w / 2, y - R - g))]
            pos, anchor, box = next((c for c in cands if clear(c[2])), cands[0])
            taken.append(box)
            out.append((i, x, y, R, name, pos, anchor))
        self._cities = out
        return out

    # -- the panel ------------------------------------------------------------------------
    def panel_args(self, kind) -> dict:
        if kind == "population":
            rows = sorted(((self.data.polity[p]["name"], v, "#c84a2c") for p, v in self.pop.items()), key=lambda r: -r[1])[:12]
            return dict(title="Population by state", subtitle="Millions of residents, 2025 federal estimate",
                        rows=rows, total=424_600_000, unit="M",
                        note="National total canon; the split by state is inferred.")
        if kind in ("religion", "ancestry"):
            table = RELIGION if kind == "religion" else ANCESTRY
            rows = [(label, pct, col) for _, label, col, pct in table]
            title = "Religion by county" if kind == "religion" else "Ancestry by county"
            note = ("Shares canon; county pattern inferred." if kind == "religion"
                    else "Masri is an origin, reported alongside race. Shares canon.")
            return dict(title=title, subtitle="Plurality in each group of muhafazat; darker is stronger",
                        rows=rows, note=note, unit="%")
        order = sorted(range(len(self.data.cities)), key=lambda i: -float(self.data.cities[i]["pop2025"]))
        rows = [(f"{n + 1}. {self.data.cities[i]['name']}", float(self.data.cities[i]["pop2025"]) / 1e6, "#e2b659")
                for n, i in enumerate(order)]
        return dict(title="Largest cities", subtitle="Metropolitan areas, millions, 2025", rows=rows, unit="M",
                    note="Canon: United States of Arabia, Population and urbanisation.")

    def draw_panel(self, img, kind, t, offset=0, alpha=1.0):
        self._panel(img, t=t, offset=offset, alpha=alpha, **self.panel_args(kind))

    def _panel(self, img, title, subtitle, rows, t, total=None, note=None, unit="%", offset=0, alpha=1.0):
        """The finale's panel: its dark ground stays put while its figures fade (`alpha`)
        between maps; `offset` slides the whole panel right (the close slides it in)."""
        s, W, H = self.s, self.W, self.H
        x0 = int(W * self.r.m["panel_x"])
        if x0 + offset >= W:
            return
        over = Image.new("RGBA", (W - x0, H), (16, 20, 24, 240))
        content = Image.new("RGBA", (W - x0, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(content)
        pad = int(46 * s)
        y = int(40 * s)
        d.text((pad, y), "ARABIA IN 2025", font=_font(17 * s, bold=True), fill=(226, 182, 89, 255))
        y += int(34 * s)
        d.text((pad, y), title, font=_font(40 * s, bold=True, serif=True), fill=(244, 239, 230, 255))
        y += int(56 * s)
        if subtitle:
            d.text((pad, y), subtitle, font=_font(16 * s), fill=(170, 176, 184, 255))
            y += int(34 * s)
        if total:
            shown = total * ease(t / 2.0)
            d.text((pad, y), f"{shown:,.0f}", font=_font(46 * s, bold=True, serif=True), fill=(244, 239, 230, 255))
            y += int(70 * s)
        bw = W - x0 - 2 * pad - int(90 * s)
        top = max(v for _, v, _ in rows) if rows else 1
        for n, (label, v, col) in enumerate(rows):
            if y > H - 60 * s:
                break
            k = ease((t - 0.4 - n * 0.12) / 0.8)
            d.text((pad, y), label, font=_font(17 * s), fill=(235, 232, 225, int(255 * max(0.2, k))))
            by = y + int(24 * s)
            d.rectangle([pad, by, pad + bw, by + int(9 * s)], fill=(46, 50, 54, 255))
            d.rectangle([pad, by, pad + int(bw * v / top * k), by + int(9 * s)], fill=hexrgb(col)[:3] + (255,))
            txt = f"{v:,.1f}{unit}"
            d.text((W - x0 - pad, y + int(10 * s)), txt, font=_font(18 * s, bold=True), fill=(244, 239, 230, int(255 * k)), anchor="ra")
            y += int(46 * s)
        if note:
            d.text((pad, H - int(42 * s)), note, font=_font(13 * s), fill=(150, 156, 164, 255))
        if alpha < 1:
            content.putalpha(content.getchannel("A").point(lambda a: int(a * alpha)))
        over.alpha_composite(content)
        img.alpha_composite(over, (x0 + int(offset), 0))

    # -- segments -----------------------------------------------------------------------------
    def frame(self, f) -> Image.Image:
        k, t = divmod(f, self.seg)
        if k >= len(SEGMENTS):
            return self._end_card((f - len(SEGMENTS) * self.seg) / self.fps)
        t = t / self.fps
        kind = SEGMENTS[k]
        seg_s = self.seg / self.fps
        edge = 0.45
        # one shot: the figures fade between maps; the first map arrives with the close
        a = min(1.0 if k == 0 else ease(t / edge), 1.0 if k == len(SEGMENTS) - 1 else ease((seg_s - t) / edge))
        s = self.s
        over = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        if kind in ("population", "religion", "ancestry"):
            over.alpha_composite(self._wipe(self._layer(kind), t))
        marks = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(marks)
        if kind == "population":
            if t > 1.4:
                la = int(255 * ease((t - 1.4) / 0.6))
                for u, v, name, pop in self._labels:
                    d.text((u, v - 9 * s), name, font=_font(15 * s, bold=True), fill=(20, 20, 20, la), anchor="mm",
                           stroke_width=2, stroke_fill=(255, 255, 255, la))
                    d.text((u, v + 9 * s), f"{pop:.1f}M", font=_font(14 * s), fill=(20, 20, 20, la), anchor="mm",
                           stroke_width=2, stroke_fill=(255, 255, 255, la))
        elif kind == "cities":
            for n, (i, x, y, R, name, pos, anchor) in enumerate(self._city_layout()):
                kk = ease((t - 0.3 - n * 0.18) / 0.7)
                if kk <= 0:
                    continue
                r = R * kk
                d.ellipse([x - r, y - r, x + r, y + r], fill=(226, 182, 89, 150), outline=(255, 240, 200, 255), width=2)
                d.text(pos, name, font=_font(15 * s, bold=True), fill=(255, 255, 255, int(255 * kk)), anchor=anchor,
                       stroke_width=2, stroke_fill=(0, 0, 0, int(200 * kk)))
        over.alpha_composite(marks)
        if a < 1:
            over.putalpha(over.getchannel("A").point(lambda v: int(v * a)))
        img = self.map_dim.convert("RGBA")
        img.alpha_composite(over)
        # a slow push-in across the four maps (the map only: the panel keeps its figures on screen)
        zoom = 1 + 0.06 * ease(f / (len(SEGMENTS) * self.seg))
        if zoom > 1.0005:
            W, H = img.size
            cw, ch = W / zoom, H / zoom
            x0 = self.r.m["anchor"][0] * W * (1 - 1 / zoom)
            y0 = (H - ch) / 2
            img = img.transform((W, H), Image.EXTENT, (x0, y0, x0 + cw, y0 + ch), Image.BICUBIC)
        self._panel(img, t=t, alpha=a, **self.panel_args(kind))
        img = img.convert("RGB")
        if k == len(SEGMENTS) - 1:
            out = ease((seg_s - t) / 0.9)   # the last map goes to black, and the end card comes up
            if out < 1:
                img = Image.blend(Image.new("RGB", img.size, (0, 0, 0)), img, out)
        return img

    def _end_card(self, t):
        from .logo import emblem
        s, W, H = self.s, self.W, self.H
        img = Image.new("RGB", (W, H), (6, 8, 12))
        dur = self.r.m["end_card_seconds"]
        a = min(ease(t / 0.8), ease((dur - t) / 1.2))
        c = lambda rgb: tuple(int(v * a) for v in rgb)
        # the emblem, turning slowly, above the name
        size = int(H * 0.36)
        em = emblem(self.cfg, size, lon0=40 + 9 * t)
        em.putalpha(em.getchannel("A").point(lambda v: int(v * a)))
        img = img.convert("RGBA")
        img.alpha_composite(em, (int(W / 2 - size / 2), int(H * 0.30 - size / 2)))
        d = ImageDraw.Draw(img)
        d.text((W / 2, H * 0.58), " ".join("CONTROGLOBE"), font=_font(72 * s, bold=True, serif=True),
               fill=c((244, 239, 230)), anchor="mm")
        d.text((W / 2, H * 0.58 + 62 * s), "  ".join("THE GLOBAL SWAP"), font=_font(26 * s, bold=True),
               fill=c((226, 182, 89)), anchor="mm")
        d.text((W / 2, H * 0.78), "Every name, border and date: mofferato.github.io/controglobe", font=_font(24 * s),
               fill=c((190, 196, 204)), anchor="mm")
        d.text((W / 2, H * 0.78 + 38 * s), "Coastlines, rivers, lakes, relief and depths: Natural Earth (public domain)",
               font=_font(18 * s), fill=c((140, 146, 154)), anchor="mm")
        return img.convert("RGB")
