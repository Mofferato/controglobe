"""The soundtrack: a score under the whole cut and sound effects on its cues, made from code.

Nothing is downloaded or licensed. Every sound is synthesised here with numpy: band-limited
wavetable pads, brass and a formant choir; Karplus-Strong plucked strings (an oud, a harp, a
harpsichord, a soft piano); drums from pitched sines and shaped noise; whooshes shaped in the
frequency domain; a convolution reverb. So the music is the channel's own and safe on YouTube.

The score follows the cut (motion.structure and the timeline):
  opening   a shimmer under the logo, a drone under the premise, a swell as the globe turns
  eras      a section per era in its own mode, tempo and band, from a Hijaz drone and darbuka
            in antiquity to a march for the revolution, an ostinato for the industrial age,
            war drums, a cold-war synth arpeggio and a brighter close to the modern era
  close     a held chord that swells under the title and resolves as the finale comes in
  finale    a calm bed for the demographics, and a last chord on the end card
The effects fall on the cues (see cues()): the logo, the premise lines, the globe and its dive,
every era card, major events, battles, campaign arrows, election results, the close, the
finale's wipes and city bubbles, the end card.

Writes output/audio/soundtrack_<key>_{music,sfx,mix}.wav at 48 kHz: the music and the effects
as stems for the edit (the Resolve script lays them on tracks of their own), and their mix,
which goes inside the video file. The key changes whenever the cut, the cues or this code do.

Your own sound wins: assets/audio/music.(wav|mp3|flac|m4a) replaces the score (looped or
trimmed to the cut, faded out at the end); assets/audio/sfx/<cue>.(wav|mp3) replaces one kind
of effect (the kinds are the keys of SFX). `python build.py audio --elevenlabs` asks the
ElevenLabs sound-effects API for every effect that has no file yet (needs ELEVENLABS_API_KEY).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
import subprocess
import wave

import numpy as np

from .config import paths

SR = 48000
VERSION = 1

# -- basics ---------------------------------------------------------------------------

HIJAZ = [0, 1, 4, 5, 7, 8, 10]
PHRYGIAN = [0, 1, 3, 5, 7, 8, 10]
AEOLIAN = [0, 2, 3, 5, 7, 8, 10]
HARMONIC = [0, 2, 3, 5, 7, 8, 11]
DORIAN = [0, 2, 3, 5, 7, 9, 10]
MAJOR = [0, 2, 4, 5, 7, 9, 11]


def hz(note: float) -> float:
    return 440.0 * 2 ** ((note - 69) / 12)


def degree(scale, root, d, octave=0):
    """MIDI note of scale degree d (may run past 7) above root."""
    o, i = divmod(d, len(scale))
    return root + scale[i] + 12 * (o + octave)


def triad(scale, root, d):
    return [degree(scale, root, d + k) for k in (0, 2, 4)]


def smooth(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def fft_filter(x, gain_fn):
    """Filter a short signal by a zero-phase gain curve over frequency (Hz)."""
    n = len(x)
    size = 1 << (n - 1).bit_length()
    spec = np.fft.rfft(x, size)
    spec *= gain_fn(np.fft.rfftfreq(size, 1 / SR))
    return np.fft.irfft(spec, size)[:n]


def band(lo, hi, slope=2.0):
    def g(f):
        f = np.maximum(f, 1.0)
        a = 1 / (1 + (lo / f) ** (2 * slope)) if lo else 1.0
        b = 1 / (1 + (f / hi) ** (2 * slope)) if hi else 1.0
        return a * b
    return g


def pan_gains(p):
    """Equal-power pan, p in [-1, 1]."""
    a = (p + 1) * math.pi / 4
    return math.cos(a), math.sin(a)


class Bus:
    """A stereo buffer the length of the cut, with a reverb send."""

    def __init__(self, seconds):
        self.n = int(round(seconds * SR))
        self.dry = np.zeros((2, self.n), np.float32)
        self.wet = np.zeros((2, self.n), np.float32)

    def add(self, t, sig, gain=1.0, pan=0.0, send=0.0):
        """Mix sig (mono (n,) or stereo (2, n)) in at t seconds."""
        if gain == 0:
            return
        start = int(round(t * SR))
        sig = np.asarray(sig, np.float32)
        if sig.ndim == 1:
            l, r = pan_gains(pan)
            sig = np.stack([sig * l, sig * r])
        a, b = max(0, start), min(self.n, start + sig.shape[1])
        if b <= a:
            return
        part = sig[:, a - start:b - start] * gain
        self.dry[:, a:b] += part
        if send:
            self.wet[:, a:b] += part * send


# -- instruments -------------------------------------------------------------------------

class Tables:
    """Band-limited single-cycle wavetables per note and timbre, so nothing aliases."""
    N = 2048

    def __init__(self):
        self.cache = {}
        self.phase = 2 * np.pi * np.arange(self.N) / self.N

    def get(self, kind, note):
        key = (kind, int(round(note)))
        if key in self.cache:
            return self.cache[key]
        f0 = hz(key[1])
        K = max(1, min(90, int(17000 / f0)))
        k = np.arange(1, K + 1, dtype=np.float64)
        if kind == "saw":
            amp = 1 / k
        elif kind == "warm":
            amp = (1 / k) * np.exp(-(k - 1) / 9.0)
        elif kind == "dark":
            amp = (1 / k) * np.exp(-(k - 1) / 3.5)
        elif kind == "square":
            amp = np.where(k % 2 == 1, 1 / k, 0.0) * np.exp(-(k - 1) / 16.0)
        elif kind == "choir":   # the vowel "ah": harmonics weighted by three formants
            f = k * f0
            form = sum(a / (1 + ((f - c) / w) ** 2) for c, w, a in ((760, 90, 1.0), (1180, 110, 0.55), (2750, 170, 0.28)))
            amp = form * np.exp(-f / 5200)
        elif kind == "sine":
            amp = np.where(k == 1, 1.0, 0.0)
        else:
            raise ValueError(kind)
        table = (amp[:, None] * np.sin(np.outer(k, self.phase))).sum(0)
        table /= np.max(np.abs(table)) or 1
        self.cache[key] = table.astype(np.float32)
        return self.cache[key]


TAB = Tables()


def osc(kind, note, n, cents=0.0, vib=0.0, vib_rate=5.0, phase=0.0):
    table = TAB.get(kind, note)
    f = hz(note + cents / 100.0)
    t = np.arange(n) / SR
    inc = np.full(n, f / SR)
    if vib:
        inc *= 1 + vib * np.sin(2 * np.pi * vib_rate * t)
    ph = phase + np.cumsum(inc)
    idx = (ph % 1.0) * Tables.N
    i0 = idx.astype(np.int64)
    frac = (idx - i0).astype(np.float32)
    return table[i0 % Tables.N] * (1 - frac) + table[(i0 + 1) % Tables.N] * frac


def envelope(n, attack, release, hold=None, curve=2.0):
    """Rise over `attack` s, hold, fall over the last `release` s (all clipped to n)."""
    t = np.arange(n) / SR
    dur = n / SR
    a = smooth(t / max(attack, 1e-3))
    r = smooth((dur - t) / max(release, 1e-3))
    return (a * r) ** (curve / 2)


def pad_note(note, dur, kind="warm", voices=3, spread=9.0, attack=1.2, release=1.6, rng=None):
    """A soft ensemble note: detuned voices panned apart, slow in and out. Returns stereo."""
    rng = rng or np.random.default_rng(int(note * 7))
    n = int((dur + release) * SR)
    out = np.zeros((2, n), np.float32)
    env = envelope(n, attack, release)
    for v in range(voices):
        c = (v - (voices - 1) / 2) * spread
        p = (v - (voices - 1) / 2) / max(1, (voices - 1) / 2) * 0.6
        s = osc(kind, note, n, cents=c, vib=0.0015, vib_rate=4.2 + 0.7 * v, phase=rng.random()) * env
        l, r = pan_gains(p)
        out[0] += s * l
        out[1] += s * r
    return out / voices


def pluck(note, dur=1.6, bright=0.5, t60=1.6, seed=0, body=0.0):
    """Karplus-Strong string: a noise burst in a delay line that loses its highs each pass.
    bright shapes the pluck (soft thumb to hard plectrum); body adds a low wooden resonance."""
    rng = np.random.default_rng(seed)
    f0 = hz(note)
    N = max(2, int(round(SR / f0 - 0.5)))
    want = int(dur * SR)
    total = int(want * 1.03) + N + 2
    burst = rng.uniform(-1, 1, N)
    # soften the burst: a one-pole low-pass, harder for a dull pluck
    a = 0.15 + 0.8 * (1 - bright)
    for i in range(1, N):
        burst[i] = burst[i] * (1 - a) + burst[i - 1] * a
    burst -= burst.mean()
    y = np.zeros(total)
    y[:N] = burst
    g = 10 ** (-3 / (t60 * f0))       # loss per pass for the wanted decay
    k = 1
    while k * N < total:
        s0, s1 = k * N, min(total, (k + 1) * N)
        prev = y[s0 - N:s1 - N]
        prev2 = y[s0 - N - 1:s1 - N - 1] if s0 - N - 1 >= 0 else np.concatenate([[0.0], y[:s1 - N - 1]])
        y[s0:s1] = g * 0.5 * (prev + prev2)
        k += 1
    # the loop sounds at SR / (N + 0.5): read it back faster or slower to land on the exact note
    speed = f0 / (SR / (N + 0.5))
    y = np.interp(np.arange(want) * speed, np.arange(total), y) if abs(speed - 1) > 1e-4 else y[:want]
    if body:
        y = y + body * fft_filter(y, band(90, 420, 1.5))
    fade = np.ones(len(y))
    fade[-int(0.02 * SR):] = np.linspace(1, 0, int(0.02 * SR))
    y = y * fade
    return (y / (np.max(np.abs(y)) or 1)).astype(np.float32)


def noise(n, seed=0):
    return np.random.default_rng(seed).normal(0, 1, n).astype(np.float32)


def expdecay(n, tau, delay=0.0):
    t = np.arange(n) / SR
    return np.where(t < delay, 0.0, np.exp(-(t - delay) / tau)).astype(np.float32)


def sweep_sine(n, f_from, f_to, tau):
    """A sine whose pitch falls from f_from toward f_to with time constant tau."""
    t = np.arange(n) / SR
    f = f_to + (f_from - f_to) * np.exp(-t / tau)
    return np.sin(2 * np.pi * np.cumsum(f) / SR).astype(np.float32)


# -- drums (made once, placed many times) --------------------------------------------------

def _mk_drums():
    d = {}
    n = int(0.7 * SR)
    d["doum"] = (sweep_sine(n, 150, 78, 0.04) * expdecay(n, 0.20)
                 + 0.3 * fft_filter(noise(n, 1), band(80, 900)) * expdecay(n, 0.02))
    n = int(0.25 * SR)
    ping = np.sin(2 * np.pi * 1180 * np.arange(n) / SR) * expdecay(n, 0.035)
    d["tek"] = 0.8 * fft_filter(noise(n, 2), band(1800, 7000)) * expdecay(n, 0.03) + 0.35 * ping
    d["ka"] = 0.6 * fft_filter(noise(n, 3), band(900, 4200)) * expdecay(n, 0.025) + 0.2 * ping * 0.7
    n = int(0.9 * SR)
    d["frame"] = (sweep_sine(n, 120, 64, 0.06) * expdecay(n, 0.32)
                  + 0.25 * fft_filter(noise(n, 4), band(300, 3000)) * expdecay(n, 0.09))
    n = int(3.5 * SR)
    modes = [(1.0, 1.0, 1.6), (1.5, 0.5, 1.1), (1.99, 0.35, 0.8), (2.44, 0.2, 0.6)]
    f0 = 73.4
    t = np.arange(n) / SR
    tim = sum(a * np.sin(2 * np.pi * f0 * m * t * (1 + 0.012 * np.exp(-t / 0.08))) * np.exp(-t / tau) for m, a, tau in modes)
    d["timpani"] = tim + 0.35 * fft_filter(noise(n, 5), band(60, 1200)) * expdecay(n, 0.03)
    n = int(2.0 * SR)
    d["taiko"] = (sweep_sine(n, 105, 52, 0.05) * expdecay(n, 0.45)
                  + 0.5 * fft_filter(noise(n, 6), band(60, 700)) * expdecay(n, 0.05))
    n = int(0.4 * SR)
    d["snare"] = (0.75 * fft_filter(noise(n, 7), band(1200, 8000)) * expdecay(n, 0.09)
                  + 0.5 * sweep_sine(n, 240, 185, 0.02) * expdecay(n, 0.05))
    d["ghost"] = 0.35 * d["snare"]
    n = int(0.6 * SR)
    d["kick"] = sweep_sine(n, 140, 48, 0.03) * expdecay(n, 0.16)
    n = int(0.12 * SR)
    d["hat"] = fft_filter(noise(n, 8), band(7000, 16000)) * expdecay(n, 0.018)
    n = int(0.2 * SR)
    d["shaker"] = fft_filter(noise(n, 9), band(5000, 13000)) * (expdecay(n, 0.035) * smooth(np.arange(n) / (0.012 * SR)))
    n = int(0.35 * SR)
    d["clap"] = sum(fft_filter(noise(n, 10 + k), band(900, 6000)) * expdecay(n, 0.012 if k < 3 else 0.09, delay=k * 0.011)
                    for k in range(4)) * 0.6
    n = int(0.5 * SR)
    t = np.arange(n) / SR
    d["clank"] = sum(np.sin(2 * np.pi * 820 * r * t) * np.exp(-t / (0.12 / r)) for r in (1.0, 2.76, 5.4)) * 0.4 \
        + 0.3 * fft_filter(noise(n, 14), band(2000, 9000)) * expdecay(n, 0.01)
    for k, v in d.items():
        d[k] = (v / (np.max(np.abs(v)) or 1)).astype(np.float32)
    return d


DRUMS = None


def drums():
    global DRUMS
    if DRUMS is None:
        DRUMS = _mk_drums()
    return DRUMS


# -- the score -------------------------------------------------------------------------

# One band per era. mode: the scale; root: the tonic (MIDI); tempo in beats a minute; chords:
# scale degrees, one every `bars_per_chord` bars; the other keys are the parts that play and
# how loud. The eras are in data/eras.csv; an era missing here plays the "default" band.
BANDS = {
    "intro":   dict(scale=HIJAZ, root=50, tempo=70, chords=[0, 1, 0, 6], bars_per_chord=1),
    "e1":      dict(scale=HIJAZ, root=50, tempo=70, chords=[0, 1], bars_per_chord=2, gain=1.41,
                    drone=0.9, ney=0.7, frame=0.35),
    "e2":      dict(scale=HIJAZ, root=50, tempo=92, chords=[0, 1, 6, 0], bars_per_chord=2, gain=1.06,
                    drone=0.6, pad=0.45, oud=0.85, darbuka=0.7, shaker=0.25),
    "e3":      dict(scale=HIJAZ, root=50, tempo=76, chords=[0, 3, 6, 0], bars_per_chord=2, gain=1.26,
                    drone=0.5, choir=0.6, pad=0.35, oud=0.5, frame=0.55),
    "e4":      dict(scale=PHRYGIAN, root=50, tempo=64, chords=[0, 1, 0, 5], bars_per_chord=2, gain=1.78,
                    drone=0.9, pad=0.45, pad_kind="dark", taiko=0.55, ney=0.45),
    "e5":      dict(scale=HARMONIC, root=50, tempo=104, chords=[0, 3, 4, 0, 5, 3, 4, 0], bars_per_chord=1,
                    pad=0.4, harpsichord=0.75, bass=0.55, frame=0.3),
    "e6":      dict(scale=MAJOR, root=50, tempo=108, chords=[0, 3, 4, 0, 5, 3, 4, 0], bars_per_chord=1, gain=0.84,
                    brass=0.55, harp=0.55, bass=0.6, march=0.7, timpani=0.5),
    "e7":      dict(scale=AEOLIAN, root=50, tempo=120, chords=[0, 5, 2, 6], bars_per_chord=2, gain=0.89,
                    ostinato=0.7, pad=0.35, pad_kind="dark", bass=0.65, industry=0.6),
    "e8":      dict(scale=AEOLIAN, root=50, tempo=84, chords=[0, 5, 3, 4], bars_per_chord=2, gain=0.79,
                    brass=0.55, brass_kind="dark", drone=0.6, war=0.8, timpani=0.6),
    "e9":      dict(scale=AEOLIAN, root=50, tempo=110, chords=[0, 2, 6, 5], bars_per_chord=2, gain=0.94,
                    arp=0.6, pad=0.4, subbass=0.6, electro=0.5),
    "e10":     dict(scale=MAJOR, root=50, tempo=100, chords=[0, 4, 5, 3], bars_per_chord=2,
                    pad=0.5, pad_kind="saw", piano=0.65, bass=0.5, pop=0.55, build=True),
    "default": dict(scale=DORIAN, root=50, tempo=90, chords=[0, 3], bars_per_chord=2, gain=2.0, pad=0.5, harp=0.4),
    "finale":  dict(scale=MAJOR, root=50, tempo=84, chords=[0, 5, 3, 4], bars_per_chord=2, gain=1.26,
                    pad=0.45, harp=0.5, bass=0.35, soft=0.35),
}


class Score:
    def __init__(self, bus: Bus, seed=1776):
        self.bus = bus
        self.rng = np.random.default_rng(seed)

    # parts
    def pad(self, notes, t, dur, level, kind="warm", attack=1.0, release=1.8, send=0.45):
        for k, note in enumerate(notes):
            sig = pad_note(note, dur, kind=kind, attack=attack, release=release, rng=self.rng)
            self.bus.add(t, sig, gain=level * 0.16, send=send)

    def choir(self, notes, t, dur, level, send=0.6):
        for note in notes:
            n = int((dur + 2.0) * SR)
            env = envelope(n, 1.6, 2.0)
            out = np.zeros((2, n), np.float32)
            for v, (c, p) in enumerate(((-7, -0.5), (0, 0.0), (6, 0.5))):
                s = osc("choir", note, n, cents=c, vib=0.004, vib_rate=5.1 + 0.4 * v, phase=self.rng.random()) * env
                l, r = pan_gains(p)
                out[0] += s * l
                out[1] += s * r
            self.bus.add(t, out / 3, gain=level * 0.13, send=send)

    def brass(self, notes, t, dur, level, kind="warm", send=0.4):
        # a swell: the dark tone opens into the bright one, like a section leaning in
        for note in notes:
            n = int((dur + 0.8) * SR)
            env = envelope(n, 0.35, 0.8)
            opening = smooth(np.arange(n) / (0.6 * SR))
            dark = osc("dark", note, n, vib=0.002, vib_rate=5.4)
            bright = osc(kind if kind != "dark" else "warm", note, n, vib=0.002, vib_rate=5.4)
            s = (dark * (1 - 0.7 * opening) + bright * 0.7 * opening) * env
            self.bus.add(t, s, gain=level * 0.11, pan=self.rng.uniform(-0.3, 0.3), send=send)

    def drone(self, note, t, dur, level, send=0.35):
        n = int((dur + 1.5) * SR)
        env = envelope(n, 1.5, 1.5)
        s = (osc("dark", note, n, cents=-4) + osc("dark", note, n, cents=4) + 0.6 * osc("sine", note - 12, n)) / 2.6
        lfo = 1 + 0.12 * np.sin(2 * np.pi * 0.11 * np.arange(n) / SR)
        self.bus.add(t, s * env * lfo, gain=level * 0.2, send=send)

    def bass(self, note, t, dur, level, send=0.08):
        n = int((dur + 0.2) * SR)
        env = envelope(n, 0.02, 0.18, curve=1.2)
        s = osc("sine", note, n) + 0.25 * osc("dark", note, n)
        self.bus.add(t, s * env, gain=level * 0.22, send=send)

    def ney(self, note, t, dur, level, send=0.6):
        # an end-blown reed flute: breathy, with a slow vibrato that grows through the note
        n = int((dur + 0.4) * SR)
        env = envelope(n, 0.25, 0.4)
        vib = 0.004 * smooth(np.arange(n) / (0.6 * SR))
        f = hz(note) * (1 + vib * np.sin(2 * np.pi * 5.3 * np.arange(n) / SR))
        tone = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.18 * np.sin(4 * np.pi * np.cumsum(f) / SR)
        breath = fft_filter(noise(n, int(note * 13)), band(hz(note) * 0.8, hz(note) * 3.5)) * 0.25
        self.bus.add(t, (tone + breath) * env, gain=level * 0.1, pan=0.15, send=send)

    def string(self, note, t, level, bright=0.5, t60=1.4, pan=0.0, send=0.3, dur=None, body=0.0):
        s = pluck(note, dur or min(3.0, t60 * 1.2), bright=bright, t60=t60, seed=int(self.rng.integers(1 << 30)), body=body)
        self.bus.add(t, s, gain=level * 0.2, pan=pan, send=send)

    def hit(self, name, t, level, pan=0.0, send=0.25):
        self.bus.add(t, drums()[name], gain=level, pan=pan, send=send)

    # a section: one band from t0 to t1
    def section(self, band, t0, t1, fade_in=0.6):
        b = {**BANDS["default"], **band}
        scale, root, tempo = b["scale"], b["root"], b["tempo"]
        beat = 60.0 / tempo
        bar = 4 * beat
        chords = b["chords"]
        bpc = b["bars_per_chord"]
        length = t1 - t0
        if length <= 0.5:
            return
        nbars = int(math.ceil(length / bar))
        R = self.rng
        # everything fades in over the first moments and out over the last beat; `gain` evens
        # the bands out (a sparse drone and a full march are not equally loud at equal levels)
        gain = b.get("gain", 1.0)

        def lvl(t, base):
            k = min(1.0, (t - t0) / max(fade_in, 1e-3) + 0.15) * min(1.0, (t1 - t) / beat)
            if b.get("build"):
                k *= 0.7 + 0.5 * (t - t0) / length
            return base * max(0.0, k) * gain

        for bi in range(nbars):
            tb = t0 + bi * bar
            if tb >= t1 - 0.05:
                break
            ci = chords[(bi // bpc) % len(chords)]
            chord = triad(scale, root, ci)
            first = bi % bpc == 0
            left = t1 - tb
            span = min(bar * bpc, t1 - tb) if first else 0
            # held parts, once per chord
            if first:
                if b.get("pad"):
                    self.pad([n + 12 for n in chord], tb, span, lvl(tb, b["pad"]), kind=b.get("pad_kind", "warm"))
                if b.get("choir"):
                    self.choir([chord[0] + 12, chord[1] + 12, chord[2] + 12], tb, span, lvl(tb, b["choir"]))
                if b.get("brass"):
                    self.brass([chord[0], chord[1], chord[2] + 12], tb, span * 0.95, lvl(tb, b["brass"]),
                               kind=b.get("brass_kind", "warm"))
                if b.get("drone"):
                    self.drone(root - 12, tb, span, lvl(tb, b["drone"]))
            # moving parts, on a grid of sixteenth notes
            for q in range(16):
                t = tb + q * beat / 4
                if t >= t1 - 0.05:
                    break
                if b.get("oud") and q % 2 == 0 and R.random() < 0.9:
                    pat = [0, 4, 2, 4, 0, 5, 4, 2]
                    note = degree(scale, root, ci + pat[q // 2], 0)
                    self.string(note, t, lvl(t, b["oud"]) * (1.0 if q % 8 == 0 else 0.7), bright=0.45, t60=1.1,
                                pan=-0.2, body=0.6)
                if b.get("harpsichord"):
                    arp = [0, 2, 4, 7, 9, 7, 4, 2, 0, 2, 4, 7, 9, 11, 9, 7]
                    note = degree(scale, root, ci + arp[q], 1)
                    self.string(note, t, lvl(t, b["harpsichord"]) * (0.85 if q % 4 else 1.0), bright=0.95, t60=0.9,
                                pan=0.25 if q % 2 else -0.1)
                if b.get("harp") and q % 2 == 0:
                    arp = [0, 2, 4, 7, 9, 7, 4, 2]
                    note = degree(scale, root, ci + arp[q // 2], 1)
                    self.string(note, t, lvl(t, b["harp"]) * 0.8, bright=0.35, t60=2.2, pan=0.3, send=0.45)
                if b.get("piano") and q % 2 == 0:
                    arp = [0, 4, 7, 9, 11, 9, 7, 4]
                    note = degree(scale, root, ci + arp[q // 2], 1)
                    self.string(note, t, lvl(t, b["piano"]) * (1.0 if q == 0 else 0.7), bright=0.25, t60=2.6,
                                pan=-0.15, send=0.4)
                if b.get("ostinato") and q % 2 == 0:
                    pat = [0, 0, 4, 0, 7, 0, 4, 0]
                    note = degree(scale, root, ci + pat[q // 2], -1)
                    n = int(beat / 2 * 0.8 * SR)
                    s = osc("saw", note, n) * envelope(n, 0.005, 0.05, curve=1.0)
                    s = s + osc("saw", note + 12, n, cents=5) * envelope(n, 0.005, 0.05, curve=1.0) * 0.5
                    self.bus.add(t, s, gain=lvl(t, b["ostinato"]) * 0.07 * (1.2 if q % 8 == 0 else 1.0), pan=-0.25, send=0.2)
                if b.get("arp"):
                    arp = [0, 2, 4, 7, 4, 2, 7, 9]
                    note = degree(scale, root, ci + arp[q % 8], 1 if q < 8 else 2)
                    n = int(beat / 4 * 0.9 * SR)
                    s = osc("square", note, n) * envelope(n, 0.003, 0.08, curve=1.0) * np.exp(-np.arange(n) / (0.09 * SR))
                    self.bus.add(t, s, gain=lvl(t, b["arp"]) * 0.08, pan=0.35 if q % 2 else -0.35, send=0.35)
                if b.get("bass") and q % 4 == 0 and (q in (0, 8) or R.random() < 0.35):
                    self.bass(degree(scale, root, ci, -1), t, beat * 1.8, lvl(t, b["bass"]))
                if b.get("subbass") and q % 2 == 0:
                    self.bass(chord[0] - 24, t, beat * 0.45, lvl(t, b["subbass"]) * (1.0 if q % 4 == 0 else 0.6))
                # drums
                if b.get("darbuka"):
                    k = {0: "doum", 2: "tek", 6: "tek", 8: "doum", 12: "tek"}.get(q)
                    if k is None and q in (14, 15, 10) and R.random() < 0.45:
                        k = "ka"
                    if k:
                        self.hit(k, t, lvl(t, b["darbuka"]) * (0.55 if k != "doum" else 0.75), pan=0.1)
                if b.get("frame") and q in (0, 8):
                    self.hit("frame", t, lvl(t, b["frame"]) * (0.6 if q else 0.8), send=0.4)
                if b.get("shaker"):
                    self.hit("shaker", t, lvl(t, b["shaker"]) * (0.12 if q % 4 else 0.2), pan=0.4, send=0.1)
                if b.get("taiko") and q == 0 and bi % 2 == 0:
                    self.hit("taiko", t, lvl(t, b["taiko"]) * 0.8, send=0.5)
                if b.get("timpani") and q == 0 and first:
                    self.hit("timpani", t, lvl(t, b["timpani"]) * 0.55, send=0.4)
                if b.get("march"):
                    # accents on two and four, a few ghost notes, a roll into every fourth bar
                    if q in (4, 12):
                        self.hit("snare", t, lvl(t, b["march"]) * 0.45, pan=-0.1)
                    elif q in (2, 7, 10, 15) or (bi % 4 == 3 and q >= 12):
                        self.hit("ghost", t, lvl(t, b["march"]) * 0.4, pan=-0.1)
                    if q in (0, 8):
                        self.hit("kick", t, lvl(t, b["march"]) * 0.5)
                if b.get("industry"):
                    if q in (2, 6, 10, 14):
                        self.hit("clank", t, lvl(t, b["industry"]) * 0.18, pan=0.3 if q % 4 == 2 else -0.3, send=0.3)
                    if q in (4, 12):
                        self.hit("snare", t, lvl(t, b["industry"]) * 0.35)
                    if q in (0, 8, 10):
                        self.hit("kick", t, lvl(t, b["industry"]) * 0.55)
                if b.get("war"):
                    if q in (0, 3, 6, 8, 11, 14):
                        self.hit("taiko", t, lvl(t, b["war"]) * (0.6 if q in (0, 8) else 0.4), send=0.45)
                    if bi % 2 == 1 and q >= 8:
                        self.hit("ghost", t, lvl(t, b["war"]) * 0.35 * (q - 7) / 8)
                if b.get("electro"):
                    if q in (0, 8):
                        self.hit("kick", t, lvl(t, b["electro"]) * 0.6)
                    if q % 2 == 0:
                        self.hit("hat", t, lvl(t, b["electro"]) * (0.12 if q % 4 else 0.08), pan=0.3)
                    if q in (4, 12):
                        self.hit("clap", t, lvl(t, b["electro"]) * 0.25)
                if b.get("pop"):
                    if q in (0, 8):
                        self.hit("kick", t, lvl(t, b["pop"]) * 0.5)
                    self.hit("shaker", t, lvl(t, b["pop"]) * (0.1 if q % 2 else 0.16), pan=0.35, send=0.1)
                    if q in (4, 12):
                        self.hit("clap", t, lvl(t, b["pop"]) * 0.2, send=0.3)
                if b.get("soft") and q in (0, 8):
                    self.hit("kick", t, lvl(t, b["soft"]) * 0.35)
            # melodies over the bar
            if b.get("ney") and bi % 2 == 0 and R.random() < 0.8:
                steps = R.choice([[4, 3, 1, 0], [2, 3, 4, 2], [5, 4, 3, 1], [4, 5, 4, 2]])
                tt = tb + beat * R.choice([0.0, 0.5, 1.0])
                for k, st in enumerate(steps):
                    d = beat * (1.5 if k < len(steps) - 1 else 3.0)
                    if tt + d > t1 - 0.2:
                        break
                    self.ney(degree(scale, root, ci + st, 1), tt, d, lvl(tt, b["ney"]))
                    tt += d


def score(bus: Bus, sections):
    """sections: [(band dict, t0, t1)] in order."""
    sc = Score(bus)
    for band_, t0, t1 in sections:
        sc.section(band_, t0, t1)
    return sc


def swell(bus: Bus, t_end, dur=1.6, level=0.35, seed=0):
    """A reversed-cymbal rush that lands on t_end: into an era, the close, the finale."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    env = (t / dur) ** 3
    s = fft_filter(noise(n, seed), band(2500, 14000)) * env
    s[-int(0.015 * SR):] *= np.linspace(1, 0, int(0.015 * SR))
    bus.add(t_end - dur, s / (np.max(np.abs(s)) or 1), gain=level * 0.25, send=0.5)


