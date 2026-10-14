/* ================= LOCUS UI ================= */
var BE = window.BE || (window.BE = { on: false, push() { } });   /* optional backend link, filled in by backend.js; BE.on stays false without a backend */
const $ = id => document.getElementById(id);
const C = { aqua: '#22C3E6', aquaD: '#0E9DBE', aquaL: '#BFE9F3', em: '#10B981', emD: '#0B8A5E', ink: '#0B3A4A', amber: '#F5A524', coral: '#EF6A6A', slate: '#7C93C3' };
const SC = 30; // px per metre on the 1200x720 canvases
const trustCol = t => t > 0.7 ? C.em : t > 0.4 ? C.amber : C.coral;
const pct = v => Math.round(v * 100);
let tabNow = 'dash';

/* ---------- shared floor drawing ---------- */
function drawFloor(ctx, o = {}) {
  const s = o.scale || SC; ctx.save(); ctx.clearRect(0, 0, FLOOR.w * s, FLOOR.h * s);
  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, FLOOR.w * s, FLOOR.h * s);
  ROOMS.forEach(r => {
    const [a, b, c, d] = r.r; const hot = o.hot && o.hot[r.id] || 0;
    ctx.fillStyle = r.id === 'corr' ? '#F2FBFD' : '#FAFEFF'; ctx.fillRect(a * s, b * s, (c - a) * s, (d - b) * s);
    if (hot > 0.02) { ctx.fillStyle = `rgba(16,185,129,${Math.min(0.32, hot * 0.36)})`; ctx.fillRect(a * s, b * s, (c - a) * s, (d - b) * s); }
    if (!o.noLabels) { ctx.fillStyle = 'rgba(11,58,74,.42)'; ctx.font = `600 ${Math.round(s * 0.5)}px Figtree, sans-serif`; ctx.textAlign = 'center'; ctx.fillText(r.name.toUpperCase(), (a + c) / 2 * s, (SITE_ID === 'warehouse' ? 8.2 : b + (b === 0 ? 8.1 : 1.15)) * s); }
  });
  ctx.strokeStyle = o.wallCol || '#7FCBDF'; ctx.lineWidth = Math.max(2, s * 0.14); ctx.lineCap = 'round'; ctx.beginPath();
  WALLS.forEach(w => { ctx.moveTo(w[0] * s, w[1] * s); ctx.lineTo(w[2] * s, w[3] * s); }); ctx.stroke(); ctx.restore();
}
function drawEllipse(ctx, e, cx, cy, s, fill, stroke) {
  ctx.save(); ctx.translate(cx * s, cy * s); ctx.rotate(e.th); ctx.beginPath(); ctx.ellipse(0, 0, e.a * s, e.b * s, 0, 0, 7); ctx.fillStyle = fill; ctx.fill(); ctx.strokeStyle = stroke; ctx.lineWidth = 2; ctx.stroke(); ctx.restore();
}

/* ---------- live simulation state ---------- */
const DEF = { sigma: 0.6, loss: 0.10, wallBias: 1.8, burst: 0.004, obstructBias: 4, driftBias: 2.5 };
const cfg = { ...DEF, dead: new Set(), obstruct: new Set(), drift: new Set() };
let nAnch = 6, anchors, walker, rng, loc, kf, lastLs, lastTruth, lastEst, acc = 0, tPrev = 0, simT = 0;
let frame = { truth: [3, 12], est: null, ls: null, out: null, kfp: null }, prevFrame = null;
let hist = { lo: [], kf: [], ls: [] }, trail = [];
const show = { cloud: true, base: true, links: true };
function resetSim() {
  anchors = DROP_ORDER.slice(0, nAnch).map(i => ANCHORS[i]);
  rng = rngMake(2026); walker = new Walker(1.2, 6); kf = new KalmanCV(); lastLs = [20, 12]; trail = []; hist = { lo: [], kf: [], ls: [] }; prevFrame = null;
  loc = new Locus(anchors, { N: 600, sigma: cfg.sigma, rng: rngMake(11), inflate: 2.0 }); buildAnchorList();
}
function simStep() {
  if (BE.on) return;   /* a live backend session drives the frames instead */
  const dt = 0.1, t = walker.step(dt).slice(); loc.sigma = cfg.sigma;
  const m = measure(t, anchors, cfg, rng), ls = lsFix(anchors, m, lastLs); if (ls) lastLs = ls;
  const kp = kf.update(ls, dt), out = loc.step(m, dt); simT += dt;
  prevFrame = frame; frame = { truth: t, ls, out, kfp: kp, meas: m };
  if (out) { trail.push(out.pos.slice()); if (trail.length > 40) trail.shift(); }
  const e = (p) => p ? Math.hypot(p[0] - t[0], p[1] - t[1]) : null;
  hist.lo.push(out ? e(out.pos) : null); hist.kf.push(e(kp)); hist.ls.push(e(ls));
  Object.values(hist).forEach(a => { if (a.length > 300) a.shift(); });
}

