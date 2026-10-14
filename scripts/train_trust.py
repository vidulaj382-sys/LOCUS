"""Phase 3: train the ML trust scorer from the TRAIN set only (never touches the hidden set).

1. Replay every train run through the Python engine, logging for each anchor reading: the engine features and the
   ground-truth labels (nlos flag, wall count, bias, impaired).
2. Round 1 uses the heuristic scorer to drive the filter; round 2 replays with the round-1 model driving the filter so the
   features match the distribution the model will actually see (then refit on both rounds).
3. Group split by run (no leakage): seeds 1001/1101 -> fit, 1002/1102 -> half calibration (isotonic), half evaluation.
4. Also fits an IsolationForest and calibrates the ellipse inflation on TRAIN to hit 90% coverage.
"""
import json, pathlib, sys, time
import numpy as np, pandas as pd
import lightgbm as lgb, joblib
from sklearn.ensemble import IsolationForest
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score, brier_score_loss

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend import dataset, replay, ml

OUT = ROOT / 'backend' / 'models'
N_PART = 400


def collect(runs, scorer, tag):
    rows = []
    for rid, run in runs.items():
        res = replay.replay(run, rid, 6, scorer=scorer, N=N_PART, keep_outs=True)
        for s, o in res['outs']:
            for i in range(6):
                x = o['features'][i]
                if x is None:
                    continue
                rows.append(dict(run_id=rid, t_idx=s, anchor=i, round=tag, **x, heur_raw=o['raw'][i],
                                 nlos=run['extra']['nlos'][s, i], n_walls=run['extra']['n_walls'][s, i],
                                 bias_m=run['extra']['bias_m'][s, i], impaired=run['extra']['impaired'][s, i]))
    return pd.DataFrame(rows)


def ece(y, p, bins=10):
    idx = np.minimum((p * bins).astype(int), bins - 1)
    return float(sum(abs(y[idx == b].mean() - p[idx == b].mean()) * (idx == b).mean() for b in range(bins) if (idx == b).any()))


def fit(df):
    run_seed = df['run_id'].str.extract(r's(\d+)-')[0].astype(int) % 100
    part = np.where(run_seed == 1, 'fit', np.where(df['run_id'].str.contains('c0|c1'), 'cal', 'eval'))
    df = df.assign(part=part)
    y = 1 - df['impaired'].to_numpy()          # 1 = trustworthy
    X = df[ml.FEATURES].to_numpy()
    f = df['part'] == 'fit'
    clf = lgb.LGBMClassifier(n_estimators=250, learning_rate=0.05, num_leaves=15, min_child_samples=60, subsample=0.8, subsample_freq=1,
                             colsample_bytree=0.9, reg_lambda=1.0, random_state=0, verbose=-1)
    clf.fit(X[f], y[f])
    booster = clf.booster_
    c = (df['part'] == 'cal').to_numpy()
    iso = IsotonicRegression(out_of_bounds='clip', y_min=0.0, y_max=1.0).fit(booster.predict(X[c]), y[c])
    e = (df['part'] == 'eval').to_numpy()
    p_raw, p_cal = booster.predict(X[e]), iso.predict(booster.predict(X[e]))
    metrics = dict(n_fit=int(f.sum()), n_cal=int(c.sum()), n_eval=int(e.sum()), impaired_rate=float(1 - y.mean()),
                   auc_lgbm=float(roc_auc_score(y[e], p_cal)), auc_heuristic=float(roc_auc_score(y[e], df['heur_raw'].to_numpy()[e])),
                   brier_raw=float(brier_score_loss(y[e], p_raw)), brier_calibrated=float(brier_score_loss(y[e], p_cal)),
                   ece_raw=ece(y[e], p_raw), ece_calibrated=ece(y[e], p_cal), acc_at_0p5=float(((p_cal > 0.5) == y[e]).mean()))
    forest = IsolationForest(n_estimators=40, contamination=0.04, random_state=0, n_jobs=1).fit(np.nan_to_num(X[f], nan=0.0))
    ev = np.nan_to_num(X[e], nan=0.0)
    metrics['iforest_flag_rate_eval'] = float((forest.predict(ev) == -1).mean())
    metrics['iforest_auc_vs_impaired'] = float(roc_auc_score(1 - y[e], -forest.score_samples(ev)))
    gain = dict(zip(ml.FEATURES, (booster.feature_importance('gain') / booster.feature_importance('gain').sum()).round(4).tolist()))
    sub = X[e][:4000]
    shap = np.abs(booster.predict(sub, pred_contrib=True)[:, :-1]).mean(0)
    shap = dict(zip(ml.FEATURES, (shap / shap.sum()).round(4).tolist()))
    return booster, iso, forest, metrics, gain, shap


