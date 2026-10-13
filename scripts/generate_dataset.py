"""LOCUS dataset generator  (Code Apex 3.0, Track 4, PS2 - AI-based indoor positioning,
sparse infrastructure, noisy measurements).

REQUIRED DATASET SCHEMA  -- READ THIS FIRST
-------------------------------------------
!! The PS2 problem-statement text was NOT available to the author of this script (the repo only
!! carries the track/problem name). The schema below is built from the four ingredients the team
!! lists for PS2 - reference-point (anchor) coordinates, measured range/RSSI, timestamp and
!! ground-truth target coordinates. If the official PS2 document names or orders columns
!! differently, change COLUMN NAMES ONLY in the two *_COLS tuples below; nothing else depends on them.

One row = one (timestamp, reference point/anchor) observation ("long" format).

  run_id        str    trajectory id, e.g. TR-hospital-s1001-c0 / HT-hospital-s90001-h0
  site          str    'hospital' | 'warehouse' (40 m x 24 m footprint, metres, origin top-left)
  t_idx         int    sample index within the run
  timestamp_s   float  seconds since run start (10 Hz => 0.1 s step)
  anchor_id     str    A1..A6   (reference point id)
  anchor_x      float  reference point x, metres
  anchor_y      float  reference point y, metres
  range_m       float  measured range to the anchor, metres; EMPTY when the packet was lost / anchor dead
  rssi_dbm      float  measured RSSI, dBm (derived from range_m with a fixed log-distance model
                       RSSI = -40 - 10*2.2*log10(range_m); SYNTHETIC, no independent RSSI noise)
  packet_ok     int    1 if a reading was received, 0 if lost
  --- ground truth (TRAIN file only; for the hidden set these live in hidden_truth.csv) ---
  truth_x, truth_y   float  true target position, metres
  true_range_m  float  true Euclidean distance target->anchor
  nlos          int    1 if the reading is non-line-of-sight / biased (wall, obstruction, burst, drift)
  n_walls       int    walls crossed by the straight anchor->target line
  bias_m        float  additive range bias injected into this reading (what an ideal model would remove)

Files written under data/:
  train.csv                 labelled training set (all columns above)
  train_meta.json           per-run noise configuration + seeds
  hidden_public.csv         HIDDEN TEST *input* only (no truth / no nlos / no bias columns)
  hidden_truth.csv          run_id,t_idx,timestamp_s,truth_x,truth_y   (kept apart, evaluation only)
  hidden_private_meta.json  noise configs / scenario tags for the hidden runs (evaluation only)

Reproducibility: TRAIN_BASE_SEED = 1000, HIDDEN_BASE_SEED = 90000. Train and hidden use disjoint seeds,
train walks the site's stock waypoint loop while hidden walks freshly generated random routes at different
speeds, hidden noise parameters (sigma / wall-bias / loss / burst) are outside the train grid, and hidden
obstruction is time-windowed on different anchor sets. assert_disjoint() enforces this at generation time.
ALL DATA IS SIMULATED - no real BLE hardware was used.
"""
import csv, json, math, pathlib, sys
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend import sim

DATA = ROOT / 'data'
DT = 0.1
TRAIN_BASE_SEED, HIDDEN_BASE_SEED = 1000, 90000
PUBLIC_COLS = ('run_id', 'site', 't_idx', 'timestamp_s', 'anchor_id', 'anchor_x', 'anchor_y', 'range_m', 'rssi_dbm', 'packet_ok')
TRAIN_COLS = PUBLIC_COLS + ('truth_x', 'truth_y', 'true_range_m', 'nlos', 'n_walls', 'bias_m')
TRUTH_COLS = ('run_id', 't_idx', 'timestamp_s', 'truth_x', 'truth_y')

# ---- TRAIN scenarios: static obstruction sets, stock waypoint loop ----
TRAIN_CFGS = [
    dict(tag='c0', sigma=0.5, loss=0.10, wallBias=1.8, burst=0.004, obstruct=[], drift=[]),
    dict(tag='c1', sigma=0.8, loss=0.15, wallBias=2.2, burst=0.012, obstruct=['A3'], drift=[]),
    dict(tag='c2', sigma=0.6, loss=0.10, wallBias=1.8, burst=0.004, obstruct=[], drift=['A5']),
    dict(tag='c3', sigma=0.8, loss=0.10, wallBias=2.2, burst=0.008, obstruct=['A2'], drift=['A6']),
]
TRAIN_SEEDS = [1001, 1002]
TRAIN_STEPS = 800

