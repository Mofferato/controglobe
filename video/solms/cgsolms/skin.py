"""The skins' textures, drawn in code: veined marble for Phase I (Marble & Bronze), vellum for
Phase II (Parchment & Heraldry). Written into the composition's assets/skin/."""

from __future__ import annotations

import numpy as np
from PIL import Image


def _fbm(w, h, seed, octaves=6, base=4):
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        n = base * 2 ** o
        small = rng.standard_normal((n + 3, n + 3)).astype(np.float32)
        big = np.asarray(Image.fromarray(small).resize((w + w // n * 3, h + h // n * 3), Image.BICUBIC))[:h, :w]
        out += amp * big
        tot += amp
        amp *= 0.5
    return out / tot


def marble(w=1024, h=1024, seed=11):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    turb = _fbm(w, h, seed)
    v = np.sin((x * 0.006 + y * 0.011) * 6.0 + turb * 7.5)
    veins = np.clip(1 - np.abs(v) * 7, 0, 1) ** 2.2
    v2 = np.sin((x * 0.013 - y * 0.004) * 5.0 + _fbm(w, h, seed + 3) * 9.0)
    veins2 = np.clip(1 - np.abs(v2) * 10, 0, 1) ** 2
    cloud = _fbm(w, h, seed + 7, base=3)
    base = np.array([238, 233, 222], np.float32)
    rgb = base[None, None, :] * (1 + 0.035 * cloud[..., None])
    rgb -= veins[..., None] * np.array([70, 74, 80], np.float32) * 0.55
    rgb -= veins2[..., None] * np.array([40, 38, 34], np.float32) * 0.4
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))


def vellum(w=1024, h=1024, seed=5):
    cloud = _fbm(w, h, seed, base=3)
    fine = _fbm(w, h, seed + 1, base=32)
    base = np.array([236, 220, 184], np.float32)
    rgb = base[None, None, :] * (1 + 0.06 * cloud[..., None] + 0.025 * fine[..., None])
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))


def build(out):
    d = out / "skin"
    d.mkdir(parents=True, exist_ok=True)
    if not (d / "marble.jpg").exists():
        marble().save(d / "marble.jpg", quality=88)
    if not (d / "vellum.jpg").exists():
        vellum().save(d / "vellum.jpg", quality=88)
