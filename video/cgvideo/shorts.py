"""The Shorts: vertical war simulations, 1080x1920, drawn by a HyperFrames composition.

    python build.py shorts --id 2                        build the composition (plates, globe, balls, score)
    python build.py shorts --id 2 --stills 0.6 3.5 9.8   single frames, to open and look at
    python build.py shorts --id 2 --render               the MP4 (npx hyperframes), then the upload kit
    python build.py shorts --id 2 --render --from 8 --to 13

A Short is a beat sheet in config/shorts.yaml. The ground is the long cut's own map (render.py's
render_map, one plate per border state, larger than the frame so the camera can move over it); the
hook is the lit globe of globe.py with that map painted on it; everything else (the HUD skin, army
banners and their numbers, arrows, battle popups, captions, the Arabic lower-thirds, countryballs, the
casualty count and the end card) is drawn by cgvideo/shorts_engine/engine.js as a pure function of
time, so any frame can be rendered alone. The soundtrack is synthesised, as the long cut's is.
"""

from __future__ import annotations

import hashlib
import json
import math
import pathlib
import shutil
import subprocess
import sys
import time

import numpy as np
import yaml
from PIL import Image, ImageDraw

from . import assets, geo
from . import data as D
from .config import load_config, paths

ENGINE = pathlib.Path(__file__).with_name("shorts_engine")
VERSION = 3           # bump when plates or the globe are drawn differently
KM_FULL = 3400.0      # zoom 1 shows this many km from the top of the frame to the bottom
SIDE = {"usa": {"colour": "#2f64a8", "light": "#9fc0ea", "name": "UNION", "name_ar": "الاتحاد"},
        "isa": {"colour": "#b5463a", "light": "#f0a99c", "name": "ISLAMIC STATES", "name_ar": "الدول الإسلامية"}}
MOODS = ("neutral", "happy", "angry", "sad", "surprised", "smug")


def spec_for(cfg, sid: int) -> tuple[dict, dict]:
    raw = yaml.safe_load((paths(cfg).root / "config" / "shorts.yaml").read_text(encoding="utf8"))
    for s in raw["shorts"]:
        if int(s["id"]) == int(sid):
            return {**raw.get("defaults", {}), **s}, raw
    raise SystemExit(f"no Short {sid} in config/shorts.yaml")


def out_dir(cfg, sid) -> pathlib.Path:
    return paths(cfg).build / "shorts" / str(sid)


# -- the ground ----------------------------------------------------------------------------

class Plate:
    """A box of the long cut's projection, drawn at `px_per_km`; px() puts lon/lat on it."""

    def __init__(self, cfg, spec):
        p = spec["plate"]
        w, s, e, n = p["bbox"]
        lons = np.concatenate([np.linspace(w, e, 60), np.full(60, e), np.linspace(e, w, 60), np.full(60, w)])
        lats = np.concatenate([np.full(60, s), np.linspace(s, n, 60), np.full(60, n), np.linspace(n, s, 60)])
        x, y = geo.project_points(cfg, lons, lats)
        self.cfg = cfg
        self.extent = (float(x.min()), float(x.max()), float(y.min()), float(y.max()))
        self.k = float(p["px_per_km"]) / 1000.0          # plate px per metre
        x0, x1, y0, y1 = self.extent
        self.w, self.h = int((x1 - x0) * self.k), int((y1 - y0) * self.k)
        self.label_scale = float(p.get("label_scale", 1.8))

    def px(self, lon, lat):
        x, y = geo.project_points(self.cfg, [lon], [lat])
        return [round((float(x[0]) - self.extent[0]) * self.k, 1), round((self.extent[3] - float(y[0])) * self.k, 1)]

    def path(self, pts):
        return [self.px(lo, la) for lo, la in pts]


