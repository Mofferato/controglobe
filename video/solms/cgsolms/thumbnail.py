"""The YouTube thumbnail of a phase: the host countryball beside a flag map of the kingdom on the
phase's painted ground, the rest of the land darkened, a few of the phase's cast looking on, and
the question in big letters. Composed as a page (Playwright, with the skin's fonts) and finished in
GIMP (unsharp mask, a little more colour, a vignette), in the open application when it is.

    python solms.py thumbnail 1   ->  build/solms/phase1/thumbnail_1280x720.jpg (upload this) and _1920x1080.png
"""

from __future__ import annotations

import json
import re

from PIL import Image

from . import frame as F

Image.MAX_IMAGE_PIXELS = None


def build(n: int, log=print):
    hf = F.build_dir(n) / "hf"
    D = json.loads((hf / "data.js").read_text(encoding="utf8")[len("window.DATA = "):].rstrip().rstrip(";"))
    solms = next(x for x in D["modern"]["nations"] if x["k"] == "solms")
    pts = [tuple(map(float, p.split(","))) for ring in re.findall(r"M([^Z]+)Z", solms["d"]) for p in ring.split("L")]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    # the crop: the kingdom on the left two-thirds, room for the ball on the right
    w = (max(xs) - min(xs)) * 1.75
    h = w * 9 / 16
    x0 = min(xs) - (max(xs) - min(xs)) * 0.12
    y0 = (min(ys) + max(ys)) / 2 - h / 2
    G = F.ground_dir(f"phase{n}")
    work = F.build_dir(n) / "thumb"
    work.mkdir(parents=True, exist_ok=True)
    Image.open(G / "plate_marble.jpg").crop((int(x0), int(y0), int(x0 + w), int(y0 + h))).resize((1920, 1080), Image.LANCZOS) \
        .save(work / "ground.jpg", quality=93)
    k = 1920 / w
    d = solms["d"]
    # the flag sits on the kingdom's broad eastern block, so the creed reads whole
    bx, by = (min(xs) - x0) * k, (min(ys) - y0) * k
    bw, bh = (max(xs) - min(xs)) * k, (max(ys) - min(ys)) * k
    bx, by, bw, bh = bx + bw * 0.34, by + bh * 0.06, bw * 0.62, bh * 0.78     # the broad eastern block
    marches = "".join(f'<path d="{m["d"]}"/>' for m in D["modern"]["marches"])
    flag = (F.SOLMS / "art" / "flag_solms.svg").read_text(encoding="utf8")
    flag_inner = re.sub(r"^<svg[^>]*>|</svg>$", "", flag.strip())
    balls = hf / "assets" / "balls"
    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: Cinzel; src: url({(hf / 'fonts' / 'Cinzel[wght].ttf').as_uri()}); font-weight: 400 900; }}
html,body {{ margin:0; }} #t {{ position:relative; width:1920px; height:1080px; overflow:hidden; background:#10303f; }}
#t > * {{ position:absolute; }}
.ball {{ filter: drop-shadow(0 0 18px rgba(255,240,200,.85)) drop-shadow(0 16px 20px rgba(0,0,0,.6)); }}
.txt {{ font-family: Cinzel, serif; font-weight: 900; color: #fff; -webkit-text-stroke: 7px #10161a; paint-order: stroke fill;
  text-shadow: 0 10px 24px rgba(0,0,0,.65); letter-spacing: .02em; line-height: .95; }}
</style></head><body><div id="t">
<img src="{(work / 'ground.jpg').as_uri()}" style="left:0;top:0;width:1920px;height:1080px">
<svg width="1920" height="1080" viewBox="0 0 1920 1080" style="left:0;top:0">
  <defs>
    <mask id="out"><rect width="1920" height="1080" fill="#fff"/><g transform="scale({k:.5f}) translate({-x0:.1f},{-y0:.1f})"><path d="{d}" fill="#000"/></g></mask>
    <clipPath id="in"><path transform="scale({k:.5f}) translate({-x0:.1f},{-y0:.1f})" d="{d}"/></clipPath>
    <filter id="glow"><feGaussianBlur stdDeviation="9"/></filter>
  </defs>
  <rect width="1920" height="1080" fill="#07141c" opacity=".62" mask="url(#out)"/>
  <g clip-path="url(#in)">
    <rect width="1920" height="1080" fill="#1e3d70"/>
    <svg x="{bx:.0f}" y="{by:.0f}" width="{bw:.0f}" height="{bh:.0f}" viewBox="0 0 900 600" preserveAspectRatio="xMidYMid meet">{flag_inner}</svg>
    <image href="{(work / 'ground.jpg').as_uri()}" width="1920" height="1080" style="mix-blend-mode:multiply" opacity=".42"/>
  </g>
  <g transform="scale({k:.5f}) translate({-x0:.1f},{-y0:.1f})" fill="none">
    <g stroke="#ffffff" stroke-width="{1.4 / k:.2f}" opacity=".35">{marches}</g>
    <path d="{d}" stroke="#7ff5e2" stroke-width="{16 / k:.2f}" opacity=".55" filter="url(#glow)"/>
    <path d="{d}" stroke="#ffffff" stroke-width="{5 / k:.2f}"/>
  </g>