def close_music(bus: Bus, t0, T):
    """The close: a hit, then a D major chord that swells in pad, choir and brass under the
    title, a bell motif as the title comes up, and a resolution as the finale arrives."""
    sc = Score(bus, seed=2026)
    root = 50
    chord = [root, root + 4, root + 7]
    sc.hit("timpani", t0, 0.7, send=0.5)
    sc.hit("taiko", t0, 0.6, send=0.6)
    sc.pad([n + 12 for n in chord] + [root + 24], t0, T - 1.2, 0.8, kind="saw", attack=1.8, release=2.5)
    sc.choir([n + 12 for n in chord], t0 + 1.0, T - 2.0, 0.8)
    sc.brass([root, root + 7, root + 12 + 4], t0 + 1.5, T - 3.0, 0.5)
    sc.drone(root - 12, t0, T, 0.6)
    for step, dt in ((12, 0.0), (9, 0.45), (7, 0.9), (4, 1.5)):   # D5, B4, A4, F#4, falling under the title
        sc.string(root + 12 + step, t0 + 2.1 + dt, 0.55, bright=0.2, t60=3.5, pan=0.2, send=0.7, dur=4.0)
    # the chord moves to the finale's key centre as its panel comes in
    sc.pad([root + 7 + 12, root + 11 + 12, root + 14 + 12], t0 + T - 1.4, 2.5, 0.5, attack=1.0, release=2.0)


