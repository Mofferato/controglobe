#!/usr/bin/env python3
"""Controglobe video pipeline.

  python build.py fetch                  download Natural Earth coastlines and rivers
  python build.py mesh                   build the province mesh -> build/mesh.gpkg
  python build.py check                  validate the data and the canon checks
  python build.py timeline               pacing, captions.srt, markers, chapters
  python build.py preview 1776 1861      render single years to output/preview (fast QA)
  python build.py render                 render every year to output/frames
  python build.py sheet                  contact sheet of era starts and canon checks
  python build.py sequence               hard-linked image sequence for Resolve
  python build.py animatic [--audio f]   H.264 preview with ffmpeg
  python build.py export-gis             build/history.gpkg for QGIS
  python build.py all                    fetch, mesh, check, timeline, render, sequence, animatic
"""

from __future__ import annotations

import argparse
import sys
import time

from cgvideo import data as D
from cgvideo import years as Y
from cgvideo.config import ROOT, load_config, paths


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "config" / "project.yaml"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch").add_argument("--force", action="store_true")
    sub.add_parser("mesh")
    sub.add_parser("check")
    sub.add_parser("timeline")
    p = sub.add_parser("preview")
    p.add_argument("years", nargs="+", help="years such as 1776, -262 or '262 BCE'")
    p.add_argument("--scale", type=float, default=None)
    p = sub.add_parser("render")
    p.add_argument("--from", dest="first", default=None)
    p.add_argument("--to", dest="last", default=None)
    p.add_argument("--scale", type=float, default=1.0)
    p.add_argument("--workers", type=int, default=None)
    sub.add_parser("sheet")
    p = sub.add_parser("sequence")
    p.add_argument("--frames", default=None, help="stills folder (default output/frames)")
    p = sub.add_parser("animatic")
    p.add_argument("--audio", default=None)
    p.add_argument("--frames", default=None, help="stills folder (default output/frames)")
    sub.add_parser("export-gis")
    p = sub.add_parser("all")
    p.add_argument("--workers", type=int, default=None)
    p.add_argument("--audio", default=None)
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    t0 = time.time()
    steps = ["fetch", "mesh", "check", "timeline", "render", "sequence", "animatic"] if args.cmd == "all" else [args.cmd]
    for step in steps:
        print(f"[{step}]")
        rc = run(step, cfg, args)
        if rc:
            return rc
    print(f"done in {time.time() - t0:.0f}s")
    return 0


def run(step: str, cfg: dict, args) -> int:
    if step == "fetch":
        from cgvideo import fetch
        fetch.fetch(cfg, force=getattr(args, "force", False))
        return 0

    data = D.load(cfg)

    if step == "mesh":
        from cgvideo import mesh
        mesh.build(cfg, data)
        for prob in dict.fromkeys(data.problems):
            print(f"  warning  {prob}")
        return 0

    if step == "check":
        from cgvideo import qa
        errors, warnings = qa.check(cfg, data)
        qa.report(cfg, errors, warnings)
        return 1 if errors else 0

    if step == "timeline":
        from cgvideo import timeline
        timeline.write(cfg, data)
        return 0

    if step == "export-gis":
        from cgvideo import export
        export.history(cfg, data)
        return 0

    from cgvideo import render, timeline

    if step == "preview":
        slots, _ = timeline.build(cfg, data)
        by_year = {s.year: s for s in slots}
        from dataclasses import asdict
        pick = []
        for y in args.years:
            y = Y.parse(y)
            if y not in by_year:
                print(f"  {Y.label(y)} is outside {Y.label(data.year_list[0])}..{Y.label(data.year_list[-1])}")
                return 1
            pick.append(asdict(by_year[y]))
        scale = args.scale or float(cfg["frame"].get("preview_scale", 0.5))
        out = render.render(cfg, args.config, pick, paths(cfg).output / "preview", scale=scale,
                            workers=min(len(pick), 4))
        for f in out:
            print(f"  {f}")
        return 0

    if step == "render":
        slots, _ = _fresh(cfg, data)  # always from the current data, so captions never go stale
        first = Y.parse(args.first) if getattr(args, "first", None) else None
        last = Y.parse(args.last) if getattr(args, "last", None) else None
        pick = [s for s in slots if (first is None or s["year"] >= first) and (last is None or s["year"] <= last)]
        render.render(cfg, args.config, pick, paths(cfg).frames, scale=getattr(args, "scale", 1.0),
                      workers=getattr(args, "workers", None))
        return 0

    if step == "sheet":
        from dataclasses import asdict
        slots, _ = timeline.build(cfg, data)
        want = {s.year for s in slots if s.era_start} | {Y.parse(c["year"]) for c in data.checks}
        pick = [asdict(s) for s in slots if s.year in want]
        out = render.render(cfg, args.config, pick, paths(cfg).qa / "sheet_frames", scale=0.25)
        render.contact_sheet(out, paths(cfg).qa / "contact_sheet.png")
        print(f"  {paths(cfg).qa / 'contact_sheet.png'}")
        return 0

    from cgvideo import sequence
    slots, _ = timeline.load(cfg)
    if step == "sequence":
        sequence.expand(cfg, slots, frames_dir=getattr(args, "frames", None))
        return 0
    if step == "animatic":
        sequence.animatic(cfg, slots, audio=getattr(args, "audio", None), frames_dir=getattr(args, "frames", None))
        return 0
    print(f"unknown step {step}")
    return 2


def _fresh(cfg, data):
    from dataclasses import asdict

    from cgvideo import timeline
    slots, meta = timeline.write(cfg, data)
    return [asdict(s) for s in slots], meta


if __name__ == "__main__":
    sys.exit(main())
