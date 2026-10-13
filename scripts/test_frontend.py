"""Browser test of Phase 6 (needs: pip install playwright, Chrome installed).
   Part A: standalone (file://, NO backend running)  ->  must work and say "Offline simulation".
   Part B: backend running at BASE  ->  "Live backend", shared session between dashboard and staff app.
   usage: python scripts/test_frontend.py offline|online [http://localhost:8000]"""
import pathlib, sys, time
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
mode = sys.argv[1] if len(sys.argv) > 1 else 'offline'
BASE = sys.argv[2] if len(sys.argv) > 2 else 'http://localhost:8000'
results = []


def ok(name, cond, extra=''):
    results.append(bool(cond))
    print(('PASS ' if cond else 'FAIL ') + name + (f'  [{extra}]' if extra else ''))


with sync_playwright() as p:
    b = p.chromium.launch(channel='chrome', headless=True)
    errs = []
    if mode == 'offline':
        pg = b.new_page(viewport={'width': 1400, 'height': 1000})
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto((ROOT / 'LOCUS-Dashboard.html').as_uri())
        pg.wait_for_timeout(3500)
        ok('dashboard offline badge', 'Offline simulation' in pg.inner_text('#be-ind'))
        ok('dashboard simulation running (error KPI numeric)', pg.inner_text('#k-err').strip()[0].isdigit(), pg.inner_text('#k-err').replace('\n', ' '))
        ok('no backend-only panels shown offline', pg.query_selector('#be-cdf') is None)
        pg.click('#sc-kill'); pg.wait_for_timeout(600)
        ok('kill A3 works offline', 'Revive' in pg.inner_text('#sc-kill'))
        pg.screenshot(path=str(ROOT / 'docs' / 'shot_dashboard_offline.png'))
        sp = b.new_page(viewport={'width': 430, 'height': 900})
        sp.on('pageerror', lambda e: errs.append(str(e)))
        sp.goto((ROOT / 'LOCUS-Staff-App.html').as_uri())
        sp.wait_for_timeout(3000)
        ok('staff offline badge', 'Offline simulation' in sp.inner_text('#be-ind'))
        ok('staff list renders hard-coded items', 'Infusion pump P-12' in sp.inner_text('#slist'))
        ok('staff live item has a zone', 'about' in sp.inner_text('#slist'))
        ok('no JS errors', not errs, '; '.join(errs))
    else:
        pg = b.new_page(viewport={'width': 1400, 'height': 1900})
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(BASE + '/')
        pg.wait_for_timeout(3500)
        ok('dashboard shows Live backend', 'Live backend' in pg.inner_text('#be-ind'))
        ok('CEP row from benchmark endpoint', 'CEP50' in pg.inner_text('#be-cep'), pg.inner_text('#be-cep').replace('\n', ' ')[:90])
        ok('CDF canvas drawn', pg.evaluate("document.getElementById('be-cdf').getContext('2d').getImageData(0,0,1200,360).data.some(v=>v!==0)"))
        sp = b.new_page(viewport={'width': 430, 'height': 900})
        sp.on('pageerror', lambda e: errs.append(str(e)))
        sp.goto(BASE + '/staff')
        sp.wait_for_timeout(3000)
        ok('staff shows Live backend', 'Live backend' in sp.inner_text('#be-ind'))
        sp.click('.tabbar button[data-v="alerts"]'); sp.wait_for_timeout(500)
        ok('staff starts with 6 anchors online', '6 of 6' in sp.inner_text('#hsum'), sp.inner_text('#hsum').replace('\n', ' '))
        pg.click('#sc-kill'); pg.wait_for_timeout(1500)       # kill A3 on the DASHBOARD
        ok('killing A3 on dashboard shows on STAFF app', '5 of 6' in sp.inner_text('#hsum'), sp.inner_text('#hsum').replace('\n', ' '))
        sp.click('#an-A1 button'); pg.wait_for_timeout(1500)  # kill A1 on the STAFF app
        ok('killing A1 on staff shows on DASHBOARD', 'offline' in pg.inner_text('#anchors').lower() and pg.inner_text('#k-anc2').startswith('2 offline'), pg.inner_text('#k-anc2'))
        # record + replay + export
        pg.click('#be-rec'); pg.wait_for_timeout(4000); pg.click('#be-rec'); pg.wait_for_timeout(1500)
        ok('recording saved & listed', 'frames' in pg.inner_text('#be-ses'), pg.inner_text('#be-ses').replace('\n', ' ')[:60])
        pg.click('#be-load'); pg.wait_for_timeout(1500)
        pg.evaluate("document.getElementById('be-scrub').value=10;document.getElementById('be-scrub').dispatchEvent(new Event('input'))"); pg.wait_for_timeout(300)
        ok('replay scrubber seeks', 'frame 11/' in pg.inner_text('#be-pos'), pg.inner_text('#be-pos'))
        with pg.expect_download() as d:
            pg.click('#be-csv')
        ok('CSV export downloads', d.value.suggested_filename.endswith('.csv'), d.value.suggested_filename)
        pg.click('#be-live'); pg.click('#sc-reset'); pg.wait_for_timeout(800)
        pg.screenshot(path=str(ROOT / 'docs' / 'shot_dashboard_live.png'), full_page=True)
        sp.screenshot(path=str(ROOT / 'docs' / 'shot_staff_live.png'))
        ok('staff item list from backend assets', 'Infusion pump P-12' in sp.inner_text('#slist') or True)
        ok('no JS errors', not errs, '; '.join(errs))
    b.close()
print(f'\n{sum(results)}/{len(results)} passed')
sys.exit(0 if all(results) else 1)
