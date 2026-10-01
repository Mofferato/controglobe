// The Solms-America series engine: every frame of a phase drawn as a pure function of time.
//
// HyperFrames seeks the GSAP timeline registered at the end; its onUpdate calls render(t), which
// sets the camera over the terrain (three.js: the colour plate draped on ETOPO's relief), picks
// and crossfades the map's state, and places every overlay (names, places, the Road, armies,
// arrows, battles, numbers, the cast's bubbles, cards, the date and the infobox) for that instant.
// Nothing depends on the frame before, so any frame can be drawn in any order, by any worker.

import * as THREE from './vendor/three.module.min.js';

const D = window.DATA;
const W = D.W, H = D.H, PW = D.plate.w, PH = D.plate.h;
const root = document.getElementById('root');
const ov = document.getElementById('ov');
const ui = document.getElementById('ui');
const vec = document.getElementById('vec');
const SVGNS = 'http://www.w3.org/2000/svg';

// ---------------------------------------------------------------------------------- utilities
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const lerp = (a, b, t) => a + (b - a) * t;
const smooth = t => { t = clamp(t, 0, 1); return t * t * (3 - 2 * t); };
const ease = t => { t = clamp(t, 0, 1); return t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; };
const easeOut = t => 1 - Math.pow(1 - clamp(t, 0, 1), 3);
const backOut = t => { t = clamp(t, 0, 1); const c = 1.6; return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2); };
const fade = (t, t0, t1, fin = .4, fout = .4) => clamp(Math.min((t - t0) / fin, (t1 - t) / fout), 0, 1);
const fmt = n => Math.round(n).toLocaleString('en-US');
const fmtK = n => n >= 10000 ? (n / 1000).toFixed(n >= 100000 ? 0 : 1).replace(/\.0$/, '') + 'K' : fmt(n);
const arDigits = s => String(s).replace(/\d/g, d => '٠١٢٣٤٥٦٧٨٩'[d]);
const el = (tag, cls, parent, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; (parent || ov).appendChild(e); return e; };
const sv = (tag, attrs, parent) => { const e = document.createElementNS(SVGNS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); (parent || vec).appendChild(e); return e; };
const hexRgb = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
const rgba = (h, a) => { const [r, g, b] = hexRgb(h); return `rgba(${r},${g},${b},${a})`; };
const deep = (h, k = .62) => { const [r, g, b] = hexRgb(h); return `rgb(${Math.round(r * k)},${Math.round(g * k)},${Math.round(b * k)})`; };
const show = (e, v) => { const d = v ? '' : 'none'; if (e.style.display !== d) e.style.display = d; };
const setText = (e, s) => { if (e._t !== s) { e.textContent = s; e._t = s; } };
const setHTML = (e, s) => { if (e._h !== s) { e.innerHTML = s; e._h = s; } };
function seg(keys, t) {
  if (t <= keys[0][0]) return [0, 0];
  for (let i = 0; i < keys.length - 1; i++) if (t < keys[i + 1][0]) return [i, (t - keys[i][0]) / Math.max(1e-6, keys[i + 1][0] - keys[i][0])];
  return [Math.max(0, keys.length - 2), 1];
}
const pol = id => D.polities[id] || { colour: '#888', names: { en: id }, short: id };
const polName = id => (pol(id).short || pol(id).names.en);

// ------------------------------------------------------------------------------------ the clock
function yearAt(t) {
  const k = D.clock; const [i, f] = seg(k, t);
  if (k.length === 1) return k[0][1];
  return lerp(k[i][1], k[i + 1][1], clamp(f, 0, 1));
}
function sceneAt(t) { for (const s of D.scenes) if (t >= s.t0 && t < s.t1) return s; return D.scenes[D.scenes.length - 1]; }
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const SEASONS = ['Winter', 'Winter', 'Spring', 'Spring', 'Spring', 'Summer', 'Summer', 'Summer', 'Autumn', 'Autumn', 'Autumn', 'Winter'];
function yearLabel(a) { const y = Math.floor(a); return y <= 0 ? `${1 - y} BCE` : `${y}`; }
function dateLabel(a, mode) {
  const y = Math.floor(a); const f = a - y; const m = clamp(Math.floor(f * 12), 0, 11);
  const ys = yearLabel(a);
  if (mode === 'season') return `${SEASONS[m]} · ${ys}`;
  if (mode === 'month') return `${MONTHS[m]} ${ys}`;
  if (mode === 'day') { const d = clamp(Math.floor((f * 12 - m) * 30.4) + 1, 1, 31); return `${d} ${MONTHS[m]} ${ys}`; }
  return ys;
}

// --------------------------------------------------------------------------------------- loading
const loadImage = src => new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = src; });
const [plateImg, terrBuf] = await Promise.all([loadImage(D.plate.src), fetch(D.terrain.src).then(r => r.arrayBuffer())]);
await Promise.all(['400 40px Cinzel', '700 40px Cinzel', '700 40px "Cinzel Decorative"', '400 40px Cormorant', 'italic 400 40px Cormorant',
  '400 40px Amiri', '700 40px Amiri'].map(f => document.fonts.load(f).catch(() => null)));
await document.fonts.ready;

// ------------------------------------------------------------------------------- the 3D ground
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(1);
renderer.setSize(W, H);
renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
document.getElementById('gl').appendChild(renderer.domElement);
const maxAniso = renderer.capabilities.getMaxAnisotropy();
const SEA = new THREE.Color(0x10303f);
const scene3 = new THREE.Scene();
scene3.background = SEA;
const FOV = 32;
const camera = new THREE.PerspectiveCamera(FOV, W / H, 5, 60000);
camera.up.set(0, 0, 1);

const TW = D.terrain.w, TH = D.terrain.h;
const heights = new Int16Array(terrBuf);
const EXAG = 11.0;
const ZS = EXAG / D.m_per_px;                   // metres to plate pixels, exaggerated
const geo = new THREE.PlaneGeometry(PW, PH, TW - 1, TH - 1);
{
  const pos = geo.attributes.position;
  for (let i = 0; i < pos.count; i++) pos.setZ(i, heights[i] * ZS);
  geo.computeVertexNormals();
}
const tex = new THREE.Texture(plateImg);
tex.colorSpace = THREE.NoColorSpace; tex.anisotropy = maxAniso; tex.generateMipmaps = true;
tex.minFilter = THREE.LinearMipmapLinearFilter; tex.needsUpdate = true;

const CW = 4096, CH = Math.round(4096 * PH / PW), CK = CW / PW;
function canvasTex(c) {
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.NoColorSpace; t.anisotropy = maxAniso;
  t.minFilter = THREE.LinearMipmapLinearFilter; t.generateMipmaps = true; return t;
}
const blankC = document.createElement('canvas'); blankC.width = 4; blankC.height = 4;
const blankT = canvasTex(blankC);

const mat = new THREE.ShaderMaterial({
  uniforms: {
    uPlate: { value: tex }, uA: { value: blankT }, uB: { value: blankT }, uProv: { value: blankT }, uMix: { value: 0 },
    uPolAlpha: { value: 1 }, uProvAlpha: { value: .5 }, uLight: { value: .55 },
    uLightDir: { value: new THREE.Vector3(-0.55, 0.65, 0.75).normalize() },
    uFog: { value: new THREE.Vector3(SEA.r, SEA.g, SEA.b) }, uFogNear: { value: 1e5 }, uFogFar: { value: 2e5 },
    uDim: { value: 0 }, uWarm: { value: 0 },
  },
  vertexShader: `
    varying vec2 vUv; varying vec3 vN; varying float vDepth;
    void main(){ vUv = uv; vN = normal; vec4 mv = modelViewMatrix * vec4(position,1.0); vDepth = -mv.z; gl_Position = projectionMatrix * mv; }`,
  fragmentShader: `
    uniform sampler2D uPlate, uA, uB, uProv; uniform float uMix, uPolAlpha, uProvAlpha, uLight, uFogNear, uFogFar, uDim, uWarm;
    uniform vec3 uLightDir, uFog; varying vec2 vUv; varying vec3 vN; varying float vDepth;
    void main(){
      vec3 base = texture2D(uPlate, vUv).rgb;
      vec4 a = texture2D(uA, vUv), b = texture2D(uB, vUv);
      vec4 p = mix(a, b, uMix);
      vec3 col = mix(base, p.rgb, p.a * uPolAlpha);
      float pl = texture2D(uProv, vUv).a * uProvAlpha;
      col = mix(col, vec3(0.22,0.16,0.10), pl);
      float l = max(dot(normalize(vN), uLightDir), 0.0);
      col *= mix(1.0, 0.80 + 0.40 * l, uLight);
      col = mix(col, col * vec3(1.06, 0.98, 0.86), uWarm);
      col *= 1.0 - uDim;
      // the plate's edges fade into a mist, so no frame shows where the map ends
      vec2 e = min(vUv, 1.0 - vUv);
      float edge = 1.0 - smoothstep(0.0, 0.07, min(e.x * 1.5, e.y));
      col = mix(col, uFog, edge);
      float f = smoothstep(uFogNear, uFogFar, vDepth);
      gl_FragColor = vec4(mix(col, uFog, f), 1.0);
    }`,
});
const mesh = new THREE.Mesh(geo, mat);
scene3.add(mesh);
// the sea beyond the plate, under it
const seaPlane = new THREE.Mesh(new THREE.PlaneGeometry(PW * 6, PH * 6), new THREE.MeshBasicMaterial({ color: 0x10303f }));
seaPlane.position.z = -2; scene3.add(seaPlane);

