// Dump anchors, walker trajectory, and measurements from the JS engine for a given seed (used by validate_port.py)
const E = require('../src/engine.js');
const [site, seed, steps, speed, off] = [process.argv[2] || 'hospital', +(process.argv[3] || 1), +(process.argv[4] || 200), +(process.argv[5] || 1.2), +(process.argv[6] || 0)];
E.setSite(site);
const cfg = { sigma: 0.8, loss: 0.15, wallBias: 2.2, burst: 0.012, obstructBias: 4, dead: new Set(), obstruct: new Set(['A3']), drift: new Set(['A5']), driftBias: 2.5, inflate: 1 };
const anchors = E.DROP_ORDER.map(i => E.ANCHORS[i]);
const rng = E.rngMake(seed), wk = new E.Walker(speed, off), tr = [], ms = [];
for (let s = 0; s < steps; s++) { const t = wk.step(0.1).slice(); tr.push(t); ms.push(E.measure(t, anchors, cfg, rng).map(m => m && m.r)); }
console.log(JSON.stringify({ anchors: E.ANCHORS, traj: tr, meas: ms, rng_next: rng() }));
