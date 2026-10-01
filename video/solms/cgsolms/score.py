"""The phase's score and effects, made in code (nothing licensed, nothing that can be claimed),
and uplifting by design: major, mixolydian and lydian colours, open fifths, rising pentatonic
lines, drums that drive rather than menace, the wars heroic and never eerie.

    python solms.py score 1   ->  hf/assets/score_mix.wav (and the music and effects stems, for Resolve)

It builds on the Arabia video's synthesiser (cgvideo/audio.py: wavetable pads, plucked strings,
drums, a hall, a limiter, a loudness meter) with a band per scene and effects on the composition's
own cues: the title, the cards, every battle, siege, arrow and bubble. The user's own music in
video/assets/audio/solms/music.(wav|mp3|flac) replaces the score; an effect file named after a cue
replaces that effect.
"""

from __future__ import annotations

import json
import math

import numpy as np

from cgvideo import audio as A
from cgvideo.audio import SR, Bus, MAJOR, DORIAN, degree, triad, envelope, osc, pluck, pan_gains, smooth

from . import frame as F

MIXO = [0, 2, 4, 5, 7, 9, 10]
LYDIAN = [0, 2, 4, 6, 7, 9, 11]
PENTA = [0, 2, 4, 7, 9]

# a band for each kind of scene; roots are MIDI (50 = D3)
BANDS = {
    "dawn":     dict(scale=LYDIAN, root=50, tempo=72, chords=[0, 1, 0, 4], bars=2, pad=0.8, choir=0.5, bells=0.5, gain=1.1),
    "gentle":   dict(scale=MAJOR, root=50, tempo=84, chords=[0, 4, 5, 3], bars=2, pad=0.55, harp=0.7, flute=0.55, bass=0.4, gain=1.15),
    "travel":   dict(scale=MAJOR, root=50, tempo=96, chords=[0, 4, 5, 3], bars=2, pad=0.45, marimba=0.65, flute=0.6,
                     frame=0.45, shaker=0.3, bass=0.5, gain=1.0),
    "pastoral": dict(scale=MAJOR, root=55, tempo=88, chords=[0, 3, 4, 0, 5, 3, 1, 4], bars=1, pad=0.5, harp=0.6, flute=0.65,
                     marimba=0.35, bass=0.45, shaker=0.2, gain=1.05),
    "heroic":   dict(scale=MIXO, root=52, tempo=116, chords=[0, 6, 3, 0], bars=2, pad=0.4, brass=0.6, ostinato=0.55,
                     taiko=0.55, frame=0.5, snare=0.35, bass=0.6, timpani=0.5, gain=0.9),
    "heroic2":  dict(scale=MIXO, root=50, tempo=108, chords=[0, 3, 6, 4], bars=2, pad=0.45, brass=0.55, ostinato=0.5,
                     taiko=0.5, frame=0.45, bass=0.55, choir=0.3, timpani=0.45, gain=0.92),
    "solemn":   dict(scale=MAJOR, root=50, tempo=66, chords=[5, 3, 0, 4], bars=2, pad=0.6, choir=0.55, harp=0.35,
                     bells=0.3, bass=0.35, gain=1.2),
    "finale":   dict(scale=MAJOR, root=50, tempo=92, chords=[0, 4, 5, 3, 0, 4, 3, 4], bars=1, pad=0.5, brass=0.55, choir=0.5,
                     harp=0.5, bass=0.55, timpani=0.55, frame=0.4, bells=0.35, flute=0.4, gain=0.95),
}
SCENE_BAND = {"open": "dawn", "premise": "gentle", "land": "gentle", "peoples": "travel", "road": "travel",
              "war1": "heroic", "peace": "pastoral", "war2": "heroic2", "fires": "pastoral", "war3": "heroic",
              "clients": "travel", "war4": "heroic2", "burn": "solemn", "results": "finale", "end": "finale"}


