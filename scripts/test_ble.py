"""Phase 8 test with a MOCKED navigator.bluetooth (real Web Bluetooth needs a phone + beacons, which don't exist yet).
Needs the backend running on localhost:8000.   python scripts/test_ble.py"""
import json, sys, urllib.request
from playwright.sync_api import sync_playwright

BASE = 'http://localhost:8000'
res = []


def ok(n, c, x=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (f'  [{x}]' if x else ''))


def api(path):
    return json.loads(urllib.request.urlopen(BASE + path, timeout=10).read())


MOCK = """
(() => {
  const bt = new EventTarget(); let scanning = false;
  bt.requestLEScan = async () => { scanning = true; return { active: true, stop() { this.active = false; scanning = false; } }; };
  bt.requestDevice = async () => { throw Object.assign(new Error('cancelled'), { name: 'NotFoundError' }); };
  Object.defineProperty(navigator, 'bluetooth', { value: bt, configurable: true });
  window.__adv = (id, name, rssi) => { const e = new Event('advertisementreceived'); e.device = { id, name }; e.rssi = rssi; bt.dispatchEvent(e); };
  window.__scanning = () => scanning;
})();
"""

with sync_playwright() as p:
    b = p.chromium.launch(channel='chrome', headless=True)
    # --- gating messages
    for label, init, ua, want in (
        ('no Web Bluetooth (desktop Firefox-like)', "delete Navigator.prototype.bluetooth; Object.defineProperty(navigator,'bluetooth',{value:undefined})", None, 'Live BLE needs Chrome'),
        ('iPhone', "Object.defineProperty(navigator,'bluetooth',{value:undefined})", 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1', 'iPhone'),
        ('Chrome without requestLEScan flag', "Object.defineProperty(navigator,'bluetooth',{value:new EventTarget(),configurable:true})", None, 'chrome://flags/#enable-experimental-web-platform-features')):
        ctx = b.new_context(**({'user_agent': ua} if ua else {}), viewport={'width': 430, 'height': 900})
        pg = ctx.new_page(); pg.add_init_script(init); pg.goto(BASE + '/staff'); pg.wait_for_timeout(1500)
        pg.click('.tabbar button[data-v="ble"]'); pg.wait_for_timeout(500)
        msg = pg.inner_text('#ble-msg')
        ok(f'message when {label}', want in msg, msg[:110]); ctx.close()
    # --- mocked scan -> pair -> ingest -> live engine
    before = api('/api/ingest/status')['total']
    ctx = b.new_context(viewport={'width': 430, 'height': 900}); pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e))); pg.add_init_script(MOCK); pg.goto(BASE + '/staff'); pg.wait_for_timeout(2000)
    pg.click('.tabbar button[data-v="ble"]'); pg.wait_for_timeout(500)
    ok('BLE switch is OFF by default and scan disabled', pg.get_attribute('#ble-sw', 'aria-pressed') == 'false' and pg.is_disabled('#ble-scan'))
    pg.evaluate("setInterval(()=>{__adv('devA','Beacon-A',-58);__adv('devB','Beacon-B',-66);__adv('devC','Beacon-C',-71)},100)")
    pg.wait_for_timeout(800)
    ok('nothing forwarded while OFF', api('/api/ingest/status')['total'] == before)
    pg.click('#ble-sw'); pg.wait_for_timeout(300)
    ok('scan enabled after switch ON', not pg.is_disabled('#ble-scan'))
    pg.click('#ble-scan'); pg.wait_for_timeout(1200)
    ok('requestLEScan started + devices listed', pg.evaluate('__scanning()') and 'Beacon-A' in pg.inner_text('#ble-devs'))
    for i, anchor in enumerate(('A1', 'A2', 'A3')):
        row = pg.locator('#ble-devs .dev').nth(i); name = row.inner_text()
        for r in range(pg.locator('#ble-devs .dev').count()):
            rr = pg.locator('#ble-devs .dev').nth(r)
            if f'Beacon-{"ABC"[i]}' in rr.inner_text():
                rr.locator('select').select_option(anchor); rr.locator('.pr').click(); break
        pg.wait_for_timeout(250)
    pg.wait_for_timeout(1500)
    pp = pg.inner_text('#ble-pairs')
    ok('3 devices paired to A1..A3', all(x in pp for x in ('A1', 'A2', 'A3')), pp.replace('\n', ' ')[:90])
    st = api('/api/ingest/status')
    ok('readings reached backend ingest endpoint', st['total'] > before and set(st['anchors']) >= {'A1', 'A2', 'A3'}, str({k: v['rssi'] for k, v in st['anchors'].items()}))
    ok('backend engine switched to LIVE mode', api('/api/health')['state']['mode'] == 'live')
    ok('UI says engine is using live readings', 'LIVE' in pg.inner_text('#ble-stat'), pg.inner_text('#ble-stat'))
    pg.screenshot(path='docs/shot_staff_ble.png')
    pg.click('#ble-sw'); pg.wait_for_timeout(300)
    t0 = api('/api/ingest/status')['total']; pg.wait_for_timeout(800)
    ok('switching OFF stops scan and forwarding', (not pg.evaluate('__scanning()')) and api('/api/ingest/status')['total'] <= t0 + 1)
    ok('no JS errors', not errs, '; '.join(errs)); ctx.close(); b.close()
print(f'\n{sum(res)}/{len(res)} passed'); sys.exit(0 if all(res) else 1)
