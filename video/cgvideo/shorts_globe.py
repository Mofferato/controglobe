"""The globe Shorts (engine: globe in config/shorts.yaml): the alternate world on a 3D globe, every era in
its own HUD skin (cgvideo/shorts_engine/globe.js, skins.css).

    python build.py shorts --id 3                 the composition: globe textures, borders, names, flags,
                                                  countryballs, the Blender hook, the score
    python build.py shorts --id 3 --stills 0.5 4 ...
    python build.py shorts --id 3 --render

The maps are the long cut's own years: cgvideo/world.py paints the mesh and the realms beyond it
(data/world/realms.yaml) as fills, and hands the engine the frontiers as vectors and the names as points.
The hook is a Blender (EEVEE) flight over the same world, from the Texas series' globe scene.
"""

from __future__ import annotations

import hashlib
import json
import math
import pathlib
import shutil
import subprocess
import sys

import numpy as np
import yaml

from . import world
from .config import paths
from .shorts import ENGINE, VERSION, build_balls, flag_img, out_dir


def _hex3(rgb):
    return "#%02x%02x%02x" % tuple(int(max(0, min(1, v)) * 255) for v in rgb)


def blender_clip(cfg, data, spec_b, seconds, out: pathlib.Path, name, log=print, W=1080, H=1920, fps=30):
    """A globe move rendered by Blender (EEVEE) over the alternate world of a year: the Texas series'
    globe scene (solms/cgsolms/blender.py) dressed in this world's texture."""
    sys.path.insert(0, str(paths(cfg).root / "solms"))
    from cgsolms import blender as B
    tex = world.texture(cfg, data, int(spec_b.get("year", 2026)), W=8192, log=log)
    bump = paths(cfg).build / "solms" / "globe" / "earth_height.png"
    if not bump.exists():
        bump = tex
    sig = hashlib.sha1(json.dumps([tex.name, spec_b, seconds, W, H, VERSION]).encode()).hexdigest()[:8]
    dst = out / "assets" / f"{name}_{sig}.mp4"
    if dst.exists():
        return dst
    frames_dir = paths(cfg).build / "shorts" / "blender" / f"{name}_{sig}"
    frames_dir.mkdir(parents=True, exist_ok=True)
    frames = int(round(seconds * fps))
    if len(list(frames_dir.glob("f_*.png"))) < frames:
        script = frames_dir / "cg_globe.py"
        script.write_text(B.BPY, encoding="utf8")
        args = {"w": W, "h": H, "fps": fps, "frames": frames, "out": str(frames_dir).replace("\\", "/"), "tex": str(tex),
                "bump": str(bump), "keys": spec_b["keys"], "sun": spec_b.get("sun", [30, 20]), "lens": spec_b.get("lens", 30)}
        log(f"  Blender: {name}, {frames} frames at {W}x{H}")
        pr = subprocess.run([B.BLENDER, "-b", "--factory-startup", "-P", str(script), "--", json.dumps(args)],
                            capture_output=True, text=True)
        if pr.returncode != 0 or len(list(frames_dir.glob("f_*.png"))) < frames:
            raise RuntimeError("Blender failed:\n" + "\n".join((pr.stdout + pr.stderr).splitlines()[-15:]))
    from .sequence import find_ffmpeg
    subprocess.run([find_ffmpeg(), "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(frames_dir / "f_%04d.png"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "15", "-preset", "slow", "-movflags", "+faststart", str(dst)],
                   check=True)
    return dst


def compose_globe(cfg, data, spec, sid, log=print) -> pathlib.Path:
    from .render import Scene
    out = out_dir(cfg, sid) / "hf"
    (out / "assets").mkdir(parents=True, exist_ok=True)
    log(f"Short {sid}: {spec['title']}")
    Wf = int(spec.get("fills_px", 4096))
    states = {}
    for key, year in spec["states"].items():
        f = world.fills(cfg, data, int(year), W=Wf, log=log)
        if not (out / "assets" / f.name).exists():
            shutil.copy2(f, out / "assets" / f.name)
        states[key] = {"year": int(year), "fills": f"assets/{f.name}", "borders": world.borders(cfg, data, int(year)),
                       "labels": world.labels(cfg, data, int(year))}
    world.base(cfg, 4096, log)
    bpath = paths(cfg).build / "world" / "base_4096.jpg"
    det = world.detail_base(cfg, log=log)
    for src in (bpath, det):
        if not (out / "assets" / src.name).exists():
            shutil.copy2(src, out / "assets" / src.name)
    scene = Scene(cfg, data)
    used = set()
    for a in spec.get("armies", []) + spec.get("arrows", []):
        used.add(a["polity"])
    for b in spec.get("battles", []):
        used |= {b["a"]["polity"], b["b"]["polity"]}
    for led in spec.get("ledgers", []):
        used |= {led[k]["polity"] for k in ("a", "b") if led.get(k)}
    for st in states.values():
        used |= {L["id"] for L in st["labels"]}
    pols = {pid: {"colour": _hex3(scene.fill.get(pid, (0.6, 0.6, 0.6)))} for pid in data.polity_ids}
    flags = {}
    for pid in sorted(used):
        if pid not in data.polity:
            continue
        name = f"flag_{pid}_v{VERSION}.png"
        if not (out / "assets" / name).exists():
            flag_img(cfg, data, pid, 300).save(out / "assets" / name)
        flags[pid] = f"assets/{name}"
    end_spec = dict(spec.get("end", {}))
    cast = build_balls(cfg, data, {b["id"] for b in spec.get("balls", [])} | set(end_spec.get("balls", [])), out)
    hook = dict(spec["hook"])
    clips = []
    if hook.get("blender"):
        try:
            mp4 = blender_clip(cfg, data, hook["blender"], float(hook["t1"]) + 0.4, out, "hook", log)
            clips.append({"src": f"assets/{mp4.name}", "t0": 0.0, "t1": float(hook["t1"]) + 0.3, "fade": 0.45})
        except Exception as e:                       # Blender missing or failed: the live globe opens instead
            log(f"  no Blender clip: {e}")
    hook.pop("blender", None)
    end_spec.pop("blender", None)
    defaults = yaml.safe_load((paths(cfg).root / "config" / "shorts.yaml").read_text(encoding="utf8")).get("defaults", {})
    end = {**defaults.get("end_card", {}), **end_spec}
    Dd = {
        "id": sid, "title": spec["title"], "W": 1080, "H": 1920, "fps": 30, "duration": float(spec["duration"]),
        "globe": {"base": f"assets/{bpath.name}", "detail": {"src": f"assets/{det.name}", "bbox": [-25, -15, 85, 72]}, "fov": 34},
        "states": states, "track": spec["track"], "camera": spec["camera"], "clock": spec["clock"], "eras": spec["eras"],
        "ledgers": spec.get("ledgers", []), "captions": spec.get("captions", []), "lower": spec.get("lower", []),
        "armies": spec.get("armies", []), "arrows": spec.get("arrows", []), "battles": spec.get("battles", []),
        "stamps": spec.get("stamps", []), "balls": spec.get("balls", []), "cast": cast, "flags": flags, "polities": pols,
        "hook": hook, "cost": spec.get("cost"), "end": end,
    }
    (out / "data.js").write_text("window.DATA = " + json.dumps(Dd, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf8")
    for f in ENGINE.iterdir():
        if f.is_file() and not f.name.endswith(".template.html"):
            shutil.copy2(f, out / f.name)
    cache = paths(cfg).root / "cache" / "solms"
    for sub in ("fonts", "vendor"):
        (out / sub).mkdir(exist_ok=True)
        for f in (cache / sub).iterdir():
            if not (out / sub / f.name).exists():
                shutil.copy2(f, out / sub / f.name)
    place_voices(cfg, spec, out / "assets", log)
    music = build_globe_score(cfg, Dd, out / "assets", log)
    clip_html = "\n".join(f'  <video class="clip" data-start="{c["t0"]:.3f}" data-duration="{c["t1"] - c["t0"]:.3f}" '
                          f'data-t0="{c["t0"]:.3f}" data-t1="{c["t1"]:.3f}" data-fade="{c["fade"]}" src="{c["src"]}" muted playsinline></video>'
                          for c in clips)
    audio = f'  <audio data-start="0" data-duration="{Dd["duration"]:.3f}" data-volume="1" src="assets/{music.name}"></audio>'
    html = (ENGINE / "index_globe.template.html").read_text(encoding="utf8")
    for k, v in {"{{TITLE}}": Dd["title"], "{{W}}": "1080", "{{H}}": "1920", "{{DUR}}": f'{Dd["duration"]:.3f}',
                 "{{CLIPS}}": clip_html, "{{AUDIO}}": audio}.items():
        html = html.replace(k, v)
    (out / "index.html").write_text(html, encoding="utf8")
    log(f"  composition: {out / 'index.html'}")
    return out


def place_voices(cfg, spec, assets: pathlib.Path, log=print):
    """The countryballs' ElevenLabs takes (build/shorts/voices/<voice>, named on each ball in shorts.yaml), sped
    up 1.3x with their pitch lifted a little, as countryballs talk, and laid at the ball's time:
    assets/vo_<t>_<id>.wav, which the score mixes in."""
    from .sequence import find_ffmpeg
    src = paths(cfg).build / "shorts" / "voices"
    want = set()
    for b in spec.get("balls", []):
        if not b.get("voice") or not (src / b["voice"]).exists():
            continue
        name = f"vo_{float(b['t']):05.2f}_{b['id']}.wav"
        want.add(name)
        if not (assets / name).exists():
            subprocess.run([find_ffmpeg(), "-loglevel", "error", "-y", "-i", str(src / b["voice"]), "-af",
                            "asetrate=44100*1.15,aresample=48000,atempo=1.13,loudnorm=I=-16:TP=-2", str(assets / name)], check=True)
    for f in assets.glob("vo_*.wav"):
        if f.name not in want:
            f.unlink()
    log(f"  voices: {len(want)}")


ERA_BANDS = {   # all major-key and heroic: the eras differ in tempo and in which voices lead
    "antiquity":   dict(tempo=104, chords=[0, 4, 5, 3], pad=0.5, brass=0.55, choir=0.4, harp=0.55, taiko=0.45, frame=0.4, bass=0.5, timpani=0.5),
    "medieval":    dict(tempo=96, chords=[0, 3, 4, 0], pad=0.55, choir=0.6, harp=0.5, flute=0.5, frame=0.45, bass=0.45, bells=0.4),
    "renaissance": dict(tempo=108, chords=[0, 4, 5, 3], pad=0.45, harp=0.6, flute=0.55, marimba=0.35, frame=0.4, bass=0.5, brass=0.4),
    "victorian":   dict(tempo=116, chords=[0, 4, 5, 3], pad=0.45, brass=0.65, ostinato=0.55, snare=0.4, taiko=0.4, bass=0.6, timpani=0.55),
    "worldwars":   dict(tempo=120, chords=[0, 5, 3, 4], pad=0.5, brass=0.6, ostinato=0.6, snare=0.5, taiko=0.55, bass=0.6, timpani=0.6),
    "coldwar":     dict(tempo=112, chords=[0, 5, 3, 4], pad=0.55, ostinato=0.65, marimba=0.3, frame=0.45, bass=0.6, bells=0.35),
    "modern":      dict(tempo=122, chords=[0, 4, 5, 3], pad=0.5, ostinato=0.55, brass=0.45, choir=0.35, taiko=0.5, frame=0.45, bass=0.6),
}


def globe_cues(Dd):
    out = [(0.0, "globe_turn", 0, 0.9), (0.12, "logo_hit", 0, 1.0), (Dd["hook"]["t1"] - 1.0, "dive", 0, 0.9)]
    for t, _k in Dd["track"][1:]:
        out.append((t, "major", 0, 0.55))                     # a sound on every border change
    for e in Dd["eras"]:
        out += [(e["t0"] - 0.05, "era", 0, 0.9), (e["t0"] + 0.1, "title", 0, 0.6)]
    for c in Dd["captions"]:
        out.append((c["t"], "text", 0, 0.7))
    for low in Dd["lower"]:
        out.append((low["t"], "panel_in", 0.2, 0.55))
    for a in Dd["armies"]:
        out.append((a["t0"], "pop", -0.3, 0.6))
    for a in Dd["arrows"]:
        out.append((a["t0"], "march", -0.2, 0.9 if a.get("big") or a.get("missile") else 0.6))
    for b in Dd["battles"]:
        out.append((b["t"], "close_hit" if b.get("nuke") else "battle", 0, 1.0))
        if not b.get("nopopup"):
            out.append((b["t"] + 1.05, "elected", 0.2, 0.8))  # a bright bell on each result
    for s in Dd["stamps"]:
        out.append((s["t"], "shine", 0.1, 0.8))
    for b in Dd["balls"]:
        out.append((b["t"], "pop", 0.3, 0.45))
    out += [(Dd["end"]["t0"], "end", 0, 0.9), (Dd["end"]["t0"] + 0.3, "shine", 0, 0.8)]
    return sorted(out)


def build_globe_score(cfg, Dd, dst: pathlib.Path, log=print) -> pathlib.Path:
    from . import audio as A
    sys.path.insert(0, str(paths(cfg).root / "solms"))
    from cgsolms.score import Score
    T = Dd["duration"] + 0.8
    vo = sorted(dst.glob("vo_*.mp3")) + sorted(dst.glob("vo_*.wav"))
    sig = hashlib.sha1(json.dumps([globe_cues(Dd), Dd["eras"], T, VERSION, [v.name for v in vo]]).encode()).hexdigest()[:8]
    name = f"short{Dd['id']}_score_{sig}.wav"
    if (dst / name).exists():
        return dst / name
    music, sfx = A.Bus(T), A.Bus(T)
    sc = Score(music, seed=2026)
    hero = dict(scale=A.MAJOR, root=50, bars=1, gain=0.95)
    sc.section({**hero, **ERA_BANDS["modern"]}, 0.0, Dd["hook"]["t1"] + 0.2)
    for e in Dd["eras"]:
        sc.section({**hero, **ERA_BANDS[e["skin"]]}, e["t0"] - 0.1, e["t1"] + 0.3, fade_in=0.4)
    A.end_music(music, Dd["end"]["t0"], T - Dd["end"]["t0"])
    for b in Dd["battles"]:
        A.swell(music, b["t"], dur=1.2, level=0.5, seed=int(b["t"] * 10))
    bank = A.sfx_bank()
    for t, nm, pan, g in globe_cues(Dd):
        gain, send = A.SFX.get(nm, (0.4, 0.3))
        sfx.add(max(0.0, t), bank[nm], gain=gain * g, send=send)
    # the countryballs' voices (ElevenLabs takes, assets/vo_<t>_<id>.mp3), when they have been made
    for v in vo:
        try:
            sfx.add(float(v.stem.split("_")[1]) + 0.1, A.read_audio(v), gain=0.9, send=0.12)
        except Exception as ex:
            log(f"  voice {v.name} skipped: {ex}")
    ir = A.impulse(2.6)
    m = music.dry + A.convolve(music.wet, ir) * 0.3
    s = sfx.dry + A.convolve(sfx.wet, ir) * 0.22
    mix = m * 0.8 + s
    mix *= 10 ** ((-14.0 - A.loudness(mix)) / 20)
    mix *= A.limit_gain(mix, ceiling=10 ** (-1.2 / 20))
    peak = 20 * math.log10(float(np.max(np.abs(mix))) + 1e-9)
    A.write_wav(dst / name, mix)
    log(f"  soundtrack: {A.loudness(mix):.1f} LUFS, peak {peak:.1f} dBFS, {mix.shape[1] / A.SR:.1f} s, {len(vo)} voices")
    return dst / name
