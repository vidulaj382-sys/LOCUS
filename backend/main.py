"""LOCUS backend: FastAPI + WebSocket. Serves the live engine, REST API, SQLite persistence, and the built dashboard / staff app.

Run:  python -m backend            (prints LAN URLs)       |   python -m backend --https   (self-signed, needed for Web Bluetooth over LAN)
No authentication - local demo network only. All data is simulated unless real readings are POSTed to /api/ingest.

WebSocket /ws  (server -> client)
  {"type":"hello","state":{...},"floorplan":{rooms,walls,anchors,...}}          once on connect
  {"type":"state","state":{...}}                                               after any control change
  {"type":"frame", idx,t,mode:"sim"|"live",site,scorer, truth:[x,y]|null, est:[x,y], ls, kf,
      ell:{a,b,th}  (90% ellipse, semi-axes metres, rotation rad), rooms:{room_id:prob}, particles:[[x,y]..],
      anchors:[{id,x,y,trust,reason,usable,dead,r}], err:{lo,kf,ls}, ctl:{dead,obstruct,drift,n}, wallMu, ess, relocal}
(client -> server)  {"type":"control", sigma?,loss?,wallBias?,nAnch?,site?,scorer?,hz?,dead?[],obstruct?[],drift?[],toggle?{kind,id},reset?}
"""
import asyncio, csv, io, json, os, pathlib, socket, threading, time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response

from . import db, sim, bench, assets, dataset
from .live import LiveSession, rssi_to_range

ROOT = pathlib.Path(__file__).resolve().parent.parent
S = LiveSession()
CLIENTS: set = set()
LOCK = asyncio.Lock()
REC = dict(id=None, n=0, buf=[])
BENCH = dict(running=False, progress=0.0, error=None, started=None)


def lan_ips():
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))       # no packet is sent; just selects the outbound interface
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip not in ips and not ip.startswith('127.'):
                ips.append(ip)
    except Exception:
        pass
    return ips or ['127.0.0.1']


def banner():
    port, scheme = os.environ.get('LOCUS_PORT', '8000'), os.environ.get('LOCUS_SCHEME', 'http')
    ips = lan_ips()
    line = '=' * 68
    print(f'\n{line}\n  L.O.C.U.S backend is running  (SIMULATION; no real hardware)\n{line}')
    print(f'  This laptop      : {scheme}://localhost:{port}/')
    for ip in ips:
        print(f'  LAN IP           : {ip}')
    print(f'\n  >>> Open on the ANDROID PHONE (same WiFi):  {scheme}://{ips[0]}:{port}/staff')
    print(f'  >>> Dashboard (laptop or phone)           :  {scheme}://{ips[0]}:{port}/')
    if scheme == 'http':
        print('  note: Web Bluetooth needs a secure context; for the Live BLE tab start with  python -m backend --https')
    print(f'{line}\n', flush=True)


async def broadcast(msg):
    if not CLIENTS:
        return
    txt = json.dumps(msg)
    dead = []
    for ws in list(CLIENTS):
        try:
            await asyncio.wait_for(ws.send_text(txt), 1.0)
        except Exception:
            dead.append(ws)
    for ws in dead:
        CLIENTS.discard(ws)


async def sim_loop():
    loop = asyncio.get_running_loop()
    while True:
        t0 = time.time()
        if CLIENTS or REC['id'] or S.mode() == 'live':
            async with LOCK:
                frame = await loop.run_in_executor(None, S.step)
            if REC['id']:
                rec = dict(frame, particles=frame['particles'][::3])
                REC['buf'].append((REC['n'], frame['t'], rec))
                REC['n'] += 1
                if len(REC['buf']) >= 30:
                    buf, REC['buf'] = REC['buf'], []
                    await loop.run_in_executor(None, db.frames_add, REC['id'], buf)
            await broadcast(frame)
        await asyncio.sleep(max(0.0, 1.0 / S.hz - (time.time() - t0)))


@asynccontextmanager
async def lifespan(app):
    cfg = db.config_active()
    if cfg:
        try:
            S.set_custom(sim.site_from_json(cfg))
        except Exception:
            pass
    if db.bench_latest() is None and (ROOT / 'results.json').exists():
        db.bench_save(json.loads((ROOT / 'results.json').read_text()), quick=False)
    task = asyncio.create_task(sim_loop())
    banner()
    yield
    task.cancel()