# ---- HIDDEN scenarios: different sigma/wall-bias/loss, time-windowed obstruction on other anchor sets ----
# windows are (anchor_id, t_start_s, t_end_s)
HIDDEN_CFGS = [
    dict(tag='h0', noise='low', sigma=0.4, loss=0.05, wallBias=1.2, burst=0.002, obstruct_win=[('A1', 15, 40), ('A4', 25, 50)], drift=[], dead_win=[]),
    dict(tag='h1', noise='low', sigma=0.6, loss=0.20, wallBias=2.8, burst=0.006, obstruct_win=[('A5', 10, 45)], drift=[], dead_win=[('A6', 30, 60)]),
    dict(tag='h2', noise='mid', sigma=1.0, loss=0.10, wallBias=3.2, burst=0.010, obstruct_win=[('A2', 5, 30), ('A3', 30, 55), ('A6', 20, 40)], drift=[], dead_win=[]),
    dict(tag='h3', noise='mid', sigma=0.9, loss=0.25, wallBias=1.5, burst=0.015, obstruct_win=[('A4', 0, 60)], drift=['A1'], dead_win=[]),
    dict(tag='h4', noise='high', sigma=1.4, loss=0.30, wallBias=2.6, burst=0.020, obstruct_win=[('A3', 20, 60), ('A5', 20, 60)], drift=[], dead_win=[('A2', 10, 25)]),
    dict(tag='h5', noise='high', sigma=1.2, loss=0.15, wallBias=3.4, burst=0.012, obstruct_win=[('A1', 0, 30), ('A6', 30, 60)], drift=['A4'], dead_win=[]),
]
HIDDEN_SEEDS = [90001, 90002]
HIDDEN_STEPS = 600
HIDDEN_SPEEDS = [0.8, 1.0, 1.4, 1.6]


# ---------------------------------------------------------------- routes
def random_route(site, rng, legs=7):
    """Fresh walkable waypoint loop (different from the stock loop). Doors/gaps are respected."""
    way = [[3.0, 12.0]]
    if site.id == 'hospital':
        rooms = [(0, 10, 5, 'T'), (10, 20, 15, 'T'), (20, 30, 25, 'T'), (30, 40, 35, 'T'),
                 (0, 12, 6, 'B'), (12, 22, 17, 'B'), (22, 32, 27, 'B'), (32, 40, 36, 'B')]
        for _ in range(legs):
            x0, x1, door, side = rooms[int(rng() * len(rooms))]
            yin = 7.0 if side == 'T' else 17.0
            px = x0 + 1.5 + rng() * (x1 - x0 - 3)
            py = (1.5 + rng() * 6.0) if side == 'T' else (16.5 + rng() * 6.0)
            way += [[door, 12.0], [door, yin], [round(px, 2), round(py, 2)], [door, yin], [door, 12.0]]
    else:
        strips = [(0, 8, False), (8, 16, True), (16, 24, True), (24, 32, True), (32, 40, False)]
        for _ in range(legs):
            x0, x1, aisle = strips[int(rng() * len(strips))]
            tx = (x0 + x1) / 2
            px = x0 + 1.5 + rng() * (x1 - x0 - 3)
            py = (5.0 + rng() * 14.0) if aisle else (2.0 + rng() * 20.0)
            way += [[tx, 12.0], [round(px, 2), round(py, 2)], [tx, 12.0]]
    way.append([3.0, 12.0])
    return way


def check_walkable(site, way):
    for p, q in zip(way[:-1], way[1:]):
        assert not site.crosses_wall(np.array([p[0]]), np.array([p[1]]), np.array([q[0]]), np.array([q[1]]))[0], \
            f'route segment {p}->{q} crosses a wall on {site.id}'


# ---------------------------------------------------------------- run synthesis
def rssi_from_range(r):
    return -40.0 - 22.0 * math.log10(max(r, 0.3))


