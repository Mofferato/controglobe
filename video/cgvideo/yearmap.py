"""The map of every year: al-Mashriq from 500 BCE to 2026 on the encyclopedia's History page.

One figure, drawn from the same data and mesh as the video: every region once, every stretch of
border between two regions once, and for each run of years with an unchanged map, who held each
region. A small script colours the regions for the year the slider shows and draws the frontiers
(dark, between different powers) and the inner lines (faint, between one power's states or
colonies) from the borders whose two sides differ. The page carries the map of 1776 as drawn, so
it reads before the script runs, and the sea, land, relief and rivers are the page's other maps'
shared layers. `python build.py sitemaps` writes it into both editions of the History page.
"""

from __future__ import annotations

import html
import json
import math
import re
from collections import defaultdict

import numpy as np
import shapely
from shapely.ops import polylabel

from . import data as D
from .sitemaps import INK, SITE, VIEW, Ground, _clean, path_d

PAGE = "history-of-the-united-states-of-arabia.html"
BEFORE = '<h2 id="before">'          # the figure goes after the contents, before the first section
START = 1776                         # the year the page shows before anyone moves the slider
BEGIN, END = "<!-- cg-years -->", "<!-- /cg-years -->"
CSS_BEGIN, CSS_END = "/* cg-years: the map of every year */", "/* /cg-years */"

UI = {
    "en": {
        "bce": "BCE", "ce": "CE", "play": "Play", "pause": "Pause",
        "prev": "Previous change of frontier", "next": "Next change of frontier", "year": "Year",
        "eras": "Eras", "jump": "Go to {}",
        "label": "Political map of al-Mashriq in the year shown, from 500 BCE to 2026",
        "caption": "<b>Al-Mashriq in every year</b>, from 500&nbsp;BCE to 2026: each power in its colour and "
                   "each frontier where it ran that year. Drag the slider, step from one change of frontier "
                   "to the next, choose an era, or press play.",
    },
    "ar": {
        "bce": "ق.م", "ce": "م", "play": "تشغيل", "pause": "إيقاف مؤقت",
        "prev": "التغيّر السابق في الحدود", "next": "التغيّر التالي في الحدود", "year": "العام",
        "eras": "الحقب", "jump": "انتقل إلى {}",
        "label": "خريطة سياسية للمشرق في العام المعروض، من 500 ق.م إلى 2026",
        "caption": "<b>المشرق في كل عام</b>، من 500&nbsp;ق.م إلى 2026: كل قوة بلونها وكل حدّ حيث جرى في ذلك "
                   "العام. اسحب المنزلق، أو انتقل من تغيّر في الحدود إلى التالي، أو اختر حقبة، أو اضغط تشغيل.",
    },
}


def _fills(cfg: dict, data: D.Data) -> dict[str, str]:
    """Each polity's colour as the video paints it: its own, else its parent's; territories
    and protectorates lighter."""
    from .render import LIGHT_KINDS, hex_rgb, mix
    st = cfg["style"]
    out = {}
    for p in data.polities:
        pid = p["polity_id"]
        colour, cur, seen = p.get("color"), pid, set()
        while not colour and data.polity[cur].get("parent") and cur not in seen:
            seen.add(cur)
            cur = data.polity[cur]["parent"]
            colour = data.polity.get(cur, {}).get("color")
        rgb = hex_rgb(colour or "#bbbbbb")
        if p.get("kind") in LIGHT_KINDS:
            rgb = mix(rgb, "#ffffff", float(st.get("territory_lighten", 0.45)))
        out[pid] = "#%02x%02x%02x" % tuple(int(round(v * 255)) for v in rgb)
    return out


def _year_label(y: int, lang: str) -> str:
    ui = UI[lang]
    if y < 0:
        return f"{-y} {ui['bce']}"
    return f"{y} {ui['ce']}" if y < 500 else str(y)


def _width(text: str, size: float, lang: str) -> float:
    return len(text) * size * (0.74 if lang == "en" else 0.52)