def build_plates(cfg, data, spec, plate: Plate, out: pathlib.Path, log=print) -> dict:
    from .render import Scene, render_map, style_key
    scene = None
    srcs = {}
    for m in spec["maps"]:
        row = data.matrix[data.year_index(int(m["year"]))]
        sig = hashlib.sha1(f"{data.state_signature(row)}|{plate.extent}|{plate.w}x{plate.h}|{plate.label_scale}|"
                           f"{style_key(cfg, data)}|v{VERSION}".encode()).hexdigest()[:10]
        name = f"plate_{m['key']}_{sig}.jpg"
        dst = out / "assets" / name
        if not dst.exists():
            scene = scene or Scene(cfg, data)
            log(f"  plate {m['key']} ({m['year']}): {plate.w}x{plate.h}")
            img = render_map(scene, row, plate.w, plate.h, scene.places_for(int(m["year"])), extent=plate.extent,
                             px_scale=plate.label_scale, insets=False, labels=True)
            img.save(dst, quality=93)
        srcs[m["key"]] = f"assets/{name}"
    return srcs


# -- the hook: the globe, with the map of the hook painted on it -----------------------------

def build_globe(cfg, spec, plate: Plate, plate_file: pathlib.Path, out: pathlib.Path, log=print) -> dict | None:
    from . import globe as G
    from .sequence import find_ffmpeg
    hk = spec["hook"]
    g = hk["globe"]
    W, H, fps = int(spec["W"]), int(spec["H"]), int(spec["fps"])
    T = float(hk["t1"]) + 0.4
    n = int(round(T * fps))
    sig = hashlib.sha1(f"{json.dumps(g)}|{T}|{plate_file.name}|{W}x{H}|v{VERSION}".encode()).hexdigest()[:8]
    name = f"globe_{sig}.mp4"
    dst = out / "assets" / name
    if not dst.exists():
        G.prepare(cfg)
        globe = G.Globe(cfg, W, H)
        tex = Image.open(plate_file).convert("RGB")
        ds = 3
        tex = np.asarray(tex.resize((tex.width // ds, tex.height // ds), Image.LANCZOS)).astype(np.float32)
        fwd = geo.to_proj(cfg)
        frames = out / "globe_frames"
        frames.mkdir(parents=True, exist_ok=True)
        log(f"  globe: {n} frames")
        for f in range(n):
            u = f / max(1, n - 1)
            turn = 1 - (1 - min(1.0, u / 0.55)) ** 3                   # the turn lands early, then the dive
            lon = g["from"][0] + (g["to"][0] - g["from"][0]) * turn
            lat = g["from"][1] + (g["to"][1] - g["from"][1]) * turn
            r0, r1 = g["radius"]
            dive = max(0.0, (u - 0.35) / 0.65) ** 2.2
            radius = W * r0 * (r1 / r0) ** dive
            img = globe.render(lon, lat, radius, cx=W / 2, cy=H * 0.46)
            img = _paint(img, lon, lat, radius, W / 2, H * 0.46, tex, ds, plate, fwd)
            img.save(frames / f"g{f:04d}.jpg", quality=92)
        cmd = [find_ffmpeg(), "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(frames / "g%04d.jpg"),
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "14", "-preset", "slow", "-movflags", "+faststart", str(dst)]
        subprocess.run(cmd, check=True)
        shutil.rmtree(frames, ignore_errors=True)
    return {"src": f"assets/{name}", "t0": 0.0, "t1": T}


def _paint(img, lon0, lat0, radius, cx, cy, tex, ds, plate: Plate, fwd):
    """The plate's colours on the sphere wherever it covers, lit like the globe, soft at its edge."""
    W, H = img.size
    x0, x1 = int(max(0, cx - radius)), int(min(W, cx + radius + 1))
    y0, y1 = int(max(0, cy - radius)), int(min(H, cy + radius + 1))
    if x1 <= x0 or y1 <= y0:
        return img
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    nx, ny = (xx - cx) / radius, -(yy - cy) / radius
    rho2 = nx * nx + ny * ny
    inside = rho2 <= 1.0
    nz = np.sqrt(np.clip(1 - rho2, 0, 1))
    la0, lo0 = math.radians(lat0), math.radians(lon0)
    lat = np.degrees(np.arcsin(np.clip(nz * math.sin(la0) + ny * math.cos(la0), -1, 1)))
    lon = np.degrees(lo0 + np.arctan2(nx, nz * math.cos(la0) - ny * math.sin(la0)))
    lon = (lon + 180) % 360 - 180
    sel = inside & (np.abs(lon - 46.5) < 60) & (np.abs(lat - 25) < 45)
    if not sel.any():
        return img
    X, Y = fwd.transform(lon[sel], lat[sel])
    px = (np.asarray(X) - plate.extent[0]) * plate.k / ds
    py = (plate.extent[3] - np.asarray(Y)) * plate.k / ds
    th, tw = tex.shape[:2]
    ok = (px >= 0) & (px < tw - 1) & (py >= 0) & (py < th - 1)
    edge = np.clip(np.minimum.reduce([px, tw - 1 - px, py, th - 1 - py]) / 40.0, 0, 1) * ok
    col = tex[np.clip(py.astype(int), 0, th - 1), np.clip(px.astype(int), 0, tw - 1)]
    edge = edge * ~((col[:, 0] < 75) & (col[:, 2] > col[:, 0]))      # the plate's sea stays the globe's sea
    sat = col.max(1) - col.min(1)
    edge = edge * np.clip((sat - 22) / 18, 0, 1)                      # and its unclaimed land the globe's ground
    light = np.clip(0.35 + 0.8 * (nx[sel] * -0.45 + ny[sel] * 0.35 + nz[sel] * 0.82), 0.25, 1.1)
    rim = np.clip((rho2[sel] - 0.8) / 0.2, 0, 1)
    a = (edge * (1 - rim))[:, None]
    arr = np.asarray(img).astype(np.float32)
    sub = arr[y0:y1, x0:x1]
    cur = sub[sel]
    sub[sel] = cur * (1 - a) + col * light[:, None] * a
    arr[y0:y1, x0:x1] = sub
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


# -- countryballs ----------------------------------------------------------------------------

def ball(flag: Image.Image, D_: int, mood: str = "neutral") -> Image.Image:
    """thumbnail.countryball()'s ball (flag skin, heavy outline, no pupils), with the mood in the
    shape of the eyes alone, as the countryball convention has it."""
    ss = 3
    S = D_ * ss
    skin = flag.convert("RGBA")
    k = S / skin.height
    skin = skin.resize((int(skin.width * k * 1.05), int(S * 1.05)), Image.LANCZOS)
    tex = Image.new("RGBA", (S, S))
    tex.paste(skin, (-int(S * 0.08), -int(S * 0.02)))
    circle = Image.new("L", (S, S), 0)
    m = 4 * ss
    ImageDraw.Draw(circle).ellipse([m, m, S - m, S - m], fill=255)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(tex, (0, 0), circle)
    yy, xx = np.mgrid[0:S, 0:S] / S
    shade = 1.12 - 0.55 * np.clip(np.hypot(xx - 0.36, yy - 0.3), 0, 1) ** 1.4
    arr = np.asarray(out).astype(np.float32)
    arr[..., :3] *= shade[..., None]
    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(out)
    lw = int(S * 0.028)
    ink = (12, 12, 12, 255)
    d.ellipse([m, m, S - m, S - m], outline=ink, width=lw)
    white = (255, 255, 255, 255)
    for i, cx in enumerate((0.40, 0.66)):
        ex, ey, rx, ry = cx * S, 0.42 * S, 0.085 * S, 0.12 * S
        box = [ex - rx, ey - ry, ex + rx, ey + ry]
        if mood == "happy":                     # closed, smiling arcs
            d.arc([ex - rx, ey - ry * 0.6, ex + rx, ey + ry * 1.1], 200, 340, fill=ink, width=int(lw * 0.9))
            continue
        if mood == "surprised":
            box = [ex - rx * 1.25, ey - ry * 1.3, ex + rx * 1.25, ey + ry * 1.3]
        d.ellipse(box, fill=white, outline=ink, width=int(lw * 0.55))
        lid = None
        if mood == "angry":                     # a lid cut down toward the middle
            inner = 1 if i == 0 else -1
            lid = [(ex - rx * 1.4, ey - ry * (1.4 if inner > 0 else 0.1)), (ex + rx * 1.4, ey - ry * (0.1 if inner > 0 else 1.4)),
                   (ex + rx * 1.4, ey - ry * 1.6), (ex - rx * 1.4, ey - ry * 1.6)]
        elif mood == "sad":                     # lids falling to the outside
            outer = -1 if i == 0 else 1
            lid = [(ex - rx * 1.4, ey - ry * (0.15 if outer < 0 else 1.2)), (ex + rx * 1.4, ey - ry * (1.2 if outer < 0 else 0.15)),
                   (ex + rx * 1.4, ey - ry * 1.6), (ex - rx * 1.4, ey - ry * 1.6)]
        elif mood == "smug":                    # half-closed, level
            lid = [(ex - rx * 1.4, ey + ry * 0.05), (ex + rx * 1.4, ey + ry * 0.05), (ex + rx * 1.4, ey - ry * 1.6), (ex - rx * 1.4, ey - ry * 1.6)]
        if lid:
            mask = Image.new("L", (S, S), 0)
            ImageDraw.Draw(mask).polygon(lid, fill=255)
            eye = Image.new("L", (S, S), 0)
            ImageDraw.Draw(eye).ellipse([box[0] - lw, box[1] - lw, box[2] + lw, box[3] + lw], fill=255)
            cut = Image.fromarray(np.minimum(np.asarray(mask), np.asarray(eye)))
            out.paste(tex.resize((S, S)).point(lambda v: int(v * 0.7)), (0, 0), cut)
            d = ImageDraw.Draw(out)
            pts = lid[:2]
            d.line(pts, fill=ink, width=int(lw * 0.7))
            d.ellipse(box, outline=ink, width=int(lw * 0.55))
    return out.resize((D_, D_), Image.LANCZOS)


# Flags the pages do not draw, so the Shorts draw their own (inferred designs, never US or Canadian
# costumes): the secession's eleven stars on a green hoist; Zagrosia's peaks between two red bands.
FLAG_SVG = {
    "isa": ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 200"><rect width="300" height="200" fill="#9e3b30"/>'
            '<rect y="84" width="300" height="32" fill="#f4efe6"/><rect width="104" height="200" fill="#1f5a3a"/>{stars}'
            '<rect width="300" height="200" fill="none" stroke="#000" stroke-opacity=".35" stroke-width="4"/></svg>'),
    "zagrosia": ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 200"><rect width="300" height="200" fill="#f4efe6"/>'
                 '<rect width="300" height="56" fill="#c9524a"/><rect y="144" width="300" height="56" fill="#c9524a"/>'
                 '<path d="M70,132 L118,74 L140,100 L166,62 L230,132 Z" fill="#2f5d46"/><path d="M166,62 L178,78 L170,76 L160,84 L154,77 Z" fill="#fff"/>'
                 '<rect width="300" height="200" fill="none" stroke="#000" stroke-opacity=".35" stroke-width="4"/></svg>'),
}


def _star(cx, cy, r):
    pts = []
    for k in range(10):
        a = -math.pi / 2 + k * math.pi / 5
        rr = r if k % 2 == 0 else r * 0.42
        pts.append(f"{cx + rr * math.cos(a):.1f},{cy + rr * math.sin(a):.1f}")
    return f'<polygon points="{" ".join(pts)}" fill="#fff"/>'


def flag_img(cfg, data, pid, width=600) -> Image.Image:
    if pid in FLAG_SVG:
        stars = "".join(_star(52 + 34 * math.cos(2 * math.pi * k / 11 - math.pi / 2), 100 + 34 * math.sin(2 * math.pi * k / 11 - math.pi / 2), 9)
                        for k in range(11))
        return assets.rasterise(FLAG_SVG[pid].replace("{stars}", stars), width)
    return assets.flag(cfg, data.polity[pid], width)


def build_balls(cfg, data, used: set, out: pathlib.Path) -> dict:
    rows = {r["id"]: r for r in D.read_csv(paths(cfg).data / "countryballs.csv")}
    res = {}
    for bid in sorted(used):
        r = rows[bid]
        flag = flag_img(cfg, data, r["flag"], 600)
        imgs = {}
        for mood in MOODS:
            name = f"ball_{bid}_{mood}_v{VERSION}.png"
            if not (out / "assets" / name).exists():
                ball(flag, 300, mood).save(out / "assets" / name)
            imgs[mood] = f"assets/{name}"
        res[bid] = {"img": imgs, "name": r["name"], "name_ar": r["name_ar"],
                    "lines_en": r["lines_en"].split("|"), "lines_ar": r["lines_ar"].split("|")}
    return res


# -- the composition -------------------------------------------------------------------------

def compose(sid: int, cfg_path="config/project.yaml", log=print) -> pathlib.Path:
    cfg = load_config(cfg_path)
    spec, raw = spec_for(cfg, sid)
    data = D.load(cfg)
    out = out_dir(cfg, sid) / "hf"
    (out / "assets").mkdir(parents=True, exist_ok=True)
    plate = Plate(cfg, spec)
    log(f"Short {sid}: {spec['title']}")
    srcs = build_plates(cfg, data, spec, plate, out, log)
    track = spec["map_track"]
    hook_map = track[0][1]
    globe = build_globe(cfg, spec, plate, out / srcs[hook_map], out, log)
    balls = build_balls(cfg, data, {b["id"] for b in spec.get("balls", [])}, out)
    flags = {}
    for side in SIDE:
        name = f"flag_{side}_v{VERSION}.png"
        flag_img(cfg, data, side, 300).save(out / "assets" / name)
        flags[side] = f"assets/{name}"

    k_screen = int(spec["H"]) / KM_FULL                   # screen px per km at zoom 1
    cam = []
    for t, lon, lat, z, rot in spec["camera"]:
        c = plate.px(lon, lat)
        cam.append([t, c[0], c[1], k_screen * z / (plate.k * 1000), math.radians(rot)])

    armies = []
    for a in spec.get("armies", []):
        armies.append({**a, "path": plate.path(a["path"]), "move": a.get("move", [[0, 0]]),
                       "ar": _unit_ar(cfg, a["unit"])})
    Dd = {
        "id": sid, "title": spec["title"], "W": int(spec["W"]), "H": int(spec["H"]), "fps": int(spec["fps"]),
        "duration": float(spec["duration"]), "skin": spec.get("skin", "victorian"), "war": spec.get("war", ""),
        "plate": {"w": plate.w, "h": plate.h, "src": srcs, "ocean": cfg["style"]["ocean"]},
        "track": track, "camera": cam, "clock": spec["clock"], "globe": globe,
        "hook": {k: v for k, v in spec["hook"].items() if k != "globe"},
        "hud": spec.get("hud", {}), "captions": spec.get("captions", []), "lower": spec.get("lower", []),
        "armies": armies,
        "arrows": [{**a, "path": plate.path(a["path"])} for a in spec.get("arrows", [])],
        "blockade": {**spec["blockade"], "ships": plate.path(spec["blockade"]["ships"])} if spec.get("blockade") else None,
        "battles": [{**b, "at": plate.px(*b["at"])} for b in spec.get("battles", [])],
        "ledger": spec.get("ledger", {}), "stamp": spec.get("stamp"), "cost": spec.get("cost"),
        "balls": spec.get("balls", []), "cast": balls, "flags": flags, "sides": SIDE,
        "end": {**spec.get("end", {}), **spec.get("end_card", {})},
    }
    (out / "data.js").write_text("window.DATA = " + json.dumps(Dd, ensure_ascii=False, separators=(",", ":")) + ";\n",
                                 encoding="utf8")
    for f in ENGINE.iterdir():
        if f.is_file() and f.name != "index.template.html":
            shutil.copy2(f, out / f.name)
    cache = paths(cfg).root / "cache" / "solms"
    for sub in ("fonts", "vendor"):
        (out / sub).mkdir(exist_ok=True)
        for f in (cache / sub).iterdir():
            if not (out / sub / f.name).exists():
                shutil.copy2(f, out / sub / f.name)
    if not (out / "vendor" / "gsap.min.js").exists():
        raise SystemExit("no gsap in cache/solms/vendor: run `python solms.py compose 1` once to fetch it")
    music = build_score(Dd, out / "assets", log)
    clip = ""
    if globe:
        clip = (f'  <video class="clip" id="globe" data-start="{globe["t0"]:.3f}" data-duration="{globe["t1"] - globe["t0"]:.3f}" '
                f'src="{globe["src"]}" muted playsinline></video>')
    audio = f'  <audio data-start="0" data-duration="{Dd["duration"]:.3f}" data-volume="1" src="assets/{music.name}"></audio>'
    html = (ENGINE / "index.template.html").read_text(encoding="utf8")
    for k, v in {"{{TITLE}}": Dd["title"], "{{SKIN}}": Dd["skin"], "{{W}}": str(Dd["W"]), "{{H}}": str(Dd["H"]),
                 "{{DUR}}": f'{Dd["duration"]:.3f}', "{{CLIPS}}": clip, "{{AUDIO}}": audio}.items():
        html = html.replace(k, v)
    (out / "index.html").write_text(html, encoding="utf8")
    log(f"  composition: {out / 'index.html'}")
    return out


def _unit_ar(cfg, unit):
    for r in D.read_csv(paths(cfg).data / "armies.csv"):
        if r["unit"] == unit:
            return r.get("unit_ar", "")
    return ""


# -- the soundtrack ----------------------------------------------------------------------------

def cues(Dd) -> list[tuple[float, str, float, float]]:
    out = [(0.0, "globe_turn", 0, 0.8), (0.15, "logo_hit", 0, 0.9), (Dd["hook"]["t1"] - 1.0, "dive", 0, 1.0)]
    track = Dd["track"]
    for t, _k in track[1:]:
        out.append((t, "era", 0, 0.8))                       # a sound on every border change
    for c in Dd["captions"]:
        out.append((c["t"], "text", 0, 0.8))
    for l in Dd["lower"]:
        out.append((l["t"], "panel_in", 0.2, 0.6))
    for a in Dd["armies"]:
        out.append((a["t0"], "pop", -0.3 if a["side"] == "usa" else 0.3, 0.6))
    for a in Dd["arrows"]:
        out.append((a["t0"], "march", -0.2, 0.9 if a.get("big") else 0.6))
    for b in Dd["battles"]:
        out += [(b["t"], "battle", 0, 1.0), (b["t"] + 1.1, "elected", 0.2, 0.8)]   # a bright bell on each result
    for b in Dd["balls"]:
        out.append((b["t"], "pop", 0.3, 0.5))
    if Dd.get("stamp"):
        out.append((Dd["stamp"]["t"], "shine", 0.1, 0.9))
    if Dd.get("cost"):
        out.append((Dd["cost"]["t0"], "close_hit", 0, 0.7))
    if Dd["hud"]:
        out.append((Dd["hud"]["t0"], "panel_in", 0, 0.9))
    out += [(Dd["end"]["t0"], "end", 0, 0.9), (Dd["end"]["t0"] + 0.3, "shine", 0, 0.8)]
    return sorted(out)


def build_score(Dd, dst: pathlib.Path, log=print) -> pathlib.Path:
    """Major-key and heroic: a driving band to the surrender, a hymn under the cost, a bright end."""
    from . import audio as A
    sys.path.insert(0, str(paths(load_config()).root / "solms"))
    from cgsolms.score import Score
    T = Dd["duration"] + 0.8
    sig = hashlib.sha1(json.dumps([cues(Dd), T, VERSION]).encode()).hexdigest()[:8]
    name = f"short{Dd['id']}_score_{sig}.wav"
    if (dst / name).exists():
        return dst / name
    music, sfx = A.Bus(T), A.Bus(T)
    sc = Score(music, seed=1861)
    cost = Dd.get("cost") or {"t0": Dd["end"]["t0"], "t1": Dd["end"]["t0"]}
    heroic = dict(scale=A.MAJOR, root=50, tempo=120, chords=[0, 4, 5, 3], bars=1, pad=0.45, brass=0.6, ostinato=0.6,
                  taiko=0.6, frame=0.5, snare=0.4, bass=0.6, timpani=0.5, gain=0.95)
    hymn = dict(scale=A.MAJOR, root=50, tempo=72, chords=[5, 3, 0, 4], bars=1, pad=0.6, choir=0.6, harp=0.4, bass=0.35, gain=1.15)
    sc.section(heroic, 0.0, cost["t0"] + 0.4)
    sc.section(hymn, cost["t0"], cost["t1"] + 0.3)
    A.end_music(music, Dd["end"]["t0"], T - Dd["end"]["t0"])
    for b in Dd["battles"]:
        A.swell(music, b["t"], dur=1.4, level=0.5, seed=int(b["t"] * 10))
    bank = A.sfx_bank()
    for t, nm, pan, g in cues(Dd):
        sig_ = bank[nm]
        gain, send = A.SFX.get(nm, (0.4, 0.3))
        sfx.add(max(0.0, t), sig_, gain=gain * g, send=send)
    ir = A.impulse(2.6)
    m = music.dry + A.convolve(music.wet, ir) * 0.3
    s = sfx.dry + A.convolve(sfx.wet, ir) * 0.22
    mix = m * 0.85 + s
    lu = A.loudness(mix)
    mix *= 10 ** ((-14.0 - lu) / 20)                     # Shorts sit a little louder than the long cut
    mix *= A.limit_gain(mix, ceiling=10 ** (-1.2 / 20))
    peak = 20 * math.log10(float(np.max(np.abs(mix))) + 1e-9)
    A.write_wav(dst / name, mix)
    log(f"  soundtrack: {A.loudness(mix):.1f} LUFS, peak {peak:.1f} dBFS, {mix.shape[1] / A.SR:.1f} s")
    return dst / name


# -- stills, render, upload kit ------------------------------------------------------------------

def stills(sid: int, times, cfg_path="config/project.yaml", log=print) -> list[pathlib.Path]:
    from playwright.sync_api import sync_playwright
    sys.path.insert(0, str(paths(load_config(cfg_path)).root / "solms"))
    from cgsolms.render import serve
    cfg = load_config(cfg_path)
    hf = out_dir(cfg, sid) / "hf"
    dst = out_dir(cfg, sid) / "stills"
    dst.mkdir(parents=True, exist_ok=True)
    Dd = json.loads((hf / "data.js").read_text(encoding="utf8")[len("window.DATA = "):].rstrip().rstrip(";"))
    res = []
    with serve(hf) as base, sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        pg = b.new_page(viewport={"width": Dd["W"], "height": Dd["H"]})
        errs = []
        pg.on("console", lambda m: errs.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        pg.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
        pg.goto(base + "/index.html")
        pg.wait_for_function("window.__render !== undefined", timeout=120000)
        for t in times:
            pg.evaluate(f"window.__render({t})")
            pg.evaluate("""async () => { const v = document.getElementById('globe'); if (!v) return;
                const t = window.__lastT; if (t < +v.dataset.start || t > +v.dataset.start + +v.dataset.duration) return;
                await new Promise(r => { const done = () => r(); v.addEventListener('seeked', done, {once: true});
                v.currentTime = t - +v.dataset.start; setTimeout(done, 1500); }); }""")
            pg.wait_for_timeout(150)
            path = dst / f"short{sid}_{t:06.2f}.png"
            pg.screenshot(path=str(path))
            res.append(path)
        b.close()
    for e in errs[:20]:
        log("  " + e)
    log(f"  {len(res)} stills in {dst}")
    return res


def render(sid: int, t0=None, t1=None, quality="looks", workers=4, cfg_path="config/project.yaml", log=print) -> pathlib.Path:
    cfg = load_config(cfg_path)
    sys.path.insert(0, str(paths(cfg).root / "solms"))
    from cgsolms import render as SR
    hf = out_dir(cfg, sid) / "hf"
    import os
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join(SR.FFMPEG_DIRS + [env.get("PATH", "")])
    stamp = time.strftime("%Y%m%d-%H%M%S")
    comp = None
    if t0 is not None or t1 is not None:
        comp = _segment(hf, t0 or 0.0, t1)
    dst = paths(cfg).root / "output" / "shorts" / str(sid) / (f"short{sid}_{stamp}.mp4" if comp is None
                                                                else f"short{sid}_slice_{int(t0 or 0)}-{int(t1 or 0)}_{stamp}.mp4")
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["npx", "-y", "hyperframes", "render", "-o", str(dst), "-q", quality, "-w", str(workers), "-f", "30"]
    if comp:
        cmd += ["-c", comp]
    log("  " + " ".join(cmd))
    subprocess.run(" ".join(f'"{c}"' if " " in c else c for c in cmd), cwd=hf, env=env, shell=True, check=True)
    log(f"  rendered: {dst}")
    return dst


def _segment(hf, t0, t1):
    import re
    html = (hf / "index.html").read_text(encoding="utf8")
    Dd = json.loads((hf / "data.js").read_text(encoding="utf8")[len("window.DATA = "):].rstrip().rstrip(";"))
    t1 = t1 or Dd["duration"]
    dur = t1 - t0
    html = re.sub(r'(id="root"[^>]*data-duration=")[^"]+"', lambda m: m.group(1) + f'{dur:.3f}"', html)
    g = Dd.get("globe")
    if g and t0 >= g["t1"]:
        html = re.sub(r'<video[^>]*id="globe"[^>]*></video>', "", html)
    elif g:
        html = re.sub(r'(id="globe" data-start=")[^"]+(" data-duration=")[^"]+"',
                      lambda m: f'{m.group(1)}0{m.group(2)}{g["t1"] - t0:.3f}" data-media-start="{t0:.3f}"', html)
    html = re.sub(r'(<audio data-start="0" data-duration=")[^"]+"', lambda m: m.group(1) + f'{dur:.3f}" data-media-start="{t0:.3f}"', html)
    html = html.replace('<script src="data.js"></script>', f'<script>window.SEG_T0={t0};window.SEG_DUR={dur};</script>\n<script src="data.js"></script>')
    name = f"seg_{int(t0 * 10):04d}_{int(t1 * 10):04d}.html"
    (hf / name).write_text(html, encoding="utf8")
    return name


def upload_kit(sid: int, video: pathlib.Path | None, cfg_path="config/project.yaml", log=print) -> pathlib.Path:
    cfg = load_config(cfg_path)
    spec, _ = spec_for(cfg, sid)
    pub = cfg.get("publish", {})
    dst = paths(cfg).root / "output" / "shorts" / str(sid)
    dst.mkdir(parents=True, exist_ok=True)

    def ts(s):
        ms = int(round(s * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    srt = []
    for i, c in enumerate(spec.get("captions", []), 1):
        srt.append(f"{i}\n{ts(c['t'])} --> {ts(c['t'] + c['d'])}\n{c['text']}\n")
    (dst / f"short{sid}.srt").write_text("\n".join(srt), encoding="utf8")
    tags = ["#Shorts", "#AlternateHistory", "#Mapping", "#Controglobe"]
    kit = f"""# Short {sid}: upload kit

**Title** ({len(spec['title'])} chars): {spec['title']}

**Description**

{spec['hook']['title'].title()}. In Controglobe's Arabia, eleven states secede as the Islamic States of Arabia, and four
years of war on three fronts end at Wadi Hanifa on 9 April 1865.

The whole history, every year from 500 BCE to 2026: {pub.get('site', '')}
Join the Discord: https://{spec.get('end_card', {}).get('discord', pub.get('community', ''))}

Army strengths on screen are illustrative (scaled from the war this one carries); dates, places and the toll are the
encyclopedia's canon.

{' '.join(tags)}

**Pinned comment**: Which front would you have defended in 1861: the Red Sea coast, the Najd or the Gulf?

**Thumbnail frame**: the frame at 0.6 s (the globe with the split map and the title), or 21.8 s (the surrender popup).

**Exports**: one 1080x1920 H.264 master serves YouTube Shorts, TikTok and Instagram Reels (all 9:16, under 60 s).

**Video**: {video.name if video else '(not rendered yet)'}
**Captions**: short{sid}.srt
"""
    (dst / f"short{sid}_upload.md").write_text(kit, encoding="utf8")
    log(f"  upload kit: {dst / f'short{sid}_upload.md'}")
    return dst