def end_music(bus: Bus, t0, T):
    sc = Score(bus, seed=7)
    root = 50
    sc.pad([root + 12, root + 16, root + 19, root + 24], t0, T - 0.5, 0.9, kind="saw", attack=0.6, release=2.5)
    sc.choir([root + 12, root + 19, root + 24], t0 + 0.2, T - 1.0, 0.6)
    sc.hit("timpani", t0, 0.55, send=0.6)
    for k, note in enumerate((root + 24, root + 31, root + 28, root + 36)):
        sc.string(note, t0 + 0.3 + 0.35 * k, 0.5, bright=0.2, t60=4.0, pan=-0.3 + 0.2 * k, send=0.7, dur=4.5)


def intro_music(bus: Bus, S, m, fps):
    """Logo shimmer, a drone under the premise, strings rising as the globe turns."""
    sc = Score(bus, seed=500)
    root = 50
    L = float(m["logo_seconds"])
    P = float(m["intro_text_seconds"])
    G = float(m["globe_seconds"])
    sc.pad([root + 24, root + 31], 0.2, L + 0.8, 0.45, kind="warm", attack=1.2, release=2.0)
    sc.drone(root - 12, L - 0.3, P + 0.6, 0.55)
    sc.pad([root + 12, root + 19], L + 0.5, P - 0.5, 0.35, kind="dark", attack=2.0, release=2.0)
    for k, dt in enumerate((0.4, 2.6, 5.0)):          # the premise lines each land on a soft oud note
        sc.string(root + [12, 16, 19][k], L + dt, 0.45, bright=0.4, t60=2.0, pan=-0.2 + 0.2 * k, body=0.5, send=0.5)
    g0 = L + P
    sc.pad([root + 12, root + 16, root + 19], g0, G, 0.55, kind="warm", attack=3.0, release=1.5)
    sc.choir([root + 12, root + 19], g0 + 1.5, G - 1.5, 0.45)
    sc.drone(root - 12, g0, G, 0.5)
    swell(bus, S["intro"] / fps, 1.8, 0.5, seed=11)