def main():
    t0 = time.time()
    runs = dataset.load_runs(dataset.DATA / 'train.csv')
    print(f'{len(runs)} train runs loaded')
    d1 = collect(runs, None, 1)
    print(f'round 1: {len(d1)} readings ({time.time() - t0:.0f}s)')
    booster, iso, forest, m1, *_ = fit(d1)
    print('round-1 model: AUC %.3f (heuristic %.3f)' % (m1['auc_lgbm'], m1['auc_heuristic']))
    OUT.mkdir(exist_ok=True)
    booster.save_model(str(OUT / 'trust_lgbm.txt')); joblib.dump(iso, OUT / 'trust_isotonic.joblib'); joblib.dump(forest, OUT / 'anomaly_iforest.joblib')
    (OUT / 'trust_meta.json').write_text(json.dumps(dict(features=ml.FEATURES)))
    scorer = ml.load_scorer()
    d2 = collect(runs, scorer, 2)
    print(f'round 2: {len(d2)} readings ({time.time() - t0:.0f}s)')
    df = pd.concat([d1, d2], ignore_index=True)
    booster, iso, forest, metrics, gain, shap = fit(df)
    print(json.dumps(metrics, indent=1))
    booster.save_model(str(OUT / 'trust_lgbm.txt')); joblib.dump(iso, OUT / 'trust_isotonic.joblib'); joblib.dump(forest, OUT / 'anomaly_iforest.joblib')
    df.drop(columns=['round']).round(5).to_csv(dataset.DATA / 'ml_trust_train.csv.gz', index=False)
    # ellipse inflation: pick on TRAIN so that 90% of true points fall inside (no hidden data involved)
    infl = {}
    scorer = ml.load_scorer()
    for name, sc in (('heuristic', None), ('ml', scorer)):
        d2s = []
        for rid, run in runs.items():
            r = replay.replay(run, rid, 6, scorer=sc, N=N_PART, methods=('lo',))
            tr = run['truth']
            for s in range(replay.WARMUP, len(tr)):
                if np.isnan(r['lo'][s, 0]):
                    continue
                dx, dy = tr[s, 0] - r['lo'][s, 0], tr[s, 1] - r['lo'][s, 1]
                c, sn = np.cos(-r['th'][s]), np.sin(-r['th'][s])
                u, v = dx * c - dy * sn, dx * sn + dy * c
                d2s.append((u * u / max(r['l1'][s], 1e-4) + v * v / max(r['l2'][s], 1e-4)) / 4.605)   # inflate^2 needed to just contain the point
        infl[name] = float(np.sqrt(np.quantile(d2s, 0.90)))
    print('ellipse inflation for 90%% train coverage: %s' % infl)
    meta = dict(features=ml.FEATURES, metrics=metrics, importance_gain=gain, importance_mean_abs_shap=shap, ellipse_inflate=infl,
                label='1 = reading NOT corrupted by obstruction/burst/drift (wall-only NLOS counts as trustworthy: the filter models walls)',
                trained_on='simulated train.csv only (seeds 1001,1002,1101,1102); no real hardware', rounds=2)
    (OUT / 'trust_meta.json').write_text(json.dumps(meta, indent=1))
    print('feature importance (mean |SHAP| share):', dict(sorted(shap.items(), key=lambda kv: -kv[1])))
    print(f'done in {time.time() - t0:.0f}s -> {OUT}')


if __name__ == '__main__':
    main()
