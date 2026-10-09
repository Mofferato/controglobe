// The war Shorts' engine: every frame of a Short drawn as a pure function of time.
//
// HyperFrames seeks the GSAP timeline registered at the end; its onUpdate calls render(t), which
// moves the camera over the map plates (crossfading at every border change), and places the HUD
// skin, the army banners and their numbers, the arrows, the blockade, the battle popups, captions,
// the Arabic lower-thirds, the countryballs, the casualty count, the hook and the end card for that
// instant. Nothing depends on the frame before, so any frame can be drawn alone, by any worker.

const D = window.DATA;
const W = D.W, H = D.H;
const AX = W / 2, AY = H * 0.46;                    // where the camera's centre sits on screen
const ov = document.getElementById('ov');
const ui = document.getElementById('ui');
const vec = document.getElementById('vec');
const SVGNS = 'http://www.w3.org/2000/svg';

const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const lerp = (a, b, t) => a + (b - a) * t;
const smooth = t => { t = clamp(t, 0, 1); return t * t * (3 - 2 * t); };
const easeOut = t => 1 - Math.pow(1 - clamp(t, 0, 1), 3);
const backOut = t => { t = clamp(t, 0, 1); const c = 1.7; return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2); };
const fade = (t, t0, t1, fin = .3, fout = .3) => clamp(Math.min((t - t0) / fin, (t1 - t) / fout), 0, 1);
const fmt = n => Math.round(n).toLocaleString('en-US');
const el = (tag, cls, parent, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; (parent || ov).appendChild(e); return e; };
const sv = (tag, attrs, parent) => { const e = document.createElementNS(SVGNS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); (parent || vec).appendChild(e); return e; };
const show = (e, v) => { const d = v ? '' : 'none'; if (e.style.display !== d) e.style.display = d; };
const setText = (e, s) => { if (e._t !== s) { e.textContent = s; e._t = s; } };
const place = (e, x, y, s = 1, r = 0, o = 1) => { e.style.transform = `translate(${x.toFixed(1)}px,${y.toFixed(1)}px) rotate(${r.toFixed(2)}deg) scale(${s.toFixed(4)})`; e.style.opacity = o.toFixed(3); };
function keyed(keys, t) {              // [[t, v], ...] eased between keys
  if (t <= keys[0][0]) return keys[0][1];
  for (let i = 0; i < keys.length - 1; i++) if (t < keys[i + 1][0]) return lerp(keys[i][1], keys[i + 1][1], smooth((t - keys[i][0]) / (keys[i + 1][0] - keys[i][0])));
  return keys[keys.length - 1][1];
}
const SIDE = D.sides;

// ------------------------------------------------------------------------------------ the camera
function camAt(t) {
  const K = D.camera;
  let a = K[0], b = K[0], f = 0;
  if (t > K[0][0]) {
    a = b = K[K.length - 1];
    for (let i = 0; i < K.length - 1; i++) if (t < K[i + 1][0]) { a = K[i]; b = K[i + 1]; f = smooth((t - a[0]) / (b[0] - a[0])); break; }
  }
  // never still: a slow drift on top of the keys
  const dx = 14 * Math.sin(t * 0.61) + 6 * Math.sin(t * 1.7), dy = 10 * Math.cos(t * 0.53);
  const s = Math.exp(lerp(Math.log(a[3]), Math.log(b[3]), f)) * (1 + 0.012 * Math.sin(t * 0.8));
  return { cx: lerp(a[1], b[1], f) + dx / s, cy: lerp(a[2], b[2], f) + dy / s, s, rot: lerp(a[4], b[4], f) };
}
let CAM = camAt(0), SHAKE = [0, 0];
function scr(p) {                       // plate px -> screen px
  const c = Math.cos(CAM.rot), s = Math.sin(CAM.rot);
  const x = (p[0] - CAM.cx) * CAM.s, y = (p[1] - CAM.cy) * CAM.s;
  return [AX + SHAKE[0] + x * c - y * s, AY + SHAKE[1] + x * s + y * c];
}
function polyAt(path, u) {              // the point a share u along a polyline, and the part before it
  if (path.length === 1) return { pt: path[0], part: [path[0]] };
  const L = []; let tot = 0;
  for (let i = 1; i < path.length; i++) { const d = Math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1]); L.push(d); tot += d; }
  let want = clamp(u, 0, 1) * tot; const part = [path[0]];
  for (let i = 1; i < path.length; i++) {
    if (want <= L[i - 1]) { const f = L[i - 1] ? want / L[i - 1] : 0; const p = [lerp(path[i - 1][0], path[i][0], f), lerp(path[i - 1][1], path[i][1], f)]; part.push(p); return { pt: p, part }; }
    want -= L[i - 1]; part.push(path[i]);
  }
  return { pt: path[path.length - 1], part };
}