def synth_run(site_id, seed, steps, cfg_spec, hidden):
    site = sim.get_site(site_id)
    anchors = [site.anchors[i] for i in site.drop]            # measurement order = DROP_ORDER (first n = n-anchor subset)
    rng = sim.Rng(seed)
    if hidden:
        rr = sim.Rng(seed + 777)
        way = random_route(site, rr)
        speed = HIDDEN_SPEEDS[seed % len(HIDDEN_SPEEDS)]
        off = float(int(rr() * 30))
        wk = sim.Walker(site, speed, off, way=way)
    else:
        way, speed, off = site.way, 1.2, float((seed % 7) * 6)
        wk = sim.Walker(site, speed, off)
    check_walkable(site, way)
    cfg = sim.make_cfg(sigma=cfg_spec['sigma'], loss=cfg_spec['loss'], wallBias=cfg_spec['wallBias'], burst=cfg_spec['burst'],
                       drift=cfg_spec.get('drift', []), obstruct=cfg_spec.get('obstruct', []))
    rows, truth = [], []
    for s in range(steps):
        t = s * DT
        if hidden:
            cfg.obstruct = {a for a, t0, t1 in cfg_spec['obstruct_win'] if t0 <= t < t1}
            cfg.dead = {a for a, t0, t1 in cfg_spec['dead_win'] if t0 <= t < t1}
        pos = list(wk.step(DT))
        ms = sim.measure(site, pos, anchors, cfg, rng)
        truth.append((s, round(t, 3), pos[0], pos[1]))
        for a, m in zip(anchors, ms):
            row = dict(site=site_id, t_idx=s, timestamp_s=round(t, 3), anchor_id=a['id'], anchor_x=a['x'], anchor_y=a['y'],
                       range_m='' if m is None else round(m['r'], 4), rssi_dbm='' if m is None else round(rssi_from_range(m['r']), 3),
                       packet_ok=0 if m is None else 1, truth_x=round(pos[0], 4), truth_y=round(pos[1], 4),
                       true_range_m=round(math.hypot(pos[0] - a['x'], pos[1] - a['y']), 4),
                       nlos='' if m is None else int(m['nlos']), n_walls='' if m is None else m['walls'],
                       bias_m='' if m is None else round(m['bias'], 4))
            rows.append(row)
    meta = dict(site=site_id, seed=seed, steps=steps, dt=DT, speed=speed, offset=off, n_waypoints=len(way),
                cfg={k: v for k, v in cfg_spec.items() if k != 'tag'}, hidden=hidden)
    return rows, truth, meta


def assert_disjoint():
    assert not set(TRAIN_SEEDS) & set(HIDDEN_SEEDS), 'train/hidden seeds overlap'
    train_noise = {(c['sigma'], c['wallBias'], c['loss']) for c in TRAIN_CFGS}
    for c in HIDDEN_CFGS:
        assert (c['sigma'], c['wallBias'], c['loss']) not in train_noise
        assert c['sigma'] not in {t['sigma'] for t in TRAIN_CFGS} or c['wallBias'] not in {t['wallBias'] for t in TRAIN_CFGS}, \
            f"hidden {c['tag']} noise point sits on the train grid"
    train_obs = {tuple(sorted(c['obstruct'])) for c in TRAIN_CFGS}
    for c in HIDDEN_CFGS:
        assert tuple(sorted({a for a, _, _ in c['obstruct_win']})) not in train_obs, 'hidden obstruction set equals a train set'


def main():
    DATA.mkdir(exist_ok=True)
    assert_disjoint()
    train_meta, hid_meta = {}, {}
    n_tr = n_hid = 0
    with open(DATA / 'train.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=TRAIN_COLS)
        w.writeheader()
        for site_id in ('hospital', 'warehouse'):
            for c in TRAIN_CFGS:
                for sd in TRAIN_SEEDS:
                    seed = sd + (0 if site_id == 'hospital' else 100)
                    rid = f"TR-{site_id}-s{seed}-{c['tag']}"
                    rows, _, meta = synth_run(site_id, seed, TRAIN_STEPS, c, False)
                    for r in rows:
                        w.writerow({'run_id': rid, **r})
                    n_tr += len(rows)
                    train_meta[rid] = meta
    with open(DATA / 'hidden_public.csv', 'w', newline='') as fp, open(DATA / 'hidden_truth.csv', 'w', newline='') as ft:
        wp = csv.DictWriter(fp, fieldnames=PUBLIC_COLS, extrasaction='ignore')
        wt = csv.writer(ft)
        wp.writeheader()
        wt.writerow(TRUTH_COLS)
        for site_id in ('hospital', 'warehouse'):
            for c in HIDDEN_CFGS:
                for sd in HIDDEN_SEEDS:
                    seed = sd + 1000 * HIDDEN_CFGS.index(c) + (0 if site_id == 'hospital' else 100)
                    rid = f"HT-{site_id}-s{seed}-{c['tag']}"
                    rows, truth, meta = synth_run(site_id, seed, HIDDEN_STEPS, c, True)
                    meta['noise_level'] = c['noise']
                    for r in rows:
                        wp.writerow({'run_id': rid, **r})
                    for s, t, x, y in truth:
                        wt.writerow([rid, s, t, round(x, 4), round(y, 4)])
                    n_hid += len(rows)
                    hid_meta[rid] = meta
    all_hid = {m['seed'] for m in hid_meta.values()}
    all_tr = {m['seed'] for m in train_meta.values()}
    assert not all_hid & all_tr, 'run seeds overlap between train and hidden'
    (DATA / 'train_meta.json').write_text(json.dumps(train_meta, indent=1))
    (DATA / 'hidden_private_meta.json').write_text(json.dumps(hid_meta, indent=1))
    print(f'train.csv: {len(train_meta)} runs, {n_tr} rows | hidden_public.csv: {len(hid_meta)} runs, {n_hid} rows (+hidden_truth.csv)')
    print('train and hidden seeds are disjoint:', sorted(all_tr), 'vs', sorted(all_hid))


if __name__ == '__main__':
    main()