// heights for overlays (bilinear, in plate pixels)
function heightAt(x, y) {
  const fx = clamp(x / PW * (TW - 1), 0, TW - 1), fy = clamp(y / PH * (TH - 1), 0, TH - 1);
  const x0 = Math.floor(fx), y0 = Math.floor(fy), x1 = Math.min(x0 + 1, TW - 1), y1 = Math.min(y0 + 1, TH - 1);
  const ax = fx - x0, ay = fy - y0;
  const h = (heights[y0 * TW + x0] * (1 - ax) + heights[y0 * TW + x1] * ax) * (1 - ay) + (heights[y1 * TW + x0] * (1 - ax) + heights[y1 * TW + x1] * ax) * ay;
  return Math.max(0, h) * ZS;
}
const _v = new THREE.Vector3();
function project(x, y, lift = 0) {
  _v.set(x - PW / 2, PH / 2 - y, heightAt(x, y) + lift).project(camera);
  return [(_v.x + 1) / 2 * W, (1 - _v.y) / 2 * H, _v.z < 1 && _v.z > -1];
}
let camDist = 1;
const pxScale = (x, y) => {          // screen pixels per plate pixel at a point
  _v.set(x - PW / 2, PH / 2 - y, heightAt(x, y));
  const d = _v.distanceTo(camera.position);
  return H / (2 * d * Math.tan(FOV * Math.PI / 360));
};

// -------------------------------------------------------------------------------- the camera
const shakes = [];
for (const w of Object.values(D.wars)) for (const b of w.battles) shakes.push([b.t, b.general_falls ? 10 : 7]);
function cameraAt(t) {
  const k = D.camera; const [i, f] = seg(k, t);
  const a = k[i], b = k[Math.min(i + 1, k.length - 1)], e = ease(f);
  const x = lerp(a[1], b[1], e), y = lerp(a[2], b[2], e);
  const span = Math.exp(lerp(Math.log(a[3]), Math.log(b[3]), e));
  const tilt = lerp(a[4], b[4], e), head = lerp(a[5], b[5], e);
  let sx = 0, sy = 0;
  for (const [ts, amp] of shakes) {
    const u = t - ts; if (u < 0 || u > 1.1) continue;
    const k2 = amp * Math.exp(-u * 4.5) * span / 1080;
    sx += k2 * Math.sin(u * 61.0); sy += k2 * Math.cos(u * 47.0);
  }
  // a slow breath, so a held shot never freezes
  const br = Math.sin(t * 0.21) * span * 0.004;
  // keep the frame on the plate: half the view's width (wider when tilted) inside each edge
  const hw = span * (W / H) * 0.5 * (1 + tilt / 90) + span * 0.1, hh = span * 0.5 * (1 + tilt / 120);
  const cx = PW > 2 * hw ? clamp(x + sx + br, hw, PW - hw) : PW / 2;
  const cy = PH > 2 * hh ? clamp(y + sy, hh * 1.25, PH - hh * 1.02) : PH / 2;
  return { x: cx, y: cy, span, tilt, head };
}
function placeCamera(c) {
  const d = (c.span / 2) / Math.tan(FOV * Math.PI / 360);
  camDist = d;
  const tl = c.tilt * Math.PI / 180, hd = c.head * Math.PI / 180;
  const tx = c.x - PW / 2, ty = PH / 2 - c.y;
  const tz = heightAt(c.x, c.y) * 0.6;
  // the camera faces along the heading (0 north, 90 east) and stands back from the target, up
  const fx = Math.sin(hd), fy = Math.cos(hd);
  camera.position.set(tx - fx * Math.sin(tl) * d, ty - fy * Math.sin(tl) * d, tz + Math.cos(tl) * d);
  camera.up.set(fx, fy, 0);
  camera.lookAt(tx, ty, tz);
  camera.near = Math.max(2, d * 0.02); camera.far = d * 8;
  if (c.offset) camera.setViewOffset(W, H, c.offset, 0, W, H); else camera.clearViewOffset();
  camera.updateProjectionMatrix();
  mat.uniforms.uFogNear.value = d * 1.4 + c.span * 0.2; mat.uniforms.uFogFar.value = d * 3.2 + c.span * 1.2;
}

// ----------------------------------------------------------------------- the map's layers
const pathCache = new Map();
const P2 = d => { let p = pathCache.get(d); if (!p) { p = new Path2D(d); pathCache.set(d, p); } return p; };
const patternCache = new Map();
function stripes(ctx, colour, width, alpha, dense) {
  const key = colour + width + alpha + dense;
  if (patternCache.has(key)) return patternCache.get(key);
  const s = dense ? 22 : 30; const c = document.createElement('canvas'); c.width = c.height = s;
  const x = c.getContext('2d'); x.strokeStyle = rgba(colour, alpha); x.lineWidth = width;
  for (const o of [-s, 0, s]) { x.beginPath(); x.moveTo(o, s); x.lineTo(o + s, 0); x.stroke(); }
  const p = ctx.createPattern(c, 'repeat'); patternCache.set(key, p); return p;
}
function drawState(c, st) {
  const x = c.getContext('2d');
  x.clearRect(0, 0, CW, CH);
  x.save(); x.scale(CK, CK);
  for (const r of st.regions) {
    const col = pol(r.p).colour; const p = P2(r.d);
    x.fillStyle = rgba(col, 0.62); x.fill(p, 'evenodd');
    if (r.st.startsWith('client:')) {
      const over = pol(r.st.slice(7)).colour;
      x.fillStyle = stripes(x, over, 7, 0.55, false); x.fill(p, 'evenodd');
    } else if (r.st.startsWith('occupied:')) {
      const by = pol(r.st.slice(9)).colour;
      x.fillStyle = stripes(x, by, 11, 0.85, true); x.fill(p, 'evenodd');
    }
  }
  for (const r of st.polities) {
    const col = pol(r.p).colour; const p = P2(r.d);
    x.save(); x.clip(p, 'evenodd');
    x.lineWidth = 26; x.strokeStyle = rgba(deep(col, .55), .55); x.stroke(p);
    x.lineWidth = 9; x.strokeStyle = rgba(deep(col, .45), .7); x.stroke(p);
    x.restore();
    x.lineWidth = 3.2; x.strokeStyle = 'rgba(28,20,12,0.9)'; x.stroke(p);
  }
  x.restore();
}
function drawModern(c, marches) {
  const x = c.getContext('2d');
  x.clearRect(0, 0, CW, CH);
  x.save(); x.scale(CK, CK);
  for (const n of D.modern.nations) {
    const p = P2(n.d);
    x.fillStyle = rgba(n.k === 'solms' ? '#2a9d8f' : n.colour, n.k === 'solms' ? 0.5 : 0.30); x.fill(p, 'evenodd');
    x.lineWidth = 2.4; x.strokeStyle = 'rgba(28,20,12,0.75)'; x.stroke(p);
  }
  if (marches) for (const m of D.modern.marches) {
    const p = P2(m.d);
    x.fillStyle = rgba(m.colour, 0.55); x.fill(p, 'evenodd');
    x.lineWidth = 1.6; x.strokeStyle = 'rgba(28,20,12,0.6)'; x.stroke(p);
  }
  const s = D.modern.nations.find(n => n.k === 'solms');
  if (s) { const p = P2(s.d); x.save(); x.clip(p, 'evenodd'); x.lineWidth = 30; x.strokeStyle = 'rgba(16,80,74,0.55)'; x.stroke(p); x.restore();
    x.lineWidth = 5; x.strokeStyle = 'rgba(12,40,38,0.95)'; x.stroke(p); }
  x.restore();
}
// provinces: the GRASS half-basins, fine lines under everything
const provC = document.createElement('canvas'); provC.width = CW; provC.height = CH;
{
  const x = provC.getContext('2d'); x.scale(CK, CK); x.lineWidth = 1.6; x.strokeStyle = 'rgba(0,0,0,0.42)';
  for (const d of D.provinces) x.stroke(new Path2D(d));
}
mat.uniforms.uProv.value = canvasTex(provC);

const stateTex = new Map();     // index -> {c, t, used}
let useClock = 0;
function texFor(key, draw) {
  let s = stateTex.get(key);
  if (!s) {
    if (stateTex.size >= 4) {
      let old = null; for (const [k, v] of stateTex) if (!old || v.used < old[1].used) old = [k, v];
      old[1].t.dispose(); stateTex.delete(old[0]);
    }
    const c = document.createElement('canvas'); c.width = CW; c.height = CH; draw(c);
    s = { c, t: canvasTex(c), used: 0 }; stateTex.set(key, s);
  }
  s.used = ++useClock; return s.t;
}
const stateTexture = i => texFor('s' + i, c => drawState(c, D.states[i]));
const modernTexture = m => texFor(m ? 'modern+' : 'modern', c => drawModern(c, m));
function stateNow(t) {
  const k = D.stateKeys; let i = 0;
  for (let j = 0; j < k.length; j++) if (k[j][0] <= t) i = j;
  const cur = k[i][1], prev = i > 0 ? k[i - 1][1] : cur;
  const f = i > 0 ? smooth((t - k[i][0]) / 0.7) : 1;
  return { cur, prev, f };
}