// ------------------------------------------------------------------------------------ the maps
const mapA = document.getElementById('mapA'), mapB = document.getElementById('mapB');
document.getElementById('root').style.background = D.plate.ocean;
const loadImage = src => new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = src; });
await Promise.all(Object.values(D.plate.src).map(loadImage));
await Promise.all(['700 40px Cinzel', '900 40px Cinzel', '700 40px Cormorant', 'italic 600 40px Cormorant', '700 40px Amiri'].map(f => document.fonts.load(f).catch(() => null)));
await document.fonts.ready;
const XF = 0.4;
function mapState(t) {
  const tr = D.track; let i = 0;
  for (let k = 0; k < tr.length; k++) if (t >= tr[k][0]) i = k;
  const cur = tr[i][1], prev = i > 0 ? tr[i - 1][1] : cur;
  return { cur, prev, f: i > 0 ? clamp((t - tr[i][0]) / XF, 0, 1) : 1, since: t - tr[i][0], changed: i > 0 };
}
function drawMap(t) {
  const st = mapState(t);
  const c = Math.cos(CAM.rot), s = Math.sin(CAM.rot);
  const tx = AX + SHAKE[0] - (CAM.cx * c - CAM.cy * s) * CAM.s, ty = AY + SHAKE[1] - (CAM.cx * s + CAM.cy * c) * CAM.s;
  const m = `matrix(${c * CAM.s},${s * CAM.s},${-s * CAM.s},${c * CAM.s},${tx},${ty})`;
  for (const [img, key, o] of [[mapA, st.prev, 1], [mapB, st.cur, st.f]]) {
    const src = D.plate.src[key];
    if (img._src !== src) { img.src = src; img._src = src; }
    img.style.transform = m; img.style.opacity = o;
  }
  // the new borders light up for a moment
  const glow = st.changed ? Math.max(0, 1 - st.since / 0.9) : 0;
  mapB.style.filter = glow > 0 ? `brightness(${1 + 0.25 * glow}) saturate(${1 + 0.4 * glow})` : '';
}

// ------------------------------------------------------------------------------------ the HUD
const badge = side => side === 'usa'
  ? `<svg viewBox="0 0 76 46" width="76" height="46"><path d="M0,0H76L60,23L76,46H0Z" fill="${SIDE.usa.colour}" stroke="#141414" stroke-width="2.5"/><circle cx="26" cy="23" r="11" fill="none" stroke="#fff" stroke-width="4"/></svg>`
  : `<svg viewBox="0 0 76 46" width="76" height="46"><path d="M0,0H76L60,23L76,46H0Z" fill="${SIDE.isa.colour}" stroke="#141414" stroke-width="2.5"/><path d="M26,10L37,23L26,36L15,23Z" fill="#fff"/></svg>`;

