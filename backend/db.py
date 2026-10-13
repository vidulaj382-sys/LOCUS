"""SQLite persistence: sessions, recorded frames, anchor/floor-plan configs, benchmark metrics."""
import json, pathlib, sqlite3, threading, time

PATH = pathlib.Path(__file__).resolve().parent / 'locus.db'
_lock = threading.Lock()
_conn = None
SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, site TEXT, started REAL, ended REAL, n_frames INTEGER DEFAULT 0, meta TEXT);
CREATE TABLE IF NOT EXISTS frames(session_id INTEGER, idx INTEGER, t REAL, data TEXT, PRIMARY KEY(session_id, idx));
CREATE TABLE IF NOT EXISTS anchor_configs(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, created REAL, active INTEGER DEFAULT 0, data TEXT);
CREATE TABLE IF NOT EXISTS benchmarks(id INTEGER PRIMARY KEY AUTOINCREMENT, created REAL, quick INTEGER, data TEXT);
"""


def conn():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
    return _conn


def q(sql, args=(), commit=False):
    with _lock:
        cur = conn().execute(sql, args)
        rows = cur.fetchall()
        if commit:
            conn().commit()
        return rows, cur.lastrowid


# ---- sessions / frames
def session_create(name, site, meta):
    return q('INSERT INTO sessions(name,site,started,meta) VALUES(?,?,?,?)', (name, site, time.time(), json.dumps(meta)), True)[1]


def frames_add(sid, items):
    with _lock:
        conn().executemany('INSERT OR REPLACE INTO frames(session_id,idx,t,data) VALUES(?,?,?,?)', [(sid, i, t, json.dumps(d)) for i, t, d in items])
        conn().commit()


def session_end(sid, n):
    q('UPDATE sessions SET ended=?, n_frames=? WHERE id=?', (time.time(), n, sid), True)


def sessions_list():
    return [dict(r) for r in q('SELECT id,name,site,started,ended,n_frames FROM sessions ORDER BY id DESC')[0]]


def session_get(sid):
    r = q('SELECT * FROM sessions WHERE id=?', (sid,))[0]
    return dict(r[0]) if r else None


def frames_get(sid, start=0, limit=100000):
    return [json.loads(r['data']) for r in q('SELECT data FROM frames WHERE session_id=? AND idx>=? ORDER BY idx LIMIT ?', (sid, start, limit))[0]]


# ---- configs
def config_save(name, data, active=False):
    if active:
        q('UPDATE anchor_configs SET active=0', (), True)
    return q('INSERT INTO anchor_configs(name,created,active,data) VALUES(?,?,?,?)', (name, time.time(), int(active), json.dumps(data)), True)[1]


def config_active():
    r = q('SELECT data FROM anchor_configs WHERE active=1 ORDER BY id DESC LIMIT 1')[0]
    return json.loads(r[0]['data']) if r else None


def config_clear_active():
    q('UPDATE anchor_configs SET active=0', (), True)


def configs_list():
    return [dict(r) for r in q('SELECT id,name,created,active FROM anchor_configs ORDER BY id DESC')[0]]


# ---- benchmarks
def bench_save(data, quick):
    return q('INSERT INTO benchmarks(created,quick,data) VALUES(?,?,?)', (time.time(), int(quick), json.dumps(data)), True)[1]


def bench_latest(prefer_full=True):
    r = q('SELECT data FROM benchmarks ORDER BY quick ASC, id DESC LIMIT 1' if prefer_full else 'SELECT data FROM benchmarks ORDER BY id DESC LIMIT 1')[0]
    return json.loads(r[0]['data']) if r else None
