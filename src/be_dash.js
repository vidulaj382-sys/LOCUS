/* ===== dashboard <-> backend wiring (only active when BE.on; otherwise nothing here runs) ===== */
(function () {
  const same = (a, b) => a.length === b.length && a.every((v, i) => v === b[i]);
  let lastCtl = '', bench = null, sessions = [], card1, card2;

  BE.hooks.collect = () => ({ sigma: cfg.sigma, loss: cfg.loss, wallBias: cfg.wallBias, nAnch, site: SITE_ID, dead: [...cfg.dead], obstruct: [...cfg.obstruct], drift: [...cfg.drift] });

  /* make the local UI mirror the shared session state (sliders, site, anchor count) */
  function applyState(st) {
    BE.applying = true;
    try {
      if (st.site !== SITE_ID && (st.site === 'hospital' || st.site === 'warehouse')) switchSite(st.site);
      if (st.n !== nAnch) { nAnch = st.n; $('s-n').value = st.n; $('o-n').textContent = st.n; resetSim(); }
      const sl = (id, v) => { if (+$(id).value !== v) { $(id).value = v; $(id).dispatchEvent(new Event('input')); } };
      sl('s-sigma', st.params.sigma); sl('s-loss', Math.round(st.params.loss * 100)); sl('s-wall', st.params.wallBias);
      cfg.dead = new Set(st.dead); cfg.obstruct = new Set(st.obstruct); cfg.drift = new Set(st.drift); syncScen();
      const sel = $('be-scorer'); if (sel) { sel.value = st.scorer; sel.querySelector('option[value=ml]').disabled = !st.ml_available; }
    } finally { BE.applying = false; }
  }
  BE.hooks.state = applyState;

  function showFrame(f) {
    if (f.site !== SITE_ID || f.ctl.n !== nAnch) applyState({ site: f.site, n: f.ctl.n, params: (BE.state && BE.state.params) || { sigma: cfg.sigma, loss: cfg.loss, wallBias: cfg.wallBias }, dead: f.ctl.dead, obstruct: f.ctl.obstruct, drift: f.ctl.drift, scorer: f.scorer, ml_available: true });
    if (!f.est) return;
    const key = f.ctl.dead + '|' + f.ctl.obstruct + '|' + f.ctl.drift;
    if (key !== lastCtl) { lastCtl = key; cfg.dead = new Set(f.ctl.dead); cfg.obstruct = new Set(f.ctl.obstruct); cfg.drift = new Set(f.ctl.drift); syncScen(); }
    if (f.anchors.length !== anchors.length) return;
    const out = { pos: f.est, ell: f.ell, rooms: f.rooms, trust: f.anchors.map(a => a.trust), reasons: f.anchors.map(a => a.reason), usable: f.anchors.map(a => a.usable), wallMu: f.wallMu, fix: f.fix };
    const t = f.truth || f.est, e = v => v == null ? null : v;
    prevFrame = frame; frame = { truth: t, ls: f.ls, out, kfp: f.kf, noTruth: !f.truth };
    const P = f.particles || []; loc = { inited: true, N: P.length, px: P.map(p => p[0]), py: P.map(p => p[1]) };
    trail.push(f.est.slice()); if (trail.length > 40) trail.shift();
    hist.lo.push(e(f.err.lo)); hist.kf.push(e(f.err.kf)); hist.ls.push(e(f.err.ls));
    Object.values(hist).forEach(a => { if (a.length > 300) a.shift(); });
  }
  BE.hooks.frame = f => { if (!BE.replay) showFrame(f); };
  BE.hooks.offline = () => { BE.replay = null; resetSim(); hist = { lo: [], kf: [], ls: [] }; trail = []; if (card1) { card1.hidden = card2.hidden = true; } };

  /* ---------- extra panels (created only once a backend answered) ---------- */
  const css = '.be-row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:10px}.be-row button,.be-row select{height:36px;padding:0 14px;border-radius:999px;border:1.5px solid var(--aqua-l);background:#fff;font:600 13px Figtree;color:var(--ink)}.be-row button:hover:not(:disabled){border-color:var(--em)}.be-row button:disabled{opacity:.45;cursor:default}.be-row input[type=range]{flex:1;min-width:160px}.be-kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.be-kpis .kpi b{font-size:22px}.be-note{font-size:12px;color:var(--ink3);margin-top:8px;line-height:1.4}';
  function buildPanels() {
    const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
    const anchor = $('errchart').closest('.card');
    card1 = document.createElement('div'); card1.className = 'card';
    card1.innerHTML = '<h3>Accuracy on hidden test set <small id="be-b-meta">backend benchmark</small></h3><div class="be-kpis" id="be-cep"></div><div class="chartwrap" style="margin-top:12px"><canvas id="be-cdf" width="1200" height="360" aria-label="Error CDF"></canvas></div><div class="cleg"><span><i style="background:#10B981"></i>LOCUS</span><span><i style="background:#7C93C3"></i>Trilateration + Kalman(CV)</span><span><i style="background:#F5A524"></i>WLS trilateration</span></div><div class="be-row"><label for="be-scorer" style="font-size:13px;font-weight:600">Trust scorer</label><select id="be-scorer"><option value="heuristic">Heuristic (default)</option><option value="ml">ML (LightGBM)</option></select><button id="be-bench">Re-run benchmark (quick)</button><span id="be-bstat" class="be-note" style="margin:0"></span></div><p class="be-note">Numbers come from the backend benchmark endpoint: simulated hidden test set, all noise levels pooled, for the number of anchors currently installed. Not real-hardware data.</p>';
    card2 = document.createElement('div'); card2.className = 'card';
    card2.innerHTML = '<h3>Session recording &amp; replay <small id="be-rec-s">live</small></h3><div class="be-row" style="margin-top:0"><button id="be-rec">● Record</button><select id="be-ses" aria-label="Recorded sessions"></select><button id="be-load">Replay</button><button id="be-live" disabled>Back to live</button></div><div class="be-row"><button id="be-play" disabled>Play</button><input type="range" id="be-scrub" min="0" max="0" value="0" disabled aria-label="Replay position"><span id="be-pos" class="be-note" style="margin:0">–</span></div><div class="be-row"><button id="be-csv" disabled>Export CSV</button><button id="be-json" disabled>Export JSON</button></div>';
    anchor.after(card2); anchor.after(card1);
    $('be-scorer').onchange = e => BE.send({ type: 'control', scorer: e.target.value });
    $('be-bench').onclick = runBench; $('be-rec').onclick = toggleRec; $('be-load').onclick = loadSession; $('be-live').onclick = backToLive;
    $('be-play').onclick = togglePlay; $('be-scrub').oninput = e => seek(+e.target.value);
    $('be-csv').onclick = () => dl('csv'); $('be-json').onclick = () => dl('json');
    $('be-ses').onchange = () => { $('be-csv').disabled = $('be-json').disabled = !$('be-ses').value; };
  }

  /* ---------- CEP50 / CEP95 + error CDF from the benchmark endpoint ---------- */
  const MCOL = { 'LOCUS (heuristic)': C.em, 'LOCUS (ML trust)': C.emD, 'Kalman(CV)': C.slate, 'WLS': C.amber };
  function drawBench() {
    if (!bench || !card1) return;
    const n = nAnch, rows = bench.results.filter(r => r.anchors === n && r.noise_level === 'all'), by = {}; rows.forEach(r => by[r.method] = r);
    const lo = by['LOCUS (' + (BE.state && BE.state.scorer === 'ml' ? 'ML trust' : 'heuristic') + ')'] || by['LOCUS (heuristic)'];
    const k = (name, r) => r ? `<div class="kpi"><span>${name}</span><b>${r.median_m.toFixed(1)}<i> m</i> <small style="font-size:13px;color:var(--ink3)">CEP50</small></b><small>CEP95 ${r.p95_m.toFixed(1)} m · ${Math.round(r.within_2m_pct)}% within 2 m</small></div>` : '';
    $('be-cep').innerHTML = k('LOCUS · ' + n + ' anchors', lo) + k('Trilateration + Kalman(CV)', by['Kalman(CV)']) + k('WLS trilateration', by['WLS']);
    $('be-b-meta').textContent = (bench.quick ? 'quick run · ' : 'full run · ') + bench.dataset.runs + ' hidden runs · simulated';
    const c = $('be-cdf'), x = c.getContext('2d'), W = 1200, H = 360, L = 52, R = 16, T = 12, B = 34, pw = W - L - R, ph = H - T - B, cdf = bench.cdf[String(n)] || {};
    x.clearRect(0, 0, W, H); x.font = '600 13px Figtree'; x.fillStyle = '#7A9AA6'; x.textAlign = 'right';
    for (let v = 0; v <= 1.001; v += 0.25) { const y = T + ph - v * ph; x.strokeStyle = '#E3F3F7'; x.beginPath(); x.moveTo(L, y); x.lineTo(W - R, y); x.stroke(); x.fillText(Math.round(v * 100) + '%', L - 8, y + 4); }
    x.textAlign = 'center'; for (let m = 0; m <= 15; m += 3) x.fillText(m + ' m', L + m / 15 * pw, H - 10);
    x.setLineDash([6, 6]); x.strokeStyle = C.em; x.globalAlpha = .6; x.beginPath(); x.moveTo(L + 2 / 15 * pw, T); x.lineTo(L + 2 / 15 * pw, T + ph); x.stroke(); x.setLineDash([]); x.globalAlpha = 1;
    ['WLS', 'Kalman(CV)', 'LOCUS (heuristic)', 'LOCUS (ML trust)'].forEach(m => { const y = cdf[m]; if (!y) return; if (m === 'LOCUS (ML trust)' && !(BE.state && BE.state.scorer === 'ml')) return;
      if (m === 'LOCUS (heuristic)' && BE.state && BE.state.scorer === 'ml') return;
      x.beginPath(); y.forEach((v, i) => { const px = L + bench.cdf_x[i] / 15 * pw, py = T + ph - v * ph; i ? x.lineTo(px, py) : x.moveTo(px, py); }); x.strokeStyle = MCOL[m]; x.lineWidth = m.startsWith('LOCUS') ? 4 : 2.5; x.lineJoin = 'round'; x.stroke(); });
  }
  function loadBench() { BE.api('/api/benchmark').then(b => { bench = b; drawBench(); }).catch(() => { $('be-cep').innerHTML = '<p class="be-note">No benchmark results on the backend yet - press “Re-run benchmark”.</p>'; }); }
  function runBench() {
    const b = $('be-bench'); b.disabled = true; BE.api('/api/benchmark?quick=true', { method: 'POST' }).then(() => {
      const poll = () => BE.api('/api/benchmark/status').then(s => { $('be-bstat').textContent = s.running ? 'running… ' + Math.round(s.progress * 100) + '%' : (s.error ? 'failed' : ''); if (s.running) setTimeout(poll, 1500); else { b.disabled = false; loadBench(); } }); poll();
    }).catch(() => { b.disabled = false; $('be-bstat').textContent = 'already running or unavailable'; });
  }
  let lastN = 0; setInterval(() => { if (BE.on && bench && nAnch !== lastN) { lastN = nAnch; drawBench(); } }, 500);

  /* ---------- recording / replay / export ---------- */
  let recording = false, rp = null, timer = null;
  function refreshSessions(sel) {
    BE.api('/api/sessions').then(l => { sessions = l.filter(s => s.n_frames > 0); const el = $('be-ses'); el.innerHTML = sessions.length ? sessions.map(s => `<option value="${s.id}">#${s.id} ${s.name} · ${s.n_frames} frames</option>`).join('') : '<option value="">no sessions yet</option>'; if (sel) el.value = sel; $('be-csv').disabled = $('be-json').disabled = !el.value; $('be-load').disabled = !el.value; });
  }
  function toggleRec() {
    const b = $('be-rec'); b.disabled = true;
    if (!recording) BE.api('/api/sessions/start?name=dashboard', { method: 'POST' }).then(() => { recording = true; b.textContent = '■ Stop recording'; $('be-rec-s').textContent = 'recording…'; }).finally(() => b.disabled = false);
    else BE.api('/api/sessions/stop', { method: 'POST' }).then(r => { recording = false; b.textContent = '● Record'; $('be-rec-s').textContent = 'saved ' + r.frames + ' frames'; refreshSessions(r.id); }).finally(() => b.disabled = false);
  }
  function loadSession() {
    const id = $('be-ses').value; if (!id) return; $('be-load').disabled = true;
    BE.api('/api/sessions/' + id + '/frames?limit=20000').then(fr => {
      if (!fr.length) return; rp = { fr, i: 0 }; BE.replay = rp; hist = { lo: [], kf: [], ls: [] }; trail = [];
      const s = $('be-scrub'); s.max = fr.length - 1; s.value = 0; s.disabled = false; $('be-play').disabled = false; $('be-live').disabled = false; $('be-rec-s').textContent = 'replaying #' + id; seek(0);
    }).finally(() => $('be-load').disabled = false);
  }
  function seek(i) {
    if (!rp) return; const back = i < rp.i; rp.i = i; if (back) { hist = { lo: [], kf: [], ls: [] }; trail = []; for (let k = Math.max(0, i - 40); k < i; k++) showFrame(rp.fr[k]); }
    showFrame(rp.fr[i]); $('be-scrub').value = i; $('be-pos').textContent = rp.fr[i].t.toFixed(1) + ' s · frame ' + (i + 1) + '/' + rp.fr.length;
  }
  function togglePlay() {
    if (timer) { clearInterval(timer); timer = null; $('be-play').textContent = 'Play'; return; }
    $('be-play').textContent = 'Pause'; timer = setInterval(() => { if (rp.i + 1 >= rp.fr.length) { togglePlay(); return; } seek(rp.i + 1); }, 100);
  }
  function backToLive() { if (timer) togglePlay(); rp = null; BE.replay = null; hist = { lo: [], kf: [], ls: [] }; trail = []; $('be-scrub').disabled = true; $('be-play').disabled = true; $('be-live').disabled = true; $('be-pos').textContent = '–'; $('be-rec-s').textContent = recording ? 'recording…' : 'live'; }
  function dl(fmt) { const id = $('be-ses').value; if (id) { const a = document.createElement('a'); a.href = BE.base + '/api/sessions/' + id + '/export?format=' + fmt; a.download = ''; document.body.appendChild(a); a.click(); a.remove(); } }

  BE.hooks.hello = m => {
    BE.state = m.state; buildPanels(); card1.hidden = card2.hidden = false; applyState(m.state); lastCtl = ''; hist = { lo: [], kf: [], ls: [] }; trail = [];
    $('hl').textContent = 'Backend feed · shared session'; loadBench(); refreshSessions(); 
  };
  BE.start();
})();
