"""Replay a recorded/generated measurement run through LS, KalmanCV and LOCUS (heuristic or ML scorer)."""
import zlib
import numpy as np
from . import sim, engine
from .dataset import meas_at

DT = 0.1
WARMUP = 15            # same warm-up skip as src/bench.js
NOMINAL_SIGMA = 0.8    # the engine does NOT get the true noise sigma on hidden data (it is unknown there)


def seed_for(run_id):
    return zlib.crc32(run_id.encode()) & 0xFFFF


def ellipse_axes(l1, l2, inflate):
    k = 4.605 * inflate * inflate
    return max(0.35, np.sqrt(k * l1)), max(0.3, np.sqrt(k * l2))


def replay(run, run_id, n_anchors=6, scorer=None, N=400, sigma=NOMINAL_SIGMA, inflate=1.0, keep_outs=False, methods=('ls', 'kf', 'lo')):
    site = sim.get_site(run['site'])
    anchors = run['anchors'][:n_anchors]
    T = len(run['ranges'])
    kf = engine.KalmanCV()
    loc = engine.Locus(site, anchors, N=N, sigma=sigma, rng=sim.Rng(seed_for(run_id) + 99), inflate=inflate, scorer=scorer) if 'lo' in methods else None
    last = [20.0, 12.0]
    res = dict(ls=np.full((T, 2), np.nan), kf=np.full((T, 2), np.nan), lo=np.full((T, 2), np.nan), l1=np.full(T, np.nan),
               l2=np.full(T, np.nan), th=np.full(T, np.nan), outs=[] if keep_outs else None)
    for s in range(T):
        m = meas_at(run, s, n_anchors)
        ls = engine.ls_fix(anchors, m, last)
        if ls:
            last = ls
            res['ls'][s] = ls
        k = kf.update(ls, DT)
        if k:
            res['kf'][s] = k
        if loc is not None:
            o = loc.step(m, DT)
            if o:
                res['lo'][s] = o['pos']
                res['l1'][s], res['l2'][s], res['th'][s] = o['ell_raw']['l1'], o['ell_raw']['l2'], o['ell_raw']['th']
                if keep_outs:
                    res['outs'].append((s, o))
    return res


def coverage(res, truth, inflate):
    """Fraction of true points inside the 90% ellipse (after warm-up)."""
    ok = tot = 0
    for s in range(WARMUP, len(truth)):
        if np.isnan(res['lo'][s, 0]):
            continue
        a, b = ellipse_axes(res['l1'][s], res['l2'][s], inflate)
        dx, dy = truth[s, 0] - res['lo'][s, 0], truth[s, 1] - res['lo'][s, 1]
        c, sn = np.cos(-res['th'][s]), np.sin(-res['th'][s])
        u, v = dx * c - dy * sn, dx * sn + dy * c
        tot += 1
        ok += (u / a) ** 2 + (v / b) ** 2 <= 1
    return ok, tot


def errors(res, truth, key):
    e = np.hypot(res[key][:, 0] - truth[:, 0], res[key][:, 1] - truth[:, 1])
    return e[WARMUP:][~np.isnan(e[WARMUP:])]
