"""The motion cut: a finished, moving video rather than one still per year.

  intro     a text card on the premise, then a lit 3D globe that turns from the Atlantic to
            Arabia while the title comes up, and dives into the map
  main      every year, with
              - a camera that eases between keyframes (data/camera.csv): pans, zooms, rotation
              - plates: each distinct map drawn once, larger than the frame, so the camera can
                move over it without redrawing; a crossfade whenever the borders change
              - a 3D tilt of the map and a sliding title card at the start of each era
              - wars (data/wars.csv): arrows that grow along their campaign, pulsing battles,
                a flash and a camera shake when a battle opens
              - the Qumur inset, and the infobox panel (cgvideo/panel.py)
  finale    demographics: population by state, religion and ancestry by county, the largest
            cities; then an end card (cgvideo/finale.py)

Frames are piped straight into ffmpeg in parallel chunks and joined, so nothing but the plates
touches the disk. `python build.py motion --from 1855 --to 1870` renders a slice; `--frame N`
writes single PNGs for review.
"""

from __future__ import annotations

import bisect
import hashlib
import math
import os
import pathlib
import subprocess
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import data as D
from . import geo
from . import timeline as T
from .config import load_config, paths
from .panel import Panel, ease, hexrgb

DEFAULTS = {
    "panel_x": 0.655,          # where the infobox starts, as a fraction of the width
    "anchor": [0.33, 0.5],     # where the camera's centre sits on screen
    "crossfade_seconds": 0.35,
    "era_fx_seconds": 1.8,     # the start of an era: push-in settle, focus pull, colour sweep
    "era_push": 0.10,          # how far in the camera starts (only ever in: no edge can show)
    "era_blur_px": 9,          # focus pull, at 1080p
    "logo_seconds": 4.0,       # the logo sting before the premise card
    "intro_text_seconds": 9.0,
    "globe_seconds": 7.5,
    "finale_seconds": 9.0,
    "end_card_seconds": 5.0,
    "plate_oversample": 1.5,
    "max_plate_megapixels": 40,
    "shake_px": 5,
    "inset_rect": [0.012, 0.72, 0.13, 0.25],
    "focus_priority": ["usa"],  # the infobox stays on these whenever they exist
}


def mcfg(cfg) -> dict:
    out = dict(DEFAULTS)
    out.update(cfg.get("motion") or {})
    return out


def intro_seconds(m: dict) -> float:
    """The opening before the first map: logo sting, premise card, globe."""
    return float(m["logo_seconds"]) + float(m["intro_text_seconds"]) + float(m["globe_seconds"])


def back_ease(t: float, over: float = 1.5) -> float:
    """Ease out with a small overshoot, for things that slide into place."""
    t = max(0.0, min(1.0, t)) - 1
    return t * t * ((over + 1) * t + over) + 1


# -- camera ------------------------------------------------------------------------------

class Camera:
    """Keyframes in screen time; smoothstep easing between them."""

    def __init__(self, cfg, data, slots, fps):
        self.cfg = cfg
        by_year = {s["year"]: s for s in slots}
        years = sorted(by_year)
        keys = []
        for k in data.camera:
            y = int(k["year"])
            i = bisect.bisect_left(years, y)
            if i >= len(years):
                i = len(years) - 1
            f = by_year[years[i]]["start_frame"]
            x, yy = geo.project_points(cfg, [float(k["lon"])], [float(k["lat"])])
            keys.append((f, float(x[0]), float(yy[0]), float(k["zoom"]), math.radians(float(k["rotation"]))))
        if not keys:
            x, yy = geo.project_points(cfg, [cfg["view"]["center"][0]], [cfg["view"]["center"][1]])
            keys = [(0, float(x[0]), float(yy[0]), 1.0, 0.0)]
        keys.sort()
        self.keys = keys
        self.frames = [k[0] for k in keys]

    def at(self, f: float):
        i = bisect.bisect_right(self.frames, f) - 1
        if i < 0:
            return self.keys[0][1:]
        if i >= len(self.keys) - 1:
            return self.keys[-1][1:]
        a, b = self.keys[i], self.keys[i + 1]
        t = ease((f - a[0]) / max(1, b[0] - a[0]))
        return tuple(a[j] + (b[j] - a[j]) * t for j in range(1, 5))