/* ---------- map render ---------- */
const mapC = $('map'), mctx = mapC.getContext('2d');
function lerp(a, b, f) { return a + (b - a) * f; }
function renderMap(f) {
  const out = frame.out; drawFloor(mctx, { hot: out && out.rooms });
  const ctx = mctx, s = SC;
  /* link lines */
  if (show.links && out) anchors.forEach((a, i) => {
    const t = out.trust[i], dead = cfg.dead.has(a.id); ctx.save(); ctx.beginPath(); ctx.moveTo(a.x * s, a.y * s); ctx.lineTo(out.pos[0] * s, out.pos[1] * s);
    ctx.strokeStyle = dead ? 'rgba(239,106,106,.35)' : trustCol(t); ctx.globalAlpha = dead ? 1 : 0.15 + 0.5 * t; ctx.lineWidth = dead ? 1.5 : 1 + t * 3; if (dead || !out.usable[i]) ctx.setLineDash([6, 7]); ctx.stroke(); ctx.restore();
  });
  /* particles */
  if (show.cloud && loc.inited) { ctx.fillStyle = 'rgba(16,185,129,.35)'; for (let i = 0; i < loc.N; i += 2) { ctx.fillRect(loc.px[i] * s - 1.5, loc.py[i] * s - 1.5, 3, 3); } }
  /* trail */
  if (trail.length > 2) { ctx.save(); ctx.lineWidth = 3; ctx.lineCap = 'round'; for (let i = 1; i < trail.length; i++) { ctx.strokeStyle = `rgba(16,185,129,${i / trail.length * 0.55})`; ctx.beginPath(); ctx.moveTo(trail[i - 1][0] * s, trail[i - 1][1] * s); ctx.lineTo(trail[i][0] * s, trail[i][1] * s); ctx.stroke(); } ctx.restore(); }
  /* anchors */
  anchors.forEach((a, i) => {
    const dead = cfg.dead.has(a.id), t = out ? out.trust[i] : 0.8, col = dead ? C.coral : trustCol(t);
    ctx.save(); ctx.translate(a.x * s, a.y * s);
    ctx.beginPath(); ctx.arc(0, 0, 17, 0, 7); ctx.fillStyle = '#fff'; ctx.fill(); ctx.lineWidth = 4; ctx.strokeStyle = '#E7F5F9'; ctx.stroke();
    ctx.beginPath(); ctx.arc(0, 0, 17, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * (dead ? 1 : Math.max(0.04, t))); ctx.strokeStyle = col; ctx.lineWidth = 4; ctx.lineCap = 'round'; ctx.stroke();
    ctx.fillStyle = dead ? C.coral : C.aquaD; ctx.beginPath(); ctx.arc(0, 0, 5, 0, 7); ctx.fill();
    ctx.fillStyle = C.ink; ctx.font = '700 13px Figtree'; ctx.textAlign = 'center'; ctx.fillText(a.id + (dead ? ' ✕' : ''), 0, -24); ctx.restore();
  });
  if (!out) return;
  const fr = Math.min(1, f), px = prevFrame && prevFrame.out ? prevFrame.out.pos : out.pos;
  const ex = lerp(px[0], out.pos[0], fr), ey = lerp(px[1], out.pos[1], fr);
  const tx = prevFrame ? lerp(prevFrame.truth[0], frame.truth[0], fr) : frame.truth[0], ty = prevFrame ? lerp(prevFrame.truth[1], frame.truth[1], fr) : frame.truth[1];
  drawEllipse(ctx, out.ell, ex, ey, s, 'rgba(16,185,129,.16)', 'rgba(16,185,129,.9)');
  if (show.base && frame.ls) { const x = frame.ls[0] * s, y = frame.ls[1] * s; ctx.save(); ctx.translate(x, y); ctx.rotate(Math.PI / 4); ctx.fillStyle = C.amber; ctx.fillRect(-6, -6, 12, 12); ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.strokeRect(-6, -6, 12, 12); ctx.restore(); }
  /* truth */
  ctx.beginPath(); ctx.arc(tx * s, ty * s, 7, 0, 7); ctx.fillStyle = C.ink; ctx.fill(); ctx.strokeStyle = '#fff'; ctx.lineWidth = 2.5; ctx.stroke();
  /* estimate with pulse */
  const pul = (performance.now() % 1800) / 1800; ctx.beginPath(); ctx.arc(ex * s, ey * s, 10 + pul * 22, 0, 7); ctx.strokeStyle = `rgba(16,185,129,${0.5 * (1 - pul)})`; ctx.lineWidth = 3; ctx.stroke();
  ctx.beginPath(); ctx.arc(ex * s, ey * s, 11, 0, 7); ctx.fillStyle = C.em; ctx.fill(); ctx.strokeStyle = '#fff'; ctx.lineWidth = 3.5; ctx.stroke();
  ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(ex * s, ey * s, 3.5, 0, 7); ctx.fill();
}