</svg>
<img class="ball" src="{(balls / 'solms_smug.svg').as_uri()}" style="right:-40px;top:250px;width:760px;height:760px">
<img class="ball" src="{(balls / 'paquime_surprised.svg').as_uri()}" style="left:36px;bottom:24px;width:290px;height:290px">
<img class="ball" src="{(balls / 'city_worried.svg').as_uri()}" style="left:306px;bottom:14px;width:262px;height:262px">
<div class="txt" style="left:46px;top:30px;font-size:178px">TEXAS</div>
<div class="txt" style="left:56px;top:205px;font-size:96px;color:#ffd84a">= SAUDI ARABIA?</div>
<div style="right:60px;top:40px;padding:12px 28px;border-radius:14px;background:#2fb3a6;border:6px solid #10161a;
  font-family:Cinzel,serif;font-weight:900;font-size:58px;color:#fff;-webkit-text-stroke:3px #10161a;paint-order:stroke fill">PHASE I</div>
</div></body></html>"""
    page = work / "thumb.html"
    page.write_text(html, encoding="utf8")
    raw = work / "thumb_raw.png"
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        pg = b.new_page(viewport={"width": 1920, "height": 1080})
        pg.goto(page.as_uri())
        pg.wait_for_timeout(600)
        pg.locator("#t").screenshot(path=str(raw))
        b.close()
    big = F.build_dir(n) / "thumbnail_1920x1080.png"
    _finish(raw, big, log)
    small = F.build_dir(n) / "thumbnail_1280x720.jpg"
    Image.open(big).convert("RGB").resize((1280, 720), Image.LANCZOS).save(small, quality=92, optimize=True)
    log(f"  thumbnail: {small} ({small.stat().st_size // 1024} KB) and {big.name}")
    return small


def _finish(raw, out, log):
    """GIMP's finish: an unsharp mask, a little more colour, a soft vignette."""
    import sys
    sys.path.insert(0, str(F.VIDEO))
    from cgvideo.terrain import _gimp_live
    reply = _gimp_live([
        "from gi.repository import Gimp, Gio",
        f"cg_img = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path({str(raw)!r}))",
        "cg_layer = cg_img.get_layers()[0]",
        "cg_f = Gimp.DrawableFilter.new(cg_layer, 'gegl:unsharp-mask', '')",
        "cg_c = cg_f.get_config(); cg_c.set_property('std-dev', 2.2); cg_c.set_property('scale', 0.6)",
        "cg_layer.merge_filter(cg_f)",
        "cg_f = Gimp.DrawableFilter.new(cg_layer, 'gegl:saturation', '')",
        "cg_c = cg_f.get_config(); cg_c.set_property('scale', 1.18)",
        "cg_layer.merge_filter(cg_f)",
        "cg_f = Gimp.DrawableFilter.new(cg_layer, 'gegl:vignette', '')",
        "cg_c = cg_f.get_config(); cg_c.set_property('radius', 1.35); cg_c.set_property('softness', 0.75); cg_c.set_property('gamma', 2.0)",
        "cg_layer.merge_filter(cg_f)",
        f"Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, cg_img, Gio.File.new_for_path({str(out)!r}), None)",
        f"cg_img.set_file(Gio.File.new_for_path({str(out)!r}))",
        "cg_img.clean_all()",
        "cg_shown = globals().setdefault('cg_shown', {})",
        "cg_old = cg_shown.pop('solms-thumbnail', None)",
        "Gimp.Display.get_by_id(cg_old).delete() if cg_old and Gimp.Display.id_is_valid(cg_old) else None",
        "cg_shown['solms-thumbnail'] = Gimp.Display.new(cg_img).get_id()",
        "Gimp.displays_flush()",
    ])
    if reply is not None and reply.get("status") == "success" and out.exists():
        log("  thumbnail finished in GIMP (unsharp mask, saturation, vignette)")
        return
    log(f"  GIMP could not finish the thumbnail ({str(reply)[:200]}); it is saved unfinished")
    Image.open(raw).save(out)
