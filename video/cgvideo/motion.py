"""The motion cut: a finished, moving video rather than one still per year.

  intro     the logo sting, a text card on the premise, then a lit 3D globe that turns from the
            Atlantic to Arabia while the title comes up, and dives into the map
  main      every year, with
              - a camera that eases between keyframes (data/camera.csv): pans, zooms, rotation
              - plates: each distinct map drawn once, larger than the frame, so the camera can
                move over it without redrawing; a crossfade whenever the borders change
              - labels on a layer of their own, placed where the shot shows them, each fading
                out before the infobox, the inset, a war label or the frame edge can cut it
              - a push-in, focus pull and colour sweep with a title card at the start of each era
              - wars (data/wars.csv): arrows that grow along their campaign, pulsing battles,
                a flash and a camera shake when a battle opens
              - the infobox panel (cgvideo/panel.py) with the Qumur inset docked at its foot
  close     the camera eases back, the infobox slides away, cinema bars come in and the title
            and motto rise over the whole map; then the map dims and the finale's panel slides in
  finale    demographics: population by state, religion and ancestry by county, the largest
            cities; then an end card (cgvideo/finale.py)

Frames are piped straight into ffmpeg in parallel chunks and joined, so nothing but the plates
touches the disk. `python build.py motion --from 1855 --to 1870` renders a slice; `--frame N`
writes single PNGs for review. A whole cut also gets its soundtrack (cgvideo/audio.py).
"""

from __future__ import annotations

import bisect
import hashlib
import json
import math
import os
import pathlib
import subprocess
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import shapely
from PIL import Image, ImageChops, ImageDraw, ImageFilter

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
    "outro_seconds": 8.0,      # the close between the last year and the finale
    "outro_zoom": 0.9,         # the close pulls the camera back to this share of its last zoom
    "finale_seconds": 9.0,
    "end_card_seconds": 6.0,
    "plate_oversample": 1.5,
    "max_plate_megapixels": 40,
    "shake_px": 5,
    "inset_rect": None,        # [x, y, w, h] of the inset's map as fractions of the frame; None docks it
    "inset_size": [0.156, 0.19],  # the docked inset's map, as fractions of the frame
    "label_fade_px": 26,       # at 1080p: how close to the panel, an inset or the edge a label fades
    "focus_priority": ["usa"],  # the infobox stays on these whenever they exist
}

PLATE_VERSION = 2  # bump when plates are drawn differently
LABEL_VERSION = 5  # bump when label layers are placed or drawn differently (plates keep)


def mcfg(cfg) -> dict:
    out = dict(DEFAULTS)
    out.update(cfg.get("motion") or {})
    return out


def intro_seconds(m: dict) -> float:
    """The opening before the first map: logo sting, premise card, globe."""
    return float(m["logo_seconds"]) + float(m["intro_text_seconds"]) + float(m["globe_seconds"])


def structure(cfg, fps: int, main: int) -> dict:
    """Frame counts of the cut's parts, in order: the opening, the years, the close, the
    finale. The renderer, the Resolve script and the soundtrack all read the cut from this."""
    from .finale import Finale
    m = mcfg(cfg)
    intro = int(round(intro_seconds(m) * fps))
    outro = int(round(float(m["outro_seconds"]) * fps))
    finale = Finale.length(cfg, fps)
    return {"intro": intro, "main": int(main), "outro": outro, "finale": finale,
            "total": intro + int(main) + outro + finale}


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


def outro_view(cfg, key):
    """Where the close's slow pull-back ends: the last keyframe, further out and level."""
    cx, cy, z, _rot = key
    return (cx, cy, z * float(mcfg(cfg)["outro_zoom"]), 0.0)


def camera_views(cfg, keys):
    """Every view the camera takes, (centre_x, centre_y, zoom, rotation) in time order: the
    keyframes, then the end of the close. Plates and drawn coastlines must cover all of them."""
    keys = list(keys)
    return keys + [outro_view(cfg, keys[-1])] if keys else keys


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
    return views_extent(cfg, camera_views(cfg, [k[1:] for k in cam.keys]), W, H)