class Score(A.Score):
    def flute(self, note, t, dur, level, send=0.55):
        """A cedar flute: a clean tone, a little breath, vibrato that blooms."""
        n = int((dur + 0.3) * SR)
        env = envelope(n, 0.08, 0.3)
        vib = 0.0035 * smooth(np.arange(n) / (0.4 * SR))
        f = A.hz(note) * (1 + vib * np.sin(2 * np.pi * 5.6 * np.arange(n) / SR))
        ph = np.cumsum(f) / SR
        tone = np.sin(2 * np.pi * ph) + 0.12 * np.sin(4 * np.pi * ph) + 0.05 * np.sin(6 * np.pi * ph)
        breath = A.fft_filter(A.noise(n, int(note * 31)), A.band(A.hz(note), A.hz(note) * 4)) * 0.12
        self.bus.add(t, (tone + breath) * env, gain=level * 0.09, pan=0.12, send=send)

    def marimba(self, note, t, level, pan=0.0, send=0.25):
        n = int(0.9 * SR)
        tt = np.arange(n) / SR
        f = A.hz(note)
        s = (np.sin(2 * np.pi * f * tt) * np.exp(-tt / 0.32) + 0.35 * np.sin(2 * np.pi * f * 3.93 * tt) * np.exp(-tt / 0.05)
             + 0.12 * np.sin(2 * np.pi * f * 10.2 * tt) * np.exp(-tt / 0.012))
        s *= smooth(tt / 0.002)
        self.bus.add(t, s.astype(np.float32), gain=level * 0.17, pan=pan, send=send)

    def bells(self, note, t, level, send=0.6):
        self.bus.add(t, A.bell(note, 2.6, 0.8), gain=level * 0.12, pan=self.rng.uniform(-.5, .5), send=send)

    def section(self, b, t0, t1, fade_in=1.2):
        scale, root, tempo = b["scale"], b["root"], b["tempo"]
        beat = 60.0 / tempo
        bar = 4 * beat
        chords, bpc = b["chords"], b["bars"]
        length = t1 - t0
        if length <= 0.5:
            return
        R = self.rng
        gain = b.get("gain", 1.0)

        def lvl(t, base):
            k = min(1.0, (t - t0) / fade_in + 0.1) * min(1.0, (t1 - t) / (beat * 1.5))
            return base * max(0.0, k) * gain

        nbars = int(math.ceil(length / bar))
        mel_last = 4
        for bi in range(nbars):
            tb = t0 + bi * bar
            if tb >= t1 - 0.05:
                break
            ci = chords[(bi // bpc) % len(chords)]
            chord = triad(scale, root, ci)
            first = bi % bpc == 0
            span = min(bar * bpc, t1 - tb)
            if first:
                if b.get("pad"):
                    self.pad([n + 12 for n in chord] + [chord[0]], tb, span, lvl(tb, b["pad"]), kind="warm", attack=0.8)
                if b.get("choir"):
                    self.choir([chord[0] + 12, chord[1] + 12, chord[2] + 12], tb, span, lvl(tb, b["choir"]))
                if b.get("brass"):
                    self.brass([chord[0], chord[2], chord[0] + 12], tb, span * 0.9, lvl(tb, b["brass"]))
                if b.get("timpani"):
                    self.hit("timpani", tb, lvl(tb, b["timpani"]) * 0.5, send=0.4)
            for q in range(16):
                t = tb + q * beat / 4
                if t >= t1 - 0.05:
                    break
                if b.get("harp") and q % 2 == 0:
                    arp = [0, 2, 4, 7, 9, 7, 4, 2]
                    self.string(degree(scale, root, ci + arp[q // 2], 1), t, lvl(t, b["harp"]) * 0.8, bright=0.4, t60=2.2,
                                pan=0.3, send=0.45)
                if b.get("marimba") and q % 2 == 0 and (q % 4 == 0 or R.random() < 0.6):
                    pat = [0, 4, 2, 4, 7, 4, 2, 4]
                    self.marimba(degree(scale, root, ci + pat[q // 2], 1), t, lvl(t, b["marimba"]) * (1 if q % 8 == 0 else .7),
                                 pan=-0.25)
                if b.get("ostinato") and q % 2 == 0:
                    pat = [0, 0, 4, 0, 7, 0, 4, 2]
                    note = degree(scale, root, ci + pat[q // 2], 0)
                    n = int(beat / 2 * 0.75 * SR)
                    s = (osc("warm", note, n) + 0.5 * osc("warm", note + 12, n, cents=4)) * envelope(n, 0.006, 0.06, curve=1.0)
                    self.bus.add(t, s, gain=lvl(t, b["ostinato"]) * 0.08 * (1.25 if q % 8 == 0 else 1.0), pan=-0.3, send=0.25)
                if b.get("bass") and q % 4 == 0 and (q in (0, 8) or R.random() < 0.4):
                    self.bass(degree(scale, root, ci, -1), t, beat * 1.6, lvl(t, b["bass"]))
                if b.get("frame") and q in (0, 6, 8, 12):
                    self.hit("frame", t, lvl(t, b["frame"]) * (0.75 if q in (0, 8) else 0.45), send=0.35)
                if b.get("shaker"):
                    self.hit("shaker", t, lvl(t, b["shaker"]) * (0.12 if q % 4 else 0.2), pan=0.4, send=0.1)
                if b.get("taiko") and q in (0, 3, 8, 11) and (q in (0, 8) or bi % 2 == 1):
                    self.hit("taiko", t, lvl(t, b["taiko"]) * (0.7 if q in (0, 8) else 0.45), send=0.45)
                if b.get("snare") and q in (4, 12):
                    self.hit("snare", t, lvl(t, b["snare"]) * 0.4, pan=-0.1)
                if b.get("bells") and q == 0 and bi % 2 == 0:
                    self.bells(chord[2] + 24, t + beat * 2, lvl(t, b["bells"]))
            # a rising pentatonic line, two bars at a time, landing on the chord
            if b.get("flute") and bi % 2 == 0:
                tt = tb + beat * R.choice([0.0, 0.5])
                steps = R.choice([[0, 1, 2, 4], [2, 3, 4, 3], [1, 2, 4, 5], [4, 3, 4, 6], [0, 2, 3, 4]])
                for k, st in enumerate(steps):
                    d = beat * (1.0 if k < len(steps) - 1 else 3.0)
                    if tt + d > t1 - 0.3:
                        break
                    o, i = divmod(st + mel_last // 2, 5)
                    note = root + 12 + PENTA[i] + 12 * o + (ci % 7 in (3, 4)) * 0
                    self.flute(note, tt, d, lvl(tt, b["flute"]))
                    tt += d
                mel_last = (mel_last + R.integers(-1, 3)) % 8


def cues(D):
    """(seconds, effect, pan, gain) from the composition's data."""
    out = []
    for c in D["cards"]:
        k = c["kind"]
        if k == "title":
            out += [(c["t"] - 0.3, "logo_rise", 0, 0.8), (c["t"] + 0.5, "logo_hit", 0, 0.9), (c["t"] + 0.7, "shine", .2, 1)]
        elif k == "war":
            out += [(c["t"] - 0.25, "era", 0, 1.0)]
        elif k in ("chapter", "premise"):
            out += [(c["t"], "text", 0, 1.0)]
        elif k in ("results", "phase_results"):
            out += [(c["t"], "panel_in", 0.3, 1.0)]
        elif k == "discord":
            out += [(c["t"], "shine", 0, 1.0), (c["t"] + 0.2, "elected", 0, 0.9)]
        elif k == "endcard":
            out += [(c["t"], "end", 0, 1.0)]
        elif k == "lineup":
            out += [(c["t"] + i * 0.12, "pop", (i - 5) / 6, 0.7) for i in range(10)]
    for ln in D["lines"]:
        out.append((ln["t"], "pop", -0.4, 0.55))
    for it in D["intros"]:
        out.append((it["t"], "panel_in", 0.5, 0.8))
    for v in D["vignettes"]:
        out.append((v["t"], "wipe", -0.5, 0.7))
    for w in D["wars"].values():
        for b in w["battles"]:
            out.append((b["t"], "battle", 0, 1.0))
            if b.get("general_falls"):
                out.append((b["t"] + 1.0, "major", 0, 0.9))
        for s in w["sieges"]:
            out.append((s["t0"], "march", 0.2, 0.9))
        for a in w["arrows"]:
            out.append((a["t0"], "march", -0.2, 0.6))
        for k in ("headgate", "viceroy_dies", "capture"):
            if w.get(k):
                out.append((w[k]["t"], "major", 0, 0.9))
    for sc in D["scenes"]:
        if sc.get("clip"):
            c = sc["clip"]
            out += [(c["t0"], "globe_turn", 0, 0.9)]
            if sc["id"] == "open":
                out += [(c["t1"] - 2.2, "dive", 0, 1.0)]
    for l in D["lower"]:
        out.append((l["t"], "panel_in", 0.0, 0.7))
    return sorted(out)


def build(n: int, log=print):
    hf = F.build_dir(n) / "hf"
    raw = (hf / "data.js").read_text(encoding="utf8")
    D = json.loads(raw[len("window.DATA = "):].rstrip().rstrip(";"))
    T = D["duration"] + 1.0
    music_bus, sfx_bus = Bus(T), Bus(T)
    user = None
    base = F.VIDEO / "assets" / "audio" / "solms"
    for ext in (".wav", ".flac", ".mp3", ".m4a"):
        if (base / f"music{ext}").exists():
            user = base / f"music{ext}"
    if user:
        x = A._fit(A.read_audio(user), music_bus.n)
        music_bus.dry[:, :x.shape[1]] += x
        log(f"  music: {user.name} (yours)")
    else:
        sc = Score(music_bus, seed=617)
        for s in D["scenes"]:
            band = BANDS[SCENE_BAND.get(s["id"], "gentle")]
            sc.section(band, max(0.0, s["t0"] - 0.6), s["t1"] + 0.6)
        log(f"  score: {len(D['scenes'])} sections")
    bank = A.sfx_bank()
    cl = cues(D)
    for t, name, pan, g in cl:
        sig = bank.get(name)
        f = None
        for ext in (".wav", ".mp3"):
            if (base / "sfx" / f"{name}{ext}").exists():
                f = base / "sfx" / f"{name}{ext}"
        if f:
            sig = A.read_audio(f)
        if sig is None:
            continue
        gain, send = A.SFX.get(name, (0.4, 0.3))
        if sig.ndim == 2 and pan:
            l, r = pan_gains(pan)
            sig = np.stack([sig[0] * l * 1.41, sig[1] * r * 1.41])
        sfx_bus.add(max(0.0, t), sig, gain=gain * g, send=send)
    log(f"  effects: {len(cl)} cues")
    ir = A.impulse(3.0)
    music = music_bus.dry + A.convolve(music_bus.wet, ir) * 0.32
    sfx = sfx_bus.dry + A.convolve(sfx_bus.wet, ir) * 0.25
    del music_bus, sfx_bus
    # the music leans back under the effects (about 4 dB at most)
    blk = int(0.02 * SR)
    env = A.block_rms(sfx, blk)
    from scipy.ndimage import maximum_filter1d, uniform_filter1d
    env = uniform_filter1d(maximum_filter1d(env, 15), 25)
    duck = 1 - 0.37 * np.clip(env / (np.percentile(env[env > 0], 95) if (env > 0).any() else 1), 0, 1)
    music *= A.stretch(duck, blk, music.shape[1])
    mix = music + sfx
    target = -15.0
    lu = A.loudness(mix)
    g = 10 ** ((target - lu) / 20)
    mix *= g
    mix *= A.limit_gain(mix, ceiling=10 ** (-1.2 / 20))
    music *= g
    sfx *= g
    peak = 20 * math.log10(np.max(np.abs(mix)) + 1e-9)
    out = hf / "assets"
    A.write_wav(out / "score_mix.wav", mix)
    A.write_wav(out / "score_music.wav", np.clip(music, -1, 1))
    A.write_wav(out / "score_sfx.wav", np.clip(sfx, -1, 1))
    log(f"  soundtrack: {A.loudness(mix):.1f} LUFS, peak {peak:.1f} dBFS, {mix.shape[1] / SR:.1f} s -> {out / 'score_mix.wav'}")
    return out / "score_mix.wav"