/* ---------- side panels ---------- */
let aRows = {};
function buildAnchorList() {
  const box = $('anchors'); box.innerHTML = ''; aRows = {};
  anchors.forEach(a => {
    const d = document.createElement('div'); d.className = 'arow';
    d.innerHTML = `<div class="t"><span>${a.id}</span><span class="pill g" data-s>Trusted</span><button class="tog" data-k aria-label="Toggle ${a.id} offline">Kill</button><em data-v>–</em></div><div class="bar"><i data-b style="width:50%"></i></div><div class="why" data-w>…</div>`;
    d.querySelector('[data-k]').onclick = () => toggleDead(a.id); box.appendChild(d);
    aRows[a.id] = { el: d, s: d.querySelector('[data-s]'), v: d.querySelector('[data-v]'), b: d.querySelector('[data-b]'), w: d.querySelector('[data-w]'), k: d.querySelector('[data-k]') };
  });
}
function updatePanels() {
  const out = frame.out; if (!out) return; const t = frame.truth;
  anchors.forEach((a, i) => {
    const r = aRows[a.id], dead = cfg.dead.has(a.id), tr = out.trust[i];
    r.el.classList.toggle('dead', dead); r.b.style.width = (dead ? 100 : Math.max(3, pct(tr))) + '%'; r.b.style.background = dead ? C.coral : trustCol(tr);
    r.v.textContent = dead ? 'offline' : tr.toFixed(2); r.k.textContent = dead ? 'Revive' : 'Kill';
    r.s.className = 'pill ' + (dead ? 'r' : tr > 0.7 ? 'g' : tr > 0.4 ? 'a' : 'r'); r.s.textContent = dead ? 'Offline' : tr > 0.7 ? 'Trusted' : tr > 0.4 ? 'Down-weighted' : 'Ignored';
    r.w.textContent = dead ? 'No packets: anchor failure detected, alert sent' : out.reasons[i];
  });
  /* rooms */
  const rs = Object.entries(out.rooms).sort((a, b) => b[1] - a[1]), top = rs[0];
  $('b-room').firstChild.textContent = roomName(top[0]) + ' · ' + pct(top[1]) + '%';
  const err = Math.hypot(out.pos[0] - t[0], out.pos[1] - t[1]), noT = !!frame.noTruth;   /* noT: live BLE readings, no ground truth */
  $('b-room2').textContent = noT ? 'Live readings: no ground truth available' : 'True room: ' + roomName(roomAt(t[0], t[1])) + (roomAt(t[0], t[1]) === top[0] ? ' ✓ match' : ' (filter still converging)');
  $('rooms').innerHTML = rs.slice(0, 4).map(([id, p]) => `<div class="r"><span>${roomName(id)}</span><div class="bar"><i style="width:${pct(p)}%;background:${C.em}"></i></div><em>${pct(p)}%</em></div>`).join('');
  /* kpis */
  const lsE = frame.ls ? Math.hypot(frame.ls[0] - t[0], frame.ls[1] - t[1]) : null;
  $('k-err').innerHTML = noT ? '–' : err.toFixed(1) + '<i>m</i>'; $('k-err2').textContent = noT ? 'no ground truth for live readings' : 'vs trilateration ' + (lsE == null ? '–' : lsE.toFixed(1) + ' m');
  $('k-ell').innerHTML = out.ell.a.toFixed(1) + '<i>m</i>';
  const usable = anchors.filter((a, i) => out.usable[i] && !cfg.dead.has(a.id)).length; $('k-anc').innerHTML = usable + '<i>/ ' + anchors.length + '</i>';
  $('k-anc2').textContent = cfg.dead.size ? cfg.dead.size + ' offline · degrading gracefully' : 'receiving this cycle';
  $('k-wall').innerHTML = out.wallMu.toFixed(1) + '<i>m / wall</i>';
  const worst = anchors.map((a, i) => [i, out.trust[i]]).filter(([i]) => out.usable[i] && !cfg.dead.has(anchors[i].id)).sort((a, b) => a[1] - b[1])[0];
  $('mapnote').innerHTML = `<b>${roomName(top[0])}</b> · ${pct(top[1])}% sure · ±${out.ell.a.toFixed(1)} m` + (worst && worst[1] < 0.5 ? `<br>${anchors[worst[0]].id} distrusted: ${out.reasons[worst[0]]}` : cfg.dead.size ? `<br>${[...cfg.dead].join(', ')} offline, using remaining anchors + motion history` : '');
}

/* ---------- error chart ---------- */
const ec = $('errchart'), ectx = ec.getContext('2d');
function drawLines(ctx, W, H, series, o) {
  ctx.clearRect(0, 0, W, H); const L = 46, R = 14, T = 12, B = 26, pw = W - L - R, ph = H - T - B;
  const ymax = o.ymax; ctx.font = '600 13px Figtree'; ctx.fillStyle = '#7A9AA6'; ctx.textAlign = 'right';
  for (let v = 0; v <= ymax + 1e-6; v += o.ystep) { const y = T + ph - v / ymax * ph; ctx.strokeStyle = '#E3F3F7'; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(L, y); ctx.lineTo(W - R, y); ctx.stroke(); ctx.fillText(v + ' m', L - 8, y + 4); }
  if (o.target) { const y = T + ph - o.target / ymax * ph; ctx.setLineDash([6, 6]); ctx.strokeStyle = C.em; ctx.globalAlpha = .6; ctx.beginPath(); ctx.moveTo(L, y); ctx.lineTo(W - R, y); ctx.stroke(); ctx.setLineDash([]); ctx.globalAlpha = 1; ctx.fillStyle = C.emD; ctx.textAlign = 'left'; ctx.fillText('2 m target', L + 6, y - 6); }
  series.forEach(se => { ctx.beginPath(); let pen = false; const n = o.n;
    se.d.forEach((v, i) => { if (v == null) { pen = false; return; } const x = L + (o.xs ? o.xs[i] : i / (n - 1)) * pw, y = T + ph - Math.min(v, ymax) / ymax * ph; if (!pen) { ctx.moveTo(x, y); pen = true; } else ctx.lineTo(x, y); });
    ctx.strokeStyle = se.c; ctx.lineWidth = se.w || 3; ctx.lineJoin = 'round'; ctx.stroke(); });
  return { L, T, pw, ph };
}
function renderChart() {
  const n = 300, pad = a => { const r = new Array(n - a.length).fill(null).concat(a); return r; };
  const sm = a => a.map((v, i) => { if (v == null) return null; let s = 0, c = 0; for (let k = Math.max(0, i - 2); k <= i; k++) if (a[k] != null) { s += a[k]; c++; } return s / c; });
  const all = [...hist.lo, ...hist.kf, ...hist.ls].filter(v => v != null); const ymax = Math.max(4, Math.ceil(Math.max(...all, 1) / 2) * 2);
  drawLines(ectx, 1200, 360, [{ d: pad(sm(hist.ls)), c: C.amber, w: 2 }, { d: pad(sm(hist.kf)), c: C.slate, w: 2.5 }, { d: pad(sm(hist.lo)), c: C.em, w: 4 }], { ymax, ystep: ymax > 8 ? 4 : 2, n, target: 2 });
}

