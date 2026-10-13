"""Phase 1 sanity check: Python simulator port vs src/engine.js with the same seed.
Compares anchor positions, walker trajectory and every range reading (incl. the RNG stream)."""
import json, subprocess, sys, pathlib
import numpy as np
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend import sim


def js_dump(site, seed, steps, speed, off):
    out = subprocess.run(['node', str(ROOT / 'scripts' / 'js_dump.js'), site, str(seed), str(steps), str(speed), str(off)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def main():
    worst = 0.0
    for site_id, seed, speed, off in [('hospital', 1, 1.2, 0), ('hospital', 7, 1.2, 36), ('warehouse', 3, 1.2, 6), ('warehouse', 12345, 0.9, 12)]:
        steps = 600
        J = js_dump(site_id, seed, steps, speed, off)
        site = sim.get_site(site_id)
        cfg = sim.make_cfg(sigma=0.8, loss=0.15, wallBias=2.2, burst=0.012, obstruct=['A3'], drift=['A5'])
        anchors = [site.anchors[i] for i in site.drop]
        rng = sim.Rng(seed)
        wk = sim.Walker(site, speed, off)
        a_err = max(abs(a['x'] - b['x']) + abs(a['y'] - b['y']) for a, b in zip(site.anchors, J['anchors']))
        traj, meas = [], []
        for _ in range(steps):
            t = list(wk.step(0.1))
            traj.append(t)
            meas.append([None if m is None else m['r'] for m in sim.measure(site, t, anchors, cfg, rng)])
        t_err = float(np.abs(np.array(traj) - np.array(J['traj'])).max())
        m_err, m_mismatch = 0.0, 0
        for pm, jm in zip(meas, J['meas']):
            for p, j in zip(pm, jm):
                if (p is None) != (j is None):
                    m_mismatch += 1
                elif p is not None:
                    m_err = max(m_err, abs(p - j))
        rng_sync = abs(rng() - J['rng_next']) < 1e-12
        print(f'{site_id:9s} seed={seed:<6d} anchors maxdiff={a_err:.1e}  trajectory max|dx|={t_err:.2e} m  '
              f'range max|dr|={m_err:.2e} m  lost/ok mismatches={m_mismatch}  rng-stream-in-sync={rng_sync}')
        worst = max(worst, a_err, t_err, m_err)
        # vectorised block RNG must equal the scalar stream
        r1, r2 = sim.Rng(seed), sim.Rng(seed)
        assert np.allclose([r1.g() for _ in range(500)], r2.g_n(500), atol=1e-12), 'vectorised RNG diverged'
    print('vectorised RNG == scalar RNG: OK')
    print(f'WORST DIFF over all checks: {worst:.2e}', 'PASS' if worst < 1e-6 else 'FAIL')
    return 0 if worst < 1e-6 else 1


if __name__ == '__main__':
    sys.exit(main())
