function ptile(a, p) { const s = a.slice().sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(p * s.length))]; }
/* One trial: identical radio data is fed to all three estimators */
function runTrial(nAnch, cfg, steps, seed, E) {
  E = E || module.exports.E;
  const anchors = E.DROP_ORDER.slice(0, nAnch).map(i => E.ANCHORS[i]);
  const rng = E.rngMake(seed), wk = new E.Walker(1.2, (seed % 7) * 6), kf = new E.KalmanCV(), loc = new E.Locus(anchors, { N: 400, sigma: cfg.sigma, rng: E.rngMake(seed + 99), inflate: cfg.inflate });
  const dt = 0.1, res = { ls: [], kf: [], lo: [], inside: 0, n: 0 }; let lastLs = [20, 12];
  for (let s = 0; s < steps; s++) {
    const t = wk.step(dt), m = E.measure(t, anchors, cfg, rng);
    const ls = E.lsFix(anchors, m, lastLs); if (ls) lastLs = ls; const k = kf.update(ls, dt), o = loc.step(m, dt);
    if (s < 15) continue;
    if (ls) res.ls.push(Math.hypot(ls[0] - t[0], ls[1] - t[1]));
    if (k) res.kf.push(Math.hypot(k[0] - t[0], k[1] - t[1]));
    if (o) { res.lo.push(Math.hypot(o.pos[0] - t[0], o.pos[1] - t[1])); const dx = t[0] - o.pos[0], dy = t[1] - o.pos[1], c = Math.cos(-o.ell.th), sn = Math.sin(-o.ell.th), u = dx * c - dy * sn, v = dx * sn + dy * c; res.n++; if ((u / o.ell.a) ** 2 + (v / o.ell.b) ** 2 <= 1) res.inside++; }
  }
  return res;
}
function benchmark(cfg, steps, seeds, E) {
  const out = [];
  for (let n = 6; n >= 2; n--) {
    const agg = { ls: [], kf: [], lo: [], inside: 0, n: 0 };
    seeds.forEach(sd => { const r = runTrial(n, cfg, steps, sd, E); ['ls', 'kf', 'lo'].forEach(k => agg[k].push(...r[k])); agg.inside += r.inside; agg.n += r.n; });
    const st = a => ({ med: ptile(a, .5), p90: ptile(a, .9), w2: a.filter(e => e < 2).length / a.length });
    out.push({ n, ls: st(agg.ls), kf: st(agg.kf), lo: st(agg.lo), cal: agg.inside / agg.n });
  }
  return out;
}
if (typeof module !== 'undefined') module.exports = { runTrial, benchmark, ptile, E: require('./engine.js') };