def _label(part, name: str, lang: str):
    """Where and how large a power's name fits in its largest piece: (x, y, size, split) or None.
    split is the word the second line starts at, 0 for one line."""
    x0, y0, x1, y1 = part.bounds
    room = (x1 - x0) * 0.92
    words = name.split()
    size = max(8.0, min(15.0, math.sqrt(part.area) / 8.5))
    best = None
    while size >= 7.5:
        if _width(name, size, lang) <= room:
            best = (size, 0)
            break
        if len(words) > 1:
            k = min(range(1, len(words)), key=lambda k: abs(len(" ".join(words[:k])) - len(" ".join(words[k:]))))
            w = max(_width(" ".join(words[:k]), size, lang), _width(" ".join(words[k:]), size, lang))
            if w <= room and size * 2.3 <= (y1 - y0):
                best = (size, k)
                break
        size -= 0.5
    if not best:
        return None
    pt = polylabel(part, tolerance=1.0)
    x = min(max(pt.x, 24), 896)
    y = min(max(pt.y, 16), 604)
    return round(x, 1), round(y, 1), best[0], best[1]


TOL = 0.8      # an overview map: coarser than the page's other maps
FADE = (672, 772)   # x where the powers begin and finish fading out, before the mesh's eastern edge


def build_data(cfg: dict, data: D.Data, g: Ground, lang: str) -> dict:
    ids = [rid for rid in data.region_ids if rid in g.region and g.region[rid].intersects(VIEW)]
    coarse = shapely.coverage_simplify(np.array([g.region[r] for r in ids]), TOL)
    geoms = [_clean(c, tol=0.05, min_area=0.0) for c in coarse]
    keep = [i for i, geom in enumerate(geoms) if not geom.is_empty]
    ids, geoms = [ids[i] for i in keep], [geoms[i] for i in keep]
    # the fills are clipped to the land, so a region's seaward side can be rough: widen each
    # into the sea, simplify hard, and take back whatever touches another region exactly
    tree = shapely.STRtree(geoms)
    fills = []
    for i, geom in enumerate(geoms):
        wide = shapely.simplify(geom.buffer(3, join_style="mitre"), 2.0)
        others = [geoms[j] for j in tree.query(wide) if j != i]
        fills.append(_clean(shapely.difference(wide, shapely.union_all(others)) if others else wide,
                            tol=0.05, min_area=0.3))
    # every stretch of border between two regions, once
    left, right = tree.query(geoms, predicate="intersects")
    edges = []
    for a, b in zip(left, right):
        if a >= b:
            continue
        line = shapely.intersection(geoms[a].boundary, geoms[b].boundary)
        line = shapely.line_merge(shapely.intersection(line, VIEW))
        parts = [p for p in shapely.get_parts(line) if p.geom_type in ("LineString", "LinearRing")]
        if parts and sum(p.length for p in parts) > 0.8:
            edges.append([int(a), int(b), path_d(shapely.MultiLineString(parts))])
    # runs of years with an unchanged map, as changes from the run before
    cols = [data.region_index[r] for r in ids]
    rows = data.matrix[:, cols]
    runs, prev = [], None
    for i, y in enumerate(data.year_list):
        row = tuple(int(v) for v in rows[i])
        if row != prev:
            runs.append((y, row))
            prev = row
    used = sorted({p for _, row in runs for p in row if p != D.UNCLAIMED})
    pindex = {p: n for n, p in enumerate(used)}
    fill = _fills(cfg, data)
    tops, tindex = [], {}
    pol = []
    for p in used:
        pid = data.polity_ids[p]
        top = data.top(pid)
        if top not in tindex:
            tindex[top] = len(tops)
            tp = data.polity[top]
            tops.append(tp.get("name_ar") or tp["name"] if lang == "ar" else tp.get("short") or tp["name"].upper())
        pol.append([fill[pid], tindex[top]])
    out_runs, labelsets, set_index, run_labels = [], [], {}, []
    before = None
    for first, row in runs:
        changes = [[i, pindex[p] if p != D.UNCLAIMED else -1] for i, p in enumerate(row)
                   if before is None or before[i] != p]
        if before is None:
            changes = [c for c in changes if c[1] != -1]
        out_runs.append([first, changes])
        before = row
        # the powers' names, where they fit
        groups = defaultdict(list)
        for i, p in enumerate(row):
            if p != D.UNCLAIMED:
                groups[tindex[data.top(data.polity_ids[p])]].append(geoms[i])
        labels = []
        for t, gs in sorted(groups.items()):
            parts = [q for q in shapely.get_parts(shapely.union_all(gs)) if q.geom_type == "Polygon"]
            if not parts:
                continue
            part = max(parts, key=lambda q: q.area)
            if part.area < 650:
                continue
            spot = _label(part, tops[t], lang)
            if spot:
                labels.append([t, *spot])
        key = json.dumps(labels)
        if key not in set_index:
            set_index[key] = len(labelsets)
            labelsets.append(labels)
        run_labels.append(set_index[key])
    events = []
    for e in data.events:
        text = (e.get("text_ar") if lang == "ar" else e.get("text")) or ""
        if text:
            events.append([int(e["year"]), int(e.get("importance") or 1), text])
    events.sort(key=lambda e: (e[0], -e[1]))
    eras = [[int(e["start"]), int(e["end"]), (e.get("name_ar") if lang == "ar" else None) or e["name"],
             e.get("color") or "#999"] for e in data.eras]
    return {"lang": lang, "first": data.year_list[0], "last": data.year_list[-1], "ids": ids,
            "geoms": fills, "edges": edges, "runs": out_runs, "pol": pol, "tops": tops,
            "labelsets": labelsets, "runlab": run_labels, "events": events, "eras": eras,
            "bce": UI[lang]["bce"], "ce": UI[lang]["ce"]}


