"""Smoke test for the running backend:  python -m backend  (other terminal)  then  python scripts/test_backend.py [http://localhost:8000]"""
import asyncio, json, sys, urllib.request, time
import websockets

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8000'


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
        return json.loads(raw) if r.headers.get('content-type', '').startswith('application/json') else raw.decode()


async def main():
    ok = lambda name, cond: print(('PASS ' if cond else 'FAIL ') + name) or cond
    res = []
    res.append(ok('health', call('GET', '/api/health')['ok']))
    async with websockets.connect(BASE.replace('http', 'ws') + '/ws') as ws:
        hello = json.loads(await ws.recv())
        res.append(ok('ws hello + floorplan', hello['type'] == 'hello' and len(hello['floorplan']['walls']) > 10))
        frames = []
        t0 = time.time()
        while len(frames) < 20:
            m = json.loads(await ws.recv())
            if m['type'] == 'frame':
                frames.append(m)
        hz = len(frames) / (time.time() - t0)
        f = frames[-1]
        res.append(ok(f'frames stream (~{hz:.1f} Hz)', 8 <= hz <= 21))
        res.append(ok('frame has est/ellipse/rooms/anchors+reasons', f['est'] and f['ell'] and f['rooms'] and len(f['anchors']) == 6 and all(a['reason'] for a in f['anchors'])))
        # control from "dashboard" is seen by every client (shared session)
        async with websockets.connect(BASE.replace('http', 'ws') + '/ws') as ws2:
            await ws2.recv()
            await ws.send(json.dumps({'type': 'control', 'toggle': {'kind': 'dead', 'id': 'A3'}}))
            seen = False
            for _ in range(60):
                m = json.loads(await ws2.recv())
                if m['type'] == 'frame' and 'A3' in m['ctl']['dead']:
                    seen = True
                    break
            res.append(ok('control from client 1 visible to client 2', seen))
        await ws.send(json.dumps({'type': 'control', 'dead': []}))
    sid = call('POST', '/api/sessions/start?name=smoke')['id']
    await asyncio.sleep(0)
    async with websockets.connect(BASE.replace('http', 'ws') + '/ws') as ws:
        n = 0
        while n < 45:
            n += json.loads(await ws.recv())['type'] == 'frame'
    stop = call('POST', '/api/sessions/stop')
    res.append(ok(f'recording stored {stop["frames"]} frames', stop['frames'] >= 30))
    fr = call('GET', f'/api/sessions/{sid}/frames?start=5&limit=10')
    res.append(ok('replay frames in order', len(fr) == 10 and all(a['t'] < b['t'] for a, b in zip(fr, fr[1:]))))
    csv_txt = call('GET', f'/api/sessions/{sid}/export?format=csv')
    res.append(ok('csv export', csv_txt.startswith('run_id,site,t_idx') and csv_txt.count('\n') > 100))
    res.append(ok('json export', len(call('GET', f'/api/sessions/{sid}/export?format=json')['frames']) == stop['frames']))
    plan = call('GET', '/api/floorplan')
    res.append(ok('anchor add', any(a['id'] == 'A7' for a in call('POST', '/api/anchors', {'id': 'A7', 'x': 20, 'y': 20}))))
    res.append(ok('anchor edit', any(a['id'] == 'A7' and a['x'] == 21 for a in call('PUT', '/api/anchors/A7', {'x': 21}))))
    res.append(ok('anchor delete', all(a['id'] != 'A7' for a in call('DELETE', '/api/anchors/A7'))))
    call('DELETE', '/api/floorplan')
    res.append(ok('floorplan upload', call('POST', '/api/floorplan?name=t', plan)['id'] == 'custom'))
    call('DELETE', '/api/floorplan')
    res.append(ok('assets', len(call('GET', '/api/assets')['items']) == 6))
    # real-reading ingest takes over the engine, then falls back to sim
    async with websockets.connect(BASE.replace('http', 'ws') + '/ws') as ws:
        await ws.recv()
        call('POST', '/api/ingest', {'readings': [{'anchor_id': a, 'rssi': -60} for a in ('A1', 'A2', 'A3', 'A4', 'A5', 'A6')]})
        modes = set()
        for _ in range(60):   # skip frames already queued before the POST landed
            m = json.loads(await ws.recv())
            if m['type'] == 'frame':
                modes.add(m['mode'])
                if m['mode'] == 'live':
                    break
    res.append(ok('ingest switches engine to live mode', 'live' in modes))
    b = call('GET', '/api/benchmark')
    res.append(ok('benchmark results served', len(b['results']) > 20))
    print(f'\n{sum(res)}/{len(res)} passed')
    return 0 if all(res) else 1


sys.exit(asyncio.run(main()))