def metres_per_px(cfg, H):
    return float(cfg["view"]["height_km"]) * 1000.0 / H


def views_extent(cfg, keys, W, H, margin=0.1):
    """Bounding box, in projected metres, of every keyframe's screen rectangle, rotation
    included, grown by `margin` of its size for the eased moves between keyframes and the
    shake. keys: (centre_x, centre_y, zoom, rotation_radians). The plates and the drawn
    coastlines (mesh.drawn_extent) both come from this, so they always agree."""
    m = mcfg(cfg)
    ax, ay = m["anchor"][0] * W, m["anchor"][1] * H
    xs, ys = [], []
    for cx, cy, z, rot in keys:
        k = metres_per_px(cfg, H) / z
        c, s = math.cos(rot), math.sin(rot)
        for u, v in ((0, 0), (W, 0), (0, H), (W, H)):
            du, dv = u - ax, v - ay                  # inverse of world_to_screen
            dx, dy = c * du + s * dv, -s * du + c * dv
            xs.append(cx + dx * k)
            ys.append(cy - dy * k)
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    gx, gy = (x1 - x0) * margin, (y1 - y0) * margin
    return x0 - gx, x1 + gx, y0 - gy, y1 + gy


def plate_extent(cfg, cam: Camera, W, H):
    return views_extent(cfg, [k[1:] for k in cam.keys], W, H)


# -- plates ------------------------------------------------------------------------------

class PlateSpec:
    def __init__(self, cfg, cam, W, H):
        m = mcfg(cfg)
        self.extent = plate_extent(cfg, cam, W, H)
        x0, x1, y0, y1 = self.extent
        max_zoom = max(k[3] for k in cam.keys)
        over = min(float(m["plate_oversample"]), max(1.0, max_zoom))
        dens = metres_per_px(cfg, H) / over
        pw, ph = (x1 - x0) / dens, (y1 - y0) / dens
        cap = float(m["max_plate_megapixels"]) * 1e6
        if pw * ph > cap:
            dens *= math.sqrt(pw * ph / cap)
        self.dens = dens
        self.size = (int((x1 - x0) / dens), int((y1 - y0) / dens))
        self.px_scale = (H / 1080) * (metres_per_px(cfg, H) / dens) * 0.5  # render.py sizes are for 2160 px


def _sig(data, scene, slot) -> str:
    places = scene.places_for(slot["year"])
    names = "|".join(p["name"] for p in places)
    return data.state_signature(data.matrix[slot["index"]]) + hashlib.sha1(names.encode()).hexdigest()[:6]


def _plate_path(cfg, W, H, sig, kind="plate"):
    # _G["pkey"] folds in the map style, the mesh (so new coastlines redraw) and the plate's
    # extent and size (so new camera keyframes redraw); `sig` is the borders and places.
    return paths(cfg).build / "plates" / f"{kind}_{W}x{H}_{_G.get('pkey', '')}_{sig}.png"


_G: dict = {}


def _init(cfg_path, W, H, slot_list=None):
    from .render import Scene
    cfg = load_config(cfg_path)
    data = D.load(cfg)
    slots = slot_list if slot_list is not None else T.load(cfg)[0]
    scene = Scene(cfg, data)
    fps = int(cfg["frame"]["fps"])
    cam = Camera(cfg, data, slots, fps)
    spec = PlateSpec(cfg, cam, W, H)
    from .render import style_key
    pkey = hashlib.sha1(f"{style_key(cfg, data)}|{spec.extent}|{spec.size}".encode()).hexdigest()[:8]
    _G.update(cfg=cfg, data=data, scene=scene, W=W, H=H, slots=slots, cam=cam, spec=spec,
              fps=fps, cfg_path=cfg_path, pkey=pkey)