const top = el('div', 'plate', ui, '');
top.id = 'topbar';
top.innerHTML = `
  <div class="side u"><img src="${D.flags.usa}"><div class="nm">${SIDE.usa.name}<span class="ar">${SIDE.usa.name_ar}</span></div><div class="men">0</div><div class="lbl">men under arms</div></div>
  <div class="side i"><img src="${D.flags.isa}"><div class="nm">${SIDE.isa.name}<span class="ar">${SIDE.isa.name_ar}</span></div><div class="men">0</div><div class="lbl">men under arms</div></div>
  <div id="dial"><svg width="210" height="210" viewBox="0 0 210 210"><g id="ticks"></g><path id="hand" d="M105,8 L113,30 L97,30 Z" fill="#7a1f1a" stroke="#4a3312" stroke-width="1.5"/></svg>
    <div class="war">${D.war.toUpperCase()}</div><div class="yr">1861</div><div class="mo">APRIL</div></div>`;
{
  const g = top.querySelector('#ticks');
  for (let k = 0; k < 12; k++) {
    const a = k / 12 * 2 * Math.PI;
    sv('line', { x1: 105 + 92 * Math.sin(a), y1: 105 - 92 * Math.cos(a), x2: 105 + 99 * Math.sin(a), y2: 105 - 99 * Math.cos(a), stroke: '#4a3312', 'stroke-width': k % 3 ? 2 : 4 }, g);
  }
}
const menU = top.querySelector('.side.u .men'), menI = top.querySelector('.side.i .men');
const dYr = top.querySelector('.yr'), dMo = top.querySelector('.mo'), hand = top.querySelector('#hand');
const MONTHS = ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER'];

const roster = el('div', 'plate', ui, '<h4>THE ARMIES</h4>');
roster.id = 'roster';
const rows = D.armies.map(a => {
  const r = el('div', 'row', roster, `<i style="background:${SIDE[a.side].colour}"></i><b>${a.unit.replace('Army of ', '')}</b><span>0</span>`);
  return { a, r, n: r.querySelector('span') };
});

function drawHud(t) {
  const h = D.hud; if (!h || !h.t0) { show(top, false); show(roster, false); return; }
  const on = t >= h.t0 - 0.1 && t <= h.t1 + 0.6;
  show(top, on);
  if (on) {
    const k = easeOut((t - h.t0) / 0.6), out = clamp((h.t1 + 0.5 - t) / 0.5, 0, 1);
    place(top, 66, lerp(-200, 150, k), 1, 0, Math.min(1, out * 1.5));
    setText(menU, fmt(keyed(D.ledger.usa, t))); setText(menI, fmt(keyed(D.ledger.isa, t)));
    const yr = keyed(D.clock, t), y = Math.floor(yr), mo = clamp(Math.floor((yr - y) * 12), 0, 11);
    setText(dYr, String(y)); setText(dMo, MONTHS[mo]);
    hand.setAttribute('transform', `rotate(${((yr - y) * 360).toFixed(1)} 105 105)`);
  }
  const popup = D.battles.some(b => t > b.t - 0.5 && t < b.t + 2.3);
  const ron = on && t < (D.cost ? D.cost.t0 : h.t1) - 0.1;
  show(roster, ron);
  if (ron) {
    const k = easeOut((t - h.t0 - 0.25) / 0.6);
    place(roster, lerp(-380, 66, k), 470, 1, 0, popup ? 0.0 : (D.cost ? clamp((D.cost.t0 - 0.1 - t) / 0.4, 0, 1) : 1) * 0.94);
    for (const r of rows) {
      const live = t >= r.a.t0 && t <= r.a.t1;
      show(r.r, t >= r.a.t0);
      setText(r.n, live ? fmt(keyed(r.a.n, t)) : (t > r.a.t1 ? '—' : ''));
      r.r.style.opacity = live ? 1 : .45;
    }
  }
}

