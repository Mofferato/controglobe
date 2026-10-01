"""The phase's cast and art: countryballs in every mood, banners, the script's glyphs, the city
vignettes; and a cast sheet (cast_sheet.png) to look at before anything is composed.

    python solms.py cast 1
"""

from __future__ import annotations

import yaml

from . import balls
from . import frame as F


def load(n: int) -> dict:
    cast = yaml.safe_load((F.phase_dir(n) / "cast.yaml").read_text(encoding="utf8"))
    for c in cast.values():
        c["_cast"] = cast
    return cast


def art_dir(n: int):
    d = F.build_dir(n) / "hf" / "assets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def build(n: int, sheet: bool = True, log=print) -> dict:
    cast = load(n)
    out = art_dir(n)
    (out / "balls").mkdir(exist_ok=True)
    (out / "flags").mkdir(exist_ok=True)
    for cid, c in cast.items():
        for m in balls.MOODS:
            (out / "balls" / f"{cid}_{m}.svg").write_text(balls.ball_svg(cid, c, m, F.SOLMS), encoding="utf8")
        (out / "flags" / f"{cid}.svg").write_text(balls.banner_svg(c, F.SOLMS), encoding="utf8")
    log(f"  {len(cast)} countryballs in {len(balls.MOODS)} moods, and their banners")
    from . import glyphs, vignettes
    glyphs.build(n, out)
    vignettes.build(n, out)
    if sheet:
        p = cast_sheet(n, cast, out)
        log(f"  cast sheet: {p}")
    return cast


def cast_sheet(n, cast, out):
    from playwright.sync_api import sync_playwright
    rows = []
    for cid, c in cast.items():
        names = c.get("names", {})
        cells = "".join(f'<div class="cell"><img src="balls/{cid}_{m}.svg"><span>{m}</span></div>' for m in balls.MOODS)
        native = names.get("native")
        nat = f"{native['word']} ({native['lang']}, “{native['means']}”)" if native else ""
        rows.append(f'<div class="row"><div class="who"><img class="flag" src="flags/{cid}.svg"><b>{names.get("en", cid)}</b>'
                    f'<i>{names.get("de", "")}</i><span class="ar">{names.get("ar", "")}</span><small>{nat}</small>'
                    f'<small>{names.get("ts", "")}</small></div>{cells}</div>')
    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
    body{{margin:0;background:#2b2722;color:#f3ead7;font:15px Georgia,serif}}
    .row{{display:flex;align-items:center;border-bottom:1px solid #4a4237;padding:6px 10px}}
    .who{{width:250px;display:flex;flex-direction:column;gap:2px}} .who .flag{{width:90px;height:60px;border:2px solid #111}}
    .ar{{font-size:18px;direction:rtl}} small{{color:#c9b98f}}
    .cell{{display:flex;flex-direction:column;align-items:center;width:150px}} .cell img{{width:140px;height:140px}}
    .cell span{{font-size:12px;color:#c9b98f}}</style></head><body>{''.join(rows)}</body></html>"""
    page_path = out / "_cast_sheet.html"
    page_path.write_text(html, encoding="utf8")
    png = F.build_dir(n) / "preview" / "cast_sheet.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1340, "height": 900})
        pg.goto(page_path.as_uri())
        pg.wait_for_timeout(400)
        pg.screenshot(path=str(png), full_page=True)
        b.close()
    return png