def inset_card(cfg, W, H):
    """The Qumur inset on screen: its card ((x, y, w, h): a title strip over the map) and the
    map inside it ((x, y, w, h)). Docked by default against the foot of the infobox, flush
    with where the panel turns solid; motion.inset_rect places the map anywhere instead."""
    if not cfg.get("insets"):
        return None
    m = mcfg(cfg)
    s = H / 1080
    b, strip = max(2, int(round(3 * s))), int(round(26 * s))
    if m.get("inset_rect"):
        x, y, w, h = m["inset_rect"]
        mx, my, mw, mh = int(x * W), int(y * H), int(w * W), int(h * H)
        return (mx - b, my - strip - b, mw + 2 * b, mh + strip + 2 * b), (mx, my, mw, mh)
    mw, mh = int(m["inset_size"][0] * W), int(m["inset_size"][1] * H)
    cw, ch = mw + 2 * b, mh + strip + 2 * b
    x = int(W * float(m["panel_x"])) + int(40 * s) - cw
    y = H - int(18 * s) - ch
    return (x, y, cw, ch), (x + b, y + b + strip, mw, mh)


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
    pkey = hashlib.sha1(f"{style_key(cfg, data)}|{spec.extent}|{spec.size}|v{PLATE_VERSION}".encode()).hexdigest()[:8]
    _G.clear()
    _G.update(cfg=cfg, data=data, scene=scene, W=W, H=H, slots=slots, cam=cam, spec=spec,
              fps=fps, cfg_path=cfg_path, pkey=pkey)


def _sig_ranges() -> dict:
    """For each distinct map, the stretches of main-part frames it is on screen, the old map's
    share of a crossfade included. Also leaves every slot's map signature in _G["sigs"]."""
    if "ranges" not in _G:
        data, scene, slots = _G["data"], _G["scene"], _G["slots"]
        sigs = [_sig(data, scene, s) for s in slots]
        xf = int(mcfg(_G["cfg"])["crossfade_seconds"] * _G["fps"]) + 1
        out: dict[str, list] = {}
        for i, (s, sig) in enumerate(zip(slots, sigs)):
            f0, f1 = s["start_frame"], s["start_frame"] + s["frames"]
            if i + 1 < len(slots) and sigs[i + 1] != sig:
                f1 += xf
            rs = out.setdefault(sig, [])
            if rs and rs[-1][1] >= f0:
                rs[-1] = (rs[-1][0], max(rs[-1][1], f1))
            else:
                rs.append((f0, f1))
        _G["ranges"], _G["sigs"] = out, sigs
    return _G["ranges"]


def screen_to_world(u, v, cam_state, W, H, anchor):
    """Screen pixels back to projected metres: the inverse of world_to_screen (no shake)."""
    cx, cy, z, rot = cam_state
    k = metres_per_px(_G["cfg"], H) / z
    c, s = math.cos(rot), math.sin(rot)
    du, dv = np.asarray(u, float) - anchor[0] * W, np.asarray(v, float) - anchor[1] * H
    dx, dy = c * du + s * dv, -s * du + c * dv
    return cx + dx * k, cy - dy * k


def _clear_view(cfg, W, H):
    """The part of the screen a map label may use: inside the frame, left of the infobox and
    off the inset, as a polygon in screen pixels."""
    m = mcfg(cfg)
    g = 0.02 * H
    rect = shapely.box(g, g, int(W * float(m["panel_x"])) - g, H - g)
    card = inset_card(cfg, W, H)
    if card:
        x, y, w, h = card[0]
        rect = rect.difference(shapely.box(x - g, y - g, x + w + g, y + h + g))
    return rect


def _visibility(sig):
    """(always, anywhere): the ground every frame showing this map sees clear of the infobox and
    the inset, and the ground some frame sees, in projected metres. Label placement uses it."""
    cache = _G.setdefault("vis", {})
    if sig in cache:
        return cache[sig]
    cfg, cam, W, H = _G["cfg"], _G["cam"], _G["W"], _G["H"]
    anchor = mcfg(cfg)["anchor"]
    ranges = _sig_ranges().get(sig, [])
    frames = []
    for f0, f1 in ranges:
        frames += list(range(f0, f1, 12)) + [f1 - 1]
    if len(frames) > 60:
        frames = [frames[int(i)] for i in np.linspace(0, len(frames) - 1, 60)]
    views = [cam.at(f) for f in frames]
    if _G["sigs"] and sig == _G["sigs"][-1]:
        views.append(outro_view(cfg, cam.keys[-1][1:]))   # the finale looks at the last map from here
    clear = _clear_view(cfg, W, H)

    def to_world(view):
        def fn(coords):
            x, y = screen_to_world(coords[:, 0], coords[:, 1], view, W, H, anchor)
            return np.column_stack([x, y])
        return fn

    polys = [shapely.transform(clear, to_world(view)) for view in views]
    if not polys:
        cache[sig] = (None, None)
    else:
        cache[sig] = (shapely.make_valid(shapely.intersection_all(polys)), shapely.union_all(polys))
    return cache[sig]