/* ---------- controls ---------- */
function bindRange(id, outId, fmt, set) { const el = $(id); const f = () => { set(+el.value); $(outId).textContent = fmt(+el.value); }; el.addEventListener('input', f); f(); return el; }
bindRange('s-sigma', 'o-sigma', v => v.toFixed(1) + ' m', v => { cfg.sigma = v; BE.push(); });
bindRange('s-loss', 'o-loss', v => v + '%', v => { cfg.loss = v / 100; BE.push(); });
bindRange('s-wall', 'o-wall', v => v.toFixed(1) + ' m/wall', v => { cfg.wallBias = v; BE.push(); });
bindRange('s-n', 'o-n', v => v, v => { if (v !== nAnch) { nAnch = v; if (anchors) resetSim(); syncScen(); BE.push(); } });
function toggleSet(set, id) { set.has(id) ? set.delete(id) : set.add(id); }
function ensure(id) { const idx = DROP_ORDER.findIndex(i => ANCHORS[i].id === id); if (idx >= nAnch) { nAnch = 6; $('s-n').value = 6; $('o-n').textContent = 6; resetSim(); } }
function toggleDead(id) { toggleSet(cfg.dead, id); syncScen(); notifyApp(); BE.push(); }
function syncScen() {
  $('sc-body').setAttribute('aria-pressed', cfg.obstruct.has('A3')); $('sc-drift').setAttribute('aria-pressed', cfg.drift.has('A2')); $('sc-kill').setAttribute('aria-pressed', cfg.dead.has('A3'));
  $('sc-kill').textContent = cfg.dead.has('A3') ? 'Revive A3' : 'Kill A3';
}
$('sc-body').onclick = () => { ensure('A3'); toggleSet(cfg.obstruct, 'A3'); syncScen(); BE.push(); };
$('sc-drift').onclick = () => { ensure('A2'); toggleSet(cfg.drift, 'A2'); syncScen(); BE.push(); };
$('sc-kill').onclick = () => { ensure('A3'); toggleDead('A3'); };
function setSl(id, v, o, fmt) { $(id).value = v; $(id).dispatchEvent(new Event('input')); }
$('sc-storm').onclick = () => { nAnch = 6; setSl('s-n', 6); resetSim(); setSl('s-sigma', 1.2); setSl('s-loss', 40); setSl('s-wall', 2.4); cfg.obstruct = new Set(['A3']); cfg.drift = new Set(['A2']); cfg.dead = new Set(['A5']); syncScen(); notifyApp(); BE.push(); };
$('sc-reset').onclick = () => { setSl('s-sigma', DEF.sigma); setSl('s-loss', 10); setSl('s-wall', DEF.wallBias); setSl('s-n', 6); cfg.dead.clear(); cfg.obstruct.clear(); cfg.drift.clear(); resetSim(); syncScen(); notifyApp(); BE.push(); };
[['c-cloud', 'cloud'], ['c-base', 'base'], ['c-links', 'links']].forEach(([id, k]) => $(id).onclick = e => { show[k] = !show[k]; e.currentTarget.setAttribute('aria-pressed', show[k]); });
mapC.addEventListener('click', e => { const r = mapC.getBoundingClientRect(), x = (e.clientX - r.left) / r.width * FLOOR.w, y = (e.clientY - r.top) / r.height * FLOOR.h; const a = anchors.find(a => Math.hypot(a.x - x, a.y - y) < 1.1); if (a) toggleDead(a.id); });
mapC.addEventListener('mousemove', e => { const r = mapC.getBoundingClientRect(), x = (e.clientX - r.left) / r.width * FLOOR.w, y = (e.clientY - r.top) / r.height * FLOOR.h; mapC.style.cursor = anchors.some(a => Math.hypot(a.x - x, a.y - y) < 1.1) ? 'pointer' : 'default'; });