def _make_plate(slot):
    from .render import render_map
    cfg, data, scene, spec, W, H = _G["cfg"], _G["data"], _G["scene"], _G["spec"], _G["W"], _G["H"]
    sig = _sig(data, scene, slot)
    out = _plate_path(cfg, W, H, sig)
    row = data.matrix[slot["index"]]
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        img = render_map(scene, row, spec.size[0], spec.size[1], scene.places_for(slot["year"]),
                         extent=spec.extent, px_scale=spec.px_scale, insets=False)
        tmp = out.with_suffix(".tmp.png")
        img.save(tmp, compress_level=1)
        os.replace(tmp, out)
    # the Qumur inset, drawn at its screen size (its own file, so moving the inset redraws only it)
    m = mcfg(cfg)
    r = m["inset_rect"]
    iw, ih = int(r[2] * W), int(r[3] * H)
    for ins in cfg.get("insets", []):
        ipath = _plate_path(cfg, W, H, f"{sig}_{ins['name']}_{iw}x{ih}", "inset")
        if ipath.exists():
            continue
        from .render import _inset_extent
        ex = _inset_extent(cfg, {**ins, "rect": [0, 0, r[2], r[3]]}, W, H)
        inset = render_map(scene, row, iw, ih, scene.places_for(slot["year"]), extent=ex,
                           px_scale=(H / 2160) * 1.3, insets=False)
        inset.save(ipath)
    return sig


# -- geometry helpers ---------------------------------------------------------------------

def affine(spec: PlateSpec, cam_state, W, H, anchor, shake=(0.0, 0.0)):
    cx, cy, z, rot = cam_state
    ax, ay = anchor[0] * W + shake[0], anchor[1] * H + shake[1]
    x0, x1, y0, y1 = spec.extent
    m = metres_per_px(_G["cfg"], H) / z
    k = m / spec.dens
    c, s = math.cos(rot), math.sin(rot)
    a, b = k * c, k * s
    d, e = -k * s, k * c
    cc = (cx - x0) / spec.dens - (a * ax + b * ay)
    ff = (y1 - cy) / spec.dens - (d * ax + e * ay)
    return (a, b, cc, d, e, ff)


def world_to_screen(X, Y, cam_state, W, H, anchor, shake=(0.0, 0.0)):
    cx, cy, z, rot = cam_state
    m = metres_per_px(_G["cfg"], H) / z
    dx, dy = (np.asarray(X) - cx) / m, -(np.asarray(Y) - cy) / m
    c, s = math.cos(rot), math.sin(rot)
    u = anchor[0] * W + shake[0] + dx * c - dy * s
    v = anchor[1] * H + shake[1] + dx * s + dy * c
    return u, v


# -- frame rendering -----------------------------------------------------------------------