def _label_path(cfg, W, H, sig):
    always, anywhere = _visibility(sig)
    h = hashlib.sha1(f"labels v{LABEL_VERSION}".encode())
    for g in (always, anywhere):
        if g is not None and not g.is_empty:
            h.update(shapely.to_wkb(shapely.set_precision(g, 1000.0)))
    return _plate_path(cfg, W, H, f"{sig}_{h.hexdigest()[:8]}", "labels")


def _make_plate(slot):
    from .render import _inset_extent, render_labels, render_map
    cfg, data, scene, spec, W, H = _G["cfg"], _G["data"], _G["scene"], _G["spec"], _G["W"], _G["H"]
    sig = _sig(data, scene, slot)
    out = _plate_path(cfg, W, H, sig)
    row = data.matrix[slot["index"]]
    places = scene.places_for(slot["year"])
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        img = render_map(scene, row, spec.size[0], spec.size[1], places, extent=spec.extent,
                         px_scale=spec.px_scale, insets=False, labels=False)
        tmp = out.with_suffix(".tmp.png")
        img.save(tmp, compress_level=1)
        os.replace(tmp, out)
    # the labels, on their own layer, placed where the frames that show this map can see them
    lpath = _label_path(cfg, W, H, sig)
    if not lpath.exists():
        img, boxes = render_labels(scene, row, spec.size[0], spec.size[1], places, extent=spec.extent,
                                   px_scale=spec.px_scale, visible=_visibility(sig))
        lpath.with_suffix(".json").write_text(json.dumps([[round(v, 1) for v in b] for b in boxes]), encoding="utf8")
        tmp = lpath.with_suffix(".tmp.png")
        img.save(tmp, compress_level=1)
        os.replace(tmp, lpath)
    # the Qumur inset, drawn at its screen size (its own file, so moving the inset redraws only it)
    card = inset_card(cfg, W, H)
    if card:
        mw, mh = card[1][2], card[1][3]
        for ins in cfg.get("insets", []):
            ipath = _plate_path(cfg, W, H, f"{sig}_{ins['name']}_{mw}x{mh}", "inset")
            if ipath.exists():
                continue
            ex = _inset_extent(cfg, {**ins, "rect": [0, 0, mw / W, mh / H]}, W, H)
            inset = render_map(scene, row, mw, mh, places, extent=ex, px_scale=(H / 2160) * 1.3, insets=False)
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


def _tracked(d, xy, text, font, fill, spacing, anchor="m"):
    """Letter-spaced text centred on xy (anchor 'm') or starting there ('l')."""
    widths = [d.textlength(ch, font=font) for ch in text]
    total = sum(widths) + spacing * (len(text) - 1)
    x = xy[0] - total / 2 if anchor == "m" else xy[0]
    for ch, w in zip(text, widths):
        d.text((x, xy[1]), ch, font=font, fill=fill, anchor="lm")
        x += w + spacing
    return total


# -- frame rendering -----------------------------------------------------------------------

