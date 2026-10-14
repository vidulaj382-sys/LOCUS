"""Shared live session: one simulated (or real-BLE-fed) world that every connected dashboard / staff app reads."""
import json, math, time
from collections import deque
import numpy as np
from . import sim, engine, ml, replay

DEF = dict(sigma=0.6, loss=0.10, wallBias=1.8, burst=0.004, obstructBias=4.0, driftBias=2.5)
LIVE_TIMEOUT = 2.0          # seconds without ingested readings before we fall back to the simulator


def rssi_to_range(rssi, rssi_at_1m=-40.0, n=2.2):
    """Inverse of the log-distance model  RSSI = rssi_at_1m - 10*n*log10(range). Defaults are the dataset's constants
    (scripts/generate_dataset.py); real beacons need their own measured rssi_at_1m / path-loss exponent."""
    return float(10 ** ((rssi_at_1m - rssi) / (10.0 * n)))


class LiveSession:
    def __init__(self):
        self.site_id, self.custom = 'hospital', None
        self.n, self.hz, self.scorer_mode = 6, 10, 'heuristic'
        self.params = dict(DEF)
        self.dead, self.obstruct, self.drift = set(), set(), set()
        self.ml = ml.load_scorer()
        self.live = {}                # anchor_id -> [range_m, server_time, consumed]
        self.errs = deque(maxlen=1500)
        self.frame_idx = 0
        self.reset()

    @property
    def site(self):
        return self.custom if (self.site_id == 'custom' and self.custom) else sim.get_site('warehouse' if self.site_id == 'warehouse' else 'hospital')

    @staticmethod
    def meta_inflate():
        try:
            return json.loads((ml.MODELS / 'trust_meta.json').read_text())['ellipse_inflate']
        except Exception:
            return {'heuristic': 2.0, 'ml': 2.0}

    def reset(self):
        site = self.site
        self.site_obj = site
        self.n = max(1, min(self.n, len(site.anchors)))
        self.anchors = [site.anchors[i] for i in site.drop][:self.n]
        self.rng = sim.Rng(2026)
        self.walker = sim.Walker(site, 1.2, 6)
        self.kf, self.last_ls = engine.KalmanCV(), [20.0, 12.0]
        use_ml = self.scorer_mode == 'ml' and self.ml is not None
        self.inflate = self.meta_inflate()['ml' if use_ml else 'heuristic']
        self.loc = engine.Locus(site, self.anchors, N=400, sigma=self.params['sigma'], rng=sim.Rng(11), inflate=self.inflate,
                                scorer=self.ml if use_ml else None)
        self.sim_t = 0.0
        self.errs.clear()

    def state(self):
        return dict(site=self.site_id, n=self.n, hz=self.hz, scorer=self.scorer_mode, ml_available=self.ml is not None, params=self.params,
                    dead=sorted(self.dead), obstruct=sorted(self.obstruct), drift=sorted(self.drift), mode=self.mode(),
                    anchors=[dict(id=a['id'], x=a['x'], y=a['y']) for a in self.anchors],
                    site_ids=['hospital', 'warehouse'] + (['custom'] if self.custom else []))

    def apply(self, d):
        rebuild = False
        for k in ('sigma', 'loss', 'wallBias', 'burst', 'obstructBias', 'driftBias'):
            if k in d:
                self.params[k] = float(d[k])
                if k == 'sigma':
                    self.loc.sigma = float(d[k])
        for k, s in (('dead', self.dead), ('obstruct', self.obstruct), ('drift', self.drift)):
            if k in d:
                s.clear()
                s.update(d[k])
        tg = d.get('toggle')
        if tg:
            s = {'dead': self.dead, 'obstruct': self.obstruct, 'drift': self.drift}[tg['kind']]
            s.symmetric_difference_update({tg['id']})
        if 'hz' in d:
            self.hz = int(min(20, max(2, d['hz'])))
        if 'nAnch' in d and int(d['nAnch']) != self.n:
            self.n, rebuild = int(d['nAnch']), True
        if 'site' in d and d['site'] != self.site_id and (d['site'] in ('hospital', 'warehouse') or (d['site'] == 'custom' and self.custom)):
            self.site_id, rebuild = d['site'], True
            self.dead.clear(); self.obstruct.clear(); self.drift.clear()
        if 'scorer' in d and d['scorer'] in ('heuristic', 'ml') and d['scorer'] != self.scorer_mode:
            self.scorer_mode, rebuild = d['scorer'], True
        if d.get('reset') or rebuild:
            self.reset()

    def set_custom(self, site):
        self.custom, self.site_id = site, 'custom'
        self.dead.clear(); self.obstruct.clear(); self.drift.clear()
        self.reset()

    def clear_custom(self):
        self.custom, self.site_id = None, 'hospital'
        self.reset()

    # ---- real readings (Web Bluetooth / any scanner) enter here, same {'r': metres} shape the simulator produces
    def ingest(self, anchor_id, rssi=None, range_m=None, rssi_at_1m=-40.0, n=2.2):
        if anchor_id not in {a['id'] for a in self.site.anchors}:
            raise KeyError(anchor_id)
        r = rssi_to_range(float(rssi), float(rssi_at_1m), float(n)) if range_m is None else float(range_m)
        self.live[anchor_id] = [max(0.3, r), time.time(), False, None if rssi is None else float(rssi)]
        self.ingested = getattr(self, 'ingested', 0) + 1

    def mode(self):
        now = time.time()
        return 'live' if any(now - v[1] < LIVE_TIMEOUT for v in self.live.values()) else 'sim'

    def step(self):
        dt = 1.0 / self.hz
        mode = self.mode()
        truth = None
        if mode == 'live':
            meas = []
            for a in self.anchors:
                v = self.live.get(a['id'])
                if v and not v[2] and time.time() - v[1] < LIVE_TIMEOUT:
                    v[2] = True
                    meas.append({'r': v[0]})
                else:
                    meas.append(None)
        else:
            p = self.params
            cfg = sim.make_cfg(sigma=p['sigma'], loss=p['loss'], wallBias=p['wallBias'], burst=p['burst'], obstructBias=p['obstructBias'],
                               driftBias=p['driftBias'], dead=self.dead, obstruct=self.obstruct, drift=self.drift)
            truth = list(self.walker.step(dt))
            meas = sim.measure(self.site_obj, truth, self.anchors, cfg, self.rng)
        ls = engine.ls_fix(self.anchors, meas, self.last_ls)
        if ls:
            self.last_ls = ls
        kfp = self.kf.update(ls, dt)
        out = self.loc.step(meas, dt)
        self.sim_t += dt
        self.frame_idx += 1

        def e(q):
            return float(math.hypot(q[0] - truth[0], q[1] - truth[1])) if (q and truth) else None
        f = dict(type='frame', idx=self.frame_idx, t=round(self.sim_t, 3), mode=mode, site=self.site_id, scorer=self.scorer_mode,
                 truth=truth, ls=ls, kf=kfp, est=None, ell=None, rooms={}, anchors=[], particles=[],
                 err=dict(lo=None, kf=e(kfp), ls=e(ls)),
                 ctl=dict(dead=sorted(self.dead), obstruct=sorted(self.obstruct), drift=sorted(self.drift), n=self.n))
        if out:
            a_, b_ = replay.ellipse_axes(out['ell_raw']['l1'], out['ell_raw']['l2'], self.inflate)
            f.update(est=out['pos'], ell=dict(a=float(a_), b=float(b_), th=out['ell_raw']['th']), rooms=out['rooms'], wallMu=out['wallMu'],
                     ess=out['ess'], relocal=out['relocal'], particles=self.loc.particles(120), fix=out['fix'])
            f['err']['lo'] = e(out['pos'])
            if f['err']['lo'] is not None:
                self.errs.append((f['err']['lo'], f['err']['kf'], f['err']['ls']))
            for i, a in enumerate(self.anchors):
                f['anchors'].append(dict(id=a['id'], x=a['x'], y=a['y'], trust=round(out['trust'][i], 4), reason=out['reasons'][i],
                                         usable=out['usable'][i], dead=a['id'] in self.dead, r=None if not meas[i] else round(meas[i]['r'], 3)))
        return f

    def live_stats(self):
        if not self.errs:
            return None
        a = np.array([[x if x is not None else np.nan for x in row] for row in self.errs], dtype=float)
        out = {}
        for j, k in enumerate(('locus', 'kalman', 'wls')):
            c = a[:, j][~np.isnan(a[:, j])]
            if len(c):
                out[k] = dict(cep50=float(np.quantile(c, .5)), cep95=float(np.quantile(c, .95)), n=int(len(c)))
        return out
