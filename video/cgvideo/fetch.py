"""Download the Natural Earth layers the pipeline uses (public domain, 1:10m)."""

from __future__ import annotations

import pathlib
import urllib.request

from .config import paths

LAYERS = {  # name: kind, or (kind, scale) when the scale is not in the name
    "ne_10m_land": "physical",
    "ne_10m_minor_islands": "physical",
    "ne_10m_rivers_lake_centerlines": "physical",
    "ne_10m_lakes": "physical",
    "ne_50m_land": "physical",       # the whole world, for the globe in the opening
    "ne_10m_bathymetry_all": "physical",  # depth zones, for the stepped ocean tints
    "SR_HR": ("raster", "10m"),      # shaded relief (1/60 degree), for the terrain under the map
}

MIRRORS = [
    "https://naciscdn.org/naturalearth/{scale}/{kind}/{name}.zip",
    "https://naturalearth.s3.amazonaws.com/{scale}_{kind}/{name}.zip",
]


def layer_path(cfg: dict, name: str) -> pathlib.Path:
    return paths(cfg).cache / "naturalearth" / f"{name}.zip"


def fetch(cfg: dict, force: bool = False) -> None:
    out = paths(cfg).cache / "naturalearth"
    out.mkdir(parents=True, exist_ok=True)
    for name, spec in LAYERS.items():
        kind, scale = spec if isinstance(spec, tuple) else (spec, name.split("_")[1])
        dest = out / f"{name}.zip"
        if dest.exists() and not force:
            print(f"  have {dest.name}")
            continue
        last = None
        for pattern in MIRRORS:
            url = pattern.format(kind=kind, name=name, scale=scale)
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
