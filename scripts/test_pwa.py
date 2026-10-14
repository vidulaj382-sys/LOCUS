"""Phase 7 browser test (Chrome via Playwright).
 1. backend origin  http://localhost:8000   (backend must be running)
 2. GitHub-Pages-style static host under a sub-path (python http.server, no backend):  http://localhost:8081/locus/
For each: manifest parses, installability errors empty, service worker active, and both pages reload + run with the network OFF."""
import functools, http.server, pathlib, shutil, sys, tempfile, threading
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
results = []


def ok(name, cond, extra=''):
    results.append(bool(cond))
    print(('PASS ' if cond else 'FAIL ') + name + (f'  [{extra}]' if extra else ''))


def static_site():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix='locus-pages-'))
    site = tmp / 'locus'
    site.mkdir()
    for f in ('LOCUS-Dashboard.html', 'LOCUS-Staff-App.html', 'manifest-dashboard.json', 'manifest-staff.json', 'sw.js'):
        shutil.copy(ROOT / f, site / f)
    shutil.copytree(ROOT / 'icons', site / 'icons')
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp))
    h.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 8081), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def check(b, label, urls):
    ctx = b.new_context(viewport={'width': 430, 'height': 900})
    for name, url in urls.items():
        pg = ctx.new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(url)
        pg.wait_for_timeout(1500)
        href = pg.evaluate("document.querySelector('link[rel=manifest]').href")
        man = pg.evaluate("fetch(document.querySelector('link[rel=manifest]').href).then(r=>r.json())")
        ok(f'{label} {name}: manifest loads & has icons/start_url', man['icons'] and man['start_url'] and man['display'] == 'standalone', href)
        cdp = ctx.new_cdp_session(pg)
        inst = cdp.send('Page.getInstallabilityErrors')
        errs_i = [e['errorId'] for e in inst['installabilityErrors'] if e['errorId'] != 'in-incognito']   # test contexts are incognito by nature
        ok(f'{label} {name}: installable (no installability errors besides test-incognito)', not errs_i, str(errs_i))
        pg.evaluate("navigator.serviceWorker.ready.then(()=>true)")
        ok(f'{label} {name}: service worker active', pg.evaluate("navigator.serviceWorker.ready.then(r=>!!r.active)"))
        pg.reload()
        pg.wait_for_timeout(1500)
        ok(f'{label} {name}: page controlled by SW after reload', pg.evaluate("!!navigator.serviceWorker.controller"))
        apple = pg.evaluate("!!document.querySelector('link[rel=apple-touch-icon]') && !!document.querySelector('meta[name=apple-mobile-web-app-capable]')")
        ok(f'{label} {name}: iOS home-screen tags present', apple)
        ok(f'{label} {name}: no JS errors', not errs, '; '.join(errs))
    ctx.set_offline(True)
    for name, url in urls.items():
        pg = ctx.new_page()
        pg.goto(url)
        pg.wait_for_timeout(3200)
        body = pg.inner_text('body')
        ok(f'{label} {name}: loads with network OFF and runs', 'LOCUS' in body and 'Offline simulation' in pg.inner_text('#be-ind'))
        if name == 'staff':
            ok(f'{label} staff: equipment list renders offline', 'Infusion pump P-12' in pg.inner_text('#slist'))
        else:
            ok(f'{label} dashboard: simulation advancing offline', pg.inner_text('#k-err').strip()[:1].isdigit())
    ctx.close()


with sync_playwright() as p:
    b = p.chromium.launch(channel='chrome', headless=True)
    if '--static-only' not in sys.argv:
        check(b, 'backend-origin', {'dashboard': 'http://localhost:8000/', 'staff': 'http://localhost:8000/staff'})
    srv = static_site()
    check(b, 'pages-subpath', {'dashboard': 'http://localhost:8081/locus/LOCUS-Dashboard.html', 'staff': 'http://localhost:8081/locus/LOCUS-Staff-App.html'})
    srv.shutdown()
    b.close()
print(f'\n{sum(results)}/{len(results)} passed')
sys.exit(0 if all(results) else 1)
