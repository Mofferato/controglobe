// The globe Shorts' engine: the alternate world on a lit 3D globe (three.js), with each era's HUD skin
// over it, every frame a pure function of time.
//
// The globe: Natural Earth II's relief (a world texture and a sharp patch over the stage), the realms'
// colours of the map state on screen (two fills crossfading at every border change), an atmosphere at the
// limb, and stars. Frontiers and names are drawn in the page as vectors from longitude and latitude, so
// they stay sharp however close the camera comes. Over it, by era (antiquity, medieval, renaissance,
// victorian, worldwars, coldwar, modern): the top bar and its ledger, the era card, army banners whose
// numbers fall, campaign arrows, missile arcs, battle popups, captions, the Arabic lower-thirds, the
// countryballs, the casualty count and the end card.

import * as THREE from './vendor/three.module.min.js';

const D = window.DATA;
const W = D.W, H = D.H;
const root = document.getElementById('root');
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
const setHTML = (e, s) => { if (e._h !== s) { e.innerHTML = s; e._h = s; } };
const place = (e, x, y, s = 1, r = 0, o = 1) => { e.style.transform = `translate(${x.toFixed(1)}px,${y.toFixed(1)}px) rotate(${r.toFixed(2)}deg) scale(${s.toFixed(4)})`; e.style.opacity = o.toFixed(3); };
function keyed(keys, t) {
  if (!keys || !keys.length) return 0;
  if (t <= keys[0][0]) return keys[0][1];
  for (let i = 0; i < keys.length - 1; i++) if (t < keys[i + 1][0]) return lerp(keys[i][1], keys[i + 1][1], smooth((t - keys[i][0]) / (keys[i + 1][0] - keys[i][0])));
  return keys[keys.length - 1][1];
}
const yearLabel = y => { y = Math.floor(y); return y <= 0 ? `${1 - y} BCE` : `${y}`; };
const POL = D.polities;
const colour = id => (POL[id] && POL[id].colour) || '#888888';

// --------------------------------------------------------------------------------------- loading
const loadImage = src => new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = src; });
const stateKeys = Object.keys(D.states);
const [baseImg, detImg, ...fillImgs] = await Promise.all([loadImage(D.globe.base), loadImage(D.globe.detail.src), ...stateKeys.map(k => loadImage(D.states[k].fills))]);
await Promise.all(['700 40px Cinzel', '900 40px Cinzel', '700 40px Cormorant', 'italic 600 40px Cormorant', '700 40px Amiri',
  '400 40px UnifrakturMaguntia'].map(f => document.fonts.load(f).catch(() => null)));
await document.fonts.ready;

// ----------------------------------------------------------------------------------- the globe
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true, alpha: true });
renderer.setPixelRatio(1);
renderer.setSize(W, H);
renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
document.getElementById('gl').appendChild(renderer.domElement);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(D.globe.fov || 34, W / H, 0.001, 100);
const aniso = renderer.capabilities.getMaxAnisotropy();
const tex = img => { const t = new THREE.Texture(img); t.colorSpace = THREE.NoColorSpace; t.anisotropy = aniso; t.generateMipmaps = true;
  t.minFilter = THREE.LinearMipmapLinearFilter; t.wrapS = THREE.RepeatWrapping; t.needsUpdate = true; return t; };