# -- sound effects --------------------------------------------------------------------------

def whoosh(dur=1.2, f_from=300.0, f_to=3500.0, peak=0.55, width=0.55, seed=0, pan_from=-0.6, pan_to=0.6):
    """Air moving past: noise through a band that glides from f_from to f_to, swelling to a
    peak and dying away, panned across. Built frame by frame in the frequency domain."""
    rng = np.random.default_rng(seed)
    hop, nfft = 256, 1024
    frames = int(dur * SR / hop) + 1
    freqs = np.fft.rfftfreq(nfft, 1 / SR)
    win = np.hanning(nfft)
    out = np.zeros(frames * hop + nfft)
    lf = np.log(np.maximum(freqs, 20.0))
    for i in range(frames):
        t = i / (frames - 1)
        fc = f_from * (f_to / f_from) ** t
        env = (t / peak) ** 2 if t < peak else ((1 - t) / (1 - peak)) ** 1.6
        mag = np.exp(-0.5 * ((lf - math.log(fc)) / width) ** 2) * env
        spec = mag * np.exp(2j * np.pi * rng.random(len(freqs)))
        out[i * hop:i * hop + nfft] += np.fft.irfft(spec, nfft) * win
    out = out[:int(dur * SR)]
    out /= np.max(np.abs(out)) or 1
    p = np.linspace(pan_from, pan_to, len(out))
    a = (p + 1) * np.pi / 4
    return np.stack([out * np.cos(a), out * np.sin(a)]).astype(np.float32)


