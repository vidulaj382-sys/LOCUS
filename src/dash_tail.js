/* ================= SITE SWITCH ================= */
function notifyApp() {}
function engineNow() { return { DROP_ORDER, ANCHORS, rngMake, Walker, KalmanCV, Locus, measure, lsFix }; }
function switchSite(id) {
  setSite(id); document.querySelectorAll('.site button').forEach(b => b.setAttribute('aria-pressed', b.dataset.site === id));
  nAnch = 6; $('s-n').value = 6; $('o-n').textContent = 6; cfg.dead.clear(); cfg.obstruct.clear(); cfg.drift.clear(); resetSim(); syncScen();
  PL.ready = false; benchRes = null; $('b-meta').textContent = ''; $('b-tab').innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--ink3);padding:30px">Press “Run benchmark”</td></tr>';
  $('d-floor').textContent = id === 'warehouse' ? 'Floor map · Bay 1' : 'Floor map · Level 2';
  if (tabNow === 'plan') renderPlanner(); if (tabNow === 'bench') renderBench();
}
document.querySelectorAll('.site button').forEach(b => b.onclick = () => { if (b.dataset.site !== SITE_ID) switchSite(b.dataset.site); });

/* ================= MAIN LOOP ================= */
resetSim(); syncScen();
let lastPanel = 0;
function loop(now) {
  if (!tPrev) tPrev = now; const d = Math.min(0.35, (now - tPrev) / 1000); tPrev = now; acc += d; let n = 0;
  while (acc >= 0.1 && n < 3) { simStep(); acc -= 0.1; n++; } if (n === 3) acc = 0;
  if (tabNow === 'dash') { renderMap(acc / 0.1); if (now - lastPanel > 250) { updatePanels(); renderChart(); lastPanel = now; } }
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);
{ const hs = location.hash.slice(1).split('-'), b = document.querySelector('nav button[data-v="' + hs[0] + '"]'); if (hs[1] === 'wh') switchSite('warehouse'); if (b) b.click(); }