// -------------------------------------------------------------------------------- armies, arrows
const armyEls = D.armies.map(a => {
  const e = el('div', 'army', ov, `<div class="base" style="background:${SIDE[a.side].colour}"></div><div class="pole"></div><div class="flag">${badge(a.side)}</div><div class="tag"><b>0</b><em>${a.unit.replace('Army of ', '').toUpperCase()}</em></div>`);
  return { a, e, n: e.querySelector('.tag b') };
});
function drawArmies(t) {
  for (const { a, e, n } of armyEls) {
    const on = t >= a.t0 && t <= a.t1 + 0.4;
    show(e, on); if (!on) continue;
    const u = keyed(a.move, t);
    const p = scr(polyAt(a.path, u).pt);
    const k = backOut((t - a.t0) / 0.45), o = clamp((a.t1 + 0.4 - t) / 0.4, 0, 1);
    const bob = 3 * Math.sin(t * 3 + a.path[0][0]);
    place(e, p[0], p[1] + bob, 0.55 + 0.45 * k, 0, Math.min(1, (t - a.t0) / 0.2) * o);
    const v = keyed(a.n, t);
    setText(n, fmt(v));
    n.style.color = v < keyed(a.n, Math.max(a.t0, t - 0.6)) - 1 ? '#7a1f1a' : '';   // falling numbers flush red
  }
}
const arrowEls = D.arrows.map(a => {
  const g = sv('g', {});
  const under = sv('path', { fill: 'none', stroke: '#141414', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, g);
  const line = sv('path', { fill: 'none', stroke: SIDE[a.side].colour, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, g);
  const head = sv('path', { fill: SIDE[a.side].colour, stroke: '#141414', 'stroke-width': 3 }, g);
  return { a, g, under, line, head };
});
function drawArrows(t) {
  for (const { a, g, under, line, head } of arrowEls) {
    const on = t >= a.t0 && t <= a.t1 + 1.2;
    show(g, on); if (!on) continue;
    const u = easeOut((t - a.t0) / (a.t1 - a.t0));
    const { part } = polyAt(a.path, u);
    const pts = part.map(scr);
    const wdt = a.big ? 18 : 12;
    const d = 'M' + pts.map(p => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join('L');
    under.setAttribute('d', d); under.setAttribute('stroke-width', wdt + 6);
    line.setAttribute('d', d); line.setAttribute('stroke-width', wdt);
    line.setAttribute('stroke-dasharray', a.big ? '' : `${wdt * 2.4} ${wdt * 0.9}`);
    line.setAttribute('stroke-dashoffset', (-t * 60).toFixed(1));
    const p1 = pts[pts.length - 1], p0 = pts[Math.max(0, pts.length - 2)];
    let ang = Math.atan2(p1[1] - p0[1], p1[0] - p0[0]);
    if (pts.length < 2 || Math.hypot(p1[0] - p0[0], p1[1] - p0[1]) < 0.5) ang = 0;
    const L = wdt * 2.6, Wd = wdt * 1.8, c = Math.cos(ang), s = Math.sin(ang);
    const P = (x, y) => `${(p1[0] + x * c - y * s).toFixed(1)},${(p1[1] + x * s + y * c).toFixed(1)}`;
    head.setAttribute('d', `M${P(L * .55, 0)}L${P(-L * .45, Wd)}L${P(-L * .2, 0)}L${P(-L * .45, -Wd)}Z`);
    g.style.opacity = clamp((a.t1 + 1.2 - t) / 0.6, 0, 1);
  }
}
const ships = D.blockade ? D.blockade.ships.map((p, i) => {
  const g = sv('g', {});
  sv('path', { d: 'M-22,0 L22,0 L15,10 L-15,10 Z', fill: '#1c2430', stroke: '#e2c27e', 'stroke-width': 2 }, g);
  sv('path', { d: 'M-2,-2 L-2,-30 L16,-6 Z', fill: '#f3e6c4', stroke: '#141414', 'stroke-width': 1.5 }, g);
  sv('path', { d: 'M-4,-4 L-4,-24 L-18,-6 Z', fill: '#f3e6c4', stroke: '#141414', 'stroke-width': 1.5 }, g);
  sv('rect', { x: 6, y: -10, width: 5, height: 9, fill: '#3a3a3a' }, g);     // a funnel: steam and sail
  return { p, g, i };
}) : [];
function drawShips(t) {
  const b = D.blockade;
  for (const { p, g, i } of ships) {
    const t0 = b.t0 + i * 0.12, on = t >= t0 && t <= b.t1;
    show(g, on); if (!on) continue;
    const q = scr(p), k = backOut((t - t0) / 0.35);
    g.setAttribute('transform', `translate(${q[0].toFixed(1)},${(q[1] + 3 * Math.sin(t * 2.4 + i)).toFixed(1)}) scale(${(1.15 * k).toFixed(3)})`);
    g.style.opacity = clamp((b.t1 - t) / 0.4, 0, 1);
  }
}

// ---------------------------------------------------------------------------------- the battles
const bursts = D.battles.map(() => [0, 1, 2].map(() => sv('circle', { fill: 'none', stroke: '#fff3c4' })));
const popup = el('div', 'plate', ui, `<div class="ttl"></div><div class="dt"></div><img class="fl a"><img class="fl b"><div class="n a"></div><div class="vs">VS</div><div class="n b"></div><div class="bar"><i></i><u></u></div><div class="res"></div>`);
popup.id = 'popup';
const pp = { ttl: popup.querySelector('.ttl'), dt: popup.querySelector('.dt'), fa: popup.querySelector('.fl.a'), fb: popup.querySelector('.fl.b'),
  na: popup.querySelector('.n.a'), nb: popup.querySelector('.n.b'), bar: popup.querySelector('.bar i'), mark: popup.querySelector('.bar u'), res: popup.querySelector('.res') };
const flash = document.getElementById('flash');
function shakeAt(t) {
  let sx = 0, sy = 0;
  for (const b of D.battles) {
    const d = t - b.t;
    if (d >= 0 && d < 0.7) { const a = 16 * (1 - d / 0.7) ** 2; sx += a * Math.sin(d * 83); sy += a * Math.cos(d * 71); }
  }
  return [sx, sy];
}
function drawBattles(t) {
  let fl = 0, cur = null;
  D.battles.forEach((b, i) => {
    const d = t - b.t;
    fl = Math.max(fl, d >= 0 && d < 0.35 ? (1 - d / 0.35) * 0.85 : 0);
    const p = scr(b.at);
    bursts[i].forEach((c, k) => {
      const dd = d - k * 0.18, on = dd >= 0 && dd < 1.1;
      show(c, on); if (!on) return;
      c.setAttribute('cx', p[0]); c.setAttribute('cy', p[1]);
      c.setAttribute('r', 10 + 140 * easeOut(dd / 1.1)); c.setAttribute('stroke-width', 10 * (1 - dd / 1.1));
      c.setAttribute('opacity', 1 - dd / 1.1);
    });
    if (d > -0.5 && d < 2.3) cur = b;
  });
  flash.style.opacity = fl.toFixed(3);
  show(popup, !!cur);
  if (!cur) return;
  const b = cur, d = t - b.t;
  const k = backOut((d + 0.5) / 0.5), o = clamp((2.3 - d) / 0.35, 0, 1);
  place(popup, 66, 452, 0.7 + 0.3 * k, 0, Math.min(1, (d + 0.5) / 0.25) * o);
  setText(pp.ttl, b.title.toUpperCase()); setText(pp.dt, b.date);
  if (pp.fa._s !== b.a.side) { pp.fa.src = D.flags[b.a.side]; pp.fa._s = b.a.side; }
  if (pp.fb._s !== b.b.side) { pp.fb.src = D.flags[b.b.side]; pp.fb._s = b.b.side; }
  const u = smooth(d / 1.1);
  const na = lerp(b.a.from, b.a.to, u), nb = lerp(b.b.from, b.b.to, u);
  setText(pp.na, fmt(na)); setText(pp.nb, fmt(nb));
  pp.na.style.color = b.a.to < b.a.from && d > 0 && d < 1.2 ? '#ff9a86' : '';
  pp.nb.style.color = b.b.to < b.b.from && d > 0 && d < 1.2 ? '#ff9a86' : '';
  const share0 = 0.5, share1 = b.winner === b.a.side ? 0.86 : 0.14;
  const sh = lerp(share0, share1, smooth((d - 0.2) / 1.0)) + 0.015 * Math.sin(t * 19) * (d > 0 && d < 1.2);
  pp.bar.style.width = (sh * 100).toFixed(2) + '%'; pp.mark.style.left = (sh * 100).toFixed(2) + '%';
  setText(pp.res, d > 1.1 ? b.result.toUpperCase() : '');
  pp.res.style.opacity = clamp((d - 1.1) / 0.25, 0, 1);
}

// --------------------------------------------------------------------- captions and lower-thirds
const capEls = D.captions.map(c => { const e = el('div', 'cap', ui, `<div class="paper">${c.text}</div>`); return { c, e }; });
function drawCaptions(t) {
  for (const { c, e } of capEls) {
    const on = t >= c.t - 0.05 && t <= c.t + c.d + 0.3;
    show(e, on); if (!on) continue;
    const k = easeOut((t - c.t) / 0.3);
    const hudOn = D.hud && t >= D.hud.t0 && t <= D.hud.t1;
    place(e, 66, (hudOn ? 322 : 168) + 24 * (1 - k), 1, 0, fade(t, c.t, c.t + c.d + 0.3, 0.2, 0.3));
  }
}
const lowEls = D.lower.map(l => {
  const e = el('div', 'lower plate', ui, `<div class="in"><span class="ar">${l.ar}</span><span class="dot"></span><span class="tr">${l.tr}</span><span class="dot"></span><span class="en">${l.en}</span></div>`);
  return { l, e };
});
function fitLower(e) {                   // shrink a long line to the plate's width, once
  if (e._fit) return; e._fit = 1;
  const inn = e.querySelector('.in'); const w = inn.offsetWidth;
  inn.style.transform = `translateX(-50%) scale(${Math.min(1, 850 / w).toFixed(3)})`;
}
function drawLower(t) {
  for (const { l, e } of lowEls) {
    const on = t >= l.t - 0.05 && t <= l.t + l.d + 0.35;
    show(e, on); if (!on) continue;
    fitLower(e);
    const k = easeOut((t - l.t) / 0.35);
    place(e, lerp(-1100, 66, k), 1112, 1, 0, fade(t, l.t, l.t + l.d + 0.35, 0.15, 0.35));
  }
}
const stamp = D.stamp ? el('div', '', ui, D.stamp.text) : null;
if (stamp) stamp.id = 'stamp';
function drawStamp(t) {
  if (!stamp) return;
  const s = D.stamp, on = t >= s.t && t <= s.t + 2.0;
  show(stamp, on); if (!on) return;
  const k = backOut((t - s.t) / 0.3);
  const w = stamp.offsetWidth || 800;
  place(stamp, 508 - w / 2, 860, 1.6 - 0.6 * k, -5, fade(t, s.t, s.t + 2.0, 0.08, 0.35));
}

// ----------------------------------------------------------------------------------- the balls
const ballEls = D.balls.map(b => {
  const c = D.cast[b.id];
  const left = b.id !== 'isa';
  const wrap = el('div', 'ball', ui, `<img src="${c.img[b.mood || 'neutral']}">`);
  const bub = el('div', 'bubble ' + (left ? 'l' : 'r'), ui, `<div class="en">${c.lines_en[b.line]}</div><span class="ar">${c.lines_ar[b.line]}</span>`);
  if (!left) wrap.querySelector('img').style.transform = 'scaleX(-1)';   // looking back across the screen
  return { b, wrap, bub, left };
});
function drawBalls(t) {
  for (const { b, wrap, bub, left } of ballEls) {
    const on = t >= b.t - 0.1 && t <= b.t + b.d + 0.35;
    show(wrap, on); show(bub, on); if (!on) continue;
    const k = backOut((t - b.t) / 0.4), out = clamp((b.t + b.d + 0.35 - t) / 0.35, 0, 1);
    const x = left ? 66 : 950 - 200, y = 1250 + 260 * (1 - k) + 260 * (1 - out);
    const hop = Math.abs(Math.sin((t - b.t) * 7)) * 10 * clamp(1 - (t - b.t) / 1.2, 0, 1);
    place(wrap, x, y - hop, 1, 4 * Math.sin(t * 5), Math.min(1, (t - b.t + 0.1) / 0.15));
    const bk = backOut((t - b.t - 0.15) / 0.3);
    const bw = bub.offsetWidth || 400;
    const bx = left ? 296 : 720 - bw;
    place(bub, bx, 1270, 0.6 + 0.4 * bk, 0, clamp((t - b.t - 0.15) / 0.12, 0, 1) * out);
    bub.style.transformOrigin = left ? '0 80%' : '100% 80%';
  }
}

// ------------------------------------------------------------------------ hook, cost, end card
const grade = el('div', '', document.getElementById('root'), ''); grade.id = 'grade';
const hook = el('div', '', ui, `<div class="sub">${D.hook.sub.toUpperCase()}</div><div class="ttl">${D.hook.title.replace(/^(\d+):/, '<b>$1:</b>')}</div>`);
hook.id = 'hook';
const globe = document.getElementById('globe');
function drawHook(t) {
  const h = D.hook, on = t <= h.t1 + 0.1;
  show(hook, on);
  if (on) {
    const k = backOut((t - 0.12) / 0.4);
    hook.style.transformOrigin = '50% 50%';
    place(hook, 66, 300, 1.35 - 0.35 * k, 0, clamp((t - 0.08) / 0.12, 0, 1) * clamp((h.t1 + 0.1 - t) / 0.35, 0, 1));
  }
  if (globe) {
    const g = D.globe; const o = clamp((g.t1 - 0.05 - t) / 0.45, 0, 1);
    globe.style.opacity = t <= g.t1 ? o : 0;
    globe.style.display = t <= g.t1 ? '' : 'none';
  }
}
const cost = D.cost ? el('div', 'plate', ui, `<div class="k">THE COST · 1861–1865</div><div class="n">0</div><div class="l">${D.cost.label} · <span class="ar">${D.cost.ar}</span></div>`) : null;
if (cost) cost.id = 'cost';
const costN = cost && cost.querySelector('.n');
function drawCost(t) {
  if (!cost) return;
  const c = D.cost, on = t >= c.t0 && t <= c.t1 + 0.3;
  show(cost, on);
  const dim = on ? fade(t, c.t0, c.t1 + 0.3, 0.4, 0.3) : 0;
  grade.style.background = dim > 0
    ? `radial-gradient(ellipse 90% 70% at 50% 46%, rgba(0,0,0,${(.35 * dim).toFixed(3)}) 30%, rgba(12,8,2,${(.5 + .3 * dim).toFixed(3)}) 100%)` : '';
  if (!on) return;
  const k = easeOut((t - c.t0) / 0.5);
  place(cost, 66, 640 + 40 * (1 - k), 1, 0, dim);
  const u = easeOut((t - c.t0 - 0.2) / 1.6);
  setText(costN, u < 1 ? fmt(c.low * u) : `${fmt(c.low)}–${fmt(c.high)}`);
}
const endc = el('div', '', ui, `<div class="box plate"><h2>THE FULL HISTORY</h2><p>${D.end.line}</p>
  <div class="discord"><b>JOIN THE DISCORD</b><span>${D.end.discord}</span></div><div class="sub">CONTROGLOBE · THE GLOBAL SWAP</div></div>`);
endc.id = 'endc';
const endBalls = ['usa', 'isa', 'zagrosia'].filter(id => D.cast[id]).map((id, i) => {
  const e = el('div', 'ball', endc, `<img src="${D.cast[id].img.happy}">`); return { e, i };
});
function drawEnd(t) {
  const t0 = D.end.t0, on = t >= t0 - 0.05;
  show(endc, on); if (!on) return;
  const k = easeOut((t - t0) / 0.45);
  place(endc, 0, 0, 1, 0, k);
  endc.querySelector('.box').style.transform = `scale(${(0.92 + 0.08 * backOut((t - t0) / 0.5)).toFixed(4)})`;
  for (const { e, i } of endBalls) {
    const hop = Math.abs(Math.sin((t - t0) * 5 + i * 1.1)) * 26;
    place(e, 110 + i * 290, 1180 - hop, 1, 3 * Math.sin(t * 4 + i), clamp((t - t0 - 0.15 * i) / 0.25, 0, 1));
  }
}

// ------------------------------------------------------------------------------------ a frame
function render(t) {
  window.__lastT = t;
  CAM = camAt(t);
  SHAKE = shakeAt(t);
  drawMap(t);
  drawArrows(t); drawShips(t); drawArmies(t); drawBattles(t);
  drawHud(t); drawCaptions(t); drawLower(t); drawStamp(t); drawBalls(t);
  drawCost(t); drawHook(t); drawEnd(t);
}

// a slice of the Short (shorts.py _segment) starts its clock at SEG_T0 and runs SEG_DUR seconds
const SEG_T0 = window.SEG_T0 || 0, SEG_DUR = window.SEG_DUR || D.duration;
render(SEG_T0);
const tl = gsap.timeline({ paused: true, onUpdate() { render(tl.time() + SEG_T0); } });
tl.to({}, { duration: SEG_DUR }, 0);
window.__timelines = window.__timelines || {};
window.__timelines.root = tl;
window.__render = render;   // for stills
