"""Python (NumPy) port of the LOCUS simulator in src/engine.js.

Bit-exact where it matters: the mulberry32 RNG stream, Walker, measure() call order and
wall geometry are ported line-for-line so the same seed gives the same anchors, trajectory and
range readings as the JS version (verified by scripts/validate_port.py).
All data here is SIMULATED - nothing in this module is calibrated against real hardware.
"""
import math
from types import SimpleNamespace
import numpy as np

FLOOR_W, FLOOR_H = 40.0, 24.0
TOP_DOORS = [5, 15, 25, 35]
BOT_DOORS = [6, 17, 27, 36]
DOOR_HALF = 1.2
M32 = 0xFFFFFFFF
_C = 0x6D2B79F5


# ---------------------------------------------------------------- RNG (mulberry32 + Box-Muller)
class Rng:
    """Same stream as rngMake() in engine.js. Scalar calls and vectorised block draws share state."""

    def __init__(self, seed):
        self.a = int(seed) & M32
        self.burst = {}  # JS keeps burst state on rng._b

    def __call__(self):
        self.a = (self.a + _C) & M32
        a = self.a
        t = ((a ^ (a >> 15)) * (1 | a)) & M32
        t = (((t + (((t ^ (t >> 7)) * (61 | t)) & M32)) & M32) ^ t) & M32
        return ((t ^ (t >> 14)) & M32) / 4294967296.0

    def g(self):
        u = 0.0
        while not u:
            u = self()
        v = self()
        return math.sqrt(-2 * math.log(u)) * math.cos(2 * math.pi * v)

    def uniform_n(self, n):
        """n consecutive uniforms; the stream is a counter hash so it vectorises exactly."""
        a = (np.uint64(self.a) + np.uint64(_C) * np.arange(1, n + 1, dtype=np.uint64)) & np.uint64(M32)
        a = a.astype(np.uint32)
        self.a = int(a[-1]) if n else self.a
        with np.errstate(over='ignore'):
            t = (a ^ (a >> np.uint32(15))) * (a | np.uint32(1))
            t = ((t + (t ^ (t >> np.uint32(7))) * (t | np.uint32(61))) ^ t)
            out = (t ^ (t >> np.uint32(14))).astype(np.float64) / 4294967296.0
        return out

    def g_n(self, n):
        """n normals, identical to n sequential g() calls (assuming no u==0 redraw, p=2^-32)."""
        r = self.uniform_n(2 * n).reshape(n, 2)
        u = np.where(r[:, 0] == 0, 1e-300, r[:, 0])
        return np.sqrt(-2 * np.log(u)) * np.cos(2 * np.pi * r[:, 1])


# ---------------------------------------------------------------- geometry
def seg_int(ax, ay, bx, by, cx, cy, dx, dy):
    """Vectorised segInt(): does segment AB properly cross segment CD (broadcasting)."""
    d1x, d1y, d2x, d2y = bx - ax, by - ay, dx - cx, dy - cy
    den = d1x * d2y - d1y * d2x
    ok = np.abs(den) >= 1e-12
    with np.errstate(divide='ignore', invalid='ignore'):
        t = ((cx - ax) * d2y - (cy - ay) * d2x) / den
        u = ((cx - ax) * d1y - (cy - ay) * d1x) / den
    return ok & (t > 1e-6) & (t < 1 - 1e-6) & (u >= 0) & (u <= 1)


