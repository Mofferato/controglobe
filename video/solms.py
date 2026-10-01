#!/usr/bin/env python
"""Alternate History of Texas (in place of Saudi Arabia): the Solms-America series, phase by phase.

    python solms.py ground 1      the frame's relief, land cover, provinces and basins (QGIS), the
                                  colour plate in the phase's skin (graded in GIMP), the terrain
    python solms.py cast 1        countryballs, banners, the phase's script, the city vignettes
    python solms.py compose 1     the HyperFrames composition (build/solms/phase1/hf/index.html)
    python solms.py stills 1 [t ...]  stills of the composition at times t (default: every scene)
    python solms.py blender 1     the 3D globe and flyovers, rendered by Blender on the GPU
    python solms.py score 1       the uplifting score and the effects, on the cut's cues
    python solms.py render 1      the finished phase (HyperFrames, Chrome, the GPU)
    python solms.py resolve 1     the Resolve build script, in Workspace > Scripts
    python solms.py thumbnail 1   the YouTube thumbnail (finished in GIMP)
    python solms.py publish 1     title, description, chapters, tags, pinned comment
    python solms.py all 1         everything, in order

See solms/README.md, and solms/prompts/MASTER_PROMPT.md and PHASES.md for the series.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "solms"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["ground", "cast", "compose", "stills", "blender", "score", "render",
                                     "resolve", "thumbnail", "publish", "all"])
    ap.add_argument("phase", type=int, nargs="?", default=1)
    ap.add_argument("times", type=float, nargs="*", help="stills: times in seconds")
    ap.add_argument("--redo", action="store_true", help="redo cached work for this step")
    ap.add_argument("--no-gimp", action="store_true", help="grade with numpy instead of the open GIMP")
    ap.add_argument("--workers", type=int, default=2, help="render: Chrome workers")
    ap.add_argument("--quality", default="looks", help="render: draft, looks or delivery")
    ap.add_argument("--from", dest="t0", type=float, default=None, help="render: start (seconds)")
    ap.add_argument("--to", dest="t1", type=float, default=None, help="render: end (seconds)")
    args = ap.parse_args(argv)
    from cgsolms import steps
    steps.run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