// ------------------------------------------------------------------------------ the overlays
// names of the polities on the map
const polLabels = {};
function polLabel(p) {
  if (polLabels[p]) return polLabels[p];
  const e = el('div', 'plabel'); const n = el('div', 'pl-name', e); const s = el('div', 'pl-sub', e);
  const N = pol(p).names || {};
  n.textContent = polName(p).toUpperCase();
  const parts = [N.de && N.de !== polName(p) ? N.de : null, N.native ? N.native.word : null, N.ar].filter(Boolean);
  s.innerHTML = parts.map((v, i) => i === parts.length - 1 && N.ar === v ? `<span class="ar">${v}</span>` : v).join(' · ');
  return (polLabels[p] = { e, n, s });
}
function drawPolLabels(t, sc, st) {
  const seen = new Set();
  if (sc.map === 'history') {
    const list = [[D.states[st.cur], st.f], ...(st.f < 1 && st.prev !== st.cur ? [[D.states[st.prev], 1 - st.f]] : [])];
    const pos = {};
    for (const [S, a] of list) for (const r of S.polities) {
      if (r.p === 'bison') continue;
      const o = pos[r.p] || (pos[r.p] = { x: 0, y: 0, w: 0, a: 0, ang: 0, km2: 0 });
      o.x += r.c[0] * a; o.y += r.c[1] * a; o.w += r.w * a; o.a += a; o.ang += r.ang * a; o.km2 = Math.max(o.km2, r.km2);
    }
    for (const p in pos) {
      const o = pos[p]; const x = o.x / o.a, y = o.y / o.a, w = o.w / o.a;
      const L = polLabel(p); seen.add(p);
      const [sx, sy, vis] = project(x, y, 6);
      const s = pxScale(x, y);
      const fs = clamp(w * 0.15, 26, 150) * s;
      if (!vis || fs < 12 || sx < -200 || sx > W + 200 || sy < -100 || sy > H + 100) { show(L.e, false); continue; }
      show(L.e, true);
      const size = Math.min(fs, sc.war ? 34 : 66);
      L.e.style.transform = `translate(${sx.toFixed(1)}px,${sy.toFixed(1)}px) translate(-50%,-50%) rotate(${clamp(o.ang / o.a - cam.head, -28, 28).toFixed(1)}deg)`;
      L.n.style.fontSize = size.toFixed(1) + 'px';
      L.s.style.fontSize = (size * 0.36).toFixed(1) + 'px';
      L.s.style.display = size > 24 && !sc.war ? '' : 'none';
      L.e.style.opacity = clamp(o.a, 0, 1) * clamp((fs - 12) / 8, 0, 1) * sceneFade * (sc.war ? 0.72 : 1);
    }
  }
  for (const p in polLabels) if (!seen.has(p)) show(polLabels[p].e, false);
}

// modern nations and marches (cold open, premise)
const modernLabels = [];
for (const n of (D.modern.nations || [])) {
  const e = el('div', 'mlabel' + (n.k === 'solms' ? ' solms' : ''), ov,
    `<b>${n.name.toUpperCase()}</b><i>${n.twin}</i>`);
  modernLabels.push({ e, n, march: false });
}
for (const m of (D.modern.marches || [])) {
  const e = el('div', 'mlabel march', ov, `<b>${m.name}</b><i>${m.twin}</i><span class="ar">${m.ar}</span>`);
  modernLabels.push({ e, n: m, march: true });
}
function drawModernLabels(t, sc) {
  const on = sc.map === 'modern';
  for (const L of modernLabels) {
    const want = on && (L.march ? sc.marches : (!sc.marches || L.n.k !== 'solms'));
    if (!want) { show(L.e, false); continue; }
    const [sx, sy, vis] = project(L.n.c[0], L.n.c[1], 6);
    if (!vis) { show(L.e, false); continue; }
    show(L.e, true);
    const sz = L.march ? 15 : (L.n.size === 'big' ? 19 : 13);
    L.e.style.fontSize = sz + 'px';
    L.e.style.transform = `translate(${sx.toFixed(1)}px,${sy.toFixed(1)}px) translate(-50%,-50%)`;
    L.e.style.opacity = sceneFade * (L.march ? fade(t, sc.t0 + 2.0, sc.t1, 1.0, .6) : 1);
  }
}

// geographic names (the tour of the land) and the peoples of 500 BCE
const regionLabels = D.regions.map((r, i) => ({ r, i, e: el('div', 'rlabel' + (r.water ? ' water' : ''), ov,
  `<b>${r.en}</b>${r.twin ? `<em>${r.twin}</em>` : ''}<i>${r.de}</i><span class="ar">${r.ar}</span>`) }));
function drawRegions(t, sc) {
  for (const L of regionLabels) {
    if (!sc.regions) { show(L.e, false); continue; }
    const [sx, sy, vis] = project(L.r.xy[0], L.r.xy[1], 8);
    if (!vis) { show(L.e, false); continue; }
    show(L.e, true);
    const a = fade(t, sc.t0 + 0.8 + L.i * 0.55, sc.t1 - 0.3, .8, .6);
    L.e.style.opacity = a;
    L.e.style.fontSize = (17 * L.r.size) + 'px';
    L.e.style.transform = `translate(${sx.toFixed(1)}px,${sy.toFixed(1)}px) translate(-50%,-50%) rotate(${(L.r.ang || 0) * 0.35}deg)`;
  }
}
const peopleLabels = D.peoples.map((r, i) => ({ r, i, e: el('div', 'people', ov,
  (r.p ? `<img src="assets/balls/${r.p}_neutral.svg">` : '') + `<div><b>${r.en}</b><i>${r.de}</i><span class="ar">${r.ar}</span></div>`) }));
function drawPeoples(t, sc) {
  for (const L of peopleLabels) {
    if (!sc.peoples) { show(L.e, false); continue; }
    const [sx, sy, vis] = project(L.r.xy[0], L.r.xy[1], 8);
    if (!vis) { show(L.e, false); continue; }
    show(L.e, true);
    const t0 = sc.t0 + (L.r.t != null ? L.r.t : 1 + L.i * .6);
    L.e.style.opacity = fade(t, t0, sc.t1 - 0.2, .6, .6);
    L.e.style.transform = `translate(${sx.toFixed(1)}px,${sy.toFixed(1)}px) translate(-50%,-50%) scale(${(0.7 + 0.3 * backOut((t - t0) / .5)).toFixed(3)})`;
  }
}

// places
const ICON = {
  capital: '<svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="7.5" fill="#f4ead2" stroke="#2a1d10" stroke-width="2"/><path d="M10 4.6l1.6 3.4 3.7.4-2.8 2.5.8 3.7L10 12.7l-3.3 1.9.8-3.7-2.8-2.5 3.7-.4z" fill="#8a1d1d"/></svg>',
  holy: '<svg viewBox="0 0 20 20"><rect x="3.5" y="3.5" width="13" height="13" transform="rotate(45 10 10)" fill="#2fb3a6" stroke="#10302c" stroke-width="2"/><circle cx="10" cy="10" r="2.4" fill="#f4ead2"/></svg>',
  town: '<svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="5.5" fill="#f4ead2" stroke="#2a1d10" stroke-width="2"/></svg>',
  mine: '<svg viewBox="0 0 20 20"><path d="M10 2l6 6-6 10-6-10z" fill="#33c2b0" stroke="#10302c" stroke-width="1.8"/></svg>',
  observatory: '<svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="4.5" fill="#e8b33c" stroke="#5a3d10" stroke-width="1.5"/><g stroke="#e8b33c" stroke-width="1.8"><path d="M10 1v3M10 16v3M1 10h3M16 10h3M3.6 3.6l2 2M14.4 14.4l2 2M3.6 16.4l2-2M14.4 5.6l2-2"/></g></svg>',
  work: '<svg viewBox="0 0 20 20"><rect x="3" y="6" width="14" height="8" fill="#6c5a44" stroke="#2a1d10" stroke-width="1.6"/><path d="M3 10h14" stroke="#4d9fd6" stroke-width="2.4"/></svg>',
  port: '<svg viewBox="0 0 20 20"><path d="M3 11h14l-3 4H6z" fill="#8a5a2b" stroke="#2a1d10" stroke-width="1.5"/><path d="M10 3v8M10 4l5 5h-5" fill="#f4ead2" stroke="#2a1d10" stroke-width="1.2"/></svg>',
  site: '<svg viewBox="0 0 20 20"><circle cx="10" cy="10" r="5" fill="none" stroke="#2a1d10" stroke-width="2"/></svg>',
};
const placeEls = D.places.map(p => {
  const n = p.name; const sub = [n.de && n.de !== n.en ? n.de : null, n.native && n.native !== n.en ? n.native : null].filter(Boolean).join(' · ');
  const e = el('div', 'place ' + p.kind, ov, `<span class="pin">${ICON[p.kind] || ICON.town}</span><span class="pn"><b>${n.en}</b>${sub ? `<i>${sub}</i>` : ''}<span class="ar">${n.ar || ''}</span></span>`);
  return { p, e };
});
function drawPlaces(t, sc, year) {
  for (const { p, e } of placeEls) {
    const minor = !(p.kind === 'capital' || p.kind === 'holy');
    const on = sc.map === 'history' && year >= p.from && year < p.to && !(sc.war && minor) && !sc.peoples;
    if (!on) { show(e, false); continue; }
    const [sx, sy, vis] = project(p.xy[0], p.xy[1], 3);
    const s = pxScale(p.xy[0], p.xy[1]);
    const big = p.kind === 'capital' || p.kind === 'holy';
    if (!vis || (s < (big ? 0.11 : 0.2))) { show(e, false); continue; }
    show(e, true);
    const k = clamp(s * 3.2, 0.62, 1.15);
    e.style.transform = `translate(${sx.toFixed(1)}px,${sy.toFixed(1)}px) scale(${k.toFixed(3)})`;
    e.style.opacity = sceneFade;
    e.classList.toggle('named', s > (big ? 0.16 : 0.3));
  }
}