app = FastAPI(title='LOCUS backend', version='0.5', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'], allow_credentials=False)


# ------------------------------------------------------------------ static apps
def _file(name):
    p = ROOT / name
    if not p.exists():
        raise HTTPException(404, f'{name} not built - run python build.py')
    return FileResponse(p, headers={'Cache-Control': 'no-cache'})


@app.get('/', include_in_schema=False)
def dashboard():
    return _file('LOCUS-Dashboard.html')


@app.get('/staff', include_in_schema=False)
def staff():
    return _file('LOCUS-Staff-App.html')


@app.get('/LOCUS-Dashboard.html', include_in_schema=False)
def dashboard_file():
    return _file('LOCUS-Dashboard.html')


@app.get('/LOCUS-Staff-App.html', include_in_schema=False)
def staff_file():
    return _file('LOCUS-Staff-App.html')


@app.get('/manifest-{which}.json', include_in_schema=False)
def manifest(which: str):
    """Same manifest as the static one used on GitHub Pages, but start_url points at the routes this server uses."""
    if which not in ('dashboard', 'staff'):
        raise HTTPException(404)
    m = json.loads((ROOT / f'manifest-{which}.json').read_text())
    m['start_url'] = '/' if which == 'dashboard' else '/staff'
    m['scope'] = '/'
    for sc in m.get('shortcuts', []):
        sc['url'] = '/staff' + sc['url'].split('.html', 1)[1]
    return JSONResponse(m, media_type='application/manifest+json')


@app.get('/sw.js', include_in_schema=False)
def sw():
    return FileResponse(ROOT / 'sw.js', media_type='text/javascript', headers={'Cache-Control': 'no-cache'})


@app.get('/icons/{name}', include_in_schema=False)
def icons(name: str):
    return _file(f'icons/{pathlib.Path(name).name}')


# ------------------------------------------------------------------ status / control
@app.get('/api/health')
def health():
    return dict(ok=True, state=S.state(), clients=len(CLIENTS), recording=REC['id'], lan=lan_ips())


@app.get('/api/state')
def get_state():
    return S.state()


@app.post('/api/control')
async def control(d: dict = Body(...)):
    async with LOCK:
        S.apply(d)
    await broadcast(dict(type='state', state=S.state()))
    return S.state()


@app.post('/api/reset')
async def reset():
    return await control({'reset': True})


@app.get('/api/stats/live')
def stats_live():
    return S.live_stats() or {}


@app.get('/api/assets')
def get_assets(site: Optional[str] = None):
    return assets.STAFF['warehouse' if (site or S.site_id) == 'warehouse' else 'hospital']


# ------------------------------------------------------------------ floor plan + anchors
def _validate_plan(d):
    try:
        site = sim.site_from_json(d)
    except Exception as e:
        raise HTTPException(422, f'invalid floor plan: {e}')
    ids = [a['id'] for a in site.anchors]
    if len(set(ids)) != len(ids):
        raise HTTPException(422, 'duplicate anchor ids')
    for a in site.anchors:
        if not (0 <= a['x'] <= sim.FLOOR_W and 0 <= a['y'] <= sim.FLOOR_H):
            raise HTTPException(422, f'anchor {a["id"]} outside the {sim.FLOOR_W:g} x {sim.FLOOR_H:g} m footprint')
    for w in d['walls']:
        if len(w) != 4:
            raise HTTPException(422, 'walls must be [x1,y1,x2,y2]')
    return site


async def _install(d, name):
    d = dict(d, id='custom')
    site = _validate_plan(d)
    async with LOCK:
        S.set_custom(site)
    db.config_save(name, sim.site_to_json(site), active=True)
    await broadcast(dict(type='hello', state=S.state(), floorplan=sim.site_to_json(S.site)))
    return sim.site_to_json(site)


@app.get('/api/floorplan')
def get_floorplan():
    return sim.site_to_json(S.site)


@app.post('/api/floorplan')
async def upload_floorplan(d: dict = Body(...), name: str = 'upload'):
    """JSON: {rooms:[{id,name,r:[x0,y0,x1,y1]}], walls:[[x1,y1,x2,y2]], anchors:[{id,x,y}], way?:[[x,y]], fallback?: room_id}. Must fit 40 x 24 m."""
    return await _install(d, name)


@app.delete('/api/floorplan')
async def delete_floorplan():
    async with LOCK:
        S.clear_custom()
    db.config_clear_active()
    await broadcast(dict(type='hello', state=S.state(), floorplan=sim.site_to_json(S.site)))
    return S.state()


@app.get('/api/anchors')
def list_anchors():
    return S.site.anchors


def _plan_with(anchors):
    d = sim.site_to_json(S.site)
    d['anchors'], d['drop'], d['id'] = anchors, list(range(len(anchors))), 'custom'
    return d


@app.post('/api/anchors')
async def add_anchor(a: dict = Body(...)):
    cur = [dict(x) for x in S.site.anchors]
    if any(x['id'] == a.get('id') for x in cur):
        raise HTTPException(409, 'anchor id exists')
    cur.append(dict(id=a['id'], x=float(a['x']), y=float(a['y'])))
    await _install(_plan_with(cur), 'anchor-edit')
    return S.site.anchors


@app.put('/api/anchors/{aid}')
async def edit_anchor(aid: str, a: dict = Body(...)):
    cur = [dict(x) for x in S.site.anchors]
    for x in cur:
        if x['id'] == aid:
            x['x'], x['y'] = float(a.get('x', x['x'])), float(a.get('y', x['y']))
            break
    else:
        raise HTTPException(404, 'no such anchor')
    await _install(_plan_with(cur), 'anchor-edit')
    return S.site.anchors


@app.delete('/api/anchors/{aid}')
async def del_anchor(aid: str):
    cur = [x for x in S.site.anchors if x['id'] != aid]
    if len(cur) == len(S.site.anchors):
        raise HTTPException(404, 'no such anchor')
    if not cur:
        raise HTTPException(422, 'need at least one anchor')
    await _install(_plan_with(cur), 'anchor-edit')
    return S.site.anchors


@app.get('/api/configs')
def configs():
    return db.configs_list()


# ------------------------------------------------------------------ real-reading ingest (same engine boundary as simulated readings)
@app.post('/api/ingest')
def ingest(d: dict = Body(...)):
    """{anchor_id, rssi (dBm) [or range_m], timestamp?}  or  {readings:[{...}, ...]}. While readings keep arriving the live engine
    uses them instead of the simulator (mode 'live')."""
    items = d.get('readings', [d])
    n = 0
    for r in items:
        try:
            S.ingest(r['anchor_id'], rssi=r.get('rssi'), range_m=r.get('range_m'))
            n += 1
        except KeyError as e:
            raise HTTPException(404, f'unknown anchor {e}')
        except (TypeError, ValueError):
            raise HTTPException(422, 'need numeric rssi or range_m')
    return dict(accepted=n, mode='live', range_m=rssi_to_range(items[-1]['rssi']) if 'rssi' in items[-1] else items[-1].get('range_m'))


# ------------------------------------------------------------------ sessions: record / replay / export
@app.post('/api/sessions/start')
async def rec_start(name: str = 'session'):
    if REC['id']:
        raise HTTPException(409, f'already recording session {REC["id"]}')
    sid = db.session_create(name, S.site_id, dict(state=S.state()))
    REC.update(id=sid, n=0, buf=[])
    return dict(id=sid)


@app.post('/api/sessions/stop')
async def rec_stop():
    if not REC['id']:
        raise HTTPException(409, 'not recording')
    sid, buf, n = REC['id'], REC['buf'], REC['n']
    REC.update(id=None, buf=[])
    if buf:
        db.frames_add(sid, buf)
    db.session_end(sid, n)
    return dict(id=sid, frames=n)


@app.get('/api/sessions')
def sessions():
    return db.sessions_list()


@app.get('/api/sessions/{sid}/frames')
def session_frames(sid: int, start: int = 0, limit: int = 2000):
    if not db.session_get(sid):
        raise HTTPException(404)
    return db.frames_get(sid, start, min(limit, 20000))


@app.websocket('/ws/replay/{sid}')
async def ws_replay(ws: WebSocket, sid: int, speed: float = 1.0, start: int = 0):
    """Streams recorded frames in order at recorded timing. Client may send {"seek": idx} or {"speed": x}."""
    await ws.accept()
    frames = db.frames_get(sid, 0, 200000)
    i = start
    try:
        while i < len(frames):
            try:
                m = json.loads(await asyncio.wait_for(ws.receive_text(), 0.001))
                i, speed = int(m.get('seek', i)), float(m.get('speed', speed))
            except asyncio.TimeoutError:
                pass
            await ws.send_text(json.dumps(dict(frames[i], type='frame', replay=True, total=len(frames), pos=i)))
            dt = (frames[i + 1]['t'] - frames[i]['t']) if i + 1 < len(frames) else 0.1
            i += 1
            await asyncio.sleep(max(0.005, dt / max(speed, 0.05)))
        await ws.send_text(json.dumps(dict(type='replay_end')))
    except (WebSocketDisconnect, RuntimeError):
        pass


@app.get('/api/sessions/{sid}/export')
def session_export(sid: int, format: str = Query('csv', pattern='^(csv|json)$')):
    """Dataset export. CSV is long format (one row per frame x anchor) using the same column names as data/train.csv, plus the engine outputs."""
    sess = db.session_get(sid)
    if not sess:
        raise HTTPException(404)
    frames = db.frames_get(sid, 0, 500000)
    if format == 'json':
        return Response(json.dumps(dict(session=sess, frames=frames)), media_type='application/json',
                        headers={'Content-Disposition': f'attachment; filename=locus-session-{sid}.json'})
    buf = io.StringIO()
    cols = ['run_id', 'site', 't_idx', 'timestamp_s', 'anchor_id', 'anchor_x', 'anchor_y', 'range_m', 'rssi_dbm', 'packet_ok', 'truth_x', 'truth_y',
            'est_x', 'est_y', 'err_m', 'trust', 'reason', 'mode']
    w = csv.writer(buf)
    w.writerow(cols)
    import math
    for k, f in enumerate(frames):
        for a in f.get('anchors', []):
            r = a['r']
            w.writerow([f'SESSION-{sid}', f['site'], k, f['t'], a['id'], a['x'], a['y'], '' if r is None else r,
                        '' if r is None else round(-40 - 22 * math.log10(max(r, .3)), 3), int(r is not None),
                        *(f['truth'] or ['', '']), *(f['est'] or ['', '']), '' if f['err']['lo'] is None else round(f['err']['lo'], 4),
                        a['trust'], a['reason'], f['mode']])
    return Response(buf.getvalue(), media_type='text/csv', headers={'Content-Disposition': f'attachment; filename=locus-session-{sid}.csv'})


# ------------------------------------------------------------------ benchmark
def _bench_job(quick):
    try:
        kw = dict(max_steps=200, run_filter=lambda rid, m: rid.endswith('1')) if quick else {}
        res = bench.run_benchmark(progress=lambda f: BENCH.update(progress=f), **kw)
        res['quick'] = quick
        db.bench_save(res, quick)
        if not quick:
            (ROOT / 'results.json').write_text(json.dumps(res, indent=1))
    except Exception as e:
        BENCH['error'] = repr(e)
    finally:
        BENCH['running'] = False


@app.post('/api/benchmark')
def bench_run(quick: bool = True):
    """Runs the Phase-4 benchmark on the hidden set in the background (quick: ~half the runs, 200 steps; full: ~10+ min)."""
    if BENCH['running']:
        raise HTTPException(409, 'benchmark already running')
    BENCH.update(running=True, progress=0.0, error=None, started=time.time())
    threading.Thread(target=_bench_job, args=(quick,), daemon=True).start()
    return dict(started=True, quick=quick)


@app.get('/api/benchmark/status')
def bench_status():
    return BENCH


@app.get('/api/benchmark')
def bench_results():
    r = db.bench_latest()
    if not r:
        raise HTTPException(404, 'no benchmark yet - POST /api/benchmark or run scripts/run_benchmark.py')
    return r


@app.get('/api/dataset/{name}')
def dataset_file(name: str):
    """Public hidden input / train CSVs (hidden ground truth is deliberately not served)."""
    if name not in ('train.csv', 'hidden_public.csv'):
        raise HTTPException(404)
    return FileResponse(dataset.DATA / name, media_type='text/csv')


# ------------------------------------------------------------------ live websocket
@app.websocket('/ws')
async def ws_live(ws: WebSocket):
    await ws.accept()
    CLIENTS.add(ws)
    try:
        await ws.send_text(json.dumps(dict(type='hello', state=S.state(), floorplan=sim.site_to_json(S.site))))
        while True:
            m = json.loads(await ws.receive_text())
            if m.get('type') == 'control':
                async with LOCK:
                    S.apply(m)
                await broadcast(dict(type='state', state=S.state()))
            elif m.get('type') == 'ping':
                await ws.send_text(json.dumps(dict(type='pong', t=m.get('t'))))
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        CLIENTS.discard(ws)
