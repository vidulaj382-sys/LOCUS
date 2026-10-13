"""Phase 2 cross-validation: JS engine (via Node) vs Python port, same seed, same measurement sequence.
The JS side simulates + estimates and dumps everything; the Python side replays the *exact same readings*
through ls_fix / KalmanCV / Locus (same particle count, same RNG seed) and reports the max divergence.
Output is saved to docs/crossval_output.txt for the slides."""
import json, subprocess, sys, pathlib, math
import numpy as np
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend import sim, engine


def run_case(site_id, seed, steps, nA, sigma):
    J = json.loads(subprocess.run(['node', str(ROOT / 'scripts' / 'js_engine_dump.js'), site_id, str(seed), str(steps), str(nA), str(sigma)],
                                  capture_output=True, text=True, encoding='utf8', check=True).stdout)
    site = sim.get_site(site_id)
    anchors = J['anchors']
    kf, loc = engine.KalmanCV(), engine.Locus(site, anchors, N=400, sigma=sigma, rng=sim.Rng(seed + 99), inflate=2.0)
    last = [20.0, 12.0]   # LS init = the JS engine's own previous fix, so we compare per-step arithmetic and
                          # do not let a 2-anchor (near-singular, mirror-ambiguous) solve amplify 1e-7 differences
    d_ls = d_kf = d_lo = d_tr = d_el = 0.0
    r_total = r_same = 0
    first_div = None
    for s, st in enumerate(J['steps']):
        m = st['meas']
        ls = engine.ls_fix(anchors, m, last)
        last = st['ls'] if st['ls'] else last
        k = kf.update(st['ls'], 0.1)   # KalmanCV driven by the JS LS sequence
        o = loc.step(m, 0.1)
        if (ls is None) != (st['ls'] is None):
            d_ls = float('inf')
        elif ls:
            d_ls = max(d_ls, math.hypot(ls[0] - st['ls'][0], ls[1] - st['ls'][1]))
        if k and st['kf']:
            d_kf = max(d_kf, math.hypot(k[0] - st['kf'][0], k[1] - st['kf'][1]))
        if o and st['lo']:
            e = math.hypot(o['pos'][0] - st['lo']['pos'][0], o['pos'][1] - st['lo']['pos'][1])
            d_lo = max(d_lo, e)
            if e > 0.05 and first_div is None:
                first_div = s
            d_tr = max(d_tr, max(abs(a - b) for a, b in zip(o['trust'], st['lo']['trust'])))
            d_el = max(d_el, abs(o['ell']['a'] - st['lo']['ell']['a']), abs(o['ell']['b'] - st['lo']['ell']['b']))
            for a, b in zip(o['reasons'], st['lo']['reasons']):
                r_total += 1
                r_same += (a == b)
    return d_ls, d_kf, d_lo, d_tr, d_el, r_same, r_total, first_div


def main():
    lines = ['Cross-validation: JS engine (Node) vs Python port - identical readings, identical RNG seed, N=400 particles, 0.1 s step',
             'columns: max divergence over the run | LS fix [m] | KalmanCV [m] | LOCUS pos [m] | trust [abs] | ellipse axis [m] | reason strings equal']
    worst = 0.0
    cases = [('hospital', 1, 300, 6, 0.8), ('hospital', 2, 300, 4, 0.8), ('hospital', 5, 300, 3, 1.2), ('warehouse', 3, 300, 6, 0.6), ('warehouse', 4, 300, 2, 0.8)]
    for c in cases:
        d_ls, d_kf, d_lo, d_tr, d_el, rs, rt, fd = run_case(*c)
        worst = max(worst, d_lo)
        lines.append(f'{c[0]:9s} seed={c[1]} anchors={c[3]} sigma={c[4]} steps={c[2]} | LS {d_ls:.2e} | KF {d_kf:.2e} | LOCUS {d_lo:.2e} | trust {d_tr:.2e} | ellipse {d_el:.2e} | reasons {rs}/{rt}'
                     + ('' if fd is None else f' | first >5cm divergence at step {fd}'))
    lines.append(f'MAX LOCUS position divergence over all runs: {worst:.3e} m')
    txt = '\n'.join(lines)
    print(txt)
    (ROOT / 'docs').mkdir(exist_ok=True)
    (ROOT / 'docs' / 'crossval_output.txt').write_text(txt + '\n', encoding='utf8')


if __name__ == '__main__':
    main()
