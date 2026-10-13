"""ML trust scorer for LOCUS.

  LightGBM classifier  -> P(reading is trustworthy), isotonic-calibrated, per anchor reading
  IsolationForest      -> general "this reading looks statistically unusual" flag
  LightGBM pred_contrib (native TreeSHAP) -> which feature actually pushed the score down; the
                          per-anchor reason string is generated from that, not canned.

Artifacts live in backend/models/. If they are missing, load_scorer() returns None and the engine
silently uses the hand-written heuristic trust scorer, so nothing breaks without a trained model.
Trained on SIMULATED data only (scripts/generate_dataset.py).
"""
import json, pathlib
import numpy as np

MODELS = pathlib.Path(__file__).resolve().parent / 'models'
FEATURES = ['res_norm', 'res', 'abs_res_norm', 'jump_norm', 'jump', 'var_norm', 'var', 'wall_count', 'prior_std',
            'range', 'pred_range', 'peer_res_norm', 'n_readings', 'wall_mu']
GROUPS = {'residual': ['res_norm', 'res', 'abs_res_norm', 'pred_range'], 'peer': ['peer_res_norm'], 'jump': ['jump_norm', 'jump'],
          'variance': ['var_norm', 'var'], 'walls': ['wall_count', 'wall_mu'], 'context': ['prior_std', 'range', 'n_readings']}
FEAT_GROUP = {f: g for g, fs in GROUPS.items() for f in fs}


def vec(x):
    return np.array([[x[f] for f in FEATURES]], dtype=np.float64)


def describe(group, x):
    if group == 'residual':
        return ('Reads +%.1f m beyond what the walls explain (obstruction-like)' % x['res']) if x['res'] > 0 \
            else 'Reads %.1f m shorter than the motion model predicts' % -x['res']
    if group == 'peer':
        return 'Disagrees with the other anchors (median peer residual %.1f sigma)' % x['peer_res_norm']
    if group == 'jump':
        return 'Sudden %.1f m jump between readings' % x['jump']
    if group == 'variance':
        return 'Variance spike (sigma %.1f m over last readings)' % x['var']
    if group == 'walls':
        return 'Link crosses %d wall(s) - noisier than line-of-sight' % int(x['wall_count'])
    return 'Low-confidence context (position uncertainty +/-%.1f m, %d anchors reporting)' % (x['prior_std'], int(x['n_readings']))


class TrustScorer:
    def __init__(self, booster, iso, forest, meta):
        self.booster, self.iso, self.forest, self.meta = booster, iso, forest, meta

    def predict_proba(self, X):
        raw = self.booster.predict(X, num_threads=1)
        return np.interp(raw, self.iso.X_thresholds_, self.iso.y_thresholds_) if self.iso is not None else raw   # == iso.predict, without sklearn overhead

    def contributions(self, x):
        """TreeSHAP log-odds contribution per feature and per group (negative = pushes toward 'untrusted')."""
        c = self.booster.predict(vec(x), pred_contrib=True, num_threads=1)[0][:-1]
        per_feat = dict(zip(FEATURES, c))
        per_group = {}
        for f, v in per_feat.items():
            per_group[FEAT_GROUP[f]] = per_group.get(FEAT_GROUP[f], 0.0) + v
        return per_feat, per_group

    def anomaly(self, x):
        if self.forest is None:
            return False
        v = np.nan_to_num(vec(x), nan=0.0)
        return bool(self.forest.predict(v)[0] == -1)

    def explain(self, x, p=None):
        per_feat, per_group = self.contributions(x)
        g = min(per_group, key=per_group.get)
        f = min((f for f in per_feat if FEAT_GROUP[f] == g), key=per_feat.get)
        return dict(group=g, feature=f, contribution=float(per_feat[f]), group_contribution=float(per_group[g]),
                    anomaly=self.anomaly(x), groups={k: float(v) for k, v in per_group.items()})

    def score_batch(self, xs):
        """Score all readings of one step with a single model call."""
        ps = self.predict_proba(np.vstack([vec(x) for x in xs]))
        return [self._pack(x, float(p)) for x, p in zip(xs, ps)]

    def score(self, x):
        return self._pack(x, float(self.predict_proba(vec(x))[0]))

    def _pack(self, x, p):
        """-> (trust probability, reason(trust) callable). The reason is computed lazily - only when trust ends up < 0.7."""
        def reason(trust):
            if trust >= 0.7:
                return 'Consistent with motion model'
            e = self.explain(x)
            txt = describe(e['group'], x) + ' [driver: %s %+.2f logit' % (e['feature'], e['contribution']) + (', statistically anomalous' if e['anomaly'] else '') + ']'
            return txt
        return p, reason


def load_scorer(path=MODELS):
    """Return a TrustScorer, or None if the model artifacts are missing/unreadable (engine then uses the heuristic)."""
    try:
        import lightgbm as lgb, joblib
        path = pathlib.Path(path)
        booster = lgb.Booster(model_file=str(path / 'trust_lgbm.txt'), params={'num_threads': 1})
        iso = joblib.load(path / 'trust_isotonic.joblib') if (path / 'trust_isotonic.joblib').exists() else None
        forest = joblib.load(path / 'anomaly_iforest.joblib') if (path / 'anomaly_iforest.joblib').exists() else None
        meta = json.loads((path / 'trust_meta.json').read_text())
        return TrustScorer(booster, iso, forest, meta)
    except Exception:
        return None
