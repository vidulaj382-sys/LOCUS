/* ===== LOCUS engine: simulator, baselines, trust scorer, map-aware particle filter ===== */
const FLOOR = { w: 40, h: 24 };
const TOP_DOORS = [5, 15, 25, 35], BOT_DOORS = [6, 17, 27, 36], DOOR_HALF = 1.2;
/* ---- sites: hospital floor and warehouse (same 40 x 24 m footprint) ---- */
let SITE_ID = 'hospital', ROOMS, WALLS, ANCHORS, DROP_ORDER, WAYPOINTS, FALLBACK = 'corr';
function hospitalSite() {
  const rooms = [
    { id: 'wardA', name: 'Ward A', r: [0, 0, 10, 9] }, { id: 'wardB', name: 'Ward B', r: [10, 0, 20, 9] },
    { id: 'icu', name: 'ICU', r: [20, 0, 30, 9] }, { id: 'pharm', name: 'Pharmacy', r: [30, 0, 40, 9] },
    { id: 'corr', name: 'Corridor', r: [0, 9, 40, 15] },
    { id: 'recep', name: 'Reception', r: [0, 15, 12, 24] }, { id: 'store', name: 'Store', r: [12, 15, 22, 24] },
    { id: 'radio', name: 'Radiology', r: [22, 15, 32, 24] }, { id: 'ot', name: 'OT', r: [32, 15, 40, 24] },
  ];
  const W = [], hseg = (y, doors) => { let c = 0; doors.forEach(d => { W.push([c, y, d - DOOR_HALF, y]); c = d + DOOR_HALF; }); W.push([c, y, FLOOR.w, y]); };
  hseg(9, TOP_DOORS); hseg(15, BOT_DOORS);
  [10, 20, 30].forEach(x => W.push([x, 0, x, 9])); [12, 22, 32].forEach(x => W.push([x, 15, x, 24]));
  W.push([0, 0, FLOOR.w, 0], [0, FLOOR.h, FLOOR.w, FLOOR.h], [0, 0, 0, FLOOR.h], [FLOOR.w, 0, FLOOR.w, FLOOR.h]);
  return { rooms, walls: W, fallback: 'corr',
    anchors: [{ id: 'A1', x: 1.5, y: 13.5 }, { id: 'A2', x: 15, y: 1.5 }, { id: 'A3', x: 25, y: 10.5 }, { id: 'A4', x: 38.5, y: 13.5 }, { id: 'A5', x: 28, y: 22.5 }, { id: 'A6', x: 7, y: 22.5 }],
    drop: [2, 5, 1, 3, 0, 4],
    way: [[3, 12], [15, 12], [15, 4], [15, 12], [25, 12], [25, 4], [25, 12], [36, 12], [36, 19.5], [36, 12], [27, 12], [27, 19.5], [27, 12], [6, 12], [6, 19.5], [6, 12]] };
}
function warehouseSite() {
  const rooms = [{ id: 'recv', name: 'Receiving', r: [0, 0, 8, 24] }, { id: 'aisA', name: 'Aisle A', r: [8, 0, 16, 24] }, { id: 'aisB', name: 'Aisle B', r: [16, 0, 24, 24] }, { id: 'aisC', name: 'Aisle C', r: [24, 0, 32, 24] }, { id: 'disp', name: 'Dispatch', r: [32, 0, 40, 24] }];
  const W = []; [8, 16, 24, 32].forEach(x => { W.push([x, 0, x, 10.5], [x, 13.5, x, 24]); });
  [12, 20, 28].forEach(x => { W.push([x - 1.8, 4, x + 1.8, 4], [x - 1.8, 20, x + 1.8, 20]); }); // end-cap shelves
  W.push([0, 0, FLOOR.w, 0], [0, FLOOR.h, FLOOR.w, FLOOR.h], [0, 0, 0, FLOOR.h], [FLOOR.w, 0, FLOOR.w, FLOOR.h]);
  return { rooms, walls: W, fallback: 'recv',
    anchors: [{ id: 'A1', x: 1.5, y: 21 }, { id: 'A2', x: 12, y: 1.5 }, { id: 'A3', x: 20, y: 12 }, { id: 'A4', x: 28, y: 22.5 }, { id: 'A5', x: 38.5, y: 3 }, { id: 'A6', x: 38.5, y: 21 }],
    drop: [2, 5, 1, 3, 0, 4],
    way: [[3, 12], [12, 12], [12, 7], [12, 17], [12, 12], [20, 12], [20, 7], [20, 17], [20, 12], [28, 12], [28, 7], [28, 17], [28, 12], [36, 12], [36, 5], [36, 19], [36, 12]] };
}
function setSite(id) { const S = id === 'warehouse' ? warehouseSite() : hospitalSite(); SITE_ID = id; ROOMS = S.rooms; WALLS = S.walls; ANCHORS = S.anchors; DROP_ORDER = S.drop; WAYPOINTS = S.way; FALLBACK = S.fallback; }
setSite('hospital');