class Renderer:
    def __init__(self):
        g = _G
        self.cfg, self.data, self.scene, self.W, self.H = g["cfg"], g["data"], g["scene"], g["W"], g["H"]
        self.slots, self.cam, self.spec, self.fps = g["slots"], g["cam"], g["spec"], g["fps"]
        self.m = mcfg(self.cfg)
        self.main = self.slots[-1]["start_frame"] + self.slots[-1]["frames"]
        self.S = structure(self.cfg, self.fps, self.main)
        self.intro, self.outro_n = self.S["intro"], self.S["outro"]
        self.starts = [s["start_frame"] for s in self.slots]
        self.panel = Panel(self.cfg, self.data, self.scene, self.W, self.H)
        self.ocean = hexrgb(self.cfg["style"]["ocean"])[:3]
        self._plates: dict[str, Image.Image] = {}
        self._labels: dict[str, tuple] = {}
        self._insets: dict[str, Image.Image] = {}
        _sig_ranges()
        self.sigs = _G["sigs"]
        self.year_frames = {}
        for s in self.slots:
            self.year_frames[s["year"]] = (s["start_frame"], s["start_frame"] + s["frames"])
        self.wars = self._prep_wars()
        self.card = inset_card(self.cfg, self.W, self.H)
        self.fade_px = float(self.m["label_fade_px"]) * self.H / 1080
        self.label_pad = 10.0 * self.spec.px_scale / 0.75
        self.outro_cam = outro_view(self.cfg, self.cam.keys[-1][1:])
        yy, xx = np.mgrid[0:self.H, 0:self.W]
        r = np.hypot((xx - self.W / 2) / (self.W / 2), (yy - self.H / 2) / (self.H / 2))
        vig = float(self.cfg["style"].get("postfx", {}).get("vignette", 0.3))
        self.vignette = (1 - vig * np.clip(r - 0.6, 0, None) ** 1.7)[..., None].astype(np.float32)
        self.diag = ((xx / self.W + 0.35 * yy / self.H) / 1.35).astype(np.float32)  # for light sweeps
        self.finale = None
        self.globe = None
        self._scrim = None
        self._shadow = None

    def total_frames(self):
        return self.S["total"]

    def finale_obj(self):
        if self.finale is None:
            from .finale import Finale
            self.finale = Finale(self)
        return self.finale

    # plates and their labels
    def plate(self, sig) -> Image.Image:
        if sig not in self._plates:
            if len(self._plates) > 2:  # the current plate, the one it crossfades from, one spare
                self._plates.pop(next(iter(self._plates)))
            self._plates[sig] = Image.open(_plate_path(self.cfg, self.W, self.H, sig)).convert("RGB")
        return self._plates[sig]

    def labels(self, sig):
        """(premultiplied RGBA layer, boxes) for a map, or None when it was drawn without one."""
        if sig not in self._labels:
            if len(self._labels) > 2:
                self._labels.pop(next(iter(self._labels)))
            p = _label_path(self.cfg, self.W, self.H, sig)
            if p.exists():
                layer = Image.open(p).convert("RGBA").convert("RGBa")  # premultiplied: clean edges when resampled
                boxes = np.asarray(json.loads(p.with_suffix(".json").read_text(encoding="utf8")), float).reshape(-1, 4)
                boxes += np.array([-1, -1, 1, 1]) * self.label_pad    # the halo reaches past the text's box
                self._labels[sig] = (layer, boxes)
            else:
                self._labels[sig] = None
        return self._labels[sig]

    def inset(self, sig, name) -> Image.Image | None:
        mw, mh = self.card[1][2], self.card[1][3]
        key = f"{sig}_{name}_{mw}x{mh}"
        if key not in self._insets:
            p = _plate_path(self.cfg, self.W, self.H, key, "inset")
            self._insets[key] = Image.open(p).convert("RGB") if p.exists() else None
            if len(self._insets) > 6:
                self._insets.pop(next(iter(self._insets)))
        return self._insets[key]

    def label_mask(self, boxes, A, hide):
        """An L mask that fades each label by how close it comes to the frame edge or to a
        rectangle it must keep clear of (hide: (x0, y0, x1, y1, strength) on screen); None
        when every label is clear."""
        if not len(boxes):
            return None
        a, b, c, d, e, f = A
        det = a * e - b * d
        x0, y0, x1, y1 = boxes.T
        X = np.stack([x0, x1, x1, x0], 1) - c
        Y = np.stack([y0, y0, y1, y1], 1) - f
        U, V = (e * X - b * Y) / det, (-d * X + a * Y) / det      # plate pixels back to the screen
        u0, u1, v0, v1 = U.min(1), U.max(1), V.min(1), V.max(1)
        F = self.fade_px
        edge = np.minimum.reduce([u0, v0, self.W - u1, self.H - v1])
        fade = np.clip((edge + 0.3 * F) / F, 0, 1)
        for hx0, hy0, hx1, hy1, strength in hide:
            gap = np.maximum.reduce([hx0 - u1, u0 - hx1, hy0 - v1, v0 - hy1])
            fade = np.minimum(fade, 1 - strength * (1 - np.clip(gap / F, 0, 1)))
        idx = np.nonzero(fade < 0.996)[0]
        if not len(idx):
            return None
        mask = Image.new("L", (self.W, self.H), 255)
        dr = ImageDraw.Draw(mask)
        for k in idx[np.argsort(-fade[idx])]:  # the most faded last, where two boxes meet
            dr.polygon(list(zip(U[k], V[k])), fill=int(255 * fade[k]))
        return mask

    def map_view(self, sig, cam_state, shake, hide):
        """One map under the camera, with its labels faded wherever they would be cut."""
        A = affine(self.spec, cam_state, self.W, self.H, self.m["anchor"], shake)
        base = self.plate(sig).transform((self.W, self.H), Image.AFFINE, A, Image.BICUBIC, fillcolor=self.ocean)
        lab = self.labels(sig)
        if lab is None:
            return base
        layer = lab[0].transform((self.W, self.H), Image.AFFINE, A, Image.BICUBIC).convert("RGBA")
        mask = self.label_mask(lab[1], A, hide)
        if mask is not None:
            layer.putalpha(ImageChops.multiply(layer.getchannel("A"), mask))
        out = base.convert("RGBA")
        out.alpha_composite(layer)
        return out.convert("RGB")

    def panel_hide(self, offset=0):
        return (self.panel.x0 + offset, -1e5, 1e5, 1e5, 1.0)

    def card_hide(self, strength=1.0):
        x, y, w, h = self.card[0]
        return (x, y, x + w, y + h, strength)

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

    def war_layer(self, f, cam_state, shake):
        """The war graphics of frame f on a transparent layer, the strength of a battle's flash,
        and the boxes of the war labels, which the map's own labels make way for."""
        active = [w for w in self.wars if w["f0"] <= f < w["f1"] + int(0.8 * self.fps)]
        if not active:
            return None, 0.0, []
        from PIL import ImageFont
        from .panel import _fontfile
        s = self.H / 1080
        over = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(over)
        anchor = self.m["anchor"]
        flash, boxes = 0.0, []
        sw = max(2, int(3 * s))
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
                        fnt = ImageFont.truetype(_fontfile("DejaVuSans-Bold.ttf"), int(17 * s))
                        pos = (qx + 14 * s, qy - 26 * s)
                        boxes.append((*d.textbbox(pos, w["label"], font=fnt, stroke_width=sw), fade))
                        d.text(pos, w["label"], font=fnt, fill=(255, 255, 255, a), stroke_width=sw,
                               stroke_fill=(10, 10, 10, a))
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
                    fnt = ImageFont.truetype(_fontfile("DejaVuSans-Bold.ttf"), int(18 * s))
                    pos = (x + 16 * s, y + 10 * s)
                    boxes.append((*d.textbbox(pos, w["label"], font=fnt, stroke_width=sw), fade))
                    d.text(pos, w["label"], font=fnt, fill=(255, 255, 255, int(255 * fade)),
                           stroke_width=sw, stroke_fill=(10, 10, 10, int(255 * fade)))
        return over, flash, boxes

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

    def era_card_box(self, slot, t):
        """Where the era card is at t seconds into its slot: (right edge, top, height, width),
        or None when it is off the screen."""
        dur = float(self.cfg["pacing"].get("era_title_seconds", 2.5))
        if not slot["era_start"] or t > dur + 0.6:
            return None
        s = self.H / 1080
        card_w = int(self.panel.x0 * 0.80)
        enter = back_ease(t / 0.75)
        leave = ease((t - dur) / 0.55) if t > dur else 0.0
        x1 = int(card_w * enter - (card_w + 40 * s) * leave)
        return (x1, int(self.H * 0.13), int(168 * s), card_w) if x1 > 2 else None

    def era_card(self, img, slot, t):
        """The era's title on frosted glass: it slides in with a small overshoot while an
        accent rule draws itself, holds, and slides back out."""
        box = self.era_card_box(slot, t)
        if box is None:
            return img
        from .panel import _fontfile
        from PIL import ImageFont
        from . import years as Y
        s = self.H / 1080
        color = hexrgb(self._era_color(slot))
        x1, y0, bh, card_w = box
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
        d.text((tx, y0 + int(20 * s)), " ".join(f"ERA {roman}"),
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

    def draw_inset(self, img, sig, alpha=1.0):
        """The Qumur inset as a card against the infobox's foot: a title strip, the map, a
        hairline frame and a soft shadow off the map."""
        if self.card is None or alpha <= 0.004:
            return
        from PIL import ImageFont
        from .panel import _fontfile
        (x, y, w, h), (mx, my, mw, mh) = self.card
        s = self.H / 1080
        hud = self.cfg["style"]["hud"]
        panel, accent = hexrgb(hud["panel"]), hexrgb(hud["accent"])
        if self._shadow is None:
            g = int(22 * s)
            sh = Image.new("L", (w + 2 * g, h + 2 * g), 0)
            ImageDraw.Draw(sh).rectangle([g, g, g + w, g + h], fill=150)
            self._shadow = (sh.filter(ImageFilter.GaussianBlur(10 * s)), g)
        sh, g = self._shadow
        for n, ins in enumerate(self.cfg.get("insets", [])):
            dx = -n * (w + int(12 * s))          # more than one inset: they queue to the left
            shade = Image.new("RGBA", sh.size, (0, 0, 0, 0))
            shade.putalpha(sh.point(lambda v: int(v * alpha)))
            img.alpha_composite(shade, (max(0, x + dx - g), max(0, y - g)))
            card = Image.new("RGBA", (w, h), panel[:3] + (250,))
            small = self.inset(sig, ins["name"])
            if small is not None:
                card.paste(small, (mx - x, my - y))
            d = ImageDraw.Draw(card)
            d.text((int(12 * s), (my - y) / 2 + 1), ins["name"].upper(),
                   font=ImageFont.truetype(_fontfile("DejaVuSans-Bold.ttf"), int(15 * s)), fill=accent, anchor="lm")
            d.line([(mx - x, my - y - 1), (mx - x + mw, my - y - 1)], fill=accent[:3] + (150,), width=1)
            d.rectangle([0, 0, w - 1, h - 1], outline=(255, 255, 255, 52), width=max(1, int(1.5 * s)))
            if alpha < 1:
                card.putalpha(card.getchannel("A").point(lambda v: int(v * alpha)))
            img.alpha_composite(card, (x + dx, y))

    def main_frame(self, f):
        i = bisect.bisect_right(self.starts, f) - 1
        slot = self.slots[i]
        t = (f - slot["start_frame"]) / self.fps
        cam_state = self.cam.at(f)
        shake = self.shake(f)
        wars, flash, war_boxes = self.war_layer(f, cam_state, shake)
        # map labels make way for the infobox, the inset, the war labels and the era card
        # (x0, y0, x1, y1, strength), so none is ever cut through
        hide = [self.panel_hide()] + ([self.card_hide()] if self.card else []) + war_boxes
        ec = self.era_card_box(slot, t)
        if ec is not None:
            hide.append((-1e5, ec[1], ec[0], ec[1] + ec[2], 1.0))
        sig = self.sigs[i]
        img = self.map_view(sig, cam_state, shake, hide)
        # crossfade from the previous map when the borders change
        if i > 0 and self.sigs[i - 1] != sig:
            xf = min(self.m["crossfade_seconds"] * self.fps, max(1, slot["frames"]))
            k = (f - slot["start_frame"]) / xf
            if k < 1:
                prev = self.map_view(self.sigs[i - 1], cam_state, shake, hide)
                img = Image.blend(prev, img, ease(k))
        img = img.convert("RGBA")
        if wars is not None:
            img.alpha_composite(wars)
        if flash > 0:
            img = Image.blend(img, Image.new("RGBA", img.size, (255, 244, 220, 255)), flash)
        if slot["era_start"] and t < self.m["era_fx_seconds"]:
            img = self.era_fx(img.convert("RGB"), slot, t).convert("RGBA")
        img = self.era_card(img, slot, t)
        self.panel.draw(img, slot, t)
        self.draw_inset(img, sig)
        return img.convert("RGB")

    # the close
    def outro_frame(self, f):
        """The camera eases back and levels; the infobox slides away and the inset fades, and in
        the infobox's place a dark gradient comes up the right of the frame (the map's edge is
        out there: nothing east of the mesh is drawn); cinema bars close in and the title and
        motto rise in the dark; then the bars open, the map dims to the finale's shade and the
        finale's panel slides in, so its first frame follows this one without a cut."""
        W, H, fps = self.W, self.H, self.fps
        s = H / 1080
        T = self.outro_n / fps
        t = f / fps
        c0, c1 = self.cam.at(self.main - 1), self.outro_cam
        k = ease(t / T)
        cam_state = tuple(a + (b - a) * k for a, b in zip(c0, c1))
        travel = W - self.panel.x0 + 60 * s
        slide = ease((t - 0.25) / 1.15) * travel               # the infobox leaves to the right
        arrive = ease((t - (T - 1.45)) / 1.45)                 # the finale's panel comes in
        fin_off = (1 - arrive) * travel
        inset_a = 1 - ease((t - 0.1) / 0.7)
        side = ease(t / 0.9) * (1 - arrive)                    # the dark on the right
        hide = [(0.6 * W, -1e5, 1e5, 1e5, side)]
        if slide < travel:
            hide.append(self.panel_hide(slide))
        if arrive > 0:
            hide.append(self.panel_hide(fin_off))
        if inset_a > 0 and self.card:
            hide.append(self.card_hide(inset_a))
        img = self.map_view(self.sigs[-1], cam_state, (0.0, 0.0), hide)
        dim = 0.45 * ease((t - (T - 2.7)) / 1.6)
        if dim > 0:
            img = Image.blend(img, Image.new("RGB", img.size, (10, 12, 16)), dim)
        img = img.convert("RGBA")
        if side > 0:
            if self._scrim is None:
                x = np.arange(W, dtype=np.float32)
                ramp = np.clip((x - 0.5 * W) / (0.24 * W), 0, 1)
                ramp = ramp * ramp * (3 - 2 * ramp)
                self._scrim = Image.fromarray((np.repeat(ramp[None, :], H, 0) * 255).astype(np.uint8))
            dark = Image.new("RGBA", img.size, (6, 8, 12, 255))
            dark.putalpha(self._scrim.point(lambda v: int(v * 0.93 * side)))
            img.alpha_composite(dark)
        if slide < travel:
            self.panel.draw(img, self.slots[-1], 99.0, offset=int(round(slide)))
        if inset_a > 0:
            self.draw_inset(img, self.sigs[-1], inset_a)
        img = self._outro_title(img, t)
        bars = ease((t - 0.6) / 1.5) * (1 - ease((t - (T - 2.2)) / 1.2))
        if bars > 0:
            bh = int(round(0.105 * H * bars))
            d = ImageDraw.Draw(img)
            d.rectangle([0, 0, W, bh], fill=(0, 0, 0, 255))
            d.rectangle([0, H - bh, W, H], fill=(0, 0, 0, 255))
        if arrive > 0:
            fin = self.finale_obj()
            fin.draw_panel(img, "population", 0.0, offset=int(round(fin_off)))
        return img.convert("RGB")

    def _outro_title(self, img, t):
        """The span of years, the Union's name and its motto, rising one after another in the
        dark on the right while a gold rule draws itself between them."""
        from PIL import ImageFont
        from .panel import _fontfile
        W, H = self.W, self.H
        s = H / 1080
        a1, a2, a3 = (ease((t - t0) / 0.9) for t0 in (2.0, 2.4, 3.3))
        out = 1 - ease((t - 5.1) / 0.7)
        if max(a1, a2, a3) * out <= 0:
            return img
        cx, cy = 0.815 * W, 0.5 * H
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        first, last = self.slots[0]["label"], self.slots[-1]["label"]
        _tracked(d, (cx, cy - 118 * s + (1 - a1) * 12 * s), f"{first}  —  {last}".upper(),
                 ImageFont.truetype(_fontfile("DejaVuSans-Bold.ttf"), int(22 * s)),
                 (226, 182, 89, int(255 * a1 * out)), 5 * s)
        name = self.data.polity.get("usa", {}).get("name", "United States of Arabia").upper().split(" ")
        cut = min(range(1, len(name)), key=lambda i: abs(len(" ".join(name[:i])) - len(" ".join(name[i:])))) \
            if len(name) > 1 else 1
        big = ImageFont.truetype(_fontfile("DejaVuSerif-Bold.ttf"), int(54 * s))
        for n, words in enumerate((name[:cut], name[cut:])):
            if words:
                _tracked(d, (cx, cy - 58 * s + n * 62 * s + (1 - a2) * 14 * s), " ".join(words), big,
                         (247, 243, 234, int(255 * a2 * out)), 5 * s)
        rule = 320 * s * ease((t - 2.9) / 0.9)
        if rule > 1:
            d.rectangle([cx - rule / 2, cy + 48 * s, cx + rule / 2, cy + 50 * s], fill=(226, 182, 89, int(220 * out)))
        d.text((cx, cy + 90 * s + (1 - a3) * 10 * s), "Out of many, one people.",
               font=ImageFont.truetype(_fontfile("DejaVuSerif-Italic.ttf"), int(28 * s)),
               fill=(222, 216, 204, int(255 * a3 * out)), anchor="mm")
        img.alpha_composite(layer)
        return img

    def frame(self, f) -> Image.Image:
        S = self.S
        if f < S["intro"]:
            from .globe import intro_frame
            img = intro_frame(self, f)
        elif f < S["intro"] + S["main"]:
            img = self.main_frame(f - S["intro"])
        elif f < S["intro"] + S["main"] + S["outro"]:
            img = self.outro_frame(f - S["intro"] - S["main"])
        else:
            img = self.finale_obj().frame(f - S["intro"] - S["main"] - S["outro"])
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
    interpreter and scene (~0.6 GB), up to three plates and three label layers, and an x264
    encoder's lookahead."""
    cpus = max(1, (os.cpu_count() or 2) - 1)
    free = available_memory()
    if not free:
        return cpus, "free memory unknown"
    per = 0.6e9 + 3 * plate_size[0] * plate_size[1] * (3 + 4) + W * H * 1.5 * 48
    n = max(1, min(cpus, int(free * 0.7 / per)))
    return n, f"{free / 1e9:.1f} GB free, ~{per / 1e9:.1f} GB per worker"


def _plates_job(slot):
    return _make_plate(slot)


def _frame_job(args):
    f, dest = args
    Renderer().frame(f).save(dest)
    return dest


def resound(cfg, cfg_path, scale=0.5):
    """Remake the soundtrack and put it into the newest motion cut, as a new file (an editor
    that has the old one open would keep showing it). Returns the new cut, or None if no cut."""
    from . import audio
    from .sequence import find_ffmpeg
    import time
    W = int(round(cfg["frame"]["width"] * scale / 2) * 2)
    H = int(round(cfg["frame"]["height"] * scale / 2) * 2)
    data = D.load(cfg)
    slot_objs, meta = T.write(cfg, data)
    from dataclasses import asdict
    slots = [asdict(s) for s in slot_objs]
    _init(str(cfg_path), W, H, slots)
    r = Renderer()
    files = audio.soundtrack(cfg, data, slots, r)
    cut = T.motion_cut(cfg)
    if cut is None:
        return None
    dest = cut.with_name(f"controglobe_motion_{time.strftime('%Y%m%d-%H%M%S')}{cut.suffix}")
    subprocess.run([find_ffmpeg(), "-y", "-loglevel", "error", "-i", str(cut), "-i", str(files["mix"]),
                    "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-shortest",
                    str(dest)], check=True)
    what = T.write_resolve_lua(cfg, slot_objs, meta, media="motion")
    installed = T.install_resolve_script(cfg)
    print(f"  Resolve build script: {what}" + (f"; installed as {installed}" if installed else ""))
    return dest


def run(cfg, cfg_path, scale=1.0, workers=None, first_year=None, last_year=None, frames=None, codec="h264",
        sound=True):
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
    # Every whole cut gets a file of its own. An editor that has imported a cut keeps that file
    # open and remembers it; writing a new cut over the same name leaves it showing the old one.
    import time
    whole = (lo, hi) == (0, total)
    stamp = time.strftime('%Y%m%d-%H%M%S')
    name = f"controglobe_motion_{stamp}" if whole else f"controglobe_slice_{lo}_{hi}"
    dest = out / f"{name}.{ext}"
    cmd = [find_ffmpeg(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing)]
    mix = None
    if sound:
        # the soundtrack: music and effects as stems for the edit, and a mix inside the file
        from . import audio
        stems = audio.build(cfg, data, slots, r, stamp if whole else f"slice_{lo}_{hi}", lo / r.fps, hi / r.fps)
        mix = stems.get("mix") if stems else None
    if mix:
        cmd += ["-i", str(mix), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "320k",
                "-shortest"]
    else:
        cmd += ["-c", "copy"]
    subprocess.run(cmd + [str(dest)], check=True)
    for p in parts:
        os.remove(p)
    print(f"  {dest}")
    if whole:
        # a whole cut: point the Resolve build script at it, markers moved past the opening
        what = T.write_resolve_lua(cfg, slot_objs, meta, media="motion")
        installed = T.install_resolve_script(cfg)
        print(f"  Resolve build script: {what}" + (f"; installed as {installed}" if installed else ""))
    return dest
