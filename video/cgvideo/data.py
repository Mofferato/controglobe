"""The scenario data: plain CSV files that Claude writes and you review.

regions.csv   building blocks of the map (a seed point each; the mesh grows them into shapes)
groups.csv    named lists of regions, so control rows stay short (@levant, @najd ...)
polities.csv  every state, colony, league and empire that ever holds a region
control.csv   who holds which regions from which year to which year (later rows win)
events.csv    dated captions
places.csv    cities, capitals, forts and battles, each with its own years
eras.csv      the chapters of the video and their base pacing
checks.csv    canon facts the data must satisfy ("in 1812 kuwait belongs to st_kuwait")

Lines starting with # are comments. Years: negative is BCE, there is no year 0.
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass, field

import numpy as np

from . import years as Y
from .config import paths

UNCLAIMED = -1


def read_csv(path) -> list[dict]:
    with open(path, encoding="utf8") as fh:
        lines = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    rows = list(csv.DictReader(io.StringIO("".join(lines))))
    return [{k.strip(): (v or "").strip() for k, v in r.items() if k} for r in rows]


@dataclass
class Data:
    regions: list[dict]
    groups: dict[str, list[str]]
    polities: list[dict]
    control: list[dict]
    events: list[dict]
    places: list[dict]
    eras: list[dict]
    checks: list[dict]
    year_list: list[int] = field(default_factory=list)
    matrix: np.ndarray | None = None        # [year, region] -> polity index or UNCLAIMED
    problems: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.region_ids = [r["region_id"] for r in self.regions]
        self.region_index = {rid: i for i, rid in enumerate(self.region_ids)}
        self.polity_ids = [p["polity_id"] for p in self.polities]
        self.polity_index = {pid: i for i, pid in enumerate(self.polity_ids)}
        self.polity = {p["polity_id"]: p for p in self.polities}

    # -- lookups -----------------------------------------------------------------
    def expand(self, spec: str, _seen=None) -> list[str]:
        """'@levant kuwait basra' -> region ids, following nested groups."""
        seen = _seen or set()
        out: list[str] = []
        for tok in spec.split():
            if tok.startswith("@"):
                name = tok[1:]
                if name in seen:
                    self.problems.append(f"group @{name} includes itself")
                    continue
                if name not in self.groups:
                    self.problems.append(f"unknown group @{name}")
                    continue
                for member in self.groups[name]:
                    out.extend(self.expand(member, seen | {name}))
            else:
                if tok not in self.region_index:
                    self.problems.append(f"unknown region '{tok}'")
                    continue
                out.append(tok)
        return out

    def year_index(self, year: int) -> int:
        start = self.year_list[0]
        return year - start - (1 if start < 0 < year else 0)

    def holder(self, year: int, region_id: str) -> str | None:
        k = self.matrix[self.year_index(year), self.region_index[region_id]]
        return None if k == UNCLAIMED else self.polity_ids[k]

    def top(self, polity_id: str) -> str:
        """The polity a region's owner rolls up to on the map (a state's union)."""
        seen = set()
        pid = polity_id
        while self.polity[pid].get("parent") and pid not in seen:
            seen.add(pid)
            parent = self.polity[pid]["parent"]
            if parent not in self.polity:
                break
            pid = parent
        return pid

    def era_of(self, year: int) -> dict | None:
        for e in self.eras:
            if int(e["start"]) <= year <= int(e["end"]):
                return e
        return None

    def state_signature(self, row: np.ndarray) -> str:
        return hashlib.sha1(row.tobytes()).hexdigest()[:12]


def load(cfg: dict) -> Data:
    d = paths(cfg).data

    def opt(name):
        p = d / name
        return read_csv(p) if p.exists() else []

    groups = {g["group_id"]: g["members"].split() for g in opt("groups.csv")}
    data = Data(
        regions=read_csv(d / "regions.csv"),
        groups=groups,
        polities=read_csv(d / "polities.csv"),
        control=read_csv(d / "control.csv"),
        events=opt("events.csv"),
        places=opt("places.csv"),
        eras=opt("eras.csv"),
        checks=opt("checks.csv"),
    )
    # the motion pass's tables: all optional, all plain CSV
    for name in ("rulers", "parties", "elections", "cities", "population", "wars", "camera", "demographics"):
        setattr(data, name, opt(f"{name}.csv"))
    compile_matrix(cfg, data)
    return data


def compile_matrix(cfg: dict, data: Data) -> None:
    start, end = int(cfg["years"]["start"]), int(cfg["years"]["end"])
    data.year_list = list(Y.iter_years(start, end))
    m = np.full((len(data.year_list), len(data.region_ids)), UNCLAIMED, dtype=np.int16)
    for n, row in enumerate(data.control, start=1):
        where = f"control.csv row {n}"
        try:
            a, b = Y.parse(row["start"]), Y.parse(row["end"])
        except (KeyError, ValueError) as exc:
            data.problems.append(f"{where}: bad year ({exc})")
            continue
        if b < a:
            data.problems.append(f"{where}: end {b} is before start {a}")
            continue
        pid = row["polity"]
        if pid in ("-", ""):
            k = UNCLAIMED
        elif pid in data.polity_index:
            k = data.polity_index[pid]
        else:
            data.problems.append(f"{where}: unknown polity '{pid}'")
            continue
        cols = [data.region_index[r] for r in data.expand(row["regions"])]
        if not cols:
            data.problems.append(f"{where}: no regions in '{row['regions']}'")
            continue
        a, b = max(a, start), min(b, end)
        if b < a:
            continue
        ia, ib = data.year_index(a), data.year_index(b)
        m[ia : ib + 1, cols] = k
    data.matrix = m


def runs(data: Data) -> list[tuple[int, int, str]]:
    """Contiguous spans of years with an identical map: (first_year, last_year, signature)."""
    out = []
    prev = None
    for i, y in enumerate(data.year_list):
        sig = data.state_signature(data.matrix[i])
        if sig != prev:
            out.append([y, y, sig])
            prev = sig
        else:
            out[-1][1] = y
    return [tuple(r) for r in out]