function roomAt(x, y) { for (const r of ROOMS) { const [a, b, c, d] = r.r; if (x >= a && x < c && y >= b && y < d) return r.id; } return FALLBACK; }
function roomName(id) { return ROOMS.find(r => r.id === id).name; }
function segInt(ax, ay, bx, by, cx, cy, dx, dy) {
  const d1x = bx - ax, d1y = by - ay, d2x = dx - cx, d2y = dy - cy;
  const den = d1x * d2y - d1y * d2x; if (Math.abs(den) < 1e-12) return false;
  const t = ((cx - ax) * d2y - (cy - ay) * d2x) / den, u = ((cx - ax) * d1y - (cy - ay) * d1x) / den;
  return t > 1e-6 && t < 1 - 1e-6 && u >= 0 && u <= 1;
}
function wallsBetween(ax, ay, bx, by) { let k = 0; for (const w of WALLS) if (segInt(ax, ay, bx, by, w[0], w[1], w[2], w[3])) k++; return k; }
function crossesWall(ax, ay, bx, by) { for (const w of WALLS) if (segInt(ax, ay, bx, by, w[0], w[1], w[2], w[3])) return true; return false; }

function rngMake(seed) { let a = seed >>> 0; const f = () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; f.g = () => { let u = 0, v = 0; while (!u) u = f(); v = f(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); }; return f; }

/* Walker along waypoint loop */
class Walker {
  constructor(speed = 1.2, offset = 0) { this.i = 0; this.pos = WAYPOINTS[0].slice(); this.speed = speed; this.vel = [0, 0]; if (offset) this.advance(offset); }
  advance(dist) { while (dist > 0) { const t = WAYPOINTS[(this.i + 1) % WAYPOINTS.length], dx = t[0] - this.pos[0], dy = t[1] - this.pos[1], d = Math.hypot(dx, dy); if (d <= dist) { this.pos = t.slice(); this.i = (this.i + 1) % WAYPOINTS.length; dist -= d; } else { this.pos[0] += dx / d * dist; this.pos[1] += dy / d * dist; dist = 0; } } }
  step(dt) { const o = this.pos.slice(); this.advance(this.speed * dt); this.vel = [(this.pos[0] - o[0]) / dt, (this.pos[1] - o[1]) / dt]; return this.pos; }
}

/* Radio simulator: noise, packet loss, wall (NLOS) bias, dead anchors, drift, forced obstruction */
function measure(pos, anchors, cfg, rng) {
  return anchors.map((a, i) => {
    if (cfg.dead && cfg.dead.has(a.id)) return null;
    if (rng() < cfg.loss) return null;
    const d = Math.hypot(pos[0] - a.x, pos[1] - a.y), k = wallsBetween(a.x, a.y, pos[0], pos[1]);
    let bias = k * cfg.wallBias * (0.5 + rng()), nlos = k > 0;
    if (cfg.obstruct && cfg.obstruct.has(a.id)) { bias += cfg.obstructBias * (0.6 + 0.8 * rng()); nlos = true; }
    if (cfg.burst) { const st = rng._b || (rng._b = {}); if (!st[a.id] && rng() < cfg.burst) st[a.id] = 20 + (rng() * 30 | 0); if (st[a.id] > 0) { st[a.id]--; bias += 3.2; nlos = true; } }
    if (cfg.drift && cfg.drift.has(a.id)) { bias += cfg.driftBias; nlos = true; }
    const sigma = cfg.sigma * (nlos ? 1.8 : 1);
    return { r: Math.max(0.3, d + bias + sigma * rng.g()), nlos, bias };
  });
}

