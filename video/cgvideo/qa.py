"""Checks that run before anything is rendered: data integrity, canon, and coverage."""

from __future__ import annotations

from collections import Counter

import geopandas as gpd

from . import years as Y
from .config import paths
from .data import UNCLAIMED, Data


def check(cfg: dict, data: Data) -> tuple[list[str], list[str]]:
    errors = list(dict.fromkeys(data.problems))
    warnings: list[str] = []

    # polities
    for p in data.polities:
        pid = p["polity_id"]
        if p.get("parent") and p["parent"] not in data.polity:
            errors.append(f"polity {pid}: unknown parent '{p['parent']}'")
        seen, cur = set(), pid
        while data.polity.get(cur, {}).get("parent"):
            if cur in seen:
                errors.append(f"polity {pid}: parent chain loops")
                break
            seen.add(cur)
            cur = data.polity[cur]["parent"]
        color, cur = p.get("color"), pid
        while not color and data.polity.get(cur, {}).get("parent"):
            cur = data.polity[cur]["parent"]
            color = data.polity.get(cur, {}).get("color")
        if not color:
            warnings.append(f"polity {pid}: no colour of its own or from a parent (drawn grey)")
    dupes = [k for k, n in Counter(data.polity_ids).items() if n > 1]
    errors += [f"polity id '{d}' is defined twice" for d in dupes]
    dupes = [k for k, n in Counter(data.region_ids).items() if n > 1]
    errors += [f"region id '{d}' is defined twice" for d in dupes]

    used = set(int(v) for v in set(data.matrix.ravel().tolist())) - {UNCLAIMED}
    for k, pid in enumerate(data.polity_ids):
        if k not in used and not any(q.get("parent") == pid for q in data.polities):
            warnings.append(f"polity {pid} never holds a region")
    for j, rid in enumerate(data.region_ids):
        if (data.matrix[:, j] == UNCLAIMED).all() and "filler" not in data.regions[j].get("notes", ""):
            warnings.append(f"region {rid} is never held by anyone")

    # eras: every year in exactly one era
    for y in data.year_list:
        hits = [e for e in data.eras if int(e["start"]) <= y <= int(e["end"])]
        if len(hits) != 1:
            errors.append(f"year {Y.label(y)} is in {len(hits)} eras (needs exactly 1)")
            break

    # events
    lo, hi = data.year_list[0], data.year_list[-1]
    for e in data.events:
        try:
            y = Y.parse(e["year"])
        except ValueError as exc:
            errors.append(f"event '{e.get('text', '')[:40]}': {exc}")
            continue
        if not lo <= y <= hi:
            warnings.append(f"event in {Y.label(y)} is outside the video's years")
        if len(e.get("text", "")) > 110:
            warnings.append(f"event {Y.label(y)} caption is {len(e['text'])} characters; aim for under 90")

    # canon checks
    passed = 0
    for c in data.checks:
        y, rid, want = Y.parse(c["year"]), c["region"], c["expected"]
        if rid not in data.region_index:
            errors.append(f"checks.csv: unknown region '{rid}'")
            continue
        got = data.holder(y, rid) or "-"
        if got != want:
            errors.append(f"CANON {Y.label(y)} {rid}: expected {want}, map has {got}  ({c.get('source', '')})")
        else:
            passed += 1

    # mesh
    mesh = paths(cfg).mesh
    if mesh.exists():
        regions = gpd.read_file(mesh, layer="regions", columns=["region_id", "n_cells"])
        have = set(regions["region_id"])
        seeds = gpd.read_file(mesh, layer="region_seeds")
        in_mesh = dict(zip(seeds["region_id"], seeds["in_mesh"]))
        for rid in data.region_ids:
            if in_mesh.get(rid, True) and rid not in have:
                warnings.append(f"region {rid} has no cells in the mesh")
            if not in_mesh.get(rid, True):
                warnings.append(f"region {rid} lies outside the mesh domain")
    else:
        warnings.append("no build/mesh.gpkg yet: run `python build.py mesh`")

    inferred = sum(1 for r in data.control if r.get("source", "").startswith("inferred"))
    print(f"  {len(data.control)} control rows ({inferred} inferred), {len(data.checks)} canon checks, "
          f"{passed} passed")
    return errors, warnings


def report(cfg: dict, errors: list[str], warnings: list[str]) -> None:
    out = paths(cfg).qa
    out.mkdir(parents=True, exist_ok=True)
    lines = ["# QA report", "", f"{len(errors)} errors, {len(warnings)} warnings", ""]
    if errors:
        lines += ["## Errors", ""] + [f"- {e}" for e in errors] + [""]
    if warnings:
        lines += ["## Warnings", ""] + [f"- {w}" for w in warnings] + [""]
    (out / "report.md").write_text("\n".join(lines), encoding="utf8")
    for e in errors:
        print(f"  ERROR    {e}")
    for w in warnings:
        print(f"  warning  {w}")
    print(f"  {len(errors)} errors, {len(warnings)} warnings -> {out / 'report.md'}")