def boom(dur=3.0, f_from=70.0, f_to=38.0, seed=0, grit=0.35):
    n = int(dur * SR)
    s = sweep_sine(n, f_from, f_to, 0.12) * expdecay(n, dur / 3.2)
    s += grit * fft_filter(noise(n, seed), band(40, 900)) * expdecay(n, 0.12)
    s += 0.25 * fft_filter(noise(n, seed + 1), band(900, 6000)) * expdecay(n, 0.03)
    return (s / (np.max(np.abs(s)) or 1)).astype(np.float32)


def bell(note, dur=3.0, bright=1.0):
    """A struck bell: inharmonic partials, the high ones dying first."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = hz(note)
    parts = [(0.5, 0.6, 1.6), (1.0, 1.0, 1.2), (1.19, 0.5, 0.9), (1.56, 0.4 * bright, 0.7),
             (2.0, 0.35 * bright, 0.6), (2.51, 0.22 * bright, 0.4), (3.01, 0.15 * bright, 0.3)]
    s = sum(a * np.sin(2 * np.pi * f * r * t) * np.exp(-t / (tau * dur / 2)) for r, a, tau in parts)
    s *= smooth(t / 0.002)
    return (s / (np.max(np.abs(s)) or 1)).astype(np.float32)


def sfx_bank():
    """Every kind of effect, made once: name -> stereo array."""
    st = lambda m, p=0.0: np.stack([m * pan_gains(p)[0], m * pan_gains(p)[1]]).astype(np.float32)
    b = {}
    b["logo_rise"] = whoosh(1.1, 200, 5200, peak=0.92, width=0.5, seed=1, pan_from=0, pan_to=0)
    b["logo_hit"] = st(0.8 * boom(2.8, 64, 36, seed=2) + 0.5 * bell(74, 2.8)[:int(2.8 * SR)])
    sh = sum(bell(n, 2.4, 1.2) for n in (86, 91, 93, 98)) / 4
    b["shine"] = st(sh * np.linspace(0.3, 1.0, len(sh)) ** 0.5, 0.2)
    b["text"] = whoosh(0.7, 900, 3000, peak=0.5, width=0.45, seed=3, pan_from=-0.3, pan_to=0.3) * 0.5
    b["globe_turn"] = whoosh(5.5, 150, 900, peak=0.6, width=0.7, seed=4, pan_from=-0.8, pan_to=0.8) * 0.6
    b["dive"] = whoosh(1.6, 250, 4500, peak=0.85, width=0.6, seed=5, pan_from=0, pan_to=0)
    e = boom(3.2, 72, 38, seed=6)
    w = whoosh(1.0, 1800, 300, peak=0.12, width=0.6, seed=7)
    era = np.zeros((2, len(e)), np.float32)
    era += st(e)
    era[:, :w.shape[1]] += w * 0.6
    b["era"] = era
    b["major"] = st(boom(2.2, 60, 42, seed=8, grit=0.2) * 0.8)
    bt = boom(2.0, 95, 45, seed=9, grit=0.6)
    crack = fft_filter(noise(int(0.4 * SR), 10), band(300, 5000)) * expdecay(int(0.4 * SR), 0.05)
    bt[:len(crack)] += 0.6 * crack / (np.max(np.abs(crack)) or 1)
    b["battle"] = st(bt / (np.max(np.abs(bt)) or 1))
    b["march"] = whoosh(0.9, 180, 900, peak=0.3, width=0.5, seed=11, pan_from=-0.4, pan_to=0.4) * 0.6
    ch = np.concatenate([bell(81, 1.2, 0.8)[:int(0.18 * SR)] * 0.9, bell(88, 2.4, 0.8)])
    b["elected"] = st(ch, 0.25)
    b["close_hit"] = st(boom(4.5, 58, 32, seed=12, grit=0.3))
    t = bell(93, 3.5, 0.7) * 0.6 + bell(98, 3.5, 0.5) * 0.4
    b["title"] = st(t, -0.1)
    b["panel_in"] = whoosh(1.2, 400, 2600, peak=0.8, width=0.5, seed=13, pan_from=0.8, pan_to=0.2) * 0.7
    b["panel_out"] = whoosh(1.0, 2200, 500, peak=0.25, width=0.5, seed=14, pan_from=0.2, pan_to=0.9) * 0.6
    b["wipe"] = whoosh(1.4, 300, 1800, peak=0.35, width=0.6, seed=15, pan_from=-0.5, pan_to=0.5) * 0.6
    n = int(0.25 * SR)
    pop = np.sin(2 * np.pi * np.cumsum(np.linspace(380, 900, n)) / SR) * expdecay(n, 0.04) * smooth(np.arange(n) / (0.003 * SR))
    b["pop"] = st(pop.astype(np.float32) * 0.8)
    b["end"] = st(boom(3.5, 60, 34, seed=16, grit=0.2) * 0.6 + np.pad(bell(74, 3.5, 0.6), (0, 0))[:int(3.5 * SR)] * 0.5)
    return b


# gain and reverb send per effect; the cue list decides when
SFX = {"logo_rise": (0.55, 0.3), "logo_hit": (0.8, 0.5), "shine": (0.35, 0.6), "text": (0.22, 0.4),
       "globe_turn": (0.35, 0.4), "dive": (0.6, 0.35), "era": (0.75, 0.45), "major": (0.35, 0.35),
       "battle": (0.5, 0.35), "march": (0.22, 0.25), "elected": (0.4, 0.5), "close_hit": (0.9, 0.55),
       "title": (0.45, 0.6), "panel_in": (0.4, 0.3), "panel_out": (0.35, 0.3), "wipe": (0.3, 0.35),
       "pop": (0.3, 0.3), "end": (0.7, 0.6)}


def cues(cfg, data, slots, r) -> list[tuple[float, str, float]]:
    """(seconds into the cut, effect, pan) for every effect, from the cut's own structure."""
    fps = r.fps
    S = r.S
    m = r.m
    out = []
    L = float(m["logo_seconds"])
    out += [(0.0, "logo_rise", 0.0), (1.05, "logo_hit", 0.0), (1.2, "shine", 0.2)]
    for dt in (0.4, 2.6, 5.0):
        out.append((L + dt, "text", 0.0))
    g0 = L + float(m["intro_text_seconds"])
    out.append((g0, "globe_turn", 0.0))
    out.append((g0 + float(m["globe_seconds"]) - 1.5, "dive", 0.0))
    main0 = S["intro"] / fps
    elections = {int(e["year"]) for e in (getattr(data, "elections", None) or [])}
    last_big = -10.0
    for s in slots:
        t = main0 + s["start_frame"] / fps
        if s["era_start"]:
            out.append((t, "era", 0.0))
            last_big = t
        elif any(int(e.get("importance", 1)) >= 3 for e in s["events"]) and t - last_big > 3.0:
            out.append((t, "major", 0.0))
            last_big = t
        if s["year"] in elections:
            out.append((t + 1.2, "elected", 0.2))
    W = r.W
    for w in r.wars:
        t = main0 + w["f0"] / fps
        x = float(np.mean(w["X"]))
        pan = float(np.clip((x - r.cam.at(w["f0"])[0]) / 1.5e6, -0.8, 0.8))   # roughly where on screen
        out.append((t, "battle" if w["kind"] == "battle" else "march", pan))
    o0 = (S["intro"] + S["main"]) / fps
    T = S["outro"] / fps
    out += [(o0, "close_hit", 0.0), (o0 + 0.3, "panel_out", 0.6), (o0 + 2.1, "title", 0.0),
            (o0 + T - 1.45, "panel_in", 0.6)]
    f0 = o0 + T
    seg = float(m["finale_seconds"])
    for k in range(1, 4):
        out.append((f0 + k * seg, "wipe", 0.0))
    ncity = len(getattr(data, "cities", []) or [])
    for n in range(ncity):
        out.append((f0 + 3 * seg + 0.3 + n * 0.18, "pop", float(np.clip(-0.6 + 1.2 * n / max(1, ncity - 1), -0.6, 0.6))))
    out.append((f0 + 4 * seg + 0.15, "end", 0.0))
    return sorted(out)