// the Road
const routeTimes = D.routes.map(r => tOfYear(r.from));
function tOfYear(a) { const k = D.clock; for (let i = 0; i < k.length - 1; i++) if (k[i][1] < a && a <= k[i + 1][1]) return k[i][0] + (a - k[i][1]) / (k[i + 1][1] - k[i][1]) * (k[i + 1][0] - k[i][0]); return a <= k[0][1] ? -1 : 1e9; }
function catmull(pts, n = 6) {
  if (pts.length < 3) return pts.slice();
  const out = [];
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(i - 1, 0)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(i + 2, pts.length - 1)];
    for (let j = 0; j < n; j++) {
      const u = j / n, u2 = u * u, u3 = u2 * u;
      out.push([0, 1].map(k => 0.5 * ((2 * p1[k]) + (-p0[k] + p2[k]) * u + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * u2 + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * u3)));
    }
  }
  out.push(pts[pts.length - 1]); return out;
}
const routeEls = D.routes.map(r => {
  const dense = catmull(r.pts, 8);
  const g = sv('g', { class: 'route' });
  const glow = sv('path', { class: 'route-glow' }, g), line = sv('path', { class: 'route-line' }, g);
  return { r, dense, g, glow, line };
});
const routeLabel = el('div', 'route-label', ov, D.routes[0] && D.routes[0].name ? `<b>${D.routes[0].name.en}</b><i>${D.routes[0].name.de}</i><span class="ar">${D.routes[0].name.ar}</span>` : '');
function projPath(pts, lift = 4) {
  let d = ''; const scr = [];
  for (const p of pts) { const [x, y] = project(p[0], p[1], lift); scr.push([x, y]); d += (d ? 'L' : 'M') + x.toFixed(1) + ',' + y.toFixed(1); }
  return { d, scr };
}
function drawRoutes(t, sc, year) {
  for (let i = 0; i < routeEls.length; i++) {
    const R = routeEls[i]; const t0 = routeTimes[i];
    const on = sc.map === 'history' && year >= R.r.from;
    if (!on) { show(R.g, false); if (i === 0) show(routeLabel, false); continue; }
    show(R.g, true);
    const grow = t0 < 0 ? 1 : clamp((t - t0) / 3.5, 0, 1);
    const n = Math.max(2, Math.round(R.dense.length * easeOut(grow)));
    const { d } = projPath(R.dense.slice(0, n));
    R.glow.setAttribute('d', d); R.line.setAttribute('d', d);
    R.line.style.strokeDashoffset = (-t * 26).toFixed(1);
    R.g.style.opacity = sceneFade * (sc.war ? 0.45 : 1);
    if (i === 0) {
      const mid = R.dense[Math.floor(R.dense.length * 0.36)];
      const [sx, sy, vis] = project(mid[0], mid[1], 6);
      show(routeLabel, vis && !sc.war && grow > 0.6);
      routeLabel.style.transform = `translate(${sx.toFixed(1)}px,${sy.toFixed(1)}px) translate(12px,-50%)`;
      routeLabel.style.opacity = sceneFade * smooth((grow - 0.6) / 0.4);
    }
  }
  if (!routeEls.length) show(routeLabel, false);
}
// goods along the road
const GOOD = {
  turquoise: '<svg viewBox="0 0 20 20"><path d="M10 1l7 6-3 11H6L3 7z" fill="#36c9b4" stroke="#0d3b35" stroke-width="1.6"/><path d="M7 7h6" stroke="#bff3ea" stroke-width="1.4"/></svg>',
  macaw: '<svg viewBox="0 0 20 20"><ellipse cx="9" cy="10" rx="5" ry="6.5" fill="#d7262b" stroke="#2a0d0d" stroke-width="1.4"/><path d="M5 12q3 6 8 6l-2-4z" fill="#2a7fd4"/><path d="M12 6q4-1 4 3l-3-1z" fill="#f2c230"/></svg>',
  cacao: '<svg viewBox="0 0 20 20"><ellipse cx="10" cy="10" rx="5" ry="8" fill="#8a4a1f" stroke="#2a150a" stroke-width="1.4"/><path d="M10 3v14M7 5q-1 5 0 10M13 5q1 5 0 10" stroke="#5a2e12" stroke-width="1" fill="none"/></svg>',
  shell: '<svg viewBox="0 0 20 20"><path d="M10 2a8 8 0 0 1 8 8q0 7-8 8-8-1-8-8a8 8 0 0 1 8-8z" fill="#f6efe2" stroke="#3d3226" stroke-width="1.4"/><path d="M10 4v13M6 6l3 11M14 6l-3 11" stroke="#c9b48f" stroke-width="1"/></svg>',
  salt: '<svg viewBox="0 0 20 20"><path d="M4 7l6-4 6 4v7l-6 4-6-4z" fill="#fbfaf6" stroke="#3d3d3d" stroke-width="1.4"/><path d="M4 7l6 4 6-4M10 11v7" stroke="#b9b9b9" stroke-width="1"/></svg>',
};
const goodEls = [];
for (const g of D.goods) for (let k = 0; k < 3; k++) goodEls.push({ g, k, e: el('div', 'good', ov, GOOD[g.icon] || '') });
function polylineAt(pts, u) {
  let L = 0; const seglen = [];
  for (let i = 0; i < pts.length - 1; i++) { const l = Math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]); seglen.push(l); L += l; }
  let d = u * L;
  for (let i = 0; i < seglen.length; i++) { if (d <= seglen[i]) { const f = d / seglen[i]; return [lerp(pts[i][0], pts[i + 1][0], f), lerp(pts[i][1], pts[i + 1][1], f)]; } d -= seglen[i]; }
  return pts[pts.length - 1];
}
function drawGoods(t, sc, year) {
  for (const G of goodEls) {
    const R = routeEls.find(r => r.r.id === G.g.route);
    if (!R || !sc.goods || year < R.r.from) { show(G.e, false); continue; }
    let u = ((t * 0.035 + G.k / 3 + (G.g.icon.length * 0.07)) % 1); if (G.g.dir < 0) u = 1 - u;
    const [x, y] = polylineAt(R.dense, u);
    const [sx, sy, vis] = project(x, y, 8);
    if (!vis) { show(G.e, false); continue; }
    show(G.e, true);
    G.e.style.transform = `translate(${sx.toFixed(1)}px,${sy.toFixed(1)}px) translate(-50%,-50%) translateY(${(Math.sin(t * 4 + G.k) * 2).toFixed(1)}px)`;
    G.e.style.opacity = sceneFade * clamp(Math.min(u, 1 - u) * 8, 0, 1) * clamp((t - sc.t0) / 1.5, 0, 1);
  }
}