class Renderer:
    def __init__(self):
        g = _G
        self.cfg, self.data, self.scene, self.W, self.H = g["cfg"], g["data"], g["scene"], g["W"], g["H"]
        self.slots, self.cam, self.spec, self.fps = g["slots"], g["cam"], g["spec"], g["fps"]
        self.m = mcfg(self.cfg)
        self.intro = int(round(intro_seconds(self.m) * self.fps))
        self.main = self.slots[-1]["start_frame"] + self.slots[-1]["frames"]
        self.starts = [s["start_frame"] for s in self.slots]
        self.panel = Panel(self.cfg, self.data, self.scene, self.W, self.H)
        self.ocean = hexrgb(self.cfg["style"]["ocean"])[:3]
        self._plates: dict[str, Image.Image] = {}
        self._insets: dict[str, Image.Image] = {}
        self.sigs = [_sig(self.data, self.scene, s) for s in self.slots]
        self.year_frames = {}
        for s in self.slots:
            self.year_frames[s["year"]] = (s["start_frame"], s["start_frame"] + s["frames"])
        self.wars = self._prep_wars()
        yy, xx = np.mgrid[0:self.H, 0:self.W]
        r = np.hypot((xx - self.W / 2) / (self.W / 2), (yy - self.H / 2) / (self.H / 2))
        vig = float(self.cfg["style"].get("postfx", {}).get("vignette", 0.3))
        self.vignette = (1 - vig * np.clip(r - 0.6, 0, None) ** 1.7)[..., None].astype(np.float32)
        self.diag = ((xx / self.W + 0.35 * yy / self.H) / 1.35).astype(np.float32)  # for light sweeps
        self.finale = None
        self.globe = None

    def total_frames(self):
        from .finale import Finale
        return self.intro + self.main + Finale.length(self.cfg, self.fps)

    # plates
    def plate(self, sig) -> Image.Image:
        if sig not in self._plates:
            if len(self._plates) > 2:  # the current plate, the one it crossfades from, one spare
                self._plates.pop(next(iter(self._plates)))
            self._plates[sig] = Image.open(_plate_path(self.cfg, self.W, self.H, sig)).convert("RGB")
        return self._plates[sig]

    def inset(self, sig, name) -> Image.Image | None:
        r = self.m["inset_rect"]
        key = f"{sig}_{name}_{int(r[2] * self.W)}x{int(r[3] * self.H)}"
        if key not in self._insets:
            p = _plate_path(self.cfg, self.W, self.H, key, "inset")
            self._insets[key] = Image.open(p).convert("RGB") if p.exists() else None
            if len(self._insets) > 6:
                self._insets.pop(next(iter(self._insets)))
        return self._insets[key]

    # wars
    def _year_span(self, y0, y1):
        ys = sorted(self.year_frames)
        i0 = min(bisect.bisect_left(ys, y0), len(ys) - 1)
        i1 = min(max(bisect.bisect_right(ys, y1) - 1, 0), len(ys) - 1)
        return self.year_frames[ys[i0]][0], self.year_frames[ys[i1]][1]

    def _prep_wars(self):
        out = []
        for w in self.data.wars:
            pts = [tuple(float(v) for v in p.split()) for p in w["path"].split(";") if p.strip()]
            x, y = geo.project_points(self.cfg, [p[0] for p in pts], [p[1] for p in pts])
            f0, f1 = self._year_span(int(w["start"]), int(w["end"]))
            out.append({**w, "X": np.asarray(x), "Y": np.asarray(y), "f0": f0, "f1": max(f1, f0 + 1)})
        return out

    def shake(self, f):
        amp = 0.0
        for w in self.wars:
            if w["kind"] == "battle" and w["f0"] <= f < w["f0"] + 18:
                amp = max(amp, 1 - (f - w["f0"]) / 18)
        a = amp * self.m["shake_px"] * self.H / 1080
        return (a * math.sin(f * 2.3), a * math.cos(f * 3.1))

    def draw_wars(self, img, f, cam_state, shake):
        active = [w for w in self.wars if w["f0"] <= f < w["f1"] + int(0.8 * self.fps)]
        if not active:
            return img
        s = self.H / 1080
        over = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(over)
        anchor = self.m["anchor"]
        flash = 0.0
        for w in active:
            u, v = world_to_screen(w["X"], w["Y"], cam_state, self.W, self.H, anchor, shake)
            col = hexrgb(w["side"])
            fade = 1.0 if f < w["f1"] else max(0.0, 1 - (f - w["f1"]) / (0.8 * self.fps))
            if w["kind"] == "arrow" and len(u) >= 2:
                t = ease((f - w["f0"]) / max(1, w["f1"] - w["f0"]))
                seg = np.hypot(np.diff(u), np.diff(v))
                total = seg.sum()
                want = total * max(0.02, t)
                pts, acc = [(u[0], v[0])], 0.0
                for i, L in enumerate(seg):
                    if acc + L >= want:
                        r = (want - acc) / max(L, 1e-6)
                        pts.append((u[i] + (u[i + 1] - u[i]) * r, v[i] + (v[i + 1] - v[i]) * r))
                        break
                    acc += L
                    pts.append((u[i + 1], v[i + 1]))
                wd = int(11 * s)
                a = int(235 * fade)
                d.line(pts, fill=(15, 15, 15, int(a * 0.8)), width=wd + int(6 * s), joint="curve")
                d.line(pts, fill=col[:3] + (a,), width=wd, joint="curve")
                if len(pts) >= 2:
                    (px, py), (qx, qy) = pts[-2], pts[-1]
                    ang = math.atan2(qy - py, qx - px)
                    L = 30 * s
                    head = [(qx + math.cos(ang) * L * 0.6, qy + math.sin(ang) * L * 0.6),
                            (qx + math.cos(ang + 2.4) * L, qy + math.sin(ang + 2.4) * L),
                            (qx + math.cos(ang - 2.4) * L, qy + math.sin(ang - 2.4) * L)]
                    d.polygon(head, fill=col[:3] + (a,), outline=(15, 15, 15, a))
                    if w.get("label"):
                        from .panel import _fontfile
                        from PIL import ImageFont
                        fnt = ImageFont.truetype(_fontfile("DejaVuSans-Bold.ttf"), int(17 * s))
                        d.text((qx + 14 * s, qy - 26 * s), w["label"], font=fnt, fill=(255, 255, 255, a),
                               stroke_width=max(2, int(3 * s)), stroke_fill=(10, 10, 10, a))
            elif w["kind"] == "battle":
                x, y = float(u[0]), float(v[0])
                age = f - w["f0"]
                for k in range(3):
                    ph = ((age / self.fps) * 1.2 + k / 3) % 1.0
                    r = (10 + 38 * ph) * s
                    d.ellipse([x - r, y - r, x + r, y + r], outline=col[:3] + (int(230 * (1 - ph) * fade),), width=max(2, int(3 * s)))
                if age < 14:
                    burst = (1 - age / 14)
                    flash = max(flash, burst * 0.35)
                    R = (20 + 40 * (1 - burst)) * s
                    star = []
                    for k in range(16):
                        ang = k * math.pi / 8
                        rr = R if k % 2 == 0 else R * 0.45
                        star.append((x + rr * math.cos(ang), y + rr * math.sin(ang)))
                    d.polygon(star, fill=(255, 214, 90, int(255 * burst)))
                d.ellipse([x - 6 * s, y - 6 * s, x + 6 * s, y + 6 * s], fill=col[:3] + (int(255 * fade),), outline=(255, 255, 255, int(255 * fade)))
                if w.get("label"):
                    from .panel import _fontfile
                    from PIL import ImageFont
                    fnt = ImageFont.truetype(_fontfile("DejaVuSans-Bold.ttf"), int(18 * s))
                    d.text((x + 16 * s, y + 10 * s), w["label"], font=fnt, fill=(255, 255, 255, int(255 * fade)),
                           stroke_width=max(2, int(3 * s)), stroke_fill=(10, 10, 10, int(255 * fade)))
        img = Image.alpha_composite(img.convert("RGBA"), over)
        if flash > 0:
            img = Image.blend(img, Image.new("RGBA", img.size, (255, 244, 220, 255)), flash)
        return img

    def era_fx(self, img, slot, t):
        """The start of an era, without bending the map: the camera settles out of a push-in,
        the focus pulls from soft to sharp, and a band of the era's colour sweeps across. It
        only ever zooms in (a crop of the frame), so no edge of the map can show."""
        T = float(self.m["era_fx_seconds"])
        W, H = self.W, self.H
        k = ease(t / T)
        z = 1 + float(self.m["era_push"]) * (1 - k)
        if z > 1.0005:
            ax, ay = self.m["anchor"][0] * W, self.m["anchor"][1] * H
            x0, y0 = ax - ax / z, ay - ay / z  # the anchor stays put as the frame grows
            img = img.transform((W, H), Image.EXTENT, (x0, y0, x0 + W / z, y0 + H / z), Image.BICUBIC)
        blur = float(self.m["era_blur_px"]) * (H / 1080) * (1 - ease(t / (T * 0.55)))
        if blur > 0.3:
            img = img.filter(ImageFilter.GaussianBlur(blur))
        pos = -0.3 + 1.6 * ease(t / (T * 0.85))
        fade = 1 - ease((t - T * 0.55) / (T * 0.45))
        band = np.exp(-((self.diag - pos) / 0.085) ** 2) * (0.42 * fade)
        tint = np.array(hexrgb(self._era_color(slot))[:3], np.float32) * 0.5 + 255 * 0.5
        a = np.asarray(img).astype(np.float32)
        a += band[..., None] * (tint - a)
        return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))

    def era_card(self, img, slot, t):
        """The era's title on frosted glass: it slides in with a small overshoot while an
        accent rule draws itself, holds, and slides back out."""
        dur = float(self.cfg["pacing"].get("era_title_seconds", 2.5))
        if not slot["era_start"] or t > dur + 0.6:
            return img
        from .panel import _fontfile
        from PIL import ImageFont
        from . import years as Y
        s = self.H / 1080
        color = hexrgb(self._era_color(slot))
        card_w = int(self.panel.x0 * 0.80)
        bh = int(168 * s)
        y0 = int(self.H * 0.13)
        enter = back_ease(t / 0.75)
        leave = ease((t - dur) / 0.55) if t > dur else 0.0
        x1 = int(card_w * enter - (card_w + 40 * s) * leave)
        if x1 <= 2:
            return img
        img = img.convert("RGBA")
        # frosted glass: the map behind the card, blurred and dimmed
        box = (0, y0, min(x1, self.W), y0 + bh)
        glass = img.crop(box).filter(ImageFilter.GaussianBlur(16 * s))
        glass = Image.blend(glass, Image.new("RGBA", glass.size, (10, 13, 18, 255)), 0.55)
        img.paste(glass, box[:2])
        over = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(over)
        d.rectangle([0, y0, x1, y0 + bh], outline=(255, 255, 255, 34), width=max(1, int(1.5 * s)))
        d.rectangle([0, y0, int(6 * s), y0 + bh], fill=color[:3] + (255,))   # the era's colour, left edge
        rule = int((card_w - 60 * s) * ease((t - 0.35) / 0.9))                # the accent rule draws itself
        d.rectangle([int(36 * s), y0 + bh - int(22 * s), int(36 * s) + max(0, min(rule, x1 - int(50 * s))),
                     y0 + bh - int(19 * s)], fill=color[:3] + (230,))
        tx = x1 - card_w + int(40 * s)
        n = [e["era_id"] for e in self.data.eras].index(slot["era_id"]) + 1
        roman = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"][n - 1]
        a = int(255 * max(0.0, min(1.0, t / 0.35)))
        d.text((tx, y0 + int(20 * s)), " ".join(f"ERA {roman}"),
               font=ImageFont.truetype(_fontfile("DejaVuSans-Bold.ttf"), int(21 * s)), fill=color[:3] + (a,))
        name = slot["era_name"]
        size = 50 if len(name) < 30 else 36
        d.text((tx, y0 + int(50 * s)), name, font=ImageFont.truetype(_fontfile("DejaVuSerif-Bold.ttf"), int(size * s)),
               fill=(247, 243, 234, a))
        era = next(e for e in self.data.eras if e["era_id"] == slot["era_id"])
        d.text((tx, y0 + int(112 * s)), f"{Y.label(int(era['start']))} – {Y.label(int(era['end']))}",
               font=ImageFont.truetype(_fontfile("DejaVuSans.ttf"), int(20 * s)), fill=(205, 210, 216, a))
        return Image.alpha_composite(img, over)

    def _era_color(self, slot):
        return next(e["color"] for e in self.data.eras if e["era_id"] == slot["era_id"])

    def main_frame(self, f):
        i = bisect.bisect_right(self.starts, f) - 1
        slot = self.slots[i]
        t = (f - slot["start_frame"]) / self.fps
        cam_state = self.cam.at(f)
        shake = self.shake(f)
        A = affine(self.spec, cam_state, self.W, self.H, self.m["anchor"], shake)
        sig = self.sigs[i]
        img = self.plate(sig).transform((self.W, self.H), Image.AFFINE, A, Image.BICUBIC, fillcolor=self.ocean)
        # crossfade from the previous map when the borders change
        if i > 0 and self.sigs[i - 1] != sig:
            xf = min(self.m["crossfade_seconds"] * self.fps, max(1, slot["frames"]))
            k = (f - slot["start_frame"]) / xf
            if k < 1:
                prev = self.plate(self.sigs[i - 1]).transform((self.W, self.H), Image.AFFINE, A, Image.BICUBIC, fillcolor=self.ocean)
                img = Image.blend(prev, img, ease(k))
        img = self.draw_wars(img, f, cam_state, shake)
        if slot["era_start"] and t < self.m["era_fx_seconds"]:
            img = self.era_fx(img.convert("RGB"), slot, t)
        img = img.convert("RGBA")
        for ins in self.cfg.get("insets", []):
            small = self.inset(sig, ins["name"])
            if small is not None:
                r = self.m["inset_rect"]
                x, y = int(r[0] * self.W), int(r[1] * self.H)
                ImageDraw.Draw(img).rectangle([x - 3, y - 3, x + small.width + 2, y + small.height + 2], fill=(10, 12, 16, 255))
                img.paste(small, (x, y))
        img = self.era_card(img, slot, t)
        self.panel.draw(img, slot, t)
        return img.convert("RGB")

    def frame(self, f) -> Image.Image:
        if f < self.intro:
            from .globe import intro_frame
            img = intro_frame(self, f)
        elif f < self.intro + self.main:
            img = self.main_frame(f - self.intro)
        else:
            from .finale import Finale
            if self.finale is None:
                self.finale = Finale(self)
            img = self.finale.frame(f - self.intro - self.main)
        a = np.asarray(img).astype(np.float32) * self.vignette
        return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def _encode_chunk(args):
    first, last, dest, codec = args
    from .sequence import find_ffmpeg
    r = Renderer()
    W, H, fps = r.W, r.H, r.fps
    # written under a temporary name and renamed only when complete, so a crash never leaves
    # a truncated chunk that a resumed render would take for a finished one
    tmp = pathlib.Path(dest).with_suffix(".tmp" + pathlib.Path(dest).suffix)
    cmd = [find_ffmpeg(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(fps), "-i", "-"]
    if codec == "prores":
        cmd += ["-c:v", "prores_ks", "-profile:v", "2", "-pix_fmt", "yuv422p10le"]
    else:
        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p"]
    cmd.append(str(tmp))
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(first, last):
        proc.stdin.write(r.frame(f).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed on chunk {first}-{last}")
    os.replace(tmp, dest)
    return dest


def frames_in(path) -> int:
    """Frames in a finished video file, by stream copy (fast); -1 if unreadable or truncated."""
    import re
    from .sequence import find_ffmpeg
    p = subprocess.run([find_ffmpeg(), "-v", "error", "-nostats", "-progress", "pipe:1", "-i", str(path),
                        "-map", "0:v:0", "-c", "copy", "-f", "null", "-"], capture_output=True, text=True)
    counts = re.findall(r"^frame=(\d+)", p.stdout, re.M)
    return int(counts[-1]) if p.returncode == 0 and counts else -1


def available_memory() -> int | None:
    """Physical memory free right now, in bytes (psutil if present, else the OS directly)."""
    try:
        import psutil
        return int(psutil.virtual_memory().available)
    except ImportError:
        pass
    if os.name == "nt":
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        st = MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return int(st.ullAvailPhys)
        return None
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass
    return None


def auto_workers(W, H, plate_size) -> tuple[int, str]:
    """As many workers as the cores allow and the free memory holds. Each worker keeps its
    interpreter and scene (~0.6 GB), up to three plates, and an x264 encoder's lookahead."""
    cpus = max(1, (os.cpu_count() or 2) - 1)
    free = available_memory()
    if not free:
        return cpus, "free memory unknown"
    per = 0.6e9 + 3 * plate_size[0] * plate_size[1] * 3 + W * H * 1.5 * 48
    n = max(1, min(cpus, int(free * 0.7 / per)))
    return n, f"{free / 1e9:.1f} GB free, ~{per / 1e9:.1f} GB per worker"


def _plates_job(slot):
    return _make_plate(slot)


def _frame_job(args):
    f, dest = args
    Renderer().frame(f).save(dest)
    return dest


def run(cfg, cfg_path, scale=1.0, workers=None, first_year=None, last_year=None, frames=None, codec="h264"):
    from .sequence import find_ffmpeg
    from . import assets
    W = int(round(cfg["frame"]["width"] * scale / 2) * 2)
    H = int(round(cfg["frame"]["height"] * scale / 2) * 2)
    data = D.load(cfg)
    slot_objs, meta = T.write(cfg, data)
    from dataclasses import asdict
    slots = [asdict(s) for s in slot_objs]
    assets.build_all(cfg, data)
    from .globe import prepare as prepare_globe
    prepare_globe(cfg)

    _init(str(cfg_path), W, H, slots)
    if not workers:
        workers, why = auto_workers(W, H, _G["spec"].size)
        print(f"  {workers} workers ({why})")
    # project the terrain once, here (QGIS), before the workers each want it
    _G["scene"].relief_overlay(_G["spec"].extent, *_G["spec"].size)
    _G["scene"]._relief.clear()
    firsts = {}
    for s in slots:
        firsts.setdefault(_sig(_G["data"], _G["scene"], s), s)
    print(f"  {len(firsts)} plates at {_G['spec'].size[0]}x{_G['spec'].size[1]} for {W}x{H}")
    with ProcessPoolExecutor(workers, initializer=_init, initargs=(str(cfg_path), W, H, slots)) as ex:
        for n, _ in enumerate(ex.map(_plates_job, list(firsts.values())), 1):
            if n % 20 == 0 or n == len(firsts):
                print(f"    plates {n}/{len(firsts)}")

    r = Renderer()
    total = r.total_frames()
    out = paths(cfg).output / "motion"
    out.mkdir(parents=True, exist_ok=True)
    if frames:
        jobs = [(int(f), str(out / f"frame_{int(f):06d}.png")) for f in frames]
        with ProcessPoolExecutor(min(workers, len(jobs)), initializer=_init, initargs=(str(cfg_path), W, H, slots)) as ex:
            return list(ex.map(_frame_job, jobs))
    lo, hi = 0, total
    if first_year is not None or last_year is not None:
        by_year = {s["year"]: s for s in slots}
        ys = sorted(by_year)
        a = by_year[ys[max(0, bisect.bisect_left(ys, first_year))]] if first_year is not None else slots[0]
        b = by_year[ys[min(len(ys) - 1, bisect.bisect_right(ys, last_year) - 1)]] if last_year is not None else slots[-1]
        lo = r.intro + a["start_frame"]
        hi = r.intro + b["start_frame"] + b["frames"]
    # Chunks of a fixed size, named by their frame range, so the same render always cuts the
    # same chunks whatever the worker count: a failed render resumes where it stopped.
    chunk = int(mcfg(cfg).get("chunk_frames", 572))
    n = max(1, math.ceil((hi - lo) / chunk))
    edges = np.linspace(lo, hi, n + 1).astype(int)
    ext = "mov" if codec == "prores" else "mp4"
    # A chunk is only reused by a render of the very same thing: the key covers the plates, the
    # config, every data table and the drawing code, so a change anywhere re-renders it.
    h = hashlib.sha1(f"{_G['pkey']}|{mcfg(cfg)}|{meta}".encode())
    for p in sorted(paths(cfg).data.glob("*.*")) + sorted(pathlib.Path(__file__).parent.glob("*.py")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    tag = f"{W}x{H}_{codec}_{h.hexdigest()[:8]}"
    for old in out.glob("part_*"):  # chunks of any other render are stale
        if tag not in old.name:
            old.unlink(missing_ok=True)
    jobs = [(int(edges[k]), int(edges[k + 1]), str(out / f"part_{tag}_{edges[k]:06d}_{edges[k + 1]:06d}.{ext}"), codec)
            for k in range(n)]
    parts = [j[2] for j in jobs]
    todo = [j for j in jobs if not (os.path.exists(j[2]) and frames_in(j[2]) == j[1] - j[0])]
    print(f"  frames {lo}-{hi} of {total} ({(hi - lo) / r.fps / 60:.1f} min) in {n} chunks on {workers} workers"
          + (f"; {n - len(todo)} chunks already done" if len(todo) < n else ""))
    if todo:
        with ProcessPoolExecutor(min(workers, len(todo)), initializer=_init,
                                 initargs=(str(cfg_path), W, H, slots)) as ex:
            for k, _ in enumerate(ex.map(_encode_chunk, todo), 1):
                print(f"    chunks {n - len(todo) + k}/{n}")
    listing = out / "parts.txt"
    listing.write_text("".join(f"file '{pathlib.Path(p).resolve().as_posix()}'\n" for p in parts), encoding="utf8")
    name = "controglobe_motion" + ("" if (lo, hi) == (0, total) else f"_{lo}_{hi}")
    dest = out / f"{name}.{ext}"
    subprocess.run([find_ffmpeg(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-c", "copy", str(dest)], check=True)
    for p in parts:
        os.remove(p)
    print(f"  {dest}")
    if (lo, hi) == (0, total):
        # a whole cut: point the Resolve build script at it, markers moved past the opening
        what = T.write_resolve_lua(cfg, slot_objs, meta, media="motion")
        installed = T.install_resolve_script(cfg)
        print(f"  Resolve build script: {what}" + (f"; installed as {installed}" if installed else ""))
    return dest