def sections(cfg, data, slots, r):
    """The score's sections: (band, t0, t1), from the eras and the cut's parts."""
    fps = r.fps
    S = r.S
    main0 = S["intro"] / fps
    out = []
    eras = [(s["era_id"], main0 + s["start_frame"] / fps) for s in slots if s["era_start"]]
    o0 = (S["intro"] + S["main"]) / fps
    for k, (eid, t) in enumerate(eras):
        t1 = eras[k + 1][1] if k + 1 < len(eras) else o0
        out.append((BANDS.get(eid, BANDS["default"]), t, t1))
    return out


# -- reverb and mastering -------------------------------------------------------------------

def impulse(seconds=3.2, seed=3):
    """A hall: decorrelated noise per ear, the lows ringing longest, a few early reflections."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    out = np.zeros((2, n))
    for ch in range(2):
        rng_n = noise(n, seed + ch).astype(np.float64)
        ir = np.zeros(n)
        for lo, hi, rt in ((0, 250, 3.0), (250, 1500, 2.4), (1500, 5000, 1.6), (5000, 0, 0.8)):
            ir += fft_filter(rng_n, band(lo or None, hi or None, 2.0)) * 10 ** (-3 * t / rt)
        pre = int(0.022 * SR)
        ir = np.concatenate([np.zeros(pre), ir[:-pre]])
        for k, (dt, g) in enumerate(((0.011, 0.5), (0.019, 0.35), (0.031, 0.3), (0.047, 0.2))):
            i = int((dt + 0.003 * ch * (k % 2)) * SR)
            ir[i] += g * (1 if (k + ch) % 2 else -1) * 3
        out[ch] = ir
    out /= np.sqrt((out ** 2).sum(1, keepdims=True).mean())
    return out


def convolve(x, ir, block=1 << 17):
    """Overlap-add FFT convolution of a long stereo signal with a stereo impulse."""
    n, L = x.shape[1], ir.shape[1]
    size = 1 << (block + L - 1).bit_length()
    H = np.fft.rfft(ir, size, axis=1)
    y = np.zeros((2, n + L), np.float32)
    for a in range(0, n, block):
        seg = x[:, a:a + block].astype(np.float64)
        Y = np.fft.irfft(np.fft.rfft(seg, size, axis=1) * H, size, axis=1)
        m = min(size, n + L - a)
        y[:, a:a + m] += Y[:, :m].astype(np.float32)
    return y[:, :n]


def stretch(curve, blk, n):
    """A per-block curve back to one value per sample (float32, in pieces to spare memory)."""
    out = np.empty(n, np.float32)
    xs = np.arange(len(curve), dtype=np.float64)
    step = 1 << 22
    for a in range(0, n, step):
        b = min(n, a + step)
        out[a:b] = np.interp(np.arange(a, b, dtype=np.float64) / blk, xs, curve)
    return out


def block_rms(x, blk):
    """RMS of a stereo signal in blocks of blk samples."""
    nb = x.shape[1] // blk
    p = (x[:, :nb * blk].astype(np.float32) ** 2).mean(0).reshape(nb, blk).mean(1)
    return np.sqrt(p)


def limit_gain(x, ceiling=0.89, release=0.25, look=0.004):
    """Gain that keeps peaks under the ceiling: an instant duck ahead of each peak, released
    slowly. Computed on blocks of 1 ms, then spread back to every sample."""
    blk = int(0.001 * SR)
    n = x.shape[1]
    nb = int(math.ceil(n / blk))
    pk = np.zeros(nb)
    step = 1 << 22
    for a in range(0, n, step):          # peaks per block, a piece at a time
        seg = np.abs(x[:, a:a + step]).max(0)
        m = len(seg) // blk * blk
        pk[a // blk:a // blk + m // blk] = seg[:m].reshape(-1, blk).max(1)
        if len(seg) > m:
            pk[(a + m) // blk] = seg[m:].max()
    need = np.minimum(1.0, ceiling / np.maximum(pk, 1e-9))
    la = int(look / 0.001)
    need = np.minimum.reduce([np.roll(need, -k) for k in range(la + 1)])
    g = np.empty(nb)
    cur = 1.0
    rel = math.exp(-0.001 / release)
    for i in range(nb):
        cur = need[i] if need[i] < cur else 1 - (1 - cur) * rel
        cur = min(cur, need[i])
        g[i] = cur
    return stretch(g, blk, n)


def loudness(x):
    """Roughly integrated loudness (LUFS) of a stereo signal: K-weighted, gated, 400 ms blocks
    stepped by 100 ms. The weighting is done in the frequency domain, a piece at a time."""
    step = SR // 10
    n = x.shape[1]
    size = 1 << 20
    p = np.zeros(n, np.float32)
    for a in range(0, n, size):
        seg = x[:, a:a + size].astype(np.float64)
        f = np.maximum(np.fft.rfftfreq(seg.shape[1], 1 / SR), 1.0)
        g = (1 / (1 + (38 / f) ** 4)) * (1 + 0.585 / (1 + (1500 / f) ** 2))
        k = np.fft.irfft(np.fft.rfft(seg, axis=1) * g, seg.shape[1], axis=1)
        p[a:a + seg.shape[1]] = (k ** 2).sum(0)
    nb = n // step
    if nb < 4:
        return -70.0
    tenths = p[:nb * step].reshape(nb, step).mean(1).astype(np.float64)
    blocks = np.convolve(tenths, np.ones(4) / 4, mode="valid") + 1e-12
    lk = -0.691 + 10 * np.log10(blocks)
    g1 = blocks[lk > -70]
    if not len(g1):
        return -70.0
    rel = -0.691 + 10 * np.log10(g1.mean()) - 10
    g2 = blocks[lk > max(-70, rel)]
    return float(-0.691 + 10 * np.log10(g2.mean()))


# -- files ------------------------------------------------------------------------------------

def write_wav(path, x, bits=24):
    x = np.clip(x, -1, 1)
    path = pathlib.Path(path)
    tmp = path.with_suffix(".tmp.wav")
    inter = x.T.reshape(-1)
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(x.shape[0])
        w.setsampwidth(bits // 8)
        w.setframerate(SR)
        if bits == 24:
            v = np.round(inter * 8388607).astype("<i4")
            raw = v.view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
        else:
            raw = np.round(inter * 32767).astype("<i2").tobytes()
        w.writeframes(raw)
    os.replace(tmp, path)
    return path


def read_audio(path, seconds=None):
    """Any audio file ffmpeg reads, as float32 stereo at 48 kHz."""
    from .sequence import find_ffmpeg
    cmd = [find_ffmpeg(), "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32).reshape(-1, 2).T.copy()
    return x


def _user_file(cfg, rel):
    base = paths(cfg).root / "assets" / "audio"
    for ext in (".wav", ".flac", ".mp3", ".m4a", ".ogg"):
        p = base / f"{rel}{ext}"
        if p.exists():
            return p
    return None


def _fit(x, n, fade=3.0):
    """Loop or trim a user's music to n samples, crossfading the loop and fading the end."""
    if x.shape[1] >= n:
        y = x[:, :n].copy()
    else:
        xf = int(2.0 * SR)
        y = np.zeros((2, n), np.float32)
        pos = 0
        while pos < n:
            take = min(x.shape[1], n - pos)
            seg = x[:, :take].copy()
            if pos:
                k = min(xf, take)
                seg[:, :k] *= np.linspace(0, 1, k)
                y[:, pos - k:pos] *= np.linspace(1, 0, k)
                pos -= k
            y[:, pos:pos + take] += seg
            pos += take
    k = min(n, int(fade * SR))
    y[:, n - k:] *= np.linspace(1, 0, k)
    return y