/* ---------- tabs ---------- */
document.querySelectorAll('nav button').forEach(b => b.onclick = () => {
  document.querySelectorAll('nav button').forEach(x => x.setAttribute('aria-selected', x === b));
  document.querySelectorAll('section.view').forEach(v => v.classList.toggle('on', v.id === 'v-' + b.dataset.v)); tabNow = b.dataset.v;
  if (tabNow === 'plan') renderPlanner(); if (tabNow === 'bench') renderBench(); window.scrollTo({ top: 0 });
});

/* ================= PLANNER ================= */
const PL = { cand: [], cells: [], plan: [], ready: false };
function errModel(info) { // info = {a,b,c} of 2x2 symmetric matrix + weak prior; expected error = sqrt(trace(inv))
  const a = info[0] + 1 / 36, b = info[1], c = info[2] + 1 / 36, det = a * c - b * b; return Math.sqrt((a + c) / det);
}
function contrib(ax, ay, cx, cy) {
  const dx = cx - ax, dy = cy - ay, d = Math.max(0.5, Math.hypot(dx, dy)), k = wallsBetween(ax, ay, cx, cy), v = 0.8 * 0.8 + Math.pow(k * 0.9, 2) + Math.pow(d * 0.06, 2), ux = dx / d, uy = dy / d;
  return [ux * ux / v, ux * uy / v, uy * uy / v];
}
function planInit() {
  if (PL.ready) return; PL.cand = []; PL.cells = [];
  for (let y = 1; y < 24; y += 2) for (let x = 1; x < 40; x += 2) PL.cand.push([x, y]);
  for (let y = 1; y < 24; y += 2) for (let x = 1; x < 40; x += 2) PL.cells.push([x, y]);
  const M = PL.cand.map(c => PL.cells.map(q => contrib(c[0], c[1], q[0], q[1])));
  const info = PL.cells.map(() => [0, 0, 0]), chosen = [];
  for (let n = 0; n < 10; n++) {
    let best = -1, bs = 1e9;
    PL.cand.forEach((c, ci) => { if (chosen.includes(ci)) return; let s = 0; for (let q = 0; q < PL.cells.length; q++) { const m = M[ci][q], I = info[q]; s += Math.min(8, errModel([I[0] + m[0], I[1] + m[1], I[2] + m[2]])); } if (s < bs) { bs = s; best = ci; } });
    chosen.push(best); for (let q = 0; q < PL.cells.length; q++) { const m = M[best][q]; info[q][0] += m[0]; info[q][1] += m[1]; info[q][2] += m[2]; }
  }
  PL.plan = chosen.map(i => PL.cand[i]); PL.ready = true;
}
function errMap(set) { const out = []; for (let y = 0; y < FLOOR.h; y++) for (let x = 0; x < FLOOR.w; x++) { const I = [0, 0, 0]; set.forEach(a => { const m = contrib(a[0], a[1], x + .5, y + .5); I[0] += m[0]; I[1] += m[1]; I[2] += m[2]; }); out.push(Math.min(8, errModel(I))); } return out; }
const mixc = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t));
function heat(e) { const G = [16, 185, 129], A = [34, 195, 230], Y = [245, 165, 36]; if (e < 0.8) return mixc([120, 226, 180], G, e / 0.8); if (e < 2) return mixc(G, A, (e - 0.8) / 1.2); return mixc(A, Y, Math.min(1, (e - 2) / 2.5)); }
const pctx = $('pmap').getContext('2d'), COST = 2800;
function stats(set) { const m = errMap(set), mean = m.reduce((a, b) => a + b, 0) / m.length, cov = m.filter(v => v < 2).length / m.length; return { m, mean, cov }; }
function renderPlanner() {
  planInit(); const n = +$('p-n').value, set = PL.plan.slice(0, n), st = stats(set);
  $('p-nv').textContent = n; $('p-err').textContent = st.mean.toFixed(1) + ' m'; $('p-cov').textContent = pct(st.cov) + '%'; $('p-cost').textContent = '₹' + (n * COST).toLocaleString('en-IN');
  $('p-sub').textContent = n + ' anchors · modelled';
  drawFloor(pctx, { noLabels: false, wallCol: 'rgba(11,58,74,.55)' });
  pctx.save(); pctx.globalCompositeOperation = 'source-over'; st.m.forEach((e, i) => { const x = i % FLOOR.w, y = (i / FLOOR.w) | 0, c = heat(e); pctx.fillStyle = `rgba(${c[0]},${c[1]},${c[2]},.62)`; pctx.fillRect(x * SC, y * SC, SC, SC); }); pctx.restore();
  pctx.save(); pctx.strokeStyle = 'rgba(11,58,74,.6)'; pctx.lineWidth = 4; pctx.lineCap = 'round'; pctx.beginPath(); WALLS.forEach(w => { pctx.moveTo(w[0] * SC, w[1] * SC); pctx.lineTo(w[2] * SC, w[3] * SC); }); pctx.stroke(); pctx.restore();
  set.forEach((a, i) => { pctx.beginPath(); pctx.arc(a[0] * SC, a[1] * SC, 15, 0, 7); pctx.fillStyle = C.ink; pctx.fill(); pctx.strokeStyle = '#fff'; pctx.lineWidth = 3; pctx.stroke(); pctx.fillStyle = '#fff'; pctx.font = '700 13px Figtree'; pctx.textAlign = 'center'; pctx.fillText(i + 1, a[0] * SC, a[1] * SC + 4.5); });
  const dense = []; for (let y = 4; y < 24; y += 8) for (let x = 4; x < 40; x += 8) dense.push([x, y]); const dn = stats(dense), cur = stats(ANCHORS.map(a => [a.x, a.y]));
  const row = (nm, k, s, win) => `<tr><td>${nm}</td><td>${k}</td><td>₹${(k * COST).toLocaleString('en-IN')}</td><td class="${win ? 'win' : ''}">${s.mean.toFixed(1)} m</td></tr>`;
  $('p-tab').innerHTML = row('Dense grid', dense.length, dn) + row('Hand-placed', ANCHORS.length, cur) + row('LOCUS plan', n, st, true);
}
$('p-n').addEventListener('input', renderPlanner);

