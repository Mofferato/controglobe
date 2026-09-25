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
  python build.py motion [--scale 1]     the finished moving cut (intro, camera, wars, infobox, finale, soundtrack)
  python build.py audio [--elevenlabs]   remake the soundtrack and put it into the newest motion cut
  python build.py thumbnail              YouTube thumbnail: countryball, flag map, "SINCE WHEN?"
  python build.py logo [--size 1024]     the emblem as a square PNG: the Discord server icon
  python build.py resolve [--media ...]  the Resolve build script, installed as Workspace > Scripts > cg_resolve_build
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
    p = sub.add_parser("motion", help="the finished moving cut: intro, camera, wars, infobox, finale")
    p.add_argument("--scale", type=float, default=0.5, help="0.5 = 1080p, 1.0 = 4K")
    p.add_argument("--workers", type=int, default=None)
    p.add_argument("--from", dest="first", default=None)
    p.add_argument("--to", dest="last", default=None)
    p.add_argument("--frame", type=int, nargs="*", default=None, help="write these frames as PNGs instead")
    p.add_argument("--prores", action="store_true", help="ProRes 422 .mov for editing in Resolve")
    p.add_argument("--silent", action="store_true", help="no soundtrack")
    p = sub.add_parser("audio", help="remake the soundtrack and put it into the newest motion cut")
    p.add_argument("--scale", type=float, default=0.5, help="the scale the cut was rendered at")
    p.add_argument("--elevenlabs", action="store_true",
                   help="first fetch every effect that has no file yet from ElevenLabs (needs ELEVENLABS_API_KEY)")
    p = sub.add_parser("thumbnail")
    p.add_argument("--text", default="SINCE WHEN?")
    p = sub.add_parser("logo", help="the emblem as a square PNG, for the Discord server icon")
    p.add_argument("--size", type=int, default=1024)
    p = sub.add_parser("resolve", help="write and install the Resolve build script (Workspace > Scripts > cg_resolve_build)")
    p.add_argument("--media", choices=["auto", "motion", "sequence"], default="auto",
                   help="auto: the motion cut if one is rendered, else the yearly stills")
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

    if step == "logo":
        from cgvideo import logo
        out = paths(cfg).output / f"logo_{args.size}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        logo.emblem(cfg, args.size).save(out)
        print(f"  {out}")
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

    if step == "motion":
        from cgvideo import motion
        motion.run(cfg, args.config, scale=args.scale, workers=args.workers,
                   first_year=Y.parse(args.first) if args.first else None,
                   last_year=Y.parse(args.last) if args.last else None,
                   frames=args.frame, codec="prores" if args.prores else "h264", sound=not args.silent)
        return 0

    if step == "audio":
        from cgvideo import audio, motion
        if args.elevenlabs:
            print(f"  {audio.elevenlabs_sfx(cfg)} effects fetched from ElevenLabs")
        dest = motion.resound(cfg, args.config, scale=args.scale)
        print(f"  {dest}" if dest else "  soundtrack made; no motion cut to put it in yet (python build.py motion)")
        return 0

    if step == "resolve":
        from cgvideo import timeline
        slots, meta = timeline.build(cfg, data)
        what = timeline.write_resolve_lua(cfg, slots, meta, media=args.media)
        installed = timeline.install_resolve_script(cfg)
        print(f"  built from {what}")
        print(f"  installed as {installed}" if installed else
              "  Resolve not found: copy output/resolve_build.lua into its Scripts/Utility folder")
        return 0

    if step == "thumbnail":
        from cgvideo import thumbnail
        for f in thumbnail.make(cfg, data, text=args.text):
            print(f"  {f}")
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