# -- the build ------------------------------------------------------------------------------

def _key(cfg, cue_list, sect, S, fps):
    h = hashlib.sha1()
    h.update(json.dumps([cue_list, [(json.dumps(b, sort_keys=True, default=str), t0, t1) for b, t0, t1 in sect],
                         S, fps, VERSION], default=str).encode())
    h.update(pathlib.Path(__file__).read_bytes())
    base = paths(cfg).root / "assets" / "audio"
    if base.exists():
        for p in sorted(base.rglob("*")):
            if p.is_file():
                h.update(f"{p.relative_to(base)}:{p.stat().st_size}:{p.stat().st_mtime_ns}".encode())
    return h.hexdigest()[:10]


def soundtrack(cfg, data, slots, r, log=print) -> dict:
    """Make (or reuse) the whole cut's soundtrack. Returns {"music", "sfx", "mix"} paths."""
    fps = r.fps
    S = r.S
    total = S["total"] / fps
    cue_list = cues(cfg, data, slots, r)
    sect = sections(cfg, data, slots, r)
    key = _key(cfg, cue_list, sect, S, fps)
    out = paths(cfg).output / "audio"
    out.mkdir(parents=True, exist_ok=True)
    files = {k: out / f"soundtrack_{key}_{k}.wav" for k in ("music", "sfx", "mix")}
    if all(p.exists() for p in files.values()):
        log(f"  soundtrack {key}: already made")
        return files
    for old in out.glob("soundtrack_*"):
        if key not in old.name:
            try:
                old.unlink()
            except OSError:
                pass   # an editor may still hold an old one open
    n = int(round(total * SR))
    # the score, or the user's own music
    own = _user_file(cfg, "music")
    music = Bus(total)
    if own:
        log(f"  music: {own.name} (your file), fitted to {total:.0f} s")
        music.dry[:] = _fit(read_audio(own), n)
    else:
        log(f"  music: the score, {len(sect)} era sections")
        intro_music(music, S, r.m, fps)
        score(music, sect)
        eras = [t0 for _, t0, _ in sect]
        for k, t in enumerate(eras[1:], 1):
            swell(music, t, 1.4, 0.45, seed=20 + k)
        o0 = (S["intro"] + S["main"]) / fps
        swell(music, o0, 2.0, 0.6, seed=40)
        close_music(music, o0, S["outro"] / fps)
        f0 = o0 + S["outro"] / fps
        seg = float(r.m["finale_seconds"])
        Score(music, seed=84).section(BANDS["finale"], f0, f0 + 4 * seg, fade_in=1.5)
        end_music(music, f0 + 4 * seg, float(r.m["end_card_seconds"]))
    # the effects
    fx = Bus(total)
    bank = sfx_bank()
    for name in {c[1] for c in cue_list}:
        mine = _user_file(cfg, f"sfx/{name}")
        if mine:
            bank[name] = read_audio(mine)
    for t, name, pan in cue_list:
        gain, send = SFX.get(name, (0.4, 0.3))
        sig = bank[name]
        if pan:
            l, rr = pan_gains(pan)
            sig = np.stack([sig.mean(0) * l * 1.4, sig.mean(0) * rr * 1.4])
        fx.add(t, sig, gain=gain, send=send)
    # one hall for both, then the balance: the music makes room under the big hits
    log("  reverb and mix")
    ir = impulse()
    music_st = music.dry
    music_st += 0.32 * convolve(music.wet, ir)
    fx_st = fx.dry
    fx_st += 0.3 * convolve(fx.wet, ir)
    del music, fx
    # the music ducks under the effects: an envelope of the effects in 5 ms blocks, smoothed
    blk = int(0.005 * SR)
    env = block_rms(fx_st, blk)
    duck = 1 - 0.45 * np.clip(env / 0.12, 0, 1)
    k = 30
    duck = np.convolve(np.pad(duck, (k, k), mode="edge"), np.ones(k) / k, mode="same")[k:-k]
    music_st *= stretch(duck, blk, music_st.shape[1])
    # levels: the score sits at a comfortable bed, the effects above it
    lm = loudness(music_st) if np.any(music_st) else -70
    music_st *= 10 ** ((-19.0 - lm) / 20) if lm > -69 else 1.0
    lf = loudness(fx_st) if np.any(fx_st) else -70
    fx_st *= 10 ** ((-22.0 - lf) / 20) if lf > -69 else 1.0
    mix = music_st + fx_st
    lmix = loudness(mix)
    g = 10 ** ((-15.0 - lmix) / 20)
    music_st *= g
    fx_st *= g
    mix = music_st + fx_st
    lim = limit_gain(mix, ceiling=10 ** (-1.2 / 20))
    music_st *= lim
    fx_st *= lim
    mix = music_st + fx_st
    log(f"  loudness {loudness(mix):.1f} LUFS, peak {20 * math.log10(np.max(np.abs(mix)) + 1e-12):.1f} dBFS")
    write_wav(files["music"], music_st)
    write_wav(files["sfx"], fx_st)
    write_wav(files["mix"], mix)
    return files