class Site:
    def __init__(self, id, rooms, walls, anchors, drop, way, fallback):
        self.id, self.rooms, self.anchors, self.drop, self.way, self.fallback = id, rooms, anchors, drop, way, fallback
        self.walls = np.array(walls, dtype=np.float64)
        self._k = {}

    def room_at(self, x, y):
        for r in self.rooms:
            a, b, c, d = r['r']
            if a <= x < c and b <= y < d:
                return r['id']
        return self.fallback

    def room_ids_at(self, x, y):
        """Vectorised room_at -> array of room indices into self.rooms (len(rooms) == fallback)."""
        idx = np.full(np.shape(x), -1, dtype=np.int64)
        for k in range(len(self.rooms) - 1, -1, -1):  # first match wins, so assign in reverse
            a, b, c, d = self.rooms[k]['r']
            idx[(x >= a) & (x < c) & (y >= b) & (y < d)] = k
        fb = [r['id'] for r in self.rooms].index(self.fallback)
        idx[idx < 0] = fb
        return idx

    def room_name(self, rid):
        return next(r['name'] for r in self.rooms if r['id'] == rid)

    def walls_between(self, ax, ay, bx, by):
        w = self.walls
        return int(seg_int(ax, ay, bx, by, w[:, 0], w[:, 1], w[:, 2], w[:, 3]).sum())

    def crosses_wall(self, ax, ay, bx, by):
        """Vectorised over points: ax..by arrays of shape (P,) -> bool (P,)."""
        w = self.walls
        ax, ay, bx, by = (np.asarray(v, dtype=np.float64)[:, None] for v in (ax, ay, bx, by))
        return seg_int(ax, ay, bx, by, w[None, :, 0], w[None, :, 1], w[None, :, 2], w[None, :, 3]).any(axis=1)

    def k_grid(self, a):
        """Wall count between anchor a and each 0.5 m cell centre (kGrid in engine.js)."""
        key = (a['id'], a['x'], a['y'])
        if key in self._k:
            return self._k[key]
        W, H = int(FLOOR_W * 2), int(FLOOR_H * 2)
        ii, jj = np.meshgrid(np.arange(W), np.arange(H))
        cx, cy = ((ii + 0.5) / 2).ravel()[:, None], ((jj + 0.5) / 2).ravel()[:, None]
        w = self.walls
        g = seg_int(a['x'], a['y'], cx, cy, w[None, :, 0], w[None, :, 1], w[None, :, 2], w[None, :, 3]).sum(axis=1)
        self._k[key] = g.astype(np.uint8)
        return self._k[key]

    @staticmethod
    def k_at(g, x, y):
        W, H = int(FLOOR_W * 2), int(FLOOR_H * 2)
        i = np.minimum(W - 1, np.maximum(0, np.trunc(np.asarray(x) * 2))).astype(np.int64)
        j = np.minimum(H - 1, np.maximum(0, np.trunc(np.asarray(y) * 2))).astype(np.int64)
        return g[j * W + i]


def _boundary():
    return [[0, 0, FLOOR_W, 0], [0, FLOOR_H, FLOOR_W, FLOOR_H], [0, 0, 0, FLOOR_H], [FLOOR_W, 0, FLOOR_W, FLOOR_H]]


def hospital_site():
    rooms = [
        {'id': 'wardA', 'name': 'Ward A', 'r': [0, 0, 10, 9]}, {'id': 'wardB', 'name': 'Ward B', 'r': [10, 0, 20, 9]},
        {'id': 'icu', 'name': 'ICU', 'r': [20, 0, 30, 9]}, {'id': 'pharm', 'name': 'Pharmacy', 'r': [30, 0, 40, 9]},
        {'id': 'corr', 'name': 'Corridor', 'r': [0, 9, 40, 15]},
        {'id': 'recep', 'name': 'Reception', 'r': [0, 15, 12, 24]}, {'id': 'store', 'name': 'Store', 'r': [12, 15, 22, 24]},
        {'id': 'radio', 'name': 'Radiology', 'r': [22, 15, 32, 24]}, {'id': 'ot', 'name': 'OT', 'r': [32, 15, 40, 24]},
    ]
    W = []

    def hseg(y, doors):
        c = 0.0
        for d in doors:
            W.append([c, y, d - DOOR_HALF, y])
            c = d + DOOR_HALF
        W.append([c, y, FLOOR_W, y])
    hseg(9, TOP_DOORS)
    hseg(15, BOT_DOORS)
    for x in (10, 20, 30):
        W.append([x, 0, x, 9])
    for x in (12, 22, 32):
        W.append([x, 15, x, 24])
    W += _boundary()
    return Site('hospital', rooms, W,
                [{'id': 'A1', 'x': 1.5, 'y': 13.5}, {'id': 'A2', 'x': 15, 'y': 1.5}, {'id': 'A3', 'x': 25, 'y': 10.5},
                 {'id': 'A4', 'x': 38.5, 'y': 13.5}, {'id': 'A5', 'x': 28, 'y': 22.5}, {'id': 'A6', 'x': 7, 'y': 22.5}],
                [2, 5, 1, 3, 0, 4],
                [[3, 12], [15, 12], [15, 4], [15, 12], [25, 12], [25, 4], [25, 12], [36, 12], [36, 19.5], [36, 12],
                 [27, 12], [27, 19.5], [27, 12], [6, 12], [6, 19.5], [6, 12]], 'corr')


def warehouse_site():
    rooms = [{'id': 'recv', 'name': 'Receiving', 'r': [0, 0, 8, 24]}, {'id': 'aisA', 'name': 'Aisle A', 'r': [8, 0, 16, 24]},
             {'id': 'aisB', 'name': 'Aisle B', 'r': [16, 0, 24, 24]}, {'id': 'aisC', 'name': 'Aisle C', 'r': [24, 0, 32, 24]},
             {'id': 'disp', 'name': 'Dispatch', 'r': [32, 0, 40, 24]}]
    W = []
    for x in (8, 16, 24, 32):
        W += [[x, 0, x, 10.5], [x, 13.5, x, 24]]
    for x in (12, 20, 28):
        W += [[x - 1.8, 4, x + 1.8, 4], [x - 1.8, 20, x + 1.8, 20]]
    W += _boundary()
    return Site('warehouse', rooms, W,
                [{'id': 'A1', 'x': 1.5, 'y': 21}, {'id': 'A2', 'x': 12, 'y': 1.5}, {'id': 'A3', 'x': 20, 'y': 12},
                 {'id': 'A4', 'x': 28, 'y': 22.5}, {'id': 'A5', 'x': 38.5, 'y': 3}, {'id': 'A6', 'x': 38.5, 'y': 21}],
                [2, 5, 1, 3, 0, 4],
                [[3, 12], [12, 12], [12, 7], [12, 17], [12, 12], [20, 12], [20, 7], [20, 17], [20, 12], [28, 12], [28, 7],
                 [28, 17], [28, 12], [36, 12], [36, 5], [36, 19], [36, 12]], 'recv')