/* Plain trilateration: Gauss-Newton least squares (optionally weighted) */
function lsFix(anchors, meas, init, w) {
  let x = init[0], y = init[1], n = 0;
  for (let it = 0; it < 12; it++) {
    let a11 = 1e-3, a12 = 0, a22 = 1e-3, b1 = 0, b2 = 0; n = 0;
    for (let i = 0; i < anchors.length; i++) {
      const m = meas[i]; if (!m) continue; n++;
      const dx = x - anchors[i].x, dy = y - anchors[i].y, d = Math.max(0.2, Math.hypot(dx, dy)), ux = dx / d, uy = dy / d, res = m.r - d, wt = w ? w[i] : 1;
      a11 += wt * ux * ux; a12 += wt * ux * uy; a22 += wt * uy * uy; b1 += wt * ux * res; b2 += wt * uy * res;
    }
    if (!n) return null;
    const lam = n < 3 ? 0.6 : 0.05, det = (a11 + lam) * (a22 + lam) - a12 * a12;
    x += ((a22 + lam) * b1 - a12 * b2) / det; y += ((a11 + lam) * b2 - a12 * b1) / det;
  }
  return [Math.min(FLOOR.w, Math.max(0, x)), Math.min(FLOOR.h, Math.max(0, y))];
}
/* Baseline B: trilateration + constant-velocity Kalman filter (what most teams build) */
class KalmanCV {
  constructor() { this.x = null; }
  update(z, dt) {
    if (!z) { if (this.x) { this.x[0] += this.x[2] * dt; this.x[1] += this.x[3] * dt; } return this.x ? [this.x[0], this.x[1]] : null; }
    if (!this.x) { this.x = [z[0], z[1], 0, 0]; this.P = [10, 10, 4, 4]; return z.slice(); }
    const q = 0.4 * dt, R = 2.0;
    for (let k = 0; k < 2; k++) {
      let p = this.x[k], v = this.x[k + 2], P = this.P[k], Pv = this.P[k + 2];
      p += v * dt; P += dt * dt * Pv + q; Pv += q;
      const K = P / (P + R), K2 = (Pv * 0.2) / (P + R); const inn = z[k] - p;
      p += K * inn; v += K2 / Math.max(dt, 1e-3) * inn * 0.5; P *= (1 - K);
      this.x[k] = p; this.x[k + 2] = v; this.P[k] = P; this.P[k + 2] = Pv;
    }
    return [this.x[0], this.x[1]];
  }
}

/* wall-count lookup per anchor (0.5 m grid) so the filter can predict wall bias for any particle */
const KCACHE = {};
function kGrid(a) {
  const key = SITE_ID + a.id + ':' + a.x + ',' + a.y; if (KCACHE[key]) return KCACHE[key];
  const W = FLOOR.w * 2, H = FLOOR.h * 2, g = new Uint8Array(W * H);
  for (let j = 0; j < H; j++) for (let i = 0; i < W; i++) g[j * W + i] = wallsBetween(a.x, a.y, (i + 0.5) / 2, (j + 0.5) / 2);
  return KCACHE[key] = g;
}
function kAt(g, x, y) { const i = Math.min(FLOOR.w * 2 - 1, Math.max(0, x * 2 | 0)), j = Math.min(FLOOR.h * 2 - 1, Math.max(0, y * 2 | 0)); return g[j * FLOOR.w * 2 + i]; }