/* ================= BENCHMARK ================= */
let benchRes = null, running = false;
const bcx = $('bchart').getContext('2d');
function renderBench() {
  if (!benchRes) { drawLines(bcx, 1200, 600, [], { ymax: 6, ystep: 2, n: 5, target: 2 }); bcx.fillStyle = '#7A9AA6'; bcx.font = '600 18px Figtree'; bcx.textAlign = 'center'; bcx.fillText('Run the benchmark to see results', 600, 300); return; }
  const r = benchRes, ymax = Math.max(6, Math.ceil(Math.max(...r.map(x => Math.max(x.ls.med, x.kf.med))) / 2) * 2), xs = r.map((_, i) => i / (r.length - 1));
  const g = drawLines(bcx, 1200, 600, [{ d: r.map(x => x.ls.med), c: C.amber, w: 3 }, { d: r.map(x => x.kf.med), c: C.slate, w: 3 }, { d: r.map(x => x.lo.med), c: C.em, w: 5 }], { ymax, ystep: 2, n: r.length, xs, target: 2 });
  bcx.textAlign = 'center'; bcx.font = '700 15px Figtree'; bcx.fillStyle = C.ink;
  r.forEach((x, i) => { const px = g.L + xs[i] * g.pw; bcx.fillText(x.n + ' anchors', px, 590); [[x.lo.med, C.em], [x.kf.med, C.slate], [x.ls.med, C.amber]].forEach(([v, c], k) => { const py = g.T + g.ph - Math.min(v, ymax) / ymax * g.ph; bcx.beginPath(); bcx.arc(px, py, k === 0 ? 7 : 5, 0, 7); bcx.fillStyle = c; bcx.fill(); bcx.strokeStyle = '#fff'; bcx.lineWidth = 2; bcx.stroke(); }); const py = g.T + g.ph - Math.min(x.lo.med, ymax) / ymax * g.ph; bcx.fillStyle = C.emD; bcx.fillText(x.lo.med.toFixed(1), px, py + 26); });
  $('b-tab').innerHTML = r.map(x => `<tr><td>${x.n}</td><td>${x.ls.med.toFixed(1)}</td><td>${x.kf.med.toFixed(1)}</td><td class="win">${x.lo.med.toFixed(1)}</td><td>${x.lo.p90.toFixed(1)}</td><td>${pct(x.lo.w2)}%</td><td>${pct(x.cal)}%</td></tr>`).join('');
}
$('b-run').onclick = async () => {
  if (running) return; running = true; const btn = $('b-run'); btn.disabled = true;
  const bc = { sigma: 0.8, loss: 0.15, wallBias: 2.2, burst: 0.012, obstructBias: 4, driftBias: 2.5, inflate: 2.0, dead: new Set(), obstruct: new Set(), drift: new Set() };
  const seeds = [1, 2, 3], res = [], t0 = performance.now(), tick = () => new Promise(r => setTimeout(r, 0));
  for (let n = 6; n >= 2; n--) {
    btn.textContent = 'Running ' + n + ' anchors…'; await tick();
    const agg = { ls: [], kf: [], lo: [], inside: 0, n: 0 };
    for (const sd of seeds) { const r = runTrial(n, bc, 300, sd, engineNow()); ['ls', 'kf', 'lo'].forEach(k => agg[k].push(...r[k])); agg.inside += r.inside; agg.n += r.n; await tick(); }
    const st = a => ({ med: ptile(a, .5), p90: ptile(a, .9), w2: a.filter(e => e < 2).length / a.length });
    res.push({ n, ls: st(agg.ls), kf: st(agg.kf), lo: st(agg.lo), cal: agg.inside / agg.n });
  }
  benchRes = res; $('b-meta').textContent = '3 paths × 300 steps · ' + ((performance.now() - t0) / 1000).toFixed(1) + ' s'; btn.disabled = false; btn.textContent = 'Run again'; running = false; renderBench();
};

