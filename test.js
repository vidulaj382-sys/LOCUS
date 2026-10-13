const B = require('./src/bench.js');
const cfg = { sigma: 0.8, loss: 0.15, wallBias: 2.2, burst: 0.012, obstructBias: 4, dead: new Set(), obstruct: new Set(), drift: new Set(), driftBias: 2.5, inflate: +(process.argv[2] || 1) };
const t = Date.now();
const r = B.benchmark(cfg, 300, [1, 2, 3], B.E);
r.forEach(x => console.log(x.n, 'LS', x.ls.med.toFixed(2), x.ls.p90.toFixed(2), '| KF', x.kf.med.toFixed(2), x.kf.p90.toFixed(2), '| LOCUS', x.lo.med.toFixed(2), x.lo.p90.toFixed(2), 'w2', (x.lo.w2 * 100).toFixed(0) + '%', 'cal', (x.cal * 100).toFixed(0) + '%'));
console.log(Date.now() - t, 'ms');