SITES = {'hospital': hospital_site, 'warehouse': warehouse_site}


def get_site(id):
    return SITES[id]()


def site_from_json(d):
    """Build a Site from an uploaded floor-plan JSON: {id?, rooms:[{id,name,r}], walls:[[x1,y1,x2,y2]],
    anchors:[{id,x,y}], drop?:[..], way?:[[x,y]..], fallback?}"""
    rooms = d['rooms']
    anchors = d['anchors']
    return Site(d.get('id', 'custom'), rooms, d['walls'], anchors, d.get('drop', list(range(len(anchors)))),
                d.get('way', [[FLOOR_W / 2, FLOOR_H / 2]]), d.get('fallback', rooms[0]['id']))


def site_to_json(s):
    return {'id': s.id, 'rooms': s.rooms, 'walls': s.walls.tolist(), 'anchors': s.anchors, 'drop': s.drop,
            'way': s.way, 'fallback': s.fallback}


# ---------------------------------------------------------------- walker + radio
class Walker:
    def __init__(self, site, speed=1.2, offset=0.0, way=None):
        self.way = way if way is not None else site.way
        self.i = 0
        self.pos = list(map(float, self.way[0]))
        self.speed = speed
        self.vel = [0.0, 0.0]
        if offset:
            self.advance(offset)

    def advance(self, dist):
        n = len(self.way)
        while dist > 0:
            t = self.way[(self.i + 1) % n]
            dx, dy = t[0] - self.pos[0], t[1] - self.pos[1]
            d = math.hypot(dx, dy)
            if d <= dist:
                self.pos = [float(t[0]), float(t[1])]
                self.i = (self.i + 1) % n
                dist -= d
            else:
                self.pos[0] += dx / d * dist
                self.pos[1] += dy / d * dist
                dist = 0

    def step(self, dt):
        o = list(self.pos)
        self.advance(self.speed * dt)
        self.vel = [(self.pos[0] - o[0]) / dt, (self.pos[1] - o[1]) / dt]
        return self.pos


def make_cfg(sigma=0.6, loss=0.10, wallBias=1.8, burst=0.004, obstructBias=4.0, driftBias=2.5,
             dead=(), obstruct=(), drift=(), inflate=1.0):
    return SimpleNamespace(sigma=sigma, loss=loss, wallBias=wallBias, burst=burst, obstructBias=obstructBias,
                           driftBias=driftBias, dead=set(dead), obstruct=set(obstruct), drift=set(drift), inflate=inflate)


def measure(site, pos, anchors, cfg, rng):
    """Port of measure(): returns per-anchor dict(r, nlos, bias, walls, d) or None (dead / packet lost).
    RNG call order is identical to the JS version."""
    out = []
    for a in anchors:
        if cfg.dead and a['id'] in cfg.dead:
            out.append(None)
            continue
        if rng() < cfg.loss:
            out.append(None)
            continue
        d = math.hypot(pos[0] - a['x'], pos[1] - a['y'])
        k = site.walls_between(a['x'], a['y'], pos[0], pos[1])
        bias = k * cfg.wallBias * (0.5 + rng())
        nlos = k > 0
        imp = False   # True when a non-wall impairment (obstruction / burst / drift) corrupts this reading
        if cfg.obstruct and a['id'] in cfg.obstruct:
            bias += cfg.obstructBias * (0.6 + 0.8 * rng())
            nlos = imp = True
        if cfg.burst:
            st = rng.burst
            if not st.get(a['id']) and rng() < cfg.burst:
                st[a['id']] = 20 + int(rng() * 30)
            if st.get(a['id'], 0) > 0:
                st[a['id']] -= 1
                bias += 3.2
                nlos = imp = True
        if cfg.drift and a['id'] in cfg.drift:
            bias += cfg.driftBias
            nlos = imp = True
        sigma = cfg.sigma * (1.8 if nlos else 1)
        out.append({'r': max(0.3, d + bias + sigma * rng.g()), 'nlos': nlos, 'bias': bias, 'walls': k, 'd': d, 'impaired': imp})
    return out