def build(cfg, data, slots, r, tag, t0, t1, log=print) -> dict:
    """The soundtrack for a render: the whole cut's stems, and a mix for [t0, t1) seconds
    (the whole cut, or a slice) to put inside the video file."""
    try:
        files = soundtrack(cfg, data, slots, r, log=log)
    except Exception as exc:  # a soundtrack problem must not cost the picture
        log(f"  no soundtrack: {exc}")
        return {}
    total = r.S["total"] / r.fps
    if t0 <= 0 and t1 >= total - 1e-6:
        return files
    x = read_audio(files["mix"])
    a, b = int(round(t0 * SR)), int(round(t1 * SR))
    part = paths(cfg).output / "audio" / f"slice_{tag}.wav"
    write_wav(part, x[:, a:b])
    return {**files, "mix": part}


def stems_for(cfg):
    """The newest soundtrack's stems, for the Resolve script: {"music", "sfx"} or None."""
    out = paths(cfg).output / "audio"
    mixes = sorted(out.glob("soundtrack_*_mix.wav"), key=lambda p: p.stat().st_mtime) if out.exists() else []
    if not mixes:
        return None
    stem = mixes[-1].name[:-len("_mix.wav")]
    music, sfx = out / f"{stem}_music.wav", out / f"{stem}_sfx.wav"
    return {"music": music, "sfx": sfx} if music.exists() and sfx.exists() else None


# -- ElevenLabs (optional) --------------------------------------------------------------------

PROMPTS = {
    "logo_rise": "cinematic shimmering riser building into a logo reveal, airy, 1 second",
    "logo_hit": "deep cinematic logo impact with a soft metallic ring and long tail",
    "shine": "magical glass shimmer, light sweep across a glossy surface",
    "text": "soft paper swipe whoosh for a text title appearing",
    "globe_turn": "slow wind-like whoosh of a planet rotating in space, calm",
    "dive": "fast air dive whoosh zooming down from space toward the ground",
    "era": "epic cinematic boom hit with a sub drop and a short whoosh, trailer transition",
    "major": "low distant cinematic impact, subtle",
    "battle": "distant cannon blast and battle explosion, cinematic, short",
    "march": "army marching whoosh, fast arrow flight, short",
    "elected": "two-note elegant chime for an election result, bright bell",
    "close_hit": "huge cinematic final boom with a long reverberant tail",
    "title": "soft glowing bell swell for a title reveal",
    "panel_in": "smooth user-interface panel slide whoosh",
    "panel_out": "smooth user-interface panel slide away whoosh",
    "wipe": "gentle circular reveal whoosh for an infographic map",
    "pop": "soft bubble pop for an infographic data point",
    "end": "warm final cinematic hit with a soft choir tail",
}


def elevenlabs_sfx(cfg, log=print, base_url="https://api.elevenlabs.io", force=False) -> int:
    """Fill assets/audio/sfx/<cue>.mp3 from the ElevenLabs sound-effects API, one request per
    effect that has no file yet. Needs ELEVENLABS_API_KEY. Returns how many were made."""
    import urllib.error
    import urllib.request
    key = os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("XI_API_KEY")
    if not key:
        raise SystemExit("set ELEVENLABS_API_KEY first (elevenlabs.io > profile > API keys)")
    dest = paths(cfg).root / "assets" / "audio" / "sfx"
    dest.mkdir(parents=True, exist_ok=True)
    made = 0
    for name, prompt in PROMPTS.items():
        if _user_file(cfg, f"sfx/{name}") and not force:
            continue
        body = json.dumps({"text": prompt, "prompt_influence": 0.45}).encode()
        req = urllib.request.Request(f"{base_url}/v1/sound-generation?output_format=mp3_44100_128", data=body,
                                     headers={"xi-api-key": key, "Content-Type": "application/json",
                                              "Accept": "audio/mpeg"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
        except urllib.error.HTTPError as exc:
            raise SystemExit(f"ElevenLabs refused '{name}': {exc.code} {exc.read()[:300]!r}") from None
        (dest / f"{name}.mp3").write_bytes(data)
        made += 1
        log(f"  {name}.mp3 ({len(data) // 1024} KB)")
    return made