const baseT = tex(baseImg), detT = tex(detImg);
const fillT = {}; stateKeys.forEach((k, i) => { fillT[k] = tex(fillImgs[i]); });
const DB = D.globe.detail.bbox;   // lon/lat box of the sharp patch
const earthMat = new THREE.ShaderMaterial({
  uniforms: {
    uBase: { value: baseT }, uDet: { value: detT }, uDetBox: { value: new THREE.Vector4(DB[0], DB[1], DB[2], DB[3]) },
    uFA: { value: fillT[stateKeys[0]] }, uFB: { value: fillT[stateKeys[0]] }, uMix: { value: 1 }, uFill: { value: .8 },
    uSun: { value: new THREE.Vector3(-.5, .6, .8).normalize() }, uTint: { value: new THREE.Vector3(1, 1, 1) }, uGlow: { value: 0 },
  },
  vertexShader: `varying vec3 vP; varying vec3 vN; void main(){ vP = position; vN = normalize(mat3(modelMatrix) * normal);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
  fragmentShader: `
    uniform sampler2D uBase, uDet, uFA, uFB; uniform vec4 uDetBox; uniform float uMix, uFill, uGlow; uniform vec3 uSun, uTint;
    varying vec3 vP; varying vec3 vN;
    const float PI = 3.14159265;
    void main(){
      vec3 p = normalize(vP);
      float lat = asin(clamp(p.y, -1.0, 1.0)); float lon = atan(-p.z, p.x);
      vec2 uv = vec2((lon + PI) / (2.0 * PI), (lat + PI * 0.5) / PI);
      float dlon = degrees(lon), dlat = degrees(lat);
      vec3 col = texture2D(uBase, uv).rgb;
      vec2 duv = vec2((dlon - uDetBox.x) / (uDetBox.z - uDetBox.x), (dlat - uDetBox.y) / (uDetBox.w - uDetBox.y));
      if (duv.x > 0.0 && duv.x < 1.0 && duv.y > 0.0 && duv.y < 1.0) {
        float e = min(min(duv.x, 1.0 - duv.x), min(duv.y, 1.0 - duv.y));
        col = mix(col, texture2D(uDet, duv).rgb, smoothstep(0.0, 0.02, e));
      }
      vec4 fa = texture2D(uFA, uv), fb = texture2D(uFB, uv);
      vec4 f = mix(fa, fb, uMix);
      float fl = dot(f.rgb, vec3(0.299, 0.587, 0.114));
      f.rgb = clamp(mix(vec3(fl), f.rgb, 1.45), 0.0, 1.0);   // the realms' colours a little richer on the globe
      float lum = dot(col, vec3(0.299, 0.587, 0.114));
      vec3 painted = mix(col, f.rgb * (0.74 + 0.42 * lum), f.a * uFill);
      painted = mix(painted, painted * 1.18 + vec3(0.05), uGlow * f.a);
      float l = clamp(dot(normalize(vN), uSun), 0.0, 1.0);
      vec3 lit = painted * (0.42 + 0.72 * l) * uTint;
      gl_FragColor = vec4(lit, 1.0);
    }`,
});
const earth = new THREE.Mesh(new THREE.SphereGeometry(1, 256, 128), earthMat);
scene.add(earth);
const atmo = new THREE.Mesh(new THREE.SphereGeometry(1.035, 128, 64), new THREE.ShaderMaterial({
  uniforms: { uCol: { value: new THREE.Vector3(.35, .62, 1.0) }, uK: { value: 1.0 } },
  vertexShader: `varying vec3 vN; varying vec3 vV; void main(){ vN = normalize(normalMatrix * normal);
    vec4 mv = modelViewMatrix * vec4(position,1.0); vV = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }`,
  fragmentShader: `uniform vec3 uCol; uniform float uK; varying vec3 vN; varying vec3 vV;
    void main(){ float r = 1.0 - abs(dot(vN, vV)); float a = pow(r, 2.6) * 1.25 * uK; gl_FragColor = vec4(uCol * a, a); }`,
  side: THREE.BackSide, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false,
}));
scene.add(atmo);
// stars, drawn once
{
  const c = document.createElement('canvas'); c.width = W; c.height = H; const g = c.getContext('2d');
  g.fillStyle = '#04070c'; g.fillRect(0, 0, W, H);
  let s = 7; const rnd = () => (s = (s * 16807) % 2147483647) / 2147483647;
  for (let i = 0; i < 900; i++) { const b = rnd(); g.fillStyle = `rgba(${200 + 55 * b | 0},${210 + 45 * b | 0},255,${.25 + .7 * b * b})`; g.fillRect(rnd() * W, rnd() * H, b > .9 ? 2 : 1, b > .9 ? 2 : 1); }
  document.getElementById('stars').style.backgroundImage = `url(${c.toDataURL()})`;
}

const ll2v = (lon, lat, r = 1) => { const a = THREE.MathUtils.degToRad(lon), b = THREE.MathUtils.degToRad(lat);
  return new THREE.Vector3(r * Math.cos(b) * Math.cos(a), r * Math.sin(b), -r * Math.cos(b) * Math.sin(a)); };
let CAMDIR = new THREE.Vector3(), SHAKE = [0, 0];
function camAt(t) {
  const K = D.camera; let a = K[0], b = K[0], f = 0;
  if (t > K[0][0]) {
    a = b = K[K.length - 1];
    for (let i = 0; i < K.length - 1; i++) if (t < K[i + 1][0]) { a = K[i]; b = K[i + 1]; f = smooth((t - a[0]) / (b[0] - a[0])); break; }
  }
  let dl = b[1] - a[1]; if (dl > 180) dl -= 360; if (dl < -180) dl += 360;
  return { lon: a[1] + dl * f + 0.35 * Math.sin(t * 0.31), lat: lerp(a[2], b[2], f) + 0.25 * Math.cos(t * 0.27),
           dist: Math.exp(lerp(Math.log(a[3]), Math.log(b[3]), f)) * (1 + 0.006 * Math.sin(t * .7)), tilt: lerp(a[4] || 0, b[4] || 0, f) };
}
function setCamera(t) {
  const c = camAt(t);
  const target = ll2v(c.lon, c.lat, 1);
  const pos = ll2v(c.lon, c.lat - c.tilt, c.dist);
  camera.position.copy(pos);
  camera.up.set(0, 1, 0);
  camera.lookAt(target.multiplyScalar(c.tilt ? 1 : 0.0));
  // the screen's centre a little above the middle, where the action sits between the HUD and the cast
  camera.setViewOffset(W, H, 0, H * 0.06, W, H);
  camera.updateMatrixWorld(); camera.updateProjectionMatrix();
  CAMDIR = camera.position.clone().normalize();
  const sun = new THREE.Vector3(-0.55, 0.55, 0.65).normalize().applyQuaternion(camera.quaternion);
  earthMat.uniforms.uSun.value.copy(sun);
  return c;
}
const _v = new THREE.Vector3();
function proj(lon, lat, alt = 0) {           // -> [x, y, facing (cos of the angle to the camera)]
  const p = ll2v(lon, lat, 1 + alt);
  const n = p.clone().normalize();
  const face = n.dot(camera.position.clone().sub(p).normalize());
  _v.copy(p).project(camera);
  return [(_v.x * .5 + .5) * W + SHAKE[0], (-_v.y * .5 + .5) * H + SHAKE[1], face];
}
function pxPerDeg(lon, lat) { const a = proj(lon, lat), b = proj(lon, lat + 1); return Math.hypot(a[0] - b[0], a[1] - b[1]); }

// --------------------------------------------------------------------------------- map states
const XF = 0.55;
function mapState(t) {
  const tr = D.track; let i = 0;
  for (let k = 0; k < tr.length; k++) if (t >= tr[k][0]) i = k;
  const cur = tr[i][1], prev = i > 0 ? tr[i - 1][1] : cur;
  return { cur, prev, f: i > 0 ? clamp((t - tr[i][0]) / XF, 0, 1) : 1, since: t - tr[i][0], changed: i > 0 };
}
const gOuter = sv('g', { class: 'frontiers' }), gInner = sv('g', { class: 'inner' });
const pathFor = (g, cls) => sv('path', { class: cls, fill: 'none' }, g);
const fOld = pathFor(gOuter, 'f old'), fNew = pathFor(gOuter, 'f'), iOld = pathFor(gInner, 'i old'), iNew = pathFor(gInner, 'i');
function ringsPath(rings, closed) {
  let d = '';
  for (const r of rings) {
    let pen = false;
    for (let k = 0; k < r.length; k += 2) {
      const p = proj(r[k], r[k + 1]);
      if (p[2] < 0.04) { pen = false; continue; }
      d += (pen ? 'L' : 'M') + p[0].toFixed(1) + ',' + p[1].toFixed(1);
      pen = true;
    }
  }
  return d;
}
const labelEls = {};
function drawMap(t) {
  const st = mapState(t);
  earthMat.uniforms.uFA.value = fillT[st.prev]; earthMat.uniforms.uFB.value = fillT[st.cur];
  earthMat.uniforms.uMix.value = st.prev === st.cur ? 1 : st.f;
  earthMat.uniforms.uGlow.value = st.changed ? Math.max(0, 1 - st.since / 0.9) * 0.9 : 0;
  const S = D.states;
  const both = st.prev !== st.cur && st.f < 1;
  fNew.setAttribute('d', ringsPath(S[st.cur].borders.outer)); fNew.style.opacity = both ? st.f : 1;
  iNew.setAttribute('d', ringsPath(S[st.cur].borders.inner)); iNew.style.opacity = both ? st.f : 1;
  fOld.setAttribute('d', both ? ringsPath(S[st.prev].borders.outer) : ''); fOld.style.opacity = 1 - st.f;
  iOld.setAttribute('d', both ? ringsPath(S[st.prev].borders.inner) : ''); iOld.style.opacity = 1 - st.f;
  // the realms' names, sized to the ground they cover on screen
  const want = new Set(), placed = [];
  for (const [key, a] of [[st.cur, both ? st.f : 1], [st.prev, both ? 1 - st.f : 0]]) {
    if (a <= 0) continue;
    for (const L of S[key].labels.slice(0, 9)) {
      const id = key + ':' + L.id; want.add(id);
      let e = labelEls[id];
      if (!e) { e = labelEls[id] = el('div', 'rlabel', ov, `<b>${L.en}</b><span class="ar">${L.ar}</span>`); }
      const p = proj(L.lon, L.lat);
      const k = pxPerDeg(L.lon, L.lat);
      const size = clamp(Math.sqrt(L.km2) / 111 * k * 0.13, 0, 46);
      let o = a * clamp((p[2] - .25) / .2, 0, 1) * clamp((size - 9) / 5, 0, 1);
      // a name that would sit on a bigger one's is left out (the list runs largest first)
      const hw = Math.max(L.en.length * size * .42, 40), hh = size * 1.25;
      const r = [p[0] - hw, p[1] - hh, p[0] + hw, p[1] + hh];
      if (o > .02 && key === st.cur && placed.some(q => r[0] < q[2] && r[2] > q[0] && r[1] < q[3] && r[3] > q[1])) o = 0;
      if (o > .02 && key === st.cur) placed.push(r);
      show(e, o > .02);
      if (o > .02) { e.style.fontSize = size.toFixed(1) + 'px'; e.style.transform = `translate(${p[0].toFixed(1)}px,${p[1].toFixed(1)}px) translate(-50%,-50%)`; e.style.opacity = o.toFixed(3); }
    }
  }
  for (const id in labelEls) if (!want.has(id)) show(labelEls[id], false);
}

// ------------------------------------------------------------------------------------ eras & HUD
let ERA = null;
function eraAt(t) { for (const e of D.eras) if (t >= e.t0 && t < e.t1) return e; return null; }
const top = el('div', 'plate topbar', ui, `<div class="side u"><img><div class="nm"></div><div class="men"></div><div class="lbl"></div></div>
  <div class="side i"><img><div class="nm"></div><div class="men"></div><div class="lbl"></div></div>
  <div class="dial"><div class="war"></div><div class="yr"></div><div class="mo"></div></div>`);
const T = { uImg: top.querySelector('.u img'), uNm: top.querySelector('.u .nm'), uMen: top.querySelector('.u .men'), uLbl: top.querySelector('.u .lbl'),
  iImg: top.querySelector('.i img'), iNm: top.querySelector('.i .nm'), iMen: top.querySelector('.i .men'), iLbl: top.querySelector('.i .lbl'),
  war: top.querySelector('.war'), yr: top.querySelector('.yr'), mo: top.querySelector('.mo') };
const eraCard = el('div', 'eracard', ui, '<div class="k"></div><div class="t"></div><div class="s"></div>');
const MONTHS = ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER'];
function ledgerAt(t) { for (const l of D.ledgers) if (t >= l.t0 && t <= l.t1) return l; return null; }
function drawHud(t) {
  const e = eraAt(t);
  if (e !== ERA) { ERA = e; root.className = e ? 'era-' + e.skin : ''; }
  const onTop = e && t > D.hook.t1 && t < D.end.t0;
  show(top, !!onTop);
  if (onTop) {
    const k = easeOut((t - e.t0) / .45);
    place(top, 66, lerp(-220, 150, k), 1, 0, 1);
    const L = ledgerAt(t);
    const y = keyed(D.clock, t);
    setText(T.yr, yearLabel(y));
    const fr = (y - Math.floor(y)) * 12, mi = clamp(Math.floor(fr), 0, 11), day = clamp(Math.floor((fr - mi) * 30.4) + 1, 1, 31);
    const inBattle = D.battles.some(bb => t > bb.t - 1.2 && t < bb.t + PDUR);
    setText(T.mo, L && L.month ? (inBattle ? `${day} ${MONTHS[mi]}` : MONTHS[mi]) : (e.label || ''));
    setText(T.war, (L && L.title) || e.title);
    for (const [s, img, nm, men, lbl] of [['a', T.uImg, T.uNm, T.uMen, T.uLbl], ['b', T.iImg, T.iNm, T.iMen, T.iLbl]]) {
      const side = L && L[s];
      img.style.visibility = side ? 'visible' : 'hidden';
      if (side) {
        if (img._s !== side.polity) { img.src = D.flags[side.polity]; img._s = side.polity; }
        setHTML(nm, `${side.name}<span class="ar">${side.ar || ''}</span>`);
        setText(men, fmt(keyed(side.keys, t)));
        setText(lbl, side.label || '');
      } else { setHTML(nm, ''); setText(men, ''); setText(lbl, ''); }
    }
  }
  // the era card: the name of the age over the turn of the skin
  const c = D.eras.find(x => t >= x.t0 - 0.05 && t < x.t0 + 1.25);
  show(eraCard, !!c);
  if (c) {
    eraCard.className = 'eracard card-' + c.skin;
    setText(eraCard.querySelector('.k'), c.kicker || ''); setText(eraCard.querySelector('.t'), c.title); setText(eraCard.querySelector('.s'), c.years);
    const d = t - c.t0;
    place(eraCard, 66, 1250, 0.85 + 0.15 * backOut(d / .35), 0, fade(t, c.t0, c.t0 + 1.25, .12, .3));
  }
}

// ------------------------------------------------------------------------------ armies & arrows
const badge = (pol, shape) => `<svg viewBox="0 0 76 46" width="76" height="46"><path d="${shape === 'shield' ? 'M8,2H68V24C68,36 52,44 38,45C24,44 8,36 8,24Z' :
  shape === 'block' ? 'M2,4H74V42H2Z' : shape === 'chip' ? 'M10,4H66L74,23L66,42H10L2,23Z' : 'M0,0H76L60,23L76,46H0Z'}" fill="${colour(pol)}" stroke="#141414" stroke-width="2.5"/>
  ${shape === 'block' ? '<path d="M2,4L74,42M74,4L2,42" stroke="#141414" stroke-width="2.5"/>' : ''}</svg>`;
const armyEls = D.armies.map(a => {
  const e = el('div', 'army', ov, `<div class="base"></div><div class="pole"></div><div class="flag"></div><div class="tag"><b>0</b><em>${a.unit.toUpperCase()}</em></div>`);
  e.querySelector('.base').style.background = colour(a.polity);
  return { a, e, n: e.querySelector('.tag b'), flag: e.querySelector('.flag') };
});
function polyAt(path, u) {
  if (path.length === 1) return path[0];
  const L = []; let tot = 0;
  for (let i = 1; i < path.length; i++) { const d = Math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1]); L.push(d); tot += d; }
  let want = clamp(u, 0, 1) * tot;
  for (let i = 1; i < path.length; i++) { if (want <= L[i - 1]) { const f = L[i - 1] ? want / L[i - 1] : 0; return [lerp(path[i - 1][0], path[i][0], f), lerp(path[i - 1][1], path[i][1], f)]; } want -= L[i - 1]; }
  return path[path.length - 1];
}
function drawArmies(t) {
  const shape = ERA ? ERA.banner : 'flag';
  for (const { a, e, n, flag } of armyEls) {
    const on = t >= a.t0 && t <= a.t1 + 0.4;
    show(e, on); if (!on) continue;
    if (flag._s !== shape) { flag.innerHTML = badge(a.polity, shape); flag._s = shape; }
    const ll = polyAt(a.path, keyed(a.move || [[0, 0]], t));
    const p = proj(ll[0], ll[1]);
    const k = backOut((t - a.t0) / .45), o = clamp((a.t1 + .4 - t) / .4, 0, 1) * clamp((p[2] - .1) / .1, 0, 1);
    place(e, p[0], p[1] + 3 * Math.sin(t * 3 + ll[0]), .6 + .4 * k, 0, Math.min(1, (t - a.t0) / .2) * o);
    const v = keyed(a.n, t);
    setText(n, fmt(v));
    n.classList.toggle('falling', v < keyed(a.n, Math.max(a.t0, t - .6)) - 1);
  }
}
const arrowEls = D.arrows.map(a => {
  const g = sv('g', { class: 'arrow' });
  return { a, g, under: sv('path', { class: 'au', fill: 'none' }, g), line: sv('path', { class: 'al', fill: 'none', stroke: colour(a.polity) }, g),
    head: sv('path', { class: 'ah', fill: colour(a.polity) }, g) };
});
function gcPath(path, n = 24) {          // great-circle points along a lon/lat polyline
  const out = [];
  for (let i = 1; i < path.length; i++) {
    const A = ll2v(path[i - 1][0], path[i - 1][1]), B = ll2v(path[i][0], path[i][1]);
    for (let k = (i === 1 ? 0 : 1); k <= n; k++) {
      const v = A.clone().lerp(B, k / n).normalize();
      out.push([THREE.MathUtils.radToDeg(Math.atan2(-v.z, v.x)), THREE.MathUtils.radToDeg(Math.asin(v.y))]);
    }
  }
  return out;
}
arrowEls.forEach(x => { x.pts = gcPath(x.a.path); });
function drawArrows(t) {
  for (const { a, g, under, line, head, pts } of arrowEls) {
    const on = t >= a.t0 && t <= a.t1 + 1.0;
    show(g, on); if (!on) continue;
    const u = easeOut((t - a.t0) / (a.t1 - a.t0));
    const m = Math.max(2, Math.round(u * (pts.length - 1)) + 1);
    const lift = a.missile ? (i => 0.18 * Math.sin(Math.PI * i / (pts.length - 1))) : (() => 0);
    const P = pts.slice(0, m).map((q, i) => proj(q[0], q[1], lift(i)));
    const d = 'M' + P.map(p => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join('L');
    const w = a.missile ? 5 : (a.big ? 16 : 11);
    under.setAttribute('d', d); under.setAttribute('stroke-width', w + 6);
    line.setAttribute('d', d); line.setAttribute('stroke-width', w);
    line.setAttribute('stroke-dasharray', a.missile ? '' : `${w * 2.4} ${w * .9}`); line.setAttribute('stroke-dashoffset', (-t * 60).toFixed(1));
    const p1 = P[P.length - 1], p0 = P[P.length - 2];
    const ang = Math.atan2(p1[1] - p0[1], p1[0] - p0[0]), c = Math.cos(ang), s = Math.sin(ang), L = w * 2.6, Wd = w * 1.8;
    const Q = (x, y) => `${(p1[0] + x * c - y * s).toFixed(1)},${(p1[1] + x * s + y * c).toFixed(1)}`;
    head.setAttribute('d', a.missile ? `M${Q(10, 0)}L${Q(-6, 6)}L${Q(-6, -6)}Z` : `M${Q(L * .55, 0)}L${Q(-L * .45, Wd)}L${Q(-L * .2, 0)}L${Q(-L * .45, -Wd)}Z`);
    g.style.opacity = clamp((a.t1 + 1.0 - t) / .5, 0, 1);
    if (a.fleet) {
      if (!g._ships) { g._ships = [...Array(9)].map(() => sv('path', { class: 'ship', d: 'M-9,0 L9,0 L6,4 L-6,4 Z M-1,-1 L-1,-11 L6,-2 Z' }, g)); }
      g._ships.forEach((sh, i) => {
        const back = 1 + (i % 3), side = Math.floor(i / 3) - 1;
        const q = P[Math.max(0, P.length - 1 - back * 2)] || p1;
        sh.setAttribute('transform', `translate(${(q[0] - side * 14 * s).toFixed(1)},${(q[1] + side * 14 * c + 2 * Math.sin(t * 3 + i)).toFixed(1)}) scale(1.3)`);
      });
    }
  }
}

// -------------------------------------------------------------------------------------- battles
const bursts = D.battles.map(() => [0, 1, 2].map(() => sv('circle', { class: 'burst', fill: 'none' })));
const popup = el('div', 'plate popup', ui, `<div class="ttl"></div><div class="dt"></div><img class="fl a"><img class="fl b"><div class="n a"></div><div class="vs">VS</div><div class="n b"></div><div class="bar"><i></i><u></u></div><div class="res"></div>`);
const pp = { ttl: popup.querySelector('.ttl'), dt: popup.querySelector('.dt'), fa: popup.querySelector('.fl.a'), fb: popup.querySelector('.fl.b'),
  na: popup.querySelector('.n.a'), nb: popup.querySelector('.n.b'), bar: popup.querySelector('.bar i'), mark: popup.querySelector('.bar u'), res: popup.querySelector('.res') };
const flash = document.getElementById('flash');
function shakeAt(t) {
  let sx = 0, sy = 0;
  for (const b of D.battles) { const d = t - b.t; if (d >= 0 && d < .7) { const a = 15 * (1 - d / .7) ** 2; sx += a * Math.sin(d * 83); sy += a * Math.cos(d * 71); } }
  return [sx, sy];
}
const PDUR = 2.1;
function drawBattles(t) {
  let fl = 0, cur = null;
  D.battles.forEach((b, i) => {
    const d = t - b.t;
    fl = Math.max(fl, d >= 0 && d < .35 ? (1 - d / .35) * (b.nuke ? 1 : .8) : 0);
    const p = proj(b.at[0], b.at[1]);
    bursts[i].forEach((c, k) => {
      const dd = d - k * .18, on = dd >= 0 && dd < 1.1 && p[2] > .1;
      show(c, on); if (!on) return;
      c.setAttribute('cx', p[0]); c.setAttribute('cy', p[1]);
      c.setAttribute('r', 10 + (b.nuke ? 260 : 140) * easeOut(dd / 1.1)); c.setAttribute('stroke-width', 10 * (1 - dd / 1.1)); c.setAttribute('opacity', 1 - dd / 1.1);
    });
    if (!b.nopopup && d > -.45 && d < PDUR) cur = b;
  });
  flash.style.opacity = fl.toFixed(3);
  show(popup, !!cur);
  if (!cur) return;
  const b = cur, d = t - b.t;
  place(popup, 66, 470, .7 + .3 * backOut((d + .45) / .45), 0, Math.min(1, (d + .45) / .2) * clamp((PDUR - d) / .3, 0, 1));
  setText(pp.ttl, b.title.toUpperCase()); setText(pp.dt, b.date);
  if (pp.fa._s !== b.a.polity) { pp.fa.src = D.flags[b.a.polity]; pp.fa._s = b.a.polity; }
  if (pp.fb._s !== b.b.polity) { pp.fb.src = D.flags[b.b.polity]; pp.fb._s = b.b.polity; }
  const u = smooth(d / 1.1);
  setText(pp.na, fmt(lerp(b.a.from, b.a.to, u))); setText(pp.nb, fmt(lerp(b.b.from, b.b.to, u)));
  pp.na.classList.toggle('falling', b.a.to < b.a.from && d > 0 && d < 1.2); pp.nb.classList.toggle('falling', b.b.to < b.b.from && d > 0 && d < 1.2);
  pp.bar.style.background = colour(b.a.polity); popup.querySelector('.bar').style.background = colour(b.b.polity);
  const sh = lerp(.5, b.winner === b.a.polity ? .86 : .14, smooth((d - .2) / 1.0)) + .015 * Math.sin(t * 19) * (d > 0 && d < 1.2);
  pp.bar.style.width = (sh * 100).toFixed(2) + '%'; pp.mark.style.left = (sh * 100).toFixed(2) + '%';
  setText(pp.res, d > 1.0 ? b.result.toUpperCase() : ''); pp.res.style.opacity = clamp((d - 1.0) / .25, 0, 1);
}

// ---------------------------------------- forces on the map: arrays of glyphs, one per unit of men, falling
const GLYPH = {   // one figure per era, our own drawing
  antiquity: '<path d="M6,2a3,3 0 1,0 0.01,0M3,6h6l1,8h-2l-1,8h-2l-1,-8h-2zM11,4v18" stroke="currentColor" stroke-width="1" fill="currentColor"/>',
  medieval: '<path d="M6,2a3,3 0 1,0 0.01,0M2,6h8v5c0,4 -2,7 -4,8c-2,-1 -4,-4 -4,-8z" fill="currentColor"/>',
  renaissance: '<path d="M6,2a3,3 0 1,0 0.01,0M3,6h6l1,8h-2l-1,8h-2l-1,-8h-2zM10,2l2,12" stroke="currentColor" stroke-width="1.2" fill="currentColor"/>',
  victorian: '<path d="M6,2a3,3 0 1,0 0.01,0M3,6h6l1,8h-2l-1,8h-2l-1,-8h-2zM9,7l4,-6" stroke="currentColor" stroke-width="1.2" fill="currentColor"/>',
  worldwars: '<path d="M1,6h11v10h-11zM1,6l11,10M12,6l-11,10" stroke="currentColor" stroke-width="1.4" fill="none"/>',
  coldwar: '<path d="M6,1l2,4v12l2,3h-8l2,-3v-12z" fill="currentColor"/>',
  modern: '<path d="M1,10l5,-6l5,6l-5,-2z M3,14h6" stroke="currentColor" stroke-width="1.4" fill="currentColor"/>',
};
const forceEls = D.battles.filter(b => !b.nopopup).map(b => {
  const g = el('div', 'forces', ov, `<div class="side a"><div class="grid"></div><b></b></div><div class="side b"><div class="grid"></div><b></b></div><div class="unit"></div>`);
  const ring = sv('circle', { class: 'encircle', fill: 'none' });
  return { b, g, ring, ga: g.querySelector('.a .grid'), gb: g.querySelector('.b .grid'), na: g.querySelector('.a b'), nb: g.querySelector('.b b'), unit: g.querySelector('.unit') };
});
const nice = x => { const p = Math.pow(10, Math.floor(Math.log10(x))); for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= x) return m * p; return 10 * p; };
function drawForces(t) {
  for (const f of forceEls) {
    const b = f.b, d = t - b.t, on = d > -0.4 && d < PDUR;
    show(f.g, on); show(f.ring, on); if (!on) continue;
    const p = proj(b.at[0], b.at[1]);
    const o = Math.min(1, (d + 0.4) / 0.25) * clamp((PDUR - d) / 0.3, 0, 1);
    const unit = nice(Math.max(b.a.from, b.b.from) / 22);
    if (f._unit !== unit || f._skin !== (ERA && ERA.skin)) {
      f._unit = unit; f._skin = ERA && ERA.skin;
      const gl = GLYPH[f._skin] || GLYPH.victorian;
      for (const [grid, side] of [[f.ga, b.a], [f.gb, b.b]]) {
        while (grid.firstChild) grid.removeChild(grid.firstChild);
        const n = Math.max(1, Math.ceil(side.from / unit));
        for (let i = 0; i < n; i++) { const s = document.createElementNS(SVGNS, 'svg'); s.setAttribute('viewBox', '0 0 13 22'); s.setAttribute('width', 30); s.setAttribute('height', 50); s.innerHTML = gl; grid.appendChild(s); }
      }
      f.ga.style.color = colour(b.a.polity); f.gb.style.color = colour(b.b.polity);
      setText(f.unit, `each figure = ${fmt(unit)}`);
    }
    const u = smooth(d / 1.1);
    for (const [grid, side, nEl] of [[f.ga, b.a, f.na], [f.gb, b.b, f.nb]]) {
      const v = lerp(side.from, side.to, clamp(u, 0, 1));
      const alive = Math.ceil(v / unit - 1e-6);
      [...grid.children].forEach((c, i) => { c.style.opacity = i < alive ? 1 : 0.18; c.style.transform = i < alive ? '' : 'translateY(4px)'; });
      setText(nEl, fmt(v));
    }
    place(f.g, 66, 790, 0.92 + 0.08 * backOut((d + 0.4) / 0.4), 0, o);
    const r = lerp(170, 70, smooth((d + 0.4) / 1.6));
    f.ring.setAttribute('cx', p[0]); f.ring.setAttribute('cy', p[1]); f.ring.setAttribute('r', r);
    f.ring.setAttribute('stroke-dashoffset', (t * 40).toFixed(1)); f.ring.style.opacity = o * 0.9;
  }
}

// ------------------------------------------------------------------------ captions, lower-thirds
const capEls = D.captions.map(c => ({ c, e: el('div', 'cap', ui, `<div class="paper">${c.text}</div>`) }));
function drawCaptions(t) {
  for (const { c, e } of capEls) {
    const on = t >= c.t - .05 && t <= c.t + c.d + .3; show(e, on); if (!on) continue;
    place(e, 66, 322 + 22 * (1 - easeOut((t - c.t) / .3)), 1, 0, fade(t, c.t, c.t + c.d + .3, .2, .3));
  }
}
const lowEls = D.lower.map(l => ({ l, e: el('div', 'lower plate', ui, `<div class="in"><span class="ar">${l.ar}</span><span class="dot"></span><span class="tr">${l.tr}</span><span class="dot"></span><span class="en">${l.en}</span></div>`) }));
function drawLower(t) {
  for (const { l, e } of lowEls) {
    const on = t >= l.t - .05 && t <= l.t + l.d + .35; show(e, on); if (!on) continue;
    if (!e._fit) { e._fit = 1; const inn = e.querySelector('.in'); inn.style.transform = `translateX(-50%) scale(${Math.min(1, 850 / inn.offsetWidth).toFixed(3)})`; }
    place(e, lerp(-1100, 66, easeOut((t - l.t) / .35)), 1112, 1, 0, fade(t, l.t, l.t + l.d + .35, .15, .35));
  }
}
const stampEls = (D.stamps || []).map(s => ({ s, e: el('div', 'stamp', ui, s.text) }));
function drawStamps(t) {
  for (const { s, e } of stampEls) {
    const d = s.d || 1.8, on = t >= s.t && t <= s.t + d; show(e, on); if (!on) continue;
    const w = e.offsetWidth || 700;
    place(e, 508 - w / 2, 880, 1.6 - .6 * backOut((t - s.t) / .3), -5, fade(t, s.t, s.t + d, .08, .35));
  }
}

// ----------------------------------------------------------------------------------- the balls
const ballEls = D.balls.map(b => {
  const c = D.cast[b.id];
  const left = b.side ? b.side === 'l' : true;
  const wrap = el('div', 'ball', ui, `<img src="${c.img[b.mood || 'neutral']}">`);
  const bub = el('div', 'bubble ' + (left ? 'l' : 'r'), ui, `<div class="who">${c.name}</div><div class="en">${c.lines_en[b.line]}</div><span class="ar">${c.lines_ar[b.line]}</span>`);
  if (!left) wrap.querySelector('img').style.transform = 'scaleX(-1)';
  return { b, wrap, bub, left };
});
function drawBalls(t) {
  for (const { b, wrap, bub, left } of ballEls) {
    const on = t >= b.t - .1 && t <= b.t + b.d + .35; show(wrap, on); show(bub, on); if (!on) continue;
    const k = backOut((t - b.t) / .4), out = clamp((b.t + b.d + .35 - t) / .35, 0, 1);
    const x = left ? 66 : 950 - 200, y = 1250 + 260 * (1 - k) + 260 * (1 - out);
    const hop = Math.abs(Math.sin((t - b.t) * 7)) * 10 * clamp(1 - (t - b.t) / 1.2, 0, 1);
    place(wrap, x, y - hop, 1, 4 * Math.sin(t * 5), Math.min(1, (t - b.t + .1) / .15));
    const bw = bub.offsetWidth || 400;
    bub.style.transformOrigin = left ? '0 80%' : '100% 80%';
    place(bub, left ? 296 : 720 - bw, 1262, .6 + .4 * backOut((t - b.t - .15) / .3), 0, clamp((t - b.t - .15) / .12, 0, 1) * out);
  }
}

// ---------------------------------------------------------------------------- hook, cost, end
const hook = el('div', 'hook', ui, `<div class="sub">${D.hook.sub}</div><div class="ttl">${D.hook.title}</div><div class="yr"></div>`);
const hookYr = hook.querySelector('.yr');
const clips = [...document.querySelectorAll('video.clip')];
function drawHook(t) {
  const h = D.hook, on = t <= h.t1 + .1;
  show(hook, on);
  if (on) {
    hook.style.transformOrigin = '50% 50%';
    place(hook, 66, 250, 1.35 - .35 * backOut((t - .1) / .4), 0, clamp((t - .05) / .12, 0, 1) * clamp((h.t1 + .1 - t) / .3, 0, 1));
    // the rewind: the year spins from now back to 500 BCE as the hook hands over to the first era
    const r = clamp((t - h.rewind) / (h.t1 - h.rewind), 0, 1);
    const y = Math.round(lerp(2026, -499, Math.pow(r, 1.6)));
    setText(hookYr, r > 0 ? yearLabel(y) : '2026');
  }
  for (const c of clips) {
    const a = +c.dataset.t0, b = +c.dataset.t1, fo = +(c.dataset.fade || .4);
    const o = t < a || t > b ? 0 : clamp(Math.min((t - a) / .15, (b - t) / fo), 0, 1);
    c.style.opacity = o; c.style.display = o > 0 ? '' : 'none';
  }
}
const cost = D.cost ? el('div', 'plate costc', ui, `<div class="k">${D.cost.kicker}</div><div class="n">0</div><div class="l">${D.cost.label} · <span class="ar">${D.cost.ar}</span></div>`) : null;
function drawCost(t) {
  if (!cost) return;
  const c = D.cost, on = t >= c.t0 && t <= c.t1 + .3; show(cost, on); if (!on) return;
  place(cost, 66, 640 + 40 * (1 - easeOut((t - c.t0) / .5)), 1, 0, fade(t, c.t0, c.t1 + .3, .4, .3));
  const u = easeOut((t - c.t0 - .2) / 1.4);
  setText(cost.querySelector('.n'), u < 1 ? fmt(c.value * u) : (c.text || fmt(c.value)));
}
const endc = el('div', 'endc', ui, `<div class="box plate"><h2>${D.end.title}</h2><p>${D.end.line}</p>
  <div class="discord"><b>JOIN THE DISCORD</b><span>${D.end.discord}</span></div><div class="sub">CONTROGLOBE · THE GLOBAL SWAP</div></div>`);
const endBalls = (D.end.balls || []).filter(id => D.cast[id]).map((id, i) => ({ e: el('div', 'ball', endc, `<img src="${D.cast[id].img.happy}">`), i }));
function drawEnd(t) {
  const t0 = D.end.t0, on = t >= t0 - .05; show(endc, on); if (!on) return;
  place(endc, 0, 0, 1, 0, easeOut((t - t0) / .45));
  endc.querySelector('.box').style.transform = `scale(${(.92 + .08 * backOut((t - t0) / .5)).toFixed(4)})`;
  const n = endBalls.length;
  for (const { e, i } of endBalls) {
    const hop = Math.abs(Math.sin((t - t0) * 5 + i * 1.1)) * 26;
    place(e, 66 + i * (684 / Math.max(1, n - 1)), 1190 - hop, .8, 3 * Math.sin(t * 4 + i), clamp((t - t0 - .12 * i) / .25, 0, 1));
  }
}

// ------------------------------------------------------------------------------------ a frame
function render(t) {
  window.__lastT = t;
  SHAKE = shakeAt(t);
  setCamera(t);
  drawHud(t);                            // first: it sets the era's skin
  drawMap(t);
  renderer.render(scene, camera);
  drawArrows(t); drawArmies(t); drawBattles(t); drawForces(t);
  drawCaptions(t); drawLower(t); drawStamps(t); drawBalls(t);
  drawCost(t); drawHook(t); drawEnd(t);
}

const SEG_T0 = window.SEG_T0 || 0, SEG_DUR = window.SEG_DUR || D.duration;
render(SEG_T0);
const tl = gsap.timeline({ paused: true, onUpdate() { render(tl.time() + SEG_T0); } });
tl.to({}, { duration: SEG_DUR }, 0);
window.__timelines = window.__timelines || {};
window.__timelines.root = tl;
window.__render = render;
