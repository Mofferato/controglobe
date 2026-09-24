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
from PIL import Image, ImageDraw

from . import data as D
from . import geo
from . import timeline as T
from .config import load_config, paths
from .panel import Panel, ease, hexrgb

DEFAULTS = {
    "panel_x": 0.655,          # where the infobox starts, as a fraction of the width
    "anchor": [0.33, 0.5],     # where the camera's centre sits on screen
    "crossfade_seconds": 0.35,
    "tilt_seconds": 1.6,
    "tilt_degrees": 32,
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


def plate_extent(cfg, cam: Camera, W, H):
    m = mcfg(cfg)
    ax, ay = m["anchor"][0] * W, m["anchor"][1] * H
    xs, ys = [], []
    for _, cx, cy, z, rot in cam.keys:
        mp = metres_per_px(cfg, H) / z
        r = math.hypot(max(ax, W - ax), max(ay, H - ay)) * mp
        xs += [cx - r, cx + r]
        ys += [cy - r, cy + r]
    return min(xs), max(xs), min(ys), max(ys)


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
    from .render import style_key
    return paths(cfg).build / "plates" / f"{kind}_{W}x{H}_{sig}.png"


_G: dict = {}


def _init(cfg_path, W, H, slot_list=None):
    from .render import Scene
    cfg = load_config(cfg_path)
    data = D.load(cfg)
    slots = slot_list if slot_list is not None else T.load(cfg)[0]
    scene = Scene(cfg, data)
    fps = int(cfg["frame"]["fps"])
    cam = Camera(cfg, data, slots, fps)
    _G.update(cfg=cfg, data=data, scene=scene, W=W, H=H, slots=slots, cam=cam, spec=PlateSpec(cfg, cam, W, H),
              fps=fps, cfg_path=cfg_path)


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


def perspective_coeffs(src_quad, dst_quad):
    """Coefficients for Image.transform(PERSPECTIVE): maps output (dst) points to input (src)."""
    A, B = [], []
    for (x, y), (u, v) in zip(dst_quad, src_quad):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        B += [u, v]
    return np.linalg.solve(np.array(A, float), np.array(B, float)).tolist()


def tilt(img: Image.Image, degrees: float, fill) -> Image.Image:
    """Lean the map back, as if the camera were pitched: a cheap, convincing 3D move."""
    if degrees <= 0.05:
        return img
    W, H = img.size
    k = math.sin(math.radians(degrees))
    inset = W * 0.22 * k
    drop = H * 0.10 * k
    dst = [(inset, drop), (W - inset, drop), (W, H), (0, H)]
    src = [(0, 0), (W, 0), (W, H), (0, H)]
    return img.transform(img.size, Image.PERSPECTIVE, perspective_coeffs(src, dst), Image.BICUBIC, fillcolor=fill)


# -- frame rendering -----------------------------------------------------------------------

class Renderer:
    def __init__(self):
        g = _G
        self.cfg, self.data, self.scene, self.W, self.H = g["cfg"], g["data"], g["scene"], g["W"], g["H"]
        self.slots, self.cam, self.spec, self.fps = g["slots"], g["cam"], g["spec"], g["fps"]
        self.m = mcfg(self.cfg)
        self.intro = int(round((self.m["intro_text_seconds"] + self.m["globe_seconds"]) * self.fps))
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
        self.finale = None
        self.globe = None

    def total_frames(self):
        from .finale import Finale
        return self.intro + self.main + Finale.length(self.cfg, self.fps)

    # plates
    def plate(self, sig) -> Image.Image:
        if sig not in self._plates:
            if len(self._plates) > 3:
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

    def era_card(self, img, slot, t):
        dur = float(self.cfg["pacing"].get("era_title_seconds", 2.5))
        if not slot["era_start"] or t > dur + 0.2:
            return img
        from .panel import _fontfile
        from PIL import ImageFont
        s = self.H / 1080
        W = self.panel.x0
        slide = ease(t / 0.45)
        out_a = 1 - ease((t - dur + 0.35) / 0.4) if t > dur - 0.35 else 1.0
        over = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(over)
        bh = int(150 * s)
        y0 = int(self.H * 0.14)
        x_end = int(W * slide)
        d.rectangle([0, y0, x_end, y0 + bh], fill=(12, 15, 20, int(215 * out_a)))
        d.rectangle([0, y0 + bh, x_end, y0 + bh + int(5 * s)], fill=hexrgb(self._era_color(slot))[:3] + (int(255 * out_a),))
        n = [e["era_id"] for e in self.data.eras].index(slot["era_id"]) + 1
        roman = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"][n - 1]
        tx = int(-W * (1 - slide)) + int(60 * s)
        d.text((tx, y0 + int(16 * s)), f"ERA {roman}", font=ImageFont.truetype(_fontfile("DejaVuSans-Bold.ttf"), int(22 * s)),
               fill=hexrgb(self._era_color(slot))[:3] + (int(255 * out_a),))
        name = slot["era_name"]
        size = 50 if len(name) < 30 else 36
        d.text((tx, y0 + int(48 * s)), name, font=ImageFont.truetype(_fontfile("DejaVuSerif-Bold.ttf"), int(size * s)),
               fill=(245, 240, 230, int(255 * out_a)))
        era = next(e for e in self.data.eras if e["era_id"] == slot["era_id"])
        from . import years as Y
        d.text((tx, y0 + int(112 * s)), f"{Y.label(int(era['start']))} - {Y.label(int(era['end']))}",
               font=ImageFont.truetype(_fontfile("DejaVuSans.ttf"), int(20 * s)), fill=(200, 205, 212, int(255 * out_a)))
        return Image.alpha_composite(img.convert("RGBA"), over)

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
        if slot["era_start"] and t < self.m["tilt_seconds"]:
            deg = self.m["tilt_degrees"] * (1 - ease(t / self.m["tilt_seconds"]))
            img = tilt(img.convert("RGB"), deg, self.ocean)
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
    cmd = [find_ffmpeg(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(fps), "-i", "-"]
    if codec == "prores":
        cmd += ["-c:v", "prores_ks", "-profile:v", "2", "-pix_fmt", "yuv422p10le"]
    else:
        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p"]
    cmd.append(dest)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(first, last):
        proc.stdin.write(r.frame(f).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed on chunk {first}-{last}")
    return dest


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
    slots, meta = T.write(cfg, data)
    from dataclasses import asdict
    slots = [asdict(s) for s in slots]
    assets.build_all(cfg, data)
    from .globe import prepare as prepare_globe
    prepare_globe(cfg)
    workers = workers or max(1, (os.cpu_count() or 2) - 1)

    _init(str(cfg_path), W, H, slots)
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
    n = max(1, min(workers * 2, (hi - lo) // 60 or 1))
    edges = np.linspace(lo, hi, n + 1).astype(int)
    ext = "mov" if codec == "prores" else "mp4"
    jobs = [(int(edges[k]), int(edges[k + 1]), str(out / f"part_{k:03d}.{ext}"), codec) for k in range(n)]
    print(f"  frames {lo}-{hi} of {total} ({(hi - lo) / r.fps / 60:.1f} min) in {n} chunks on {workers} workers")
    with ProcessPoolExecutor(workers, initializer=_init, initargs=(str(cfg_path), W, H, slots)) as ex:
        parts = list(ex.map(_encode_chunk, jobs))
    listing = out / "parts.txt"
    listing.write_text("".join(f"file '{pathlib.Path(p).resolve().as_posix()}'\n" for p in parts), encoding="utf8")
    name = "controglobe_motion" + ("" if (lo, hi) == (0, total) else f"_{lo}_{hi}")
    dest = out / f"{name}.{ext}"
    subprocess.run([find_ffmpeg(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-c", "copy", str(dest)], check=True)
    for p in parts:
        os.remove(p)
    print(f"  {dest}")
    return dest
