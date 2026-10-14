"""LOCUS Python engine - faithful NumPy port of src/engine.js.

  ls_fix    : Gauss-Newton (optionally weighted) least-squares trilateration
  KalmanCV  : constant-velocity *linear* Kalman filter on the LS fix  (NOT an EKF)
  Locus     : trust scorer + trust-weighted robust fix + wall-aware particle filter,
              self-calibrating wall bias (wallMu), 90% ellipse, room probabilities,
              and a per-anchor human-readable "reason" for every trust score.

A pluggable `scorer` (see backend/ml.py) can replace the hand-written heuristic trust formula;
with scorer=None the original heuristic is used, so the system works without any trained model.
SIMULATION ONLY - nothing here has been calibrated against real BLE hardware.
"""
import math
import numpy as np
from . import sim
from .sim import FLOOR_W, FLOOR_H


def js_fixed(v, d):
    """JS Number.toFixed (round-half-up on the decimal repr) so reason strings match the JS engine."""
    return f'{math.floor(abs(v) * 10 ** d + 0.5 + 1e-9) / 10 ** d * (1 if v >= 0 else -1):.{d}f}'


def _seqsum(a):
    """Sequential (JS-like) sum; np.sum is pairwise and differs in the last bits."""
    return float(np.cumsum(a)[-1]) if len(a) else 0.0


def ls_fix(anchors, meas, init, w=None):
    """lsFix(): 12 damped Gauss-Newton iterations. meas[i] is None or a dict with key 'r'."""
    x, y = float(init[0]), float(init[1])
    n = 0
    for _ in range(12):
        a11, a12, a22, b1, b2 = 1e-3, 0.0, 1e-3, 0.0, 0.0
        n = 0
        for i, a in enumerate(anchors):
            m = meas[i]
            if not m:
                continue
            n += 1
            dx, dy = x - a['x'], y - a['y']
            d = max(0.2, math.hypot(dx, dy))
            ux, uy = dx / d, dy / d
            res = m['r'] - d
            wt = w[i] if w is not None else 1.0
            a11 += wt * ux * ux
            a12 += wt * ux * uy
            a22 += wt * uy * uy
            b1 += wt * ux * res
            b2 += wt * uy * res
        if not n:
            return None
        lam = 0.6 if n < 3 else 0.05
        det = (a11 + lam) * (a22 + lam) - a12 * a12
        x += ((a22 + lam) * b1 - a12 * b2) / det
        y += ((a11 + lam) * b2 - a12 * b1) / det
    return [min(FLOOR_W, max(0.0, x)), min(FLOOR_H, max(0.0, y))]


class KalmanCV:
    """Per-axis constant-velocity linear Kalman filter fed with LS fixes (the 'typical team' baseline)."""

    def __init__(self):
        self.x = None
        self.P = None

    def update(self, z, dt):
        if z is None:
            if self.x:
                self.x[0] += self.x[2] * dt
                self.x[1] += self.x[3] * dt
            return [self.x[0], self.x[1]] if self.x else None
        if not self.x:
            self.x = [z[0], z[1], 0.0, 0.0]
            self.P = [10.0, 10.0, 4.0, 4.0]
            return list(z)
        q, R = 0.4 * dt, 2.0
        for k in range(2):
            p, v, P, Pv = self.x[k], self.x[k + 2], self.P[k], self.P[k + 2]
            p += v * dt
            P += dt * dt * Pv + q
            Pv += q
            K = P / (P + R)
            K2 = (Pv * 0.2) / (P + R)
            inn = z[k] - p
            p += K * inn
            v += K2 / max(dt, 1e-3) * inn * 0.5
            P *= (1 - K)
            self.x[k], self.x[k + 2], self.P[k], self.P[k + 2] = p, v, P, Pv
        return [self.x[0], self.x[1]]


FEATURES = ['res_norm', 'res', 'abs_res_norm', 'jump_norm', 'jump', 'var_norm', 'var', 'wall_count', 'prior_std',
            'range', 'pred_range', 'peer_res_norm', 'n_readings', 'wall_mu']


