"""Phase 4 benchmark: WLS vs KalmanCV vs LOCUS(heuristic) vs LOCUS(ML trust) on the HIDDEN test set.

The engine only ever sees data/hidden_public.csv; ground truth (hidden_truth.csv) and the noise-level tags
(hidden_private_meta.json) are used only here, for scoring/bucketing. Anchor counts 6..2 are produced by keeping the
first n anchors in each site's DROP_ORDER. The engine is NOT told the true noise sigma (fixed nominal sigma).
Ellipse inflation is calibrated on TRAIN data (scripts/train_trust.py) - not tuned on hidden data.
"""
import json, pathlib, time
from concurrent.futures import ProcessPoolExecutor
import numpy as np
from . import dataset, replay, ml

ROOT = pathlib.Path(__file__).resolve().parent.parent
METHODS = ['WLS', 'Kalman(CV)', 'LOCUS (heuristic)', 'LOCUS (ML trust)']
CDF_X = np.round(np.arange(0, 15.01, 0.25), 2)


def _meta_inflate():
    try:
        return json.loads((ml.MODELS / 'trust_meta.json').read_text())['ellipse_inflate']
    except Exception:
        return {'heuristic': 2.0, 'ml': 2.0}


def _job(args):
    rid, run, n, with_ml, N = args
    infl = _meta_inflate()
    truth = run['truth']
    out = {}
    h = replay.replay(run, rid, n, scorer=None, N=N)
    out['WLS'] = (replay.errors(h, truth, 'ls'), None)
    out['Kalman(CV)'] = (replay.errors(h, truth, 'kf'), None)
    out['LOCUS (heuristic)'] = (replay.errors(h, truth, 'lo'), replay.coverage(h, truth, infl['heuristic']))
    if with_ml:
        scorer = ml.load_scorer()
        if scorer is not None:
            m = replay.replay(run, rid, n, scorer=scorer, N=N)
            out['LOCUS (ML trust)'] = (replay.errors(m, truth, 'lo'), replay.coverage(m, truth, infl['ml']))
    return rid, n, out


def stats(errs, cov):
    e = np.concatenate(errs) if errs else np.array([])
    if not len(e):
        return None
    d = dict(n_fixes=int(len(e)), median_m=float(np.median(e)), p90_m=float(np.quantile(e, 0.9)), p95_m=float(np.quantile(e, 0.95)),
             within_2m_pct=float((e < 2).mean() * 100), rmse_m=float(np.sqrt((e ** 2).mean())))
    if cov is not None and cov[1]:
        d['ellipse90_coverage_pct'] = float(cov[0] / cov[1] * 100)
    return d


def run_benchmark(public_csv=None, truth_csv=None, meta_json=None, workers=None, anchor_counts=(6, 5, 4, 3, 2), max_steps=None,
                  run_filter=None, N=400, progress=None):
    public_csv = public_csv or dataset.DATA / 'hidden_public.csv'
    truth_csv = truth_csv or dataset.DATA / 'hidden_truth.csv'
    meta = json.loads(pathlib.Path(meta_json or dataset.DATA / 'hidden_private_meta.json').read_text())
    runs = dataset.load_runs(public_csv, truth_csv)
    if run_filter:
        runs = {k: v for k, v in runs.items() if run_filter(k, meta[k])}
    if max_steps:
        for r in runs.values():
            r['ranges'], r['truth'] = r['ranges'][:max_steps], r['truth'][:max_steps]
    with_ml = ml.load_scorer() is not None
    jobs = [(rid, run, n, with_ml, N) for rid, run in runs.items() for n in anchor_counts]
    acc = {}
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for k, (rid, n, out) in enumerate(ex.map(_job, jobs)):
            level = meta[rid]['noise_level']
            for method, (e, cov) in out.items():
                for lv in (level, 'all'):
                    a = acc.setdefault((n, lv, method), dict(errs=[], ok=0, tot=0))
                    a['errs'].append(e)
                    if cov:
                        a['ok'] += cov[0]
                        a['tot'] += cov[1]
            if progress:
                progress((k + 1) / len(jobs))
    results = []
    for (n, lv, method), a in sorted(acc.items(), key=lambda kv: (-kv[0][0], kv[0][1], METHODS.index(kv[0][2]))):
        s = stats(a['errs'], (a['ok'], a['tot']) if a['tot'] else None)
        if s:
            results.append(dict(anchors=n, noise_level=lv, method=method, **s))
    cdf = {}
    for (n, lv, method), a in acc.items():
        if lv != 'all':
            continue
        e = np.concatenate(a['errs'])
        cdf.setdefault(str(n), {})[method] = [round(float((e <= x).mean()), 4) for x in CDF_X]
    sigmas = {lv: sorted({m['cfg']['sigma'] for m in meta.values() if m['noise_level'] == lv}) for lv in ('low', 'mid', 'high')}
    return dict(
        generated_at=time.strftime('%Y-%m-%d %H:%M:%S'), seconds=round(time.time() - t0, 1),
        dataset=dict(public=str(pathlib.Path(public_csv).name), runs=len(runs), note='HIDDEN test set; simulated data only, no real hardware'),
        settings=dict(particles=N, nominal_sigma=replay.NOMINAL_SIGMA, warmup_steps=replay.WARMUP, ellipse_inflate=_meta_inflate(),
                      ml_model_present=with_ml, noise_levels_sigma_m=sigmas),
        cdf_x=CDF_X.tolist(), cdf=cdf, results=results)


def summary_table(res, anchors=(6, 4, 3, 2)):
    lines = []
    for n in anchors:
        lines.append(f'--- {n} anchors, ALL hidden noise levels pooled ---')
        lines.append(f'{"method":20s} {"median":>7s} {"p90":>7s} {"p95":>7s} {"<2m %":>7s} {"90% ell. cov %":>15s}')
        for r in res['results']:
            if r['anchors'] == n and r['noise_level'] == 'all':
                lines.append(f'{r["method"]:20s} {r["median_m"]:7.2f} {r["p90_m"]:7.2f} {r["p95_m"]:7.2f} {r["within_2m_pct"]:7.1f} '
                             f'{r.get("ellipse90_coverage_pct", float("nan")):15.1f}')
    return '\n'.join(lines)


def plot_cdf(res, path, counts=('6', '4', '2')):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    cols = {'WLS': '#7C93C3', 'Kalman(CV)': '#F5A524', 'LOCUS (heuristic)': '#10B981', 'LOCUS (ML trust)': '#0B3A4A'}
    fig, axs = plt.subplots(1, len(counts), figsize=(4.6 * len(counts), 3.8), sharey=True)
    for ax, n in zip(np.atleast_1d(axs), counts):
        for m, y in res['cdf'].get(n, {}).items():
            ax.plot(res['cdf_x'], y, label=m, color=cols[m], lw=2)
        ax.axvline(2, color='#bbb', ls='--', lw=1)
        ax.set_title(f'{n} anchors'); ax.set_xlabel('position error (m)'); ax.grid(alpha=.25); ax.set_xlim(0, 15); ax.set_ylim(0, 1)
    np.atleast_1d(axs)[0].set_ylabel('fraction of fixes <= error')
    np.atleast_1d(axs)[-1].legend(loc='lower right', fontsize=8)
    fig.suptitle('Error CDF on the HIDDEN simulated test set (all noise levels pooled)')
    fig.tight_layout(); fig.savefig(path, dpi=140); plt.close(fig)
