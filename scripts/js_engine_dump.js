// Run the JS engine (lsFix, KalmanCV, Locus) on a simulated sequence and dump every step (used by crossval_engine.py)
const E = require('../src/engine.js');
const [site, seed, steps, nA, sigma] = [process.argv[2] || 'hospital', +(process.argv[3] || 1), +(process.argv[4] || 300), +(process.argv[5] || 6), +(process.argv[6] || 0.8)];
E.setSite(site);
const cfg = { sigma, loss: 0.15, wallBias: 2.2, burst: 0.012, obstructBias: 4, dead: new Set(), obstruct: new Set(['A3']), drift: new Set(['A5']), driftBias: 2.5, inflate: 2.0 };
const anchors = E.DROP_ORDER.slice(0, nA).map(i => E.ANCHORS[i]);
const rng = E.rngMake(seed), wk = new E.Walker(1.2, (seed % 7) * 6), kf = new E.KalmanCV();
const loc = new E.Locus(anchors, { N: 400, sigma, rng: E.rngMake(seed + 99), inflate: 2.0 });
let lastLs = [20, 12]; const out = [];
for (let s = 0; s < steps; s++) {
  const t = wk.step(0.1).slice(), m = E.measure(t, anchors, cfg, rng);
  const ls = E.lsFix(anchors, m, lastLs); if (ls) lastLs = ls; const k = kf.update(ls, 0.1), o = loc.step(m, 0.1);
  out.push({ truth: t, meas: m.map(x => x && { r: x.r }), ls, kf: k, lo: o && { pos: o.pos, trust: o.trust, ell: o.ell, reasons: o.reasons, wallMu: o.wallMu, relocal: o.relocal } });
}
console.log(JSON.stringify({ anchors, steps: out }));