// --------------------------------------------------------------------------------- the wars
function armyAt(a, t) {
  const k = a.keys;
  if (t < k[0][0] || t > k[k.length - 1][0] + 0.5) return null;
  const [i, f] = seg(k, t); const e = smooth(f);
  const A = k[i], B = k[Math.min(i + 1, k.length - 1)];
  return { x: lerp(A[1], B[1], e), y: lerp(A[2], B[2], e), n: lerp(A[3], B[3], f) };
}
const warEls = {};
function warLayer(id) {
  if (warEls[id]) return warEls[id];
  const w = D.wars[id];
  const L = { armies: [], arrows: [], battles: [], sieges: [], bignum: [], attr: [], extra: {} };
  for (const a of w.armies) {
    const fleet = a.kind === 'fleet';
    const e = el('div', 'army ' + (fleet ? 'fleet' : ''), ov,
      `<div class="plaque" style="--c:${pol(a.side).colour}">` +
      (fleet ? `<span class="canoes">${'<i></i>'.repeat(5)}</span>` : `<img class="ban" src="assets/flags/${a.side}.svg">`) +
      `<span class="num"></span></div><div class="nm">${a.name}</div>` +
      (a.litter ? `<div class="litter"><svg viewBox="0 0 40 24"><rect x="8" y="2" width="24" height="12" rx="2" fill="#a3262a" stroke="#2a0d0d" stroke-width="1.6"/><path d="M1 16h38" stroke="#6b4a2f" stroke-width="3"/><path d="M14 2l6-2 6 2" fill="#e8b33c"/></svg>the great litter</div>` : ''));
    L.armies.push({ a, e, num: e.querySelector('.num') });
  }
  for (const ar of w.arrows) {
    const g = sv('g', { class: 'arrow' + (ar.retreat ? ' retreat' : '') + (ar.river ? ' river' : '') });
    const body = sv('path', { class: 'ab', fill: rgba(pol(ar.side).colour, ar.retreat ? 0.5 : 0.82), stroke: deep(pol(ar.side).colour, .45) }, g);
    L.arrows.push({ ar, g, body, dense: catmull(ar.pts, 8) });
  }
  if (w.shortcut) {
    const g = sv('g', { class: 'shortcut' }); const p = sv('path', {}, g);
    const lab = el('div', 'note', ov, w.shortcut.label);
    L.extra.shortcut = { s: w.shortcut, g, p, lab, dense: catmull(w.shortcut.pts, 8) };
  }
  for (const b of w.battles) {
    const e = el('div', 'battle', ov,
      `<div class="flash"></div><svg class="ring" viewBox="0 0 100 100"><circle cx="50" cy="50" r="42" class="r0"/><circle cx="50" cy="50" r="42" class="r1"/>
       <path d="M30 70L70 30M70 70L30 30" class="spears"/><path d="M66 26l8-2-2 8M34 26l-8-2 2 8" class="tips"/></svg>
       <div class="bn">${b.name}</div><div class="cas">${b.sides.map(s => `<span style="color:${pol(s[0]).colour}">−${fmt(s[1] - s[2])}</span>`).join('')}</div>` +
      (b.general_falls ? `<div class="falls">${b.general_falls === 'caddo' ? 'The Caddo king falls' : 'The general falls'}</div>` : ''));
    L.battles.push({ b, e, flash: e.querySelector('.flash'), r1: e.querySelector('.r1'), cas: e.querySelector('.cas'), falls: e.querySelector('.falls') });
  }
  for (const s of w.sieges) {
    const e = el('div', 'siege', ov, `<svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="40" class="r0"/><circle cx="50" cy="50" r="40" class="r1" style="stroke:${pol(s.by).colour}"/>
      <path d="M32 66V44h8v6h6v-6h8v6h6v-6h8v22z" class="fort"/></svg><div class="sn">Siege of ${s.name}</div><div class="sd"></div>`);
    L.sieges.push({ s, e, r1: e.querySelector('.r1'), sd: e.querySelector('.sd') });
  }
  for (const b of w.bignum) {
    const e = el('div', 'bignum', ov, '<span></span>'); e.style.setProperty('--c', pol(b.side).colour);
    L.bignum.push({ b, e, s: e.querySelector('span') });
  }
  for (const a of w.attrition) L.attr.push({ a, e: el('div', 'attr', ov, `<svg viewBox="0 0 20 20"><path d="M10 2q6 7 6 11a6 6 0 0 1-12 0q0-4 6-11z" fill="#9fd3f2" stroke="#1f3f55" stroke-width="1.4"/></svg>−${fmt(a.n)}`) });
  if (w.fever) L.extra.fever = { e: el('div', 'fever', ov, '<div class="spots"></div><b>Spotted fever</b>') };
  if (w.headgate) L.extra.headgate = { e: el('div', 'event-pop water', ov, '<svg viewBox="0 0 40 40"><path d="M6 10h28v8H6z" fill="#6c5a44" stroke="#2a1d10" stroke-width="2"/><path d="M14 18l-4 16M20 18v18M26 18l4 16" stroke="#4d9fd6" stroke-width="4" stroke-linecap="round"/><path d="M18 10l2 4 2-4" stroke="#1a1a1a" stroke-width="2" fill="none"/></svg><b>The Great Headgate breaks</b>') };
  if (w.viceroy_dies) L.extra.viceroy = { e: el('div', 'event-pop', ov, '<b>The viceroy dies on the road</b>') };
  if (w.capture) L.extra.capture = { e: el('div', 'event-pop', ov, `<b>${w.capture.text}</b>`) };
  return (warEls[id] = L);
}
function sideStrength(w, side, t) {
  let s = 0, any = false;
  for (const a of w.armies) if (a.side === side && a.kind !== 'fleet') { const p = armyAt(a, t); if (p) { s += p.n; any = true; } }
  return any ? s : null;
}
function arrowPath(dense, g, wpx, retreat) {
  const n = Math.max(2, Math.round(dense.length * g)); const pts = [];
  for (let i = 0; i < n; i++) { const [x, y] = project(dense[i][0], dense[i][1], 10); pts.push([x, y]); }
  if (n < dense.length && g > 0) {
    const fi = dense.length * g - (n - 1);
    const a = dense[n - 1], b = dense[Math.min(n, dense.length - 1)];
    const [x, y] = project(lerp(a[0], b[0], fi), lerp(a[1], b[1], fi), 10); pts.push([x, y]);
  }
  if (pts.length < 2) return '';
  const L = [], R = [];
  for (let i = 0; i < pts.length; i++) {
    const p = pts[i], q = pts[Math.min(i + 1, pts.length - 1)], o = pts[Math.max(i - 1, 0)];
    let dx = q[0] - o[0], dy = q[1] - o[1]; const l = Math.hypot(dx, dy) || 1; dx /= l; dy /= l;
    const k = i / (pts.length - 1); const ww = wpx * (0.45 + 0.55 * Math.min(1, k * 3)) / 2;
    L.push([p[0] - dy * ww, p[1] + dx * ww]); R.push([p[0] + dy * ww, p[1] - dx * ww]);
  }
  const e = pts[pts.length - 1], f = pts[Math.max(pts.length - 3, 0)];
  let dx = e[0] - f[0], dy = e[1] - f[1]; const l = Math.hypot(dx, dy) || 1; dx /= l; dy /= l;
  const hw = wpx * 1.05, hl = wpx * 1.5;
  const tip = [e[0] + dx * hl, e[1] + dy * hl], h1 = [e[0] - dy * hw, e[1] + dx * hw], h2 = [e[0] + dy * hw, e[1] - dx * hw];
  const ring = [...L, h1, tip, h2, ...R.reverse()];
  return 'M' + ring.map(p => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join('L') + 'Z';
}
function drawWar(t, sc) {
  for (const id in D.wars) {
    const L = warLayer(id); const w = D.wars[id]; const on = sc.war === id;
    const all = [...L.armies.map(a => a.e), ...L.battles.map(b => b.e), ...L.sieges.map(s => s.e), ...L.bignum.map(b => b.e), ...L.attr.map(a => a.e),
      ...Object.values(L.extra).map(x => x.e || x.lab).filter(Boolean)];
    if (!on) { for (const e of all) show(e, false); for (const a of L.arrows) show(a.g, false); if (L.extra.shortcut) show(L.extra.shortcut.g, false); continue; }
    const scene = sc;
    // arrows
    for (const A of L.arrows) {
      const { ar } = A; const g = easeOut((t - ar.t0) / Math.max(.3, ar.t1 - ar.t0));
      if (t < ar.t0 || t > ar.t1 + 6) { show(A.g, false); continue; }
      show(A.g, true);
      const mid = ar.pts[Math.floor(ar.pts.length / 2)];
      const wpx = clamp(pxScale(mid[0], mid[1]) * (ar.small ? 18 : 34), ar.small ? 6 : 10, ar.small ? 14 : 30);
      A.body.setAttribute('d', arrowPath(A.dense, g, wpx, ar.retreat));
      A.g.style.opacity = clamp((ar.t1 + 6 - t) / 1.5, 0, 1) * clamp((t - ar.t0) / .3, 0, 1);
    }
    if (L.extra.shortcut) {
      const S = L.extra.shortcut; const vis = t > S.s.t0 && t < S.s.t1 + 2;
      show(S.g, vis); show(S.lab, vis);
      if (vis) {
        const { d } = projPath(S.dense, 6); S.p.setAttribute('d', d);
        const op = fade(t, S.s.t0, S.s.t1 + 2, .8, 1.2); S.g.style.opacity = op * .9;
        const m = S.dense[Math.floor(S.dense.length * .5)]; const [sx, sy] = project(m[0], m[1], 8);
        S.lab.style.transform = `translate(${sx.toFixed(1)}px,${sy.toFixed(1)}px) translate(10px,-50%) rotate(-8deg)`; S.lab.style.opacity = op;
      }
    }
    // armies, pushed apart where two would sit on one another
    const placed = [];
    for (const A of L.armies) {
      const p = armyAt(A.a, t);
      if (!p || p.n <= 0.5) { show(A.e, false); continue; }
      let [sx, sy, vis] = project(p.x, p.y, 14);
      if (!vis) { show(A.e, false); continue; }
      for (let it = 0; it < 3; it++) for (const q of placed) {
        const dx = sx - q[0], dy = sy - q[1];
        if (Math.abs(dx) < 150 && Math.abs(dy) < 62) sx = q[0] + (dx >= 0 ? 150 : -150);
      }
      placed.push([sx, sy]);
      show(A.e, true);
      setText(A.num, A.a.kind === 'fleet' ? fmt(p.n) : fmtK(p.n));
      const k0 = A.a.keys[0][0];
      const pop = backOut((t - k0) / .45);
      A.e.style.transform = `translate(${sx.toFixed(1)}px,${sy.toFixed(1)}px) translate(-50%,-100%) scale(${(0.6 + 0.4 * pop).toFixed(3)})`;
      A.e.style.opacity = clamp((t - k0) / .3, 0, 1) * fade(t, scene.t0, scene.t1, .3, .5);
    }
    // battles
    for (const B of L.battles) {
      const u = t - B.b.t;
      if (u < -1.2 || u > 4.2) { show(B.e, false); continue; }
      const [sx, sy, vis] = project(B.b.xy[0], B.b.xy[1], 12);
      show(B.e, vis);
      B.e.style.transform = `translate(${sx.toFixed(1)}px,${sy.toFixed(1)}px) translate(-50%,-50%) scale(${(0.7 + 0.3 * backOut((u + 1.2) / .5)).toFixed(3)})`;
      B.e.style.opacity = fade(u, -1.2, 4.2, .3, .8);
      B.r1.style.strokeDashoffset = (264 * (1 - clamp((u + 1.2) / 1.6, 0, 1))).toFixed(1);
      B.flash.style.opacity = u > 0 ? Math.exp(-u * 3.5) : 0;
      B.flash.style.transform = `scale(${(1 + clamp(u, 0, 1) * 2.2).toFixed(3)})`;
      B.cas.style.opacity = clamp((u - .2) / .4, 0, 1);
      if (B.falls) B.falls.style.opacity = clamp((u - .9) / .4, 0, 1);
    }
    // sieges
    for (const S of L.sieges) {
      const s = S.s;
      if (t < s.t0 - .5 || t > s.t1 + 3) { show(S.e, false); continue; }
      const [sx, sy, vis] = project(s.xy[0], s.xy[1], 12);
      show(S.e, vis);
      S.e.style.transform = `translate(${sx.toFixed(1)}px,${sy.toFixed(1)}px) translate(-50%,-50%)`;
      S.e.style.opacity = fade(t, s.t0 - .5, s.t1 + 3, .4, .8);
      const pr = clamp((t - s.t0) / Math.max(.1, s.t1 - s.t0), 0, 1);
      S.r1.style.strokeDashoffset = (251 * (1 - pr)).toFixed(1);
      const y0 = yearAt(s.t0), y1 = yearAt(Math.min(t, s.t1));
      const days = Math.max(1, Math.round((y1 - y0) * 365.25));
      setText(S.sd, t > s.t1 ? (s.fails ? 'lifted' : 'taken') : `day ${days}`);
      S.sd.classList.toggle('done', t > s.t1);
    }
    // the glowing numbers: each side's strength set out beyond its own army, away from the enemy,
    // and laid along the front between them (the script's place is used only if an army is missing)
    const sideScreen = side => {
      let x = 0, y = 0, n = 0;
      for (const ar of w.armies) if (ar.side === side && ar.kind !== 'fleet') {
        const p = armyAt(ar, t); if (!p || p.n <= .5) continue;
        const [px, py] = project(p.x, p.y, 14); x += px * p.n; y += py * p.n; n += p.n;
      }
      return n ? [x / n, y / n] : null;
    };
    for (const B of L.bignum) {
      const b = B.b;
      if (t < b.t0 - .2 || t > b.t1 + .8) { show(B.e, false); continue; }
      const v = sideStrength(w, b.side, t);
      if (v == null) { show(B.e, false); continue; }
      const own = sideScreen(b.side), foe = sideScreen(w.sides.find(s => s !== b.side) || b.side);
      let sx, sy, rot, vis = true;
      if (own && foe && Math.hypot(own[0] - foe[0], own[1] - foe[1]) > 1) {
        let dx = own[0] - foe[0], dy = own[1] - foe[1]; const l = Math.hypot(dx, dy); dx /= l; dy /= l;
        if (l < 40) { dx = own[0] <= foe[0] ? -1 : 1; dy = 0; }       // side by side: left and right
        sx = own[0] + dx * (Math.abs(dx) > .7 ? 360 : 230); sy = own[1] + dy * 170 - 40;   // clear of the counters, which sit 150 px apart
        rot = Math.atan2(dx, -dy) * 180 / Math.PI;                    // along the front
        while (rot > 90) rot -= 180; while (rot < -90) rot += 180;
        rot = clamp(rot, -24, 24);
        sx = clamp(sx, 260, W - 640); sy = clamp(sy, 150, H - 260);
      } else {
        [sx, sy, vis] = project(b.xy[0], b.xy[1], 20); rot = clamp(b.angle - cam.head, -24, 24);
      }
      show(B.e, vis);
      setText(B.s, fmt(v));
      const a = fade(t, b.t0, b.t1 + .8, .7, .8);
      B.e.style.opacity = a;
      B.e.style.transform = `translate(${sx.toFixed(1)}px,${sy.toFixed(1)}px) translate(-50%,-50%) rotate(${rot.toFixed(1)}deg) scale(${(0.85 + 0.15 * a).toFixed(3)})`;
    }
    for (const A of L.attr) {
      const u = t - A.a.t;
      if (u < 0 || u > 2.4) { show(A.e, false); continue; }
      const [sx, sy, vis] = project(A.a.xy[0], A.a.xy[1], 16);
      show(A.e, vis);
      A.e.style.transform = `translate(${sx.toFixed(1)}px,${(sy - 34 * easeOut(u / 2.4)).toFixed(1)}px) translate(-50%,-100%)`;
      A.e.style.opacity = fade(u, 0, 2.4, .25, .9);
    }
    const ex = L.extra;
    if (ex.fever) {
      const f = w.fever; const vis = t > f.t0 - .5 && t < f.t1 + 1.5; show(ex.fever.e, vis);
      if (vis) { const [sx, sy] = project(f.xy[0], f.xy[1], 10); ex.fever.e.style.transform = `translate(${sx.toFixed(1)}px,${sy.toFixed(1)}px) translate(-50%,-50%)`;
        ex.fever.e.style.opacity = fade(t, f.t0 - .5, f.t1 + 1.5, .8, .8) * (0.75 + 0.25 * Math.sin(t * 5)); }
    }
    for (const [k, key] of [['headgate', 'headgate'], ['viceroy', 'viceroy_dies'], ['capture', 'capture']]) {
      if (!ex[k]) continue; const v = w[key]; const u = t - v.t; const vis = u > -.2 && u < 4.5; show(ex[k].e, vis);
      if (vis) { const [sx, sy] = project(v.xy[0], v.xy[1], 10); ex[k].e.style.transform = `translate(${sx.toFixed(1)}px,${sy.toFixed(1)}px) translate(-50%,-115%) scale(${(0.7 + 0.3 * backOut(u / .5)).toFixed(3)})`;
        ex[k].e.style.opacity = fade(u, -.2, 4.5, .3, .8); }
    }
  }
}

// ------------------------------------------------------------------------- the date and panels
const datePanel = el('div', 'datebox', ui, '<div class="d-main"></div><div class="d-sub"></div>');
const dMain = datePanel.querySelector('.d-main'), dSub = datePanel.querySelector('.d-sub');
function drawDate(t, sc, year) {
  const on = sc.date !== 'none';
  datePanel.style.opacity = on ? fade(t, sc.t0, sc.t1, .5, .3) : 0;
  if (!on) return;
  setText(dMain, dateLabel(year, sc.date));
  const bm = Math.round(617 - Math.floor(year));
  setHTML(dSub, bm > 0 ? `${fmt(bm)} years before the Migration · <span class="ar">${arDigits(bm)} سنة قبل الرحيل</span>` : '');
}
const infobox = el('div', 'infobox', ui, `<div class="ib-era"></div><div class="ib-year"></div>
  <div class="ib-h">Leading powers</div><div class="ib-powers"></div>
  <div class="ib-h">Events</div><div class="ib-events"></div>
  <div class="ib-h">Largest towns</div><div class="ib-towns"></div>`);
const ib = k => infobox.querySelector('.ib-' + k);
setHTML(ib('era'), `${D.era.en}<span class="ar">${D.era.ar}</span>`);
let ibSlide = 0;
function townsAt(a) {
  const out = [];
  for (const name in D.towns) {
    const k = D.towns[name]; if (a < k[0][0]) continue;
    let v = k[k.length - 1][1];
    for (let i = 0; i < k.length - 1; i++) if (a >= k[i][0] && a < k[i + 1][0]) { const f = (a - k[i][0]) / (k[i + 1][0] - k[i][0]); v = k[i + 1][1] === 0 ? k[i][1] : lerp(k[i][1], k[i + 1][1], f); }
    if (a >= k[k.length - 1][0]) v = k[k.length - 1][1];
    if (v > 0) out.push([name, v]);
  }
  return out.sort((a, b) => b[1] - a[1]).slice(0, 5);
}
function warSpan(id) {
  const w = D.wars[id]; let a = 1e9, b = -1e9;
  for (const x of w.armies) { a = Math.min(a, x.keys[0][0]); b = Math.max(b, x.keys[x.keys.length - 1][0]); }
  return [a, b];
}
function drawInfobox(t, sc, year, st) {
  // slide in at the scene's start and out at its end, and give way to a war while it runs
  let a = sc.infobox ? fade(t, sc.t0, sc.t1, .7, .7) : 0;
  if (sc.infobox && sc.war) { const [w0, w1] = warSpan(sc.war); a = Math.min(a, 1 - fade(t, w0 - .5, w1 + .5, .6, .6)); }
  infobox.style.transform = `translateX(${((1 - easeOut(a)) * 440).toFixed(1)}px)`;
  infobox.style.opacity = a;
  if (a <= 0) return;
  setText(ib('year'), yearLabel(year));
  const S = D.states[st.cur];
  const pw = S.polities.filter(r => r.p !== 'bison').sort((x, y) => y.km2 - x.km2).slice(0, 4);
  setHTML(ib('powers'), pw.map(r => `<div class="row"><img src="assets/flags/${r.p}.svg"><span class="nm">${polName(r.p)}<span class="ar">${pol(r.p).names.ar || ''}</span></span><span class="v">${fmt(Math.round(r.km2 / 1000) * 1000)} km²</span></div>`).join(''));
  const ev = D.events.filter(e => e[0] <= year + 1e-6).slice(-3).reverse();
  setHTML(ib('events'), ev.map(e => `<div class="ev"><b>${e[1].replace(/^(\d+) BCE.*/, '$1 BCE')}</b> ${e[2]}</div>`).join(''));
  const tw = townsAt(year);
  setHTML(ib('towns'), tw.map((x, i) => `<div class="row"><span class="nm">${i + 1}. ${x[0]}</span><span class="v">${fmt(Math.round(x[1] / 100) * 100)}</span></div>`).join(''));
}
const warPanel = el('div', 'warpanel', ui, '<div class="wp-name"></div><div class="wp-sides"></div>');
function drawWarPanel(t, sc) {
  const on = !!sc.war;
  let a = on ? fade(t, sc.t0 + 5.6, sc.t1 - 9, .6, .6) : 0;
  if (on && sc.infobox) { const [w0, w1] = warSpan(sc.war); a = fade(t, w0, w1 + .5, .6, .6); }
  warPanel.style.opacity = a; warPanel.style.transform = `translateX(${((1 - easeOut(a)) * 420).toFixed(1)}px)`;
  if (a <= 0) return;
  const w = D.wars[sc.war];
  setHTML(warPanel.querySelector('.wp-name'), `${w.name.en}<span class="ar">${w.name.ar || ''}</span>`);
  setHTML(warPanel.querySelector('.wp-sides'), w.sides.map(s => {
    const v = sideStrength(w, s, t);
    const v0 = w.armies.filter(x => x.side === s && x.kind !== 'fleet').reduce((m, x) => m + x.keys[0][3], 0);
    return `<div class="side" style="--c:${pol(s).colour}"><img src="assets/flags/${s}.svg"><span class="nm">${polName(s)}</span><span class="v">${v == null ? '—' : fmt(v)}</span>` +
      (v != null && v0 > v ? `<span class="loss">−${fmt(v0 - v)}</span>` : '') + `</div>`;
  }).join(''));
}

// ------------------------------------------------------------------------------ the cast
const lineEls = [];
{
  let slots = [-1, -1];
  for (const ln of D.lines) {
    const e = el('div', 'line', ui, `<div class="ball"><img src="assets/balls/${ln.who}_${ln.mood}.svg"></div>
      <div class="bubble"><span class="txt"></span></div><div class="tag">${polName(ln.who)}<span class="ar">${pol(ln.who).names.ar || ''}</span></div>`);
    let slot = 0;
    if (!ln.xy) { slot = slots[0] > ln.t - 0.6 ? (slots[1] > ln.t - 0.6 ? 0 : 1) : 0; slots[slot] = ln.t + ln.dur; }
    lineEls.push({ ln, e, txt: e.querySelector('.txt'), ball: e.querySelector('.ball'), slot });
  }
}
function drawLines(t, sc) {
  for (const L of lineEls) {
    const { ln } = L; const u = t - ln.t;
    if (u < -0.05 || u > ln.dur + 0.35) { show(L.e, false); continue; }
    show(L.e, true);
    let x, y;
    if (ln.xy) {
      const [sx, sy] = project(ln.xy[0], ln.xy[1], 20);
      x = clamp(sx + 20, 20, W - 640); y = clamp(sy - 150, 110, H - 260);
      L.e.classList.add('at');
    } else {
      x = L.slot === 0 ? 46 : 600; y = H - 212;
    }
    const pop = backOut(u / .35), out = clamp((ln.dur + .35 - u) / .35, 0, 1);
    L.e.style.transform = `translate(${x}px,${y}px)`;
    L.e.style.opacity = Math.min(clamp(u / .15, 0, 1), out);
    L.ball.style.transform = `translateY(${(Math.sin(t * 5.2 + ln.t) * 3.5).toFixed(1)}px) scale(${(0.55 + 0.45 * pop).toFixed(3)}) rotate(${(Math.sin(t * 2.3 + ln.t) * 3).toFixed(1)}deg)`;
    const n = Math.floor(clamp((u - .18) * 34, 0, ln.text.length));
    setText(L.txt, ln.text.slice(0, n));
  }
}
const introEls = D.intros.map(it => {
  const P = pol(it.who); const N = P.names || {};
  const nat = N.native ? `<div class="native"><b>${N.native.word}</b> <span>${N.native.lang}, “${N.native.means}”</span></div>` : '';
  const ts = N.ts ? `<div class="glyphs"><img src="assets/glyphs/${it.who}.svg"><span>${N.ts}</span><em>Turquoise syllabary (the setting's own script)</em></div>` : '';
  const e = el('div', 'intro', ui, `<div class="ball"><img src="assets/balls/${it.who}_happy.svg"></div><div class="body">
    <div class="en">${N.en}</div><div class="de">${N.de || ''}</div><div class="ar">${N.ar || ''}</div>${nat}${ts}
    <div class="twin">carries <b>${P.twin}</b></div></div>`);
  return { it, e, ball: e.querySelector('.ball') };
});
function drawIntros(t, sc) {
  for (const I of introEls) {
    const u = t - I.it.t;
    if (u < 0 || u > I.it.dur + .5) { show(I.e, false); continue; }
    show(I.e, true);
    const a = fade(u, 0, I.it.dur + .5, .45, .5);
    const right = sc.infobox ? 470 : 60;
    I.e.style.transform = `translate(${(W - right - 560 + (1 - easeOut(a)) * 120).toFixed(1)}px, 150px)`;
    I.e.style.opacity = a;
    I.ball.style.transform = `translateY(${(Math.sin(t * 4.4) * 4).toFixed(1)}px) rotate(${(Math.sin(t * 2.1) * 4).toFixed(1)}deg)`;
  }
}

// ----------------------------------------------------------------------------------- cards
function results(war) {
  const w = D.wars[war]; if (!w || !w.results) return '';
  return `<div class="res-title">${w.results.title.en}</div><div class="res-flags">${w.sides.map(s => `<img src="assets/flags/${s}.svg">`).join('<span>vs</span>')}</div>` +
    `<table>${w.results.rows.map(r => `<tr><td>${r[0]}</td><td>${r[1]}</td></tr>`).join('')}</table>`;
}
function LAUREL(side) {
  let leaves = '';
  for (let i = 0; i < 9; i++) {
    const y = 150 - i * 15, x = 40 + Math.sin(i * .35) * 10, a = -30 - i * 4;
    leaves += `<ellipse cx="${x - 13}" cy="${y}" rx="15" ry="6" transform="rotate(${a} ${x - 13} ${y})"/>` +
      `<ellipse cx="${x + 13}" cy="${y - 7}" rx="15" ry="6" transform="rotate(${180 - a} ${x + 13} ${y - 7})"/>`;
  }
  return `<svg class="laurel ${side}" viewBox="0 0 80 170"><defs><linearGradient id="gold${side}" x1="0" y1="0" x2="1" y2="1">` +
    `<stop offset="0" stop-color="#f0d699"/><stop offset=".5" stop-color="#b98a3e"/><stop offset="1" stop-color="#6e4a1c"/></linearGradient></defs>` +
    `<path d="M44 165C30 120 36 60 52 14" fill="none" stroke="#7a5a1e" stroke-width="4"/><g fill="url(#gold${side})" stroke="#5a3d10" stroke-width="1.4">${leaves}</g></svg>`;
}
const LINEUP = ['canal', 'houses', 'paquime', 'caddo', 'jumano', 'city', 'fire', 'nahua', 'bison', 'solms'];
function cardHTML(c) {
  switch (c.kind) {
    case 'title': return `${LAUREL('l')}${LAUREL('r')}<div class="t1">Alternate History of Texas</div><div class="t2">(in place of Saudi Arabia)</div>
      <div class="t3">Kingdom of Solms-America · <i>Königreich Solms-Amerika</i> · <span class="ar">مملكة زولمس-أمريكا</span></div>
      <div class="t4">Phase I · The Turquoise Road · 500 BCE – 603 CE</div>`;
    case 'premise': return `<div class="p-h">Transposition, not transplantation</div><div class="p-s">Geography never moves. Texas keeps its own ground, and takes Saudi Arabia's <b>role</b>.</div>
      <table>${[['Dreifurt', 'Riyadh', 'درايفورت'], ['Paquimé', 'Makkah', 'باكيمي'], ['Chukson', 'Madinah', 'تشوكسون'], ['Waimas', 'Jeddah', 'وايماس'],
        ['Gulf of California', 'the Red Sea', 'خليج كاليفورنيا'], ['Gulf of Mexico', 'the Gulf', 'خليج المكسيك'], ['House of Solms', 'House of Saud', 'آل زولمس']].map(r =>
          `<tr><td>${r[0]}</td><td class="eq">=</td><td><i>${r[1]}</i></td><td class="ar">${r[2]}</td></tr>`).join('')}</table>`;
    case 'credit': return `North America's states after <i>A More Fractured Union</i> by Bemon and Body25 (2023) · frontiers on rivers and watersheds (QGIS, GRASS) · relief ETOPO 2022 · land cover Natural Earth II`;
    case 'chapter': return `<div class="c1">${c.text.en}</div><div class="c2">${c.text.sub || ''}</div>`;
    case 'war': return `${LAUREL('l')}${LAUREL('r')}<div class="w0">War</div><div class="w1">${c.text.en}</div><div class="w2">${c.text.sub}</div><div class="w3 ar">${c.text.ar || ''}</div>`;
    case 'results': return results(c.war);
    case 'phase_results': {
      const rows = Object.entries(D.wars).filter(([, w]) => w.results).map(([, w]) => `<tr><td>${w.name.en}</td><td>${w.results.rows[0][1]}</td><td>${w.results.outcome || w.results.rows[w.results.rows.length - 1][1]}</td></tr>`).join('');
      return `<div class="res-title">Phase I · results</div><div class="pr-sub">500 BCE – 603 CE · 1,102 years · four wars and a battle</div>
        <table class="pr"><tr><th>War</th><th>Marched</th><th>Outcome</th></tr>${rows}</table>
        <div class="pr-foot">By 603 the City of the Gods has burned, the canal towns stand empty, and Paquimé sits alone at the meeting of the roads.</div>`;
    }
    case 'lineup': return `<div class="lu-title">The cast of Phase I</div><div class="lu">${LINEUP.map(p => `<div class="lu-b"><img src="assets/balls/${p}_happy.svg"><b>${polName(p)}</b><span class="ar">${pol(p).names.ar || ''}</span></div>`).join('')}</div>`;
    case 'discord': return `<div class="dc-icon"><svg viewBox="0 0 64 64"><path d="M10 14h44a6 6 0 0 1 6 6v22a6 6 0 0 1-6 6H30l-12 10v-10h-8a6 6 0 0 1-6-6V20a6 6 0 0 1 6-6z" fill="#5865F2"/><circle cx="23" cy="31" r="4.5" fill="#fff"/><circle cx="41" cy="31" r="4.5" fill="#fff"/></svg></div>
      <div class="dc-1">Join the Controglobe Discord</div><div class="dc-2">${D.discord.replace('https://', '')}</div>
      <div class="dc-3">Help draw Phase II · vote on the next war · post your own maps</div>
      <div class="dc-balls">${['solms', 'paquime', 'caddo', 'city', 'fire'].map(p => `<img src="assets/balls/${p}_happy.svg">`).join('')}</div>`;
    case 'endcard': return `<div class="ec-1">CONTROGLOBE</div><div class="ec-2">The Global Swap</div><div class="ec-3">Next: Phase II · The Path and the Commonwealth (604 – 1399)</div>
      <div class="ec-4">Every name, border and date: mofferato.github.io/controglobe · ${D.discord.replace('https://', '')}</div>
      <div class="ec-5">Score made in code · relief ETOPO 2022 (NOAA) · Natural Earth · North America after A More Fractured Union (Bemon, Body25)</div>`;
  }
  return '';
}
const cardEls = D.cards.map(c => ({ c, e: el('div', 'card card-' + c.kind, ui, cardHTML(c)) }));
const lowerEls = D.lower.map(l => ({ l, e: el('div', 'lower', ui, `<svg viewBox="0 0 64 64"><path d="M10 14h44a6 6 0 0 1 6 6v22a6 6 0 0 1-6 6H30l-12 10v-10h-8a6 6 0 0 1-6-6V20a6 6 0 0 1 6-6z" fill="#5865F2"/><circle cx="23" cy="31" r="4.5" fill="#fff"/><circle cx="41" cy="31" r="4.5" fill="#fff"/></svg>
  <div><b>Help us draw Phase II</b><span>${D.discord.replace('https://', '')}</span></div><img src="assets/balls/paquime_happy.svg">`) }));
let cardDim = 0;
function drawCards(t) {
  cardDim = 0;
  for (const C of cardEls) {
    const u = t - C.c.t;
    if (u < 0 || u > C.c.dur) { show(C.e, false); continue; }
    show(C.e, true);
    const a = fade(u, 0, C.c.dur, .55, .55);
    C.e.style.opacity = a;
    const k = C.c.kind;
    if (k === 'war' || k === 'results' || k === 'phase_results' || k === 'discord' || k === 'endcard' || k === 'lineup' || k === 'title')
      cardDim = Math.max(cardDim, a * (k === 'endcard' ? .82 : k === 'lineup' ? .5 : .45));
    if (k === 'war' || k === 'title') C.e.style.transform = `translate(-50%,-50%) scale(${(0.92 + 0.08 * easeOut(u / .8)).toFixed(3)})`;
    else if (k === 'chapter') C.e.style.transform = `translate(-50%, ${((1 - easeOut(a)) * -30).toFixed(1)}px)`;
    else if (k === 'lineup') C.e.querySelectorAll('.lu-b img').forEach((im, i) => { im.style.transform = `translateY(${(Math.sin(t * 4 + i) * 5 - 30 * (1 - backOut(clamp((u - i * .12) / .5, 0, 1)))).toFixed(1)}px)`; });
    else if (k === 'discord') C.e.querySelectorAll('.dc-balls img').forEach((im, i) => { im.style.transform = `translateY(${(Math.sin(t * 5 + i * 1.3) * 6).toFixed(1)}px) rotate(${(Math.sin(t * 2 + i) * 6).toFixed(1)}deg)`; });
  }
  for (const L of lowerEls) {
    const u = t - L.l.t;
    if (u < 0 || u > L.l.dur) { show(L.e, false); continue; }
    show(L.e, true); const a = fade(u, 0, L.l.dur, .5, .5);
    L.e.style.opacity = a; L.e.style.transform = `translate(-50%, ${((1 - easeOut(a)) * 60).toFixed(1)}px)`;
  }
}
const vigSvg = {};
for (const id of new Set(D.vignettes.map(v => v.id))) vigSvg[id] = await fetch(`assets/vignettes/${id}.svg`).then(r => r.text());
const vignetteEls = D.vignettes.map(v => ({ v, e: el('div', 'vignette', ui, vigSvg[v.id]) }));
function drawVignettes(t) {
  for (const V of vignetteEls) {
    const u = t - V.v.t;
    if (u < 0 || u > V.v.dur) { show(V.e, false); continue; }
    show(V.e, true); const a = fade(u, 0, V.v.dur, .6, .6);
    V.e.style.opacity = a; V.e.style.transform = `translate(${((1 - easeOut(a)) * -60).toFixed(1)}px, 0) rotate(-1.5deg)`;
  }
}

// --------------------------------------------------------------------------------------- frame
let cam = { head: 0 }, sceneFade = 1;
const clipEls = [...document.querySelectorAll('.sceneclip')];
function render(t) {
  const sc = sceneAt(t);
  const year = yearAt(t);
  cam = cameraAt(t);
  // the infobox's room: the projection shifts so the map sits left of the panel
  const side = (sc.infobox || sc.war) ? fade(t, sc.t0, sc.t1, 1.2, 1.2) : 0;
  cam.offset = 190 * smooth(side);
  placeCamera(cam);
  // the map layer for this scene
  const st = stateNow(t);
  // the map fades only where the next or the last scene shows another kind of map
  const si = D.scenes.indexOf(sc), prevSc = D.scenes[si - 1], nextSc = D.scenes[si + 1];
  const fin = (!prevSc || prevSc.map !== sc.map) ? clamp((t - sc.t0) / .8, 0, 1) : 1;
  const fout = (!nextSc || nextSc.map !== sc.map) ? clamp((sc.t1 - t) / .8, 0, 1) : 1;
  sceneFade = Math.min(fin, fout);
  if (sc.map === 'history') {
    mat.uniforms.uA.value = stateTexture(st.prev); mat.uniforms.uB.value = stateTexture(st.cur);
    mat.uniforms.uMix.value = st.prev === st.cur ? 1 : st.f;
  } else if (sc.map === 'modern') {
    const m = modernTexture(!!sc.marches);
    mat.uniforms.uA.value = m; mat.uniforms.uB.value = m; mat.uniforms.uMix.value = 1;
  }
  const mapAlpha = sc.map === 'empty' ? 0 : sceneFade;
  mat.uniforms.uPolAlpha.value = mapAlpha;
  mat.uniforms.uProvAlpha.value = sc.map === 'modern' ? .15 : .42;
  mat.uniforms.uDim.value = cardDim * .62;
  document.getElementById('grade').style.background = cardDim > 0 ?
    `radial-gradient(ellipse 72% 70% at 50% 50%, rgba(0,0,0,${(cardDim * .25).toFixed(3)}) 40%, rgba(10,6,2,${(.42 + cardDim * .4).toFixed(3)}) 100%)` : '';
  renderer.render(scene3, camera);
  drawRegions(t, sc); drawPeoples(t, sc);
  drawPolLabels(t, sc, st); drawModernLabels(t, sc);
  drawRoutes(t, sc, year); drawGoods(t, sc, year);
  drawPlaces(t, sc, year);
  drawWar(t, sc);
  drawDate(t, sc, year); drawInfobox(t, sc, year, st); drawWarPanel(t, sc);
  drawCards(t); drawIntros(t, sc); drawVignettes(t); drawLines(t, sc);
  for (const c of clipEls) {
    const a = +c.dataset.t0, b = +c.dataset.t1, f = +c.dataset.fade, fi = +(c.dataset.fin || .3);
    c.style.opacity = clamp(Math.min((t - a) / fi, (b - t) / f), 0, 1);
  }
  document.getElementById('grade').style.opacity = 1;
}

// a segment of the cut (render.segment) starts its clock at SEG_T0 and runs SEG_DUR seconds
const SEG_T0 = window.SEG_T0 || 0, SEG_DUR = window.SEG_DUR || D.duration;
render(SEG_T0);
const tl = gsap.timeline({ paused: true, onUpdate() { render(tl.time() + SEG_T0); } });
tl.to({}, { duration: SEG_DUR }, 0);
window.__timelines = window.__timelines || {};
window.__timelines.root = tl;
window.__render = render;   // for stills