class Locus:
    def __init__(self, site, anchors, N=600, sigma=0.6, rng=None, inflate=1.0, wallMu=1.4, scorer=None):
        self.site, self.anchors, self.N, self.sigma = site, anchors, N, sigma
        self.rng = rng or sim.Rng(7)
        self.inflate, self.wallMu, self.scorer = inflate, wallMu, scorer
        self.kg = [site.k_grid(a) for a in anchors]
        self.px, self.py = np.zeros(N), np.zeros(N)
        self.vx, self.vy = np.zeros(N), np.zeros(N)
        self.w = np.full(N, 1.0 / N)
        self.inited = False
        n = len(anchors)
        self.trust = [0.8] * n
        self.last = [None] * n
        self.silent = [0.0] * n
        self.hist = [[] for _ in range(n)]
        self.est = None
        self.fix = None
        self.lostN = 0

    # ------------------------------------------------------------------ helpers
    def _init(self, meas):
        c = [FLOOR_W / 2, FLOOR_H / 2]
        f = ls_fix(self.anchors, meas, c) or c
        z = self.rng.g_n(self.N * 4).reshape(self.N, 4)
        self.px = np.minimum(FLOOR_W - .1, np.maximum(.1, f[0] + z[:, 0] * 3.5))
        self.py = np.minimum(FLOOR_H - .1, np.maximum(.1, f[1] + z[:, 1] * 3.5))
        self.vx, self.vy = z[:, 2] * .5, z[:, 3] * .5
        self.inited = True
        self.est = list(f)

    def _moments(self):
        sw = _seqsum(self.w)
        mx = _seqsum(self.w * self.px) / sw
        my = _seqsum(self.w * self.py) / sw
        dx, dy = self.px - mx, self.py - my
        return dict(mx=mx, my=my, sxx=_seqsum(self.w * dx * dx) / sw, sxy=_seqsum(self.w * dx * dy) / sw,
                    syy=_seqsum(self.w * dy * dy) / sw)

    def _features(self, meas, prior, prior_std):
        """Per-reading features (computed from state *before* this step's trust update)."""
        A, sg = self.anchors, self.sigma
        feats = [None] * len(A)
        for i, a in enumerate(A):
            m = meas[i]
            if not m:
                continue
            kp = int(self.site.k_at(self.kg[i], prior[0], prior[1]))
            pred = math.hypot(prior[0] - a['x'], prior[1] - a['y']) + kp * self.wallMu
            res = m['r'] - pred
            s = math.sqrt(sg * sg + prior_std * prior_std + (kp * 0.8) ** 2)
            tol = 2.0 * s if res > 0 else 3.2 * s
            zr = abs(res) / tol
            h = (self.hist[i] + [m['r']])[-8:]
            jump = 0.0 if self.last[i] is None else abs(m['r'] - self.last[i])
            jx = max(0.0, jump - 0.25 - 3 * sg)
            vr = 0.0
            if len(h) > 3:
                mu = sum(h) / len(h)
                vr = math.sqrt(sum((c - mu) ** 2 for c in h) / len(h))
            feats[i] = dict(res=res, s=s, zr=zr, tR=1 / (1 + zr ** 3), jump=jump,
                            tJ=1 / (1 + (jx / (3 * sg)) ** 2),
                            tV=1 / (1 + (max(0.0, vr - 1.6 * sg) / (1.5 * sg)) ** 2), vr=vr, kp=kp, pred=pred, r=m['r'])
        n_read = sum(1 for f in feats if f)
        for i, f in enumerate(feats):
            if not f:
                continue
            others = [abs(g['res']) / g['s'] for j, g in enumerate(feats) if g and j != i]
            f['x'] = dict(res_norm=f['res'] / f['s'], res=f['res'], abs_res_norm=abs(f['res']) / f['s'],
                          jump_norm=f['jump'] / (3 * sg), jump=f['jump'], var_norm=f['vr'] / sg, var=f['vr'],
                          wall_count=f['kp'], prior_std=prior_std, range=f['r'], pred_range=f['pred'],
                          peer_res_norm=float(np.median(others)) if others else float('nan'),
                          n_readings=n_read, wall_mu=self.wallMu)
        return feats

    @staticmethod
    def heuristic_reason(trust, f):
        why = 'Consistent with motion model'
        if trust < 0.7:
            if f['tR'] <= f['tJ'] and f['tR'] <= f['tV']:
                res = f['res']
                why = ('Reads +%s m beyond what the walls explain (obstruction)' % js_fixed(res, 1)) if res > 0 \
                    else 'Reads %s m shorter than predicted' % js_fixed(-res, 1)
            elif f['tJ'] <= f['tV']:
                why = 'Sudden %s m jump between readings' % js_fixed(f['jump'], 1)
            else:
                why = 'Variance spike (σ %s m)' % js_fixed(f['vr'], 1)
        return why

    # ------------------------------------------------------------------ main step
    def step(self, meas, dt):
        A, r, N, sg, site = self.anchors, self.rng, self.N, self.sigma, self.site
        if not self.inited:
            if not any(meas):
                return None
            self._init(meas)
        # 1. predict (motion history), wall-aware: particles may not cross walls
        z = r.g_n(N * 4).reshape(N, 4)
        ox, oy = self.px, self.py
        vx = self.vx * 0.96 + z[:, 0] * 0.28
        vy = self.vy * 0.96 + z[:, 1] * 0.28
        sp = np.hypot(vx, vy)
        cap = sp > 2.2
        vx = np.where(cap, vx * 2.2 / np.where(sp == 0, 1, sp), vx)
        vy = np.where(cap, vy * 2.2 / np.where(sp == 0, 1, sp), vy)
        nx, ny = ox + vx * dt + z[:, 2] * 0.05, oy + vy * dt + z[:, 3] * 0.05
        bad = (nx < 0) | (ny < 0) | (nx > FLOOR_W) | (ny > FLOOR_H)
        chk = ~bad
        if chk.any():
            bad[chk] = site.crosses_wall(ox[chk], oy[chk], nx[chk], ny[chk])
        nx, ny = np.where(bad, ox, nx), np.where(bad, oy, ny)
        self.vx, self.vy = np.where(bad, vx * -0.2, vx), np.where(bad, vy * -0.2, vy)
        self.w = np.where(bad, self.w * 0.2, self.w)
        self.px, self.py = nx, ny
        pm = self._moments()
        prior = [pm['mx'], pm['my']]
        prior_std = math.sqrt(max(0.04, (pm['sxx'] + pm['syy']) / 2))
        # 2. trust scorer: residual vs motion prior, jump, variance -> 0..1 + reason
        feats = self._features(meas, prior, prior_std)
        reasons, usable, tRs, scored = [None] * len(A), [False] * len(A), [], [None] * len(A)
        batch = {}
        if self.scorer is not None:
            idx = [i for i, f in enumerate(feats) if f]
            if idx:
                batch = dict(zip(idx, self.scorer.score_batch([feats[i]['x'] for i in idx])))
        for i, a in enumerate(A):
            m = meas[i]
            if not m:
                self.silent[i] += dt
                self.trust[i] = max(0.0, self.trust[i] - dt * 0.8)
                reasons[i] = ('No packets for %s s' % js_fixed(self.silent[i], 0)) if self.silent[i] > 1 else 'Packet lost'
                continue
            self.silent[i] = 0.0
            f = feats[i]
            h = self.hist[i]
            h.append(m['r'])
            if len(h) > 8:
                h.pop(0)
            tRs.append(f['tR'])
            ml_reason = None
            if self.scorer is not None:
                p, ml_reason = batch[i]
                raw = max(0.02, p)
            else:
                raw = max(0.02, f['tR'] * f['tJ'] * math.sqrt(f['tV']))
            self.trust[i] = self.trust[i] * 0.55 + raw * 0.45
            self.last[i] = m['r']
            if self.scorer is not None:
                reasons[i] = ml_reason(self.trust[i]) if callable(ml_reason) else (ml_reason or 'Consistent with motion model')
            else:
                reasons[i] = self.heuristic_reason(self.trust[i], f)
            scored[i] = raw
            usable[i] = True
        # collective disagreement => our prior is probably wrong, not the anchors: relocalise
        lost = len(tRs) >= 2 and sum(1 for t in tRs if t < 0.3) >= math.ceil(len(tRs) * 0.6)
        self.lostN = self.lostN + 1 if lost else 0
        relocal = self.lostN >= 3
        # 3. trust-weighted robust fix from the motion prior
        w_trust = [t if usable[i] else 0.0 for i, t in enumerate(self.trust)]
        self.fix = ls_fix(A, meas, prior, [t * t for t in w_trust]) if any(t > 0.05 for t in w_trust) else None
        # 4. particle weight update with trust-inflated sigma + heavy-tail mix
        if relocal:
            f = ls_fix(A, meas, prior)
            if f:
                for _ in range(int(math.ceil(N * 0.15))):
                    j = int(r() * N)
                    self.px[j] = min(FLOOR_W - .1, max(.1, f[0] + r.g() * 3))
                    self.py[j] = min(FLOOR_H - .1, max(.1, f[1] + r.g() * 3))
                    self.w[j] = 1.0 / N
        eps = 0.04
        lw = np.log(self.w + 1e-300)
        for i, a in enumerate(A):
            m = meas[i]
            if not m or not usable[i]:
                continue
            t = max(self.trust[i], 0.45) if relocal else self.trust[i]
            if t < 0.08:
                continue
            kk = site.k_at(self.kg[i], self.px, self.py).astype(np.float64)
            si = np.sqrt(sg * sg / t + (kk * 0.8) ** 2) + 0.15
            d = np.hypot(self.px - a['x'], self.py - a['y']) + kk * self.wallMu
            zz = (m['r'] - d) / si
            lw = lw + np.log((1 - eps) * np.exp(-0.5 * zz * zz) / si + eps / 25)
        self.w = np.exp(lw)
        sw = _seqsum(self.w)
        if not sw > 0:
            self.w = np.full(N, 1.0 / N)
            sw = 1.0
        self.w = self.w / sw
        ess = 1.0 / _seqsum(self.w * self.w)
        # 5. estimate + 90% ellipse + room probabilities
        mo = self._moments()
        cxx, cyy, cxy = mo['sxx'], mo['syy'], mo['sxy']
        tr, det = cxx + cyy, cxx * cyy - cxy * cxy
        disc = math.sqrt(max(0.0, tr * tr / 4 - det))
        l1, l2 = tr / 2 + disc, max(1e-4, tr / 2 - disc)
        k = 4.605 * self.inflate * self.inflate
        ell = dict(a=max(0.35, math.sqrt(k * l1)), b=max(0.3, math.sqrt(k * l2)), th=0.5 * math.atan2(2 * cxy, cxx - cyy))
        ridx = site.room_ids_at(self.px, self.py)
        rw = np.bincount(ridx, weights=self.w, minlength=len(site.rooms))
        rp = {site.rooms[j]['id']: float(rw[j]) for j in range(len(site.rooms)) if np.any(ridx == j)}
        self.est = [mo['mx'], mo['my']]
        # self-calibration: re-fit wall bias (m per wall) from readings we trust
        for i, a in enumerate(A):
            m = meas[i]
            if not m or not usable[i] or self.trust[i] < 0.5:
                continue
            ke = int(site.k_at(self.kg[i], mo['mx'], mo['my']))
            if ke < 1:
                continue
            mu = (m['r'] - math.hypot(mo['mx'] - a['x'], mo['my'] - a['y'])) / ke
            self.wallMu = min(3.5, max(0.8, self.wallMu + 0.02 * (mu - self.wallMu)))
        out = dict(wallMu=self.wallMu, pos=list(self.est), ell=ell, rooms=rp, trust=list(self.trust), reasons=reasons,
                   usable=usable, fix=self.fix, ess=ess / N, relocal=relocal, ell_raw=dict(l1=l1, l2=l2, th=ell['th']),
                   features=[f['x'] if f else None for f in feats], raw=scored)
        # 6. resample + roughen
        if ess < N * 0.6:
            u = r() / N + np.arange(N) / N
            c = np.cumsum(self.w)
            idx = np.minimum(np.searchsorted(c, u, side='left'), N - 1)
            g = r.g_n(N * 2).reshape(N, 2)
            self.px, self.py = self.px[idx] + g[:, 0] * 0.07, self.py[idx] + g[:, 1] * 0.07
            self.vx, self.vy = self.vx[idx], self.vy[idx]
            self.w = np.full(N, 1.0 / N)
        return out

    def particles(self, n=150):
        """Down-sampled particle cloud [[x,y],...] for the dashboard."""
        step = max(1, self.N // n)
        return np.round(np.stack([self.px[::step], self.py[::step]], 1), 2).tolist()
