"""Stills and the finished render of a phase's composition.

  stills: the composition opened in Chrome (Playwright, the GPU) through a local web server, drawn
          at chosen times by the engine's own render(t), and saved as PNGs to look at.
  render: HyperFrames renders the composition to MP4 with Chrome on the GPU (`npx hyperframes`).
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import os
import shutil
import socketserver
import subprocess
import threading

from . import frame as F

FFMPEG_DIRS = [r"C:\Users\PC\tools\ffmpeg-master-latest-win64-gpl\bin"]


@contextlib.contextmanager
def serve(root):
    handler = functools.partial(_Quiet, directory=str(root))
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as httpd:
        th = threading.Thread(target=httpd.serve_forever, daemon=True)
        th.start()
        try:
            yield f"http://127.0.0.1:{httpd.server_address[1]}"
        finally:
            httpd.shutdown()


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def stills(n: int, times=None, out=None, log=print):
    from playwright.sync_api import sync_playwright
    hf = F.build_dir(n) / "hf"
    out = out or (F.build_dir(n) / "stills")
    out.mkdir(parents=True, exist_ok=True)
    data = (hf / "data.js").read_text(encoding="utf8")
    import json
    D = json.loads(data[len("window.DATA = "):].rstrip().rstrip(";"))
    if not times:
        times = []
        for sc in D["scenes"]:
            times += [round(sc["t0"] + (sc["t1"] - sc["t0"]) * f, 2) for f in (0.15, 0.5, 0.85)]
    paths = []
    with serve(hf) as base, sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True,
                              args=["--ignore-gpu-blocklist", "--enable-gpu-rasterization", "--use-angle=d3d11",
                                    "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": D["W"], "height": D["H"]})
        errs = []
        pg.on("console", lambda m: errs.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        pg.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
        pg.goto(base + "/index.html")
        pg.wait_for_function("window.__render !== undefined", timeout=120000)
        for t in times:
            pg.evaluate(f"window.__render({t})")
            pg.wait_for_timeout(120)
            path = out / f"still_{t:07.2f}.png"
            pg.screenshot(path=str(path))
            paths.append(path)
        b.close()
    for e in errs[:30]:
        log("  " + e)
    log(f"  {len(paths)} stills in {out}")
    return paths


def segment(n: int, t0: float, t1: float) -> str:
    """A composition file for a slice of the cut: the same page with its clock starting at t0,
    the clips and the soundtrack moved to match. Returns its file name inside hf/."""
    import re
    hf = F.build_dir(n) / "hf"
    html = (hf / "index.html").read_text(encoding="utf8")
    dur = t1 - t0
    html = re.sub(r'(id="root"[^>]*data-duration=")[^"]+"', lambda m: m.group(1) + f'{dur:.3f}"', html)

    def clip(m):
        tag = m.group(0)
        a = float(re.search(r'data-t0="([^"]+)"', tag).group(1))
        b = float(re.search(r'data-t1="([^"]+)"', tag).group(1))
        if b <= t0 or a >= t1:
            return ""
        start = max(a, t0)
        tag = re.sub(r'data-start="[^"]+"', f'data-start="{start - t0:.3f}"', tag)
        tag = re.sub(r'data-duration="[^"]+"', f'data-duration="{min(b, t1) - start:.3f}"', tag)
        if a < t0:
            tag = tag.replace("<video ", f'<video data-media-start="{t0 - a:.3f}" ')
        return tag
    html = re.sub(r'<video class="clip sceneclip"[^>]*></video>', clip, html)
    html = re.sub(r'(<audio data-start="0" data-duration=")[^"]+"', lambda m: m.group(1) + f'{dur:.3f}" data-media-start="{t0:.3f}"', html)
    html = html.replace('<script src="data.js"></script>', f'<script>window.SEG_T0={t0};window.SEG_DUR={dur};</script>\n<script src="data.js"></script>')
    name = f"seg_{int(t0):04d}_{int(t1):04d}.html"
    (hf / name).write_text(html, encoding="utf8")
    return name


def render(n: int, workers=2, quality="looks", t0=None, t1=None, log=print):
    hf = F.build_dir(n) / "hf"
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join(FFMPEG_DIRS + [env.get("PATH", "")])
    import time
    stamp = time.strftime("%Y%m%d-%H%M%S")
    seg = None
    if t0 is not None or t1 is not None:
        import json
        D = json.loads((hf / "data.js").read_text(encoding="utf8")[len("window.DATA = "):].rstrip().rstrip(";"))
        seg = segment(n, t0 or 0.0, t1 or D["duration"])
    name = f"solms_phase{n}_{stamp}.mp4" if seg is None else f"segment_phase{n}_{seg[4:-5]}_{stamp}.mp4"
    dst = F.build_dir(n) / ("renders" if seg is None else "segments") / name
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["npx", "-y", "hyperframes", "render", "-o", str(dst), "-q", quality, "-w", str(workers), "--browser-gpu"]
    if seg:
        cmd += ["-c", seg]
    log("  " + " ".join(cmd))
    subprocess.run(" ".join(f'"{c}"' if " " in c else c for c in cmd), cwd=hf, env=env, shell=True, check=True)
    log(f"  rendered: {dst}")
    return dst
