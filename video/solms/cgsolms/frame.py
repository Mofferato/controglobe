"""The frames the phases are drawn on, and the paths everything is built into.

A frame is a map projection, an extent in metres and the grids the ground is drawn at: `tex` for
the colour plate the camera looks at, `mesh` for the terrain the plate is draped on, `ws` for the
watersheds that give the provinces. The frame of Phase I holds the City of the Gods in the south,
the Ohio in the north-east and the Great Salt Lake in the north-west, with the kingdom's ground in
the middle; its projection is Lambert's azimuthal equal-area, centred on the southern plains, so
areas on the infobox are true.
"""

from __future__ import annotations

import pathlib

VIDEO = pathlib.Path(__file__).resolve().parents[2]
SOLMS = VIDEO / "solms"
BUILD = VIDEO / "build" / "solms"

# outlets of the river basins the polities are built from: lon, lat and the search window in
# cells (the outlet is moved onto the strongest flow within it); closed basins at their sinks
OUTLETS = {
    # each set on its own main stem, inland of any delta and upstream of the confluence with a
    # bigger river, so the outlet cannot slide onto the bigger one
    "gila": (-114.36, 32.75, 1), "salt": (-111.93, 33.43, 1), "san_juan": (-109.55, 37.28, 1),
    "little_colorado": (-111.41, 35.87, 1), "colorado": (-114.75, 32.45, 4), "rio_grande": (-98.3, 26.1, 4),
    "pecos": (-101.6, 30.15, 1), "conchos": (-105.15, 28.35, 4), "casas_grandes": (-107.45, 31.25, 3),
    "yaqui": (-109.95, 27.6, 1), "nazas": (-102.85, 25.45, 3), "lerma": (-101.0, 20.3, 4),
    "valley_mexico": (-99.0, 19.45, 3), "panuco": (-98.3, 22.1, 4), "red": (-92.45, 31.31, 1),
    "arkansas": (-92.0, 34.22, 4), "canadian": (-95.4, 35.3, 1), "brazos": (-95.76, 29.58, 1),
    "trinity": (-94.8, 30.06, 1), "neches": (-94.07, 30.35, 1), "sabine": (-93.75, 30.3, 1),
    "mississippi": (-91.4, 31.55, 4), "ohio": (-88.73, 37.15, 1), "tennessee": (-88.05, 36.5, 3),
    "missouri": (-90.5, 38.8, 1), "mobile": (-87.95, 31.1, 1), "great_salt": (-112.5, 41.1, 3),
    "sacramento": (-121.5, 38.6, 4), "nueces": (-97.83, 28.1, 4), "colorado_tx": (-96.1, 29.31, 1),
    "guadalupe": (-97.0, 28.8, 4), "sonora": (-110.95, 29.1, 1), "fuerte": (-108.8, 26.0, 4),
    "mezquital": (-104.6, 22.6, 4),
}

FRAMES = {
    "phase1": {
        "name": "phase1",
        "proj": "+proj=laea +lat_0=30.5 +lon_0=-100.5 +datum=WGS84 +units=m +no_defs",
        "extent": (-2250e3, -1500e3, 2250e3, 1500e3),      # x0, y0, x1, y1
        "grids": {"tex": (8192, 5461), "mesh": (1536, 1024)},
        "ll_bbox": (-129.0, 14.0, -72.0, 45.0),             # the grid GRASS works on (W, S, E, N)
        "ws_res": 0.025,                                    # degrees, about 2.6 km
        "threshold": 700,                                   # r.watershed: cells per half-basin
        "z_factor": 2.2,
        "outlets": OUTLETS,
    },
}


def frame(name: str = "phase1") -> dict:
    f = dict(FRAMES[name])
    f["video"] = str(VIDEO)
    return f


def ground_dir(name: str = "phase1") -> pathlib.Path:
    return BUILD / "ground" / name


def phase_dir(n: int) -> pathlib.Path:
    return SOLMS / f"phase{n}"


def build_dir(n: int) -> pathlib.Path:
    return BUILD / f"phase{n}"