/* LOCUS: trust scorer + weighted robust fix + map-aware particle filter */
class Locus {
  constructor(anchors, opts = {}) {
    this.anchors = anchors; this.N = opts.N || 600; this.sigma = opts.sigma || 0.6; this.rng = opts.rng || rngMake(7);
    this.inflate = opts.inflate || 1.0; this.wallMu = opts.wallMu || 1.4; this.kg = anchors.map(kGrid);
    this.px = new Float64Array(this.N); this.py = new Float64Array(this.N); this.vx = new Float64Array(this.N); this.vy = new Float64Array(this.N); this.w = new Float64Array(this.N).fill(1 / this.N);
    this.inited = false; this.trust = anchors.map(() => 0.8); this.last = anchors.map(() => null); this.silent = anchors.map(() => 0); this.hist = anchors.map(() => []);
    this.est = null; this.fix = null;
  }
  _init(meas) {
    const c = [FLOOR.w / 2, FLOOR.h / 2], f = lsFix(this.anchors, meas, c) || c, r = this.rng;
    for (let i = 0; i < this.N; i++) { this.px[i] = Math.min(FLOOR.w - .1, Math.max(.1, f[0] + r.g() * 3.5)); this.py[i] = Math.min(FLOOR.h - .1, Math.max(.1, f[1] + r.g() * 3.5)); this.vx[i] = r.g() * .5; this.vy[i] = r.g() * .5; }
    this.inited = true; this.est = f.slice();
  }
  _moments() {
    let mx = 0, my = 0, sw = 0; for (let i = 0; i < this.N; i++) { const q = this.w[i]; mx += q * this.px[i]; my += q * this.py[i]; sw += q; }
    mx /= sw; my /= sw; let sxx = 0, sxy = 0, syy = 0;
    for (let i = 0; i < this.N; i++) { const q = this.w[i], dx = this.px[i] - mx, dy = this.py[i] - my; sxx += q * dx * dx; sxy += q * dx * dy; syy += q * dy * dy; }
    return { mx, my, sxx: sxx / sw, sxy: sxy / sw, syy: syy / sw };
  }
  step(meas, dt) {
    const A = this.anchors, r = this.rng, N = this.N, sg = this.sigma;
    if (!this.inited) { if (!meas.some(Boolean)) return null; this._init(meas); }
    /* 1. predict (motion history) */
    for (let i = 0; i < N; i++) {
      const ox = this.px[i], oy = this.py[i];
      this.vx[i] = this.vx[i] * 0.96 + r.g() * 0.28; this.vy[i] = this.vy[i] * 0.96 + r.g() * 0.28;
      const sp = Math.hypot(this.vx[i], this.vy[i]); if (sp > 2.2) { this.vx[i] *= 2.2 / sp; this.vy[i] *= 2.2 / sp; }
      let nx = ox + this.vx[i] * dt + r.g() * 0.05, ny = oy + this.vy[i] * dt + r.g() * 0.05;
      if (nx < 0 || ny < 0 || nx > FLOOR.w || ny > FLOOR.h || crossesWall(ox, oy, nx, ny)) { nx = ox; ny = oy; this.vx[i] *= -0.2; this.vy[i] *= -0.2; this.w[i] *= 0.2; }
      this.px[i] = nx; this.py[i] = ny;
    }
    const pm = this._moments(), prior = [pm.mx, pm.my], priorStd = Math.sqrt(Math.max(0.04, (pm.sxx + pm.syy) / 2));
    /* 2. trust scorer: residual vs motion prior, jump, variance -> 0..1 + reason */
    const reasons = [], usable = [], tRs = [];
    A.forEach((a, i) => {
      const m = meas[i];
      if (!m) { this.silent[i] += dt; this.trust[i] = Math.max(0, this.trust[i] - dt * 0.8); reasons[i] = this.silent[i] > 1 ? 'No packets for ' + this.silent[i].toFixed(0) + ' s' : 'Packet lost'; usable[i] = false; return; }
      this.silent[i] = 0;
      const kp = kAt(this.kg[i], prior[0], prior[1]), pred = Math.hypot(prior[0] - a.x, prior[1] - a.y) + kp * this.wallMu, res = m.r - pred, s = Math.sqrt(sg * sg + priorStd * priorStd + Math.pow(kp * 0.8, 2));
      const tol = res > 0 ? 2.0 * s : 3.2 * s, zr = Math.abs(res) / tol, tR = 1 / (1 + Math.pow(zr, 3));
      const h = this.hist[i]; h.push(m.r); if (h.length > 8) h.shift();
      const jump = this.last[i] == null ? 0 : Math.abs(m.r - this.last[i]), jx = Math.max(0, jump - 0.25 - 3 * sg), tJ = 1 / (1 + Math.pow(jx / (3 * sg), 2));
      let vr = 0; if (h.length > 3) { const mu = h.reduce((p, c) => p + c, 0) / h.length; vr = Math.sqrt(h.reduce((p, c) => p + (c - mu) * (c - mu), 0) / h.length); }
      const tV = 1 / (1 + Math.pow(Math.max(0, vr - 1.6 * sg) / (1.5 * sg), 2));
      tRs.push(tR); const raw = Math.max(0.02, tR * tJ * Math.sqrt(tV)); this.trust[i] = this.trust[i] * 0.55 + raw * 0.45; this.last[i] = m.r;
      let why = 'Consistent with motion model';
      if (this.trust[i] < 0.7) { if (tR <= tJ && tR <= tV) why = res > 0 ? 'Reads +' + res.toFixed(1) + ' m beyond what the walls explain (obstruction)' : 'Reads ' + (-res).toFixed(1) + ' m shorter than predicted'; else if (tJ <= tV) why = 'Sudden ' + jump.toFixed(1) + ' m jump between readings'; else why = 'Variance spike (σ ' + vr.toFixed(1) + ' m)'; }
      reasons[i] = why; usable[i] = true;
    });
    /* collective disagreement => our prior is probably wrong, not the anchors: relocalise */
    const lost = tRs.length >= 2 && tRs.filter(t => t < 0.3).length >= Math.ceil(tRs.length * 0.6);
    this.lostN = lost ? (this.lostN || 0) + 1 : 0; const relocal = this.lostN >= 3;
    /* 3. trust-weighted robust fix from the motion prior */
    const wTrust = this.trust.map((t, i) => usable[i] ? t : 0);
    this.fix = wTrust.some(t => t > 0.05) ? lsFix(A, meas, prior, wTrust.map(t => t * t)) : null;
    /* 4. particle weight update with trust-inflated sigma + heavy-tail mix */
    if (relocal) { const f = lsFix(A, meas, prior); if (f) for (let p = 0; p < N * 0.15; p++) { const j = (r() * N) | 0; this.px[j] = Math.min(FLOOR.w - .1, Math.max(.1, f[0] + r.g() * 3)); this.py[j] = Math.min(FLOOR.h - .1, Math.max(.1, f[1] + r.g() * 3)); this.w[j] = 1 / N; } }
    let sw = 0; const eps = 0.04;
    for (let p = 0; p < N; p++) {
      let lw = Math.log(this.w[p] + 1e-300);
      for (let i = 0; i < A.length; i++) { const m = meas[i]; if (!m || !usable[i]) continue; const t = relocal ? Math.max(this.trust[i], 0.45) : this.trust[i]; if (t < 0.08) continue; const kk = kAt(this.kg[i], this.px[p], this.py[p]), si = Math.sqrt(sg * sg / t + Math.pow(kk * 0.8, 2)) + 0.15, d = Math.hypot(this.px[p] - A[i].x, this.py[p] - A[i].y) + kk * this.wallMu, z = (m.r - d) / si; lw += Math.log((1 - eps) * Math.exp(-0.5 * z * z) / si + eps / 25); }
      this.w[p] = Math.exp(lw); sw += this.w[p];
    }
    if (!(sw > 0)) { this.w.fill(1 / N); sw = 1; }
    let ess = 0; for (let p = 0; p < N; p++) { this.w[p] /= sw; ess += this.w[p] * this.w[p]; } ess = 1 / ess;
    /* 5. estimate + 90% ellipse + room probabilities */
    const mo = this._moments(), cxx = mo.sxx, cyy = mo.syy, cxy = mo.sxy;
    const tr = cxx + cyy, det = cxx * cyy - cxy * cxy, disc = Math.sqrt(Math.max(0, tr * tr / 4 - det)), l1 = tr / 2 + disc, l2 = Math.max(1e-4, tr / 2 - disc);
    const k = 4.605 * this.inflate * this.inflate, ell = { a: Math.max(0.35, Math.sqrt(k * l1)), b: Math.max(0.3, Math.sqrt(k * l2)), th: 0.5 * Math.atan2(2 * cxy, cxx - cyy) };
    const rp = {}; for (let p = 0; p < N; p++) { const id = roomAt(this.px[p], this.py[p]); rp[id] = (rp[id] || 0) + this.w[p]; }
    this.est = [mo.mx, mo.my];
    /* self-calibration: re-fit wall bias (m per wall) from readings we trust */
    A.forEach((a, i) => { const m = meas[i]; if (!m || !usable[i] || this.trust[i] < 0.5) return; const ke = kAt(this.kg[i], mo.mx, mo.my); if (ke < 1) return; const mu = (m.r - Math.hypot(mo.mx - a.x, mo.my - a.y)) / ke; this.wallMu = Math.min(3.5, Math.max(0.8, this.wallMu + 0.02 * (mu - this.wallMu))); });
    const out = { wallMu: this.wallMu, pos: this.est.slice(), ell, rooms: rp, trust: this.trust.slice(), reasons, usable, fix: this.fix, ess: ess / N, relocal };
    /* 6. resample + roughen */
    if (ess < N * 0.6) {
      const nx = new Float64Array(N), ny = new Float64Array(N), nvx = new Float64Array(N), nvy = new Float64Array(N); let c = this.w[0], idx = 0; const u0 = r() / N;
      for (let j = 0; j < N; j++) { const u = u0 + j / N; while (u > c && idx < N - 1) { idx++; c += this.w[idx]; } nx[j] = this.px[idx] + r.g() * 0.07; ny[j] = this.py[idx] + r.g() * 0.07; nvx[j] = this.vx[idx]; nvy[j] = this.vy[idx]; }
      this.px = nx; this.py = ny; this.vx = nvx; this.vy = nvy; this.w.fill(1 / N);
    }
    return out;
  }
}
if (typeof module !== 'undefined') module.exports = { get ROOMS() { return ROOMS; }, get WALLS() { return WALLS; }, get ANCHORS() { return ANCHORS; }, get DROP_ORDER() { return DROP_ORDER; }, get WAYPOINTS() { return WAYPOINTS; }, FLOOR, setSite, roomAt, roomName, wallsBetween, crossesWall, rngMake, Walker, measure, lsFix, KalmanCV, Locus };
