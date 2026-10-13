r = lambda f: open(f, encoding='utf8').read()
eng, bench, app = r('src/engine.js'), r('src/bench.js'), r('src/app.js')
be = r('src/backend.js')   # optional backend link; both pages work without a backend (fallback to in-browser simulation)
i = app.index('/* ---------- live simulation state')
j = app.index('/* ================= STAFF APP')
common, dash = app[:i], app[i:j] + r('src/dash_tail.js')

t = r('src/index.template.html').replace('/*__ENGINE__*/', eng).replace('/*__BENCH__*/', bench).replace('/*__APP__*/', common + dash).replace('/*__BE__*/', be + r('src/be_dash.js'))
open('LOCUS-Dashboard.html', 'w', encoding='utf8').write(t)

t = r('src/staff.template.html').replace('/*__ENGINE__*/', eng).replace('/*__COMMON__*/', common).replace('/*__APP__*/', r('src/staff.js')).replace('/*__BE__*/', be + r('src/be_staff.js'))
open('LOCUS-Staff-App.html', 'w', encoding='utf8').write(t)
print('built')
