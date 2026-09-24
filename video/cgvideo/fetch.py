"""Download the Natural Earth layers the pipeline uses (public domain, 1:10m)."""

from __future__ import annotations

import pathlib
import urllib.request

from .config import paths

LAYERS = {
    "ne_10m_land": "physical",
    "ne_10m_minor_islands": "physical",
    "ne_10m_rivers_lake_centerlines": "physical",
    "ne_10m_lakes": "physical",
}

MIRRORS = [
    "https://naciscdn.org/naturalearth/10m/{kind}/{name}.zip",
    "https://naturalearth.s3.amazonaws.com/10m_{kind}/{name}.zip",
]


def layer_path(cfg: dict, name: str) -> pathlib.Path:
    return paths(cfg).cache / "naturalearth" / f"{name}.zip"


def fetch(cfg: dict, force: bool = False) -> None:
    out = paths(cfg).cache / "naturalearth"
    out.mkdir(parents=True, exist_ok=True)
    for name, kind in LAYERS.items():
        dest = out / f"{name}.zip"
        if dest.exists() and not force:
            print(f"  have {dest.name}")
            continue
        last = None
        for pattern in MIRRORS:
            url = pattern.format(kind=kind, name=name)
            try:
                print(f"  get  {url}")
                req = urllib.request.Request(url, headers={"User-Agent": "controglobe-video/0.1"})
                with urllib.request.urlopen(req, timeout=120) as resp:
                    dest.write_bytes(resp.read())
                break
            except OSError as exc:
                last = exc
        else:
            raise SystemExit(f"could not download {name}: {last}")