/* ================= STAFF APP ================= */
const STAFF = {
  hospital: { lvl: 'Level 2', head: 'Find equipment fast', ph: 'Search pump, wheelchair, ECG', cats: ['All', 'Pumps', 'Wheelchairs', 'ECG', 'Oxygen'], me: [2.5, 12],
    items: [
      { id: 'P-12', name: 'Infusion pump P-12', cat: 'Pumps', live: true },
      { id: 'W-3', name: 'Wheelchair W-3', cat: 'Wheelchairs', pos: [8.5, 12.3], conf: 91 },
      { id: 'E-7', name: 'ECG machine E-7', cat: 'ECG', pos: [27, 19.5], conf: 88 },
      { id: 'P-07', name: 'Infusion pump P-07', cat: 'Pumps', pos: [4.5, 4.5], conf: 93 },
      { id: 'W-9', name: 'Wheelchair W-9', cat: 'Wheelchairs', pos: [35, 4.8], conf: 86 },
      { id: 'O-2', name: 'Oxygen cylinder O-2', cat: 'Oxygen', pos: [16.5, 20], conf: 94 }] },
  warehouse: { lvl: 'Bay 1', head: 'Find stock fast', ph: 'Search forklift, pallet, scanner', cats: ['All', 'Vehicles', 'Pallets', 'Tools'], me: [2.5, 12],
    items: [
      { id: 'FL-2', name: 'Forklift FL-2', cat: 'Vehicles', live: true },
      { id: 'PJ-4', name: 'Pallet jack PJ-4', cat: 'Vehicles', pos: [6, 8], conf: 92 },
      { id: 'PL-1042', name: 'Pallet #1042 (frozen)', cat: 'Pallets', pos: [20, 18], conf: 89 },
      { id: 'PL-0877', name: 'Pallet #0877', cat: 'Pallets', pos: [28, 6], conf: 90 },
      { id: 'SC-9', name: 'Handheld scanner SC-9', cat: 'Tools', pos: [36, 14], conf: 85 },
      { id: 'C-11', name: 'Picking cart C-11', cat: 'Vehicles', pos: [12.5, 17.5], conf: 91 }] },
};
let ITEMS = STAFF.hospital.items, ME = STAFF.hospital.me, selId = 'P-12', cat = 'All', query = '';
function route(to) {
  const near = (arr, v) => arr.reduce((b, x) => Math.abs(x - v) < Math.abs(b - v) ? x : b, arr[0]), pts = [ME];
  if (SITE_ID === 'warehouse') { if (to[0] < 8) pts.push([to[0], 12]); else { const ax = near([12, 20, 28, 36], to[0]); pts.push([ax, 12], [ax, to[1]]); } }
  else { const d = to[1] < 9 ? TOP_DOORS : to[1] > 15 ? BOT_DOORS : null; if (!d) pts.push([to[0], 12]); else { const dx = near(d, to[0]); pts.push([dx, 12], [dx, to[1] < 9 ? 6 : 18]); } }
  pts.push(to); return pts;
}
function rlen(p) { let s = 0; for (let i = 1; i < p.length; i++) s += Math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1]); return s; }
function itemInfo(it) {
  if (it.live) { const o = frame.out; if (!o) return { pos: [15, 12], zone: '…', conf: 0, ell: null }; const top = Object.entries(o.rooms).sort((a, b) => b[1] - a[1])[0]; return { pos: o.pos, zone: roomName(top[0]), conf: pct(top[1]), ell: o.ell }; }
  return { pos: it.pos, zone: roomName(roomAt(it.pos[0], it.pos[1])), conf: it.conf, ell: null };
}
function renderChips() { $('schips').innerHTML = STAFF[SITE_ID].cats.map(c => `<button class="chip" aria-pressed="${c === cat}">${c}</button>`).join(''); $('schips').querySelectorAll('button').forEach(b => b.onclick = () => { cat = b.textContent; renderChips(); renderList(); }); }
function renderList() {
  const q = query.trim().toLowerCase(), list = ITEMS.filter(i => (cat === 'All' || i.cat === cat) && (!q || (i.name + ' ' + i.cat).toLowerCase().includes(q)));
  const box = $('slist'); box.innerHTML = '';
  if (!list.length) { box.innerHTML = '<p class="note" style="text-align:center;padding:30px 10px">No equipment matches. Try “pump”, “wheelchair” or “ECG”.</p>'; return; }
  list.forEach(it => { const d = document.createElement('div'); const sel = it.id === selId; d.className = 'item' + (sel ? ' sel' : ''); d.tabIndex = 0; d.setAttribute('role', 'button'); d.dataset.id = it.id;
    d.innerHTML = `<div class="row"><div><b>${it.name}</b><small data-sub></small></div><span class="pill g" data-conf></span></div>` + (sel ? `<canvas id="smap" width="720" height="432"></canvas><button class="go"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round"><path d="M3 11l18-8-8 18-2-8z"/></svg>Navigate to ${it.id}</button>` : '');
    d.onclick = e => { if (selId !== it.id) { selId = it.id; renderList(); } }; d.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); d.click(); } }; box.appendChild(d); });
  updateApp();
}
function updateApp() {
  document.querySelectorAll('#slist .item').forEach(d => { const it = ITEMS.find(i => i.id === d.dataset.id), inf = itemInfo(it), dist = rlen(route(inf.pos));
    d.querySelector('[data-sub]').textContent = inf.zone + ' · about ' + Math.round(dist) + ' m from you'; const p = d.querySelector('[data-conf]'); p.textContent = inf.conf + '% sure'; p.className = 'pill ' + (inf.conf >= 85 ? 'g' : inf.conf >= 60 ? 'a' : 'r'); });
  const c = $('smap'); if (!c) return; const it = ITEMS.find(i => i.id === selId), inf = itemInfo(it), ctx = c.getContext('2d'), s = 18;
  drawFloor(ctx, { scale: s, noLabels: true }); ctx.save(); ctx.font = '600 11px Figtree'; ctx.fillStyle = 'rgba(11,58,74,.45)'; ctx.textAlign = 'center'; ROOMS.forEach(r => { if (r.id !== 'corr') ctx.fillText(r.name, (r.r[0] + r.r[2]) / 2 * s, (r.r[1] + 1) * s + 4); }); ctx.restore();
  const rt = route(inf.pos); ctx.save(); ctx.setLineDash([8, 7]); ctx.lineWidth = 4; ctx.strokeStyle = C.aqua; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.beginPath(); rt.forEach((p, i) => i ? ctx.lineTo(p[0] * s, p[1] * s) : ctx.moveTo(p[0] * s, p[1] * s)); ctx.stroke(); ctx.restore();
  if (inf.ell) drawEllipse(ctx, inf.ell, inf.pos[0], inf.pos[1], s, 'rgba(16,185,129,.2)', 'rgba(16,185,129,.9)'); else { ctx.beginPath(); ctx.arc(inf.pos[0] * s, inf.pos[1] * s, 1.3 * s, 0, 7); ctx.fillStyle = 'rgba(16,185,129,.18)'; ctx.fill(); }
  ctx.beginPath(); ctx.arc(inf.pos[0] * s, inf.pos[1] * s, 9, 0, 7); ctx.fillStyle = C.em; ctx.fill(); ctx.strokeStyle = '#fff'; ctx.lineWidth = 3; ctx.stroke();
  ctx.beginPath(); ctx.arc(ME[0] * s, ME[1] * s, 8, 0, 7); ctx.fillStyle = C.aquaD; ctx.fill(); ctx.strokeStyle = '#fff'; ctx.lineWidth = 3; ctx.stroke(); ctx.fillStyle = C.ink; ctx.font = '700 12px Figtree'; ctx.textAlign = 'left'; ctx.fillText('You', ME[0] * s + 12, ME[1] * s + 4);
}
$('q').addEventListener('input', e => { query = e.target.value; renderList(); });
let toastT; function notifyApp() { const t = $('toast'), d = [...cfg.dead]; if (!d.length) { t.classList.remove('on'); return; } t.innerHTML = `<b>Anchor ${d.join(', ')} offline</b><br>Accuracy reduced nearby. Maintenance notified.`; t.classList.add('on'); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove('on'), 6000); }

