"""Load LOCUS datasets (CSV from scripts/generate_dataset.py) into per-run measurement sequences the engine can replay."""
import json, pathlib
import numpy as np
import pandas as pd
from . import sim

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'


def load_runs(csv_path, truth_path=None):
    """-> {run_id: dict(site, anchors[list ordered by site.drop], t[T], ranges[T,A] (nan = lost), truth[T,2] or None, extra[col][T,A])}"""
    df = pd.read_csv(csv_path)
    truth = pd.read_csv(truth_path).set_index(['run_id', 't_idx']) if truth_path else None
    runs = {}
    for rid, g in df.groupby('run_id', sort=False):
        site_id = g['site'].iloc[0]
        site = sim.get_site(site_id)
        order = [site.anchors[i]['id'] for i in site.drop]
        T = int(g['t_idx'].max()) + 1
        piv = lambda col: g.pivot(index='t_idx', columns='anchor_id', values=col).reindex(columns=order).reindex(range(T))
        run = dict(site=site_id, anchors=[site.anchors[i] for i in site.drop], t=piv('timestamp_s')[order[0]].to_numpy(),
                   ranges=piv('range_m').to_numpy(), rssi=piv('rssi_dbm').to_numpy(), truth=None, extra={})
        if 'truth_x' in g:
            run['truth'] = np.stack([g.groupby('t_idx')['truth_x'].first().to_numpy(), g.groupby('t_idx')['truth_y'].first().to_numpy()], 1)
            for col in ('nlos', 'n_walls', 'bias_m', 'impaired', 'true_range_m'):
                run['extra'][col] = piv(col).to_numpy()
        elif truth is not None:
            tr = truth.loc[rid]
            run['truth'] = tr[['truth_x', 'truth_y']].to_numpy()
        runs[rid] = run
    return runs


def meas_at(run, s, n_anchors=None):
    """Engine-style measurement list for step s, optionally only the first n anchors (DROP_ORDER subset)."""
    row = run['ranges'][s]
    n = len(row) if n_anchors is None else n_anchors
    return [None if np.isnan(row[i]) else {'r': float(row[i])} for i in range(n)]


def load_meta(name):
    return json.loads((DATA / name).read_text())