def _state(d: dict, year: int):
    """The owner of each region in a year, as the script computes it (for the map at rest)."""
    first_years = [r[0] for r in d["runs"]]
    run = max(i for i, f in enumerate(first_years) if f <= year)
    owners = [-1] * len(d["ids"])
    for r in d["runs"][: run + 1]:
        for i, p in r[1]:
            owners[i] = p
    return run, owners


def figure(d: dict) -> str:
    lang = d["lang"]
    ui = UI[lang]
    run, owners = _state(d, START)
    regions = "".join(f'<path d="{path_d(geom)}" fill="{d["pol"][o][0] if o >= 0 else "none"}"/>'
                      for geom, o in zip(d["geoms"], owners))
    front, inner = [], []
    for a, b, dd in d["edges"]:
        oa, ob = owners[a], owners[b]
        if oa < 0 and ob < 0:
            continue
        ta = d["pol"][oa][1] if oa >= 0 else -1
        tb = d["pol"][ob][1] if ob >= 0 else -1
        (front if ta != tb else inner if oa != ob else []).append(dd)
    rtl = ' direction="rtl"' if lang == "ar" else ""
    labels = []
    for t, x, y, size, split in d["labelsets"][d["runlab"][run]]:
        words = d["tops"][t].split()
        lines = [" ".join(words[:split]), " ".join(words[split:])] if split else [d["tops"][t]]
        spans = "".join(f'<tspan x="{x}" dy="{(-0.2 if len(lines) > 1 else 0.35) if k == 0 else 1.15}em">'
                        f"{html.escape(s)}</tspan>" for k, s in enumerate(lines))
        labels.append(f'<text x="{x}" y="{y}" font-size="{size}">{spans}</text>')
    stamp_x, anchor = (898, "start") if lang == "ar" else (22, "start")
    data_json = json.dumps({k: d[k] for k in ("lang", "first", "last", "edges", "runs", "pol", "tops", "labelsets",
                                              "runlab", "events", "eras", "bce", "ce")},
                           ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    total = d["last"] - d["first"] + (0 if d["first"] > 0 or d["last"] < 0 else -1)
    start_i = START - d["first"] - (1 if d["first"] < 0 < START else 0)
    era_buttons = "".join(
        f'<button type="button" style="flex-grow:{max(1, e[1] - e[0] + 1)};--c:{e[3]}" data-year="{e[0]}" '
        f'aria-label="{html.escape(ui["jump"].format(e[2]))}" title="{html.escape(e[2])}"></button>'
        for e in d["eras"])
    ink = INK
    svg = (f'<svg class="cgy-map" viewBox="0 0 920 620" xmlns="http://www.w3.org/2000/svg" role="img" '
           f'aria-label="{html.escape(ui["label"])}">'
           f'<use href="#cgm-sea"/><use href="#cgm-land" fill="{ink["land"]}"/>'
           f'<defs><clipPath id="cgy-land"><use href="#cgm-land"/></clipPath>'
           # the mesh ends in eastern Iran on a ruled line: fade the powers out before it
           f'<linearGradient id="cgy-east" gradientUnits="userSpaceOnUse" x1="{FADE[0]}" y1="0" x2="{FADE[1]}" y2="0">'
           f'<stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#000"/></linearGradient>'
           f'<mask id="cgy-fade" maskUnits="userSpaceOnUse" x="0" y="0" width="920" height="620">'
           f'<rect width="920" height="620" fill="url(#cgy-east)"/></mask>'
           f'<path id="cgy-front" d="{"".join(front)}"/></defs>'
           f'<g mask="url(#cgy-fade)">'
           f'<g class="cgy-regions" fill-rule="evenodd" clip-path="url(#cgy-land)">{regions}</g></g>'
           f'<use href="#cgm-relief" opacity=".55" style="mix-blend-mode:multiply"/>'
           f'<use href="#cgm-water"/>'
           f'<g mask="url(#cgy-fade)">'
           f'<path class="cgy-inner" fill="none" stroke="{ink["inner"]}" stroke-width=".7" stroke-opacity=".5" '
           f'stroke-linejoin="round" d="{"".join(inner)}"/>'
           f'<g fill="none" stroke-linejoin="round" stroke-linecap="round">'
           f'<use href="#cgy-front" stroke="#fff" stroke-width="3" stroke-opacity=".6"/>'
           f'<use href="#cgy-front" stroke="{ink["frontier"]}" stroke-width="1.35"/></g></g>'
           f'<use href="#cgm-land" fill="none" stroke="{ink["coast"]}" stroke-width=".8" stroke-linejoin="round"/>'
           f'<g class="cgy-labels" mask="url(#cgy-fade)" font-family="Georgia,serif" fill="#23292c" '
           f'text-anchor="middle" letter-spacing=".06em" paint-order="stroke" stroke="rgba(255,255,255,.8)" '
           f'stroke-width="2.6"{rtl}>{"".join(labels)}</g>'
           f'<text class="cgy-stamp" x="{stamp_x}" y="58" text-anchor="{anchor}" font-family="Georgia,serif" '
           f'font-size="44" fill="#0d3940" fill-opacity=".82" paint-order="stroke" stroke="rgba(255,255,255,.7)" '
           f'stroke-width="4"{rtl}>{html.escape(_year_label(START, lang))}</text>'
           "</svg>")
    return (f"{BEGIN}\n"
            f'<figure class="mapwrap cg-years" id="every-year">\n'
            f'<div class="cgy-bar">'
            f'<button type="button" class="cgy-play" aria-label="{ui["play"]}" data-l-play="{ui["play"]}" '
            f'data-l-pause="{ui["pause"]}"><svg viewBox="0 0 20 20" aria-hidden="true"><path class="cgy-i-play" '
            f'd="M6 4l10 6-10 6z"/><path class="cgy-i-pause" d="M5 4h3.6v12H5zM11.4 4H15v12h-3.6z"/></svg></button>'
            f'<button type="button" class="cgy-step" data-dir="-1" aria-label="{ui["prev"]}" title="{ui["prev"]}">'
            f'<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M12.5 4.5L7 10l5.5 5.5"/></svg></button>'
            f'<button type="button" class="cgy-step" data-dir="1" aria-label="{ui["next"]}" title="{ui["next"]}">'
            f'<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M7.5 4.5L13 10l-5.5 5.5"/></svg></button>'
            f'<output class="cgy-year">{html.escape(_year_label(START, lang))}</output>'
            f'<span class="cgy-era"></span></div>\n'
            f'<div class="cgy-track"><input class="cgy-range" type="range" min="0" max="{total}" step="1" '
            f'value="{start_i}" aria-label="{ui["year"]}" aria-valuetext="{html.escape(_year_label(START, lang))}">'
            f'<div class="cgy-eras" role="group" aria-label="{ui["eras"]}">{era_buttons}</div></div>\n'
            f'<div class="mapscroll">{svg}</div>\n'
            f'<figcaption><span class="cgy-event"></span>{ui["caption"]}</figcaption>\n'
            f'<script type="application/json" class="cgy-data">{data_json}</script>\n'
            "</figure>\n"
            f"<script>{SCRIPT}</script>\n"
            f"{END}\n")


SCRIPT = r"""(function(){
var fig=document.getElementById('every-year');if(!fig)return;
var D=JSON.parse(fig.querySelector('.cgy-data').textContent),NS='http://www.w3.org/2000/svg';
var regs=fig.querySelectorAll('.cgy-regions path'),front=fig.querySelector('#cgy-front'),inner=fig.querySelector('.cgy-inner'),
 lab=fig.querySelector('.cgy-labels'),stamp=fig.querySelector('.cgy-stamp'),range=fig.querySelector('.cgy-range'),
 out=fig.querySelector('.cgy-year'),era=fig.querySelector('.cgy-era'),ev=fig.querySelector('.cgy-event'),
 play=fig.querySelector('.cgy-play');
var N=regs.length,owners=[],firsts=[],cur=new Int16Array(N).fill(-1);
D.runs.forEach(function(r){r[1].forEach(function(c){cur[c[0]]=c[1];});owners.push(Int16Array.from(cur));firsts.push(r[0]);});
var gap=(D.first<0&&D.last>0)?1:0;
function yearAt(i){var y=D.first+i;return(gap&&y>=0)?y+1:y;}
function indexOf(y){return y-D.first-((gap&&y>0)?1:0);}
function label(y){return y<0?(-y)+' '+D.bce:(y<500?y+' '+D.ce:''+y);}
function find(list,y,key){var lo=0,hi=list.length-1,at=-1;while(lo<=hi){var m=(lo+hi)>>1;if(key(list[m])<=y){at=m;lo=m+1;}else hi=m-1;}return at;}
var shown=-1;
function draw(run){
 var o=owners[run],f=[],n=[],i;
 for(i=0;i<N;i++){var p=o[i];regs[i].setAttribute('fill',p<0?'none':D.pol[p][0]);}
 D.edges.forEach(function(e){var a=o[e[0]],b=o[e[1]];if(a<0&&b<0)return;
  var ta=a<0?-1:D.pol[a][1],tb=b<0?-1:D.pol[b][1];if(ta!==tb)f.push(e[2]);else if(a!==b)n.push(e[2]);});
 front.setAttribute('d',f.join(''));inner.setAttribute('d',n.join(''));
 while(lab.firstChild)lab.removeChild(lab.firstChild);
 D.labelsets[D.runlab[run]].forEach(function(L){
  var name=D.tops[L[0]],w=name.split(' '),lines=L[4]?[w.slice(0,L[4]).join(' '),w.slice(L[4]).join(' ')]:[name],
   t=document.createElementNS(NS,'text');
  t.setAttribute('x',L[1]);t.setAttribute('y',L[2]);t.setAttribute('font-size',L[3]);
  lines.forEach(function(s,k){var ts=document.createElementNS(NS,'tspan');ts.setAttribute('x',L[1]);
   ts.setAttribute('dy',(k?1.15:(lines.length>1?-0.2:0.35))+'em');ts.textContent=s;t.appendChild(ts);});
  lab.appendChild(t);});
}
function set(i){
 i=Math.max(0,Math.min(+range.max,i));var y=yearAt(i),s=label(y);range.value=i;
 var r=find(firsts,y,function(v){return v;});if(r!==shown){draw(r);shown=r;}
 out.textContent=s;stamp.textContent=s;range.setAttribute('aria-valuetext',s);
 var e=find(D.eras,y,function(v){return v[0];});era.textContent=e>=0&&y<=D.eras[e][1]?D.eras[e][2]:'';
 var k=find(D.events,y,function(v){return v[0];});
 if(k<0){ev.textContent='';ev.className='cgy-event';return;}
 var same=D.events[k][0]===y;ev.className='cgy-event'+(same?'':' old');
 ev.textContent=(same?'':label(D.events[k][0])+': ')+D.events[k][2];
}
var timer=null;
function stop(){clearTimeout(timer);timer=null;fig.classList.remove('cgy-on');play.setAttribute('aria-label',play.dataset.lPlay);
 ev.setAttribute('aria-live','polite');}
function tick(){var i=+range.value+1;if(i>+range.max){stop();return;}var before=shown;set(i);var y=yearAt(i),hold=45,
 k=find(D.events,y,function(v){return v[0];});
 if(k>=0&&D.events[k][0]===y)hold=D.events[k][1]>=3?1500:D.events[k][1]===2?1000:600;else if(shown!==before)hold=220;
 timer=setTimeout(tick,hold);}
play.addEventListener('click',function(){if(timer){stop();return;}if(+range.value>=+range.max)set(0);
 fig.classList.add('cgy-on');play.setAttribute('aria-label',play.dataset.lPause);ev.setAttribute('aria-live','off');tick();});
range.addEventListener('input',function(){stop();set(+range.value);});
fig.querySelectorAll('.cgy-step').forEach(function(b){b.addEventListener('click',function(){stop();
 var y=yearAt(+range.value),r=find(firsts,y,function(v){return v;});
 if(+b.dataset.dir>0){if(r+1<firsts.length)set(indexOf(firsts[r+1]));}
 else set(indexOf(firsts[firsts[r]<y?r:Math.max(0,r-1)]));});});
fig.querySelectorAll('.cgy-eras button').forEach(function(b){b.addEventListener('click',function(){stop();set(indexOf(+b.dataset.year));});});
set(+range.value);
})();"""

CSS = CSS_BEGIN + """
.cg-years .cgy-bar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:0 2px 8px}
.cg-years button{font:inherit;cursor:pointer;display:inline-grid;place-items:center;flex:none;padding:0}
.cg-years button svg{background:none;border-radius:0;display:block}
.cgy-play{width:40px;height:40px;border-radius:50%;border:0;background:var(--brand);color:#fff}
.cgy-play:hover{background:var(--brand-2)}
.cgy-play svg{width:18px;height:18px;fill:currentColor}
.cgy-play .cgy-i-pause,.cgy-on .cgy-play .cgy-i-play{display:none}
.cgy-on .cgy-play .cgy-i-pause{display:inline}
.cgy-step{width:34px;height:34px;border-radius:50%;border:1px solid var(--line);background:var(--panel);color:var(--ink)}
.cgy-step:hover{border-color:var(--accent)}
.cgy-step svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
[dir="rtl"] .cgy-step svg{transform:scaleX(-1)}
.cgy-year{font-family:var(--serif);font-size:26px;line-height:1;font-variant-numeric:tabular-nums;color:var(--ink);
 margin-inline-start:6px;min-width:4.6em}
.cgy-era{color:var(--muted);font-size:14px}
.cgy-track{padding:0 2px 10px}
.cgy-range{display:block;width:100%;margin:0;accent-color:var(--accent);height:26px}
.cgy-eras{display:flex;gap:2px;margin:2px 8px 0;height:8px}
.cgy-eras button{height:8px;border:0;border-radius:2px;background:var(--c);opacity:.75}
.cgy-eras button:hover,.cgy-eras button:focus-visible{opacity:1}
.cgy-event{display:block;color:var(--ink);font-size:14px;min-height:1.55em;margin-bottom:4px}
.cgy-event.old{color:var(--muted)}
""" + CSS_END


def install(cfg: dict, data: D.Data, g: Ground) -> list[str]:
    changed = []
    for lang, path in (("en", SITE / PAGE), ("ar", SITE / "ar" / PAGE)):
        if not path.exists():
            continue
        with open(path, encoding="utf8", newline="") as fh:
            text = fh.read()
        nl = "\r\n" if "\r\n" in text else "\n"
        block = figure(build_data(cfg, data, g, lang)).replace("\n", nl)
        if BEGIN in text:
            new = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\r?\n?", lambda m: block, text, count=1, flags=re.S)
        else:
            new = text.replace(BEFORE, block + BEFORE, 1)
        css = CSS.replace("\n", nl)
        if CSS_BEGIN in new:
            new = re.sub(re.escape(CSS_BEGIN) + r".*?" + re.escape(CSS_END), lambda m: css, new, count=1, flags=re.S)
        else:
            marker = re.search(r"/\* ==== end of design system[^\n]*\n", new)
            new = new[:marker.end()] + css + nl + new[marker.end():]
        if new != text:
            with open(path, "w", encoding="utf8", newline="") as fh:
                fh.write(new)
            changed.append(path.relative_to(SITE).as_posix())
    return changed