/* ================= SITE SWITCH ================= */
const TXT = {
  hospital: ['A simulated hospital floor with 6 BLE anchors. Break things in the Fault Lab (click an anchor on the map to kill it) and watch LOCUS keep the estimate honest, with a reason for every distrusted reading.', 'Floor map · Level 2'],
  warehouse: ['A simulated warehouse: racking blocks the radio signal, a forklift loops the aisles, 6 BLE anchors. Same engine, different floor plan. Click an anchor to kill it and watch LOCUS cope.', 'Floor map · Bay 1'],
};
function engineNow() { return { DROP_ORDER, ANCHORS, rngMake, Walker, KalmanCV, Locus, measure, lsFix }; }
function switchSite(id) {
  setSite(id); document.querySelectorAll('.site button').forEach(b => b.setAttribute('aria-pressed', b.dataset.site === id));
  nAnch = 6; $('s-n').value = 6; $('o-n').textContent = 6; cfg.dead.clear(); cfg.obstruct.clear(); cfg.drift.clear(); resetSim(); syncScen(); notifyApp();
  PL.ready = false; benchRes = null; $('b-meta').textContent = 'not run yet'; $('b-tab').innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--ink3);padding:30px">Press “Run benchmark”</td></tr>';
  $('d-sub').textContent = TXT[id][0]; $('d-floor').textContent = TXT[id][1];
  const S = STAFF[id]; ITEMS = S.items; ME = S.me; selId = S.items[0].id; cat = 'All'; query = ''; $('q').value = ''; $('q').placeholder = S.ph; $('s-h').textContent = S.head; $('s-lvl').textContent = S.lvl; renderChips(); renderList();
  if (tabNow === 'plan') renderPlanner(); if (tabNow === 'bench') renderBench();
}
document.querySelectorAll('.site button').forEach(b => b.onclick = () => { if (b.dataset.site !== SITE_ID) switchSite(b.dataset.site); });

/* ================= MAIN LOOP ================= */
resetSim(); syncScen(); renderChips(); renderList();
let lastPanel = 0;
function loop(now) {
  if (!tPrev) tPrev = now; let d = Math.min(0.35, (now - tPrev) / 1000); tPrev = now; acc += d; let n = 0;
  while (acc >= 0.1 && n < 3) { simStep(); acc -= 0.1; n++; } if (n === 3) acc = 0;
  if (tabNow === 'dash') { renderMap(acc / 0.1); if (now - lastPanel > 250) { updatePanels(); renderChart(); lastPanel = now; } }
  else if (tabNow === 'app' && now - lastPanel > 400) { updateApp(); lastPanel = now; }
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);

{ const hs = location.hash.slice(1).split('-'), h = hs[0]; if (hs[1] === 'wh') switchSite('warehouse'); const b = document.querySelector('nav button[data-v="' + h + '"]'); if (b) b.click(); }
