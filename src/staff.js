/* ================= LOCUS STAFF APP (standalone) ================= */
const cfg = { sigma: 0.6, loss: 0.10, wallBias: 1.8, burst: 0.004, obstructBias: 4, driftBias: 2.5, dead: new Set(), obstruct: new Set(), drift: new Set() };
let anchors, walker, rng, loc, frame = { out: null, truth: [3, 12] }, acc = 0, tPrev = 0, deadSeen = 0;
function resetSim() { anchors = DROP_ORDER.slice(0, 6).map(i => ANCHORS[i]); rng = rngMake(5); walker = new Walker(1.2, 6); loc = new Locus(anchors, { N: 400, sigma: cfg.sigma, rng: rngMake(11), inflate: 2.0 }); frame = { out: null, truth: [3, 12] }; }
function simStep() { if (BE.on) return; const t = walker.step(0.1).slice(), m = measure(t, anchors, cfg, rng); frame = { truth: t, out: loc.step(m, 0.1) }; }

const STAFF = {
  hospital: { tag: 'Level 2', head: 'Find equipment fast', ph: 'Search pump, wheelchair, ECG', cats: ['All', 'Pumps', 'Wheelchairs', 'ECG', 'Oxygen'], me: [2.5, 12],
    items: [
      { id: 'P-12', name: 'Infusion pump P-12', cat: 'Pumps', live: true },
      { id: 'W-3', name: 'Wheelchair W-3', cat: 'Wheelchairs', pos: [8.5, 12.3], conf: 91 },
      { id: 'E-7', name: 'ECG machine E-7', cat: 'ECG', pos: [27, 19.5], conf: 88 },
      { id: 'P-07', name: 'Infusion pump P-07', cat: 'Pumps', pos: [4.5, 4.5], conf: 93 },
      { id: 'W-9', name: 'Wheelchair W-9', cat: 'Wheelchairs', pos: [35, 4.8], conf: 86 },
      { id: 'O-2', name: 'Oxygen cylinder O-2', cat: 'Oxygen', pos: [16.5, 20], conf: 94 }] },
  warehouse: { tag: 'Bay 1', head: 'Find stock fast', ph: 'Search forklift, pallet, scanner', cats: ['All', 'Vehicles', 'Pallets', 'Tools'], me: [2.5, 12],
    items: [
      { id: 'FL-2', name: 'Forklift FL-2', cat: 'Vehicles', live: true },
      { id: 'PJ-4', name: 'Pallet jack PJ-4', cat: 'Vehicles', pos: [6, 8], conf: 92 },
      { id: 'PL-1042', name: 'Pallet #1042 (frozen)', cat: 'Pallets', pos: [20, 18], conf: 89 },
      { id: 'PL-0877', name: 'Pallet #0877', cat: 'Pallets', pos: [28, 6], conf: 90 },
      { id: 'SC-9', name: 'Handheld scanner SC-9', cat: 'Tools', pos: [36, 14], conf: 85 },
      { id: 'C-11', name: 'Picking cart C-11', cat: 'Vehicles', pos: [12.5, 17.5], conf: 91 }] },
};
let ITEMS = STAFF.hospital.items, ME = STAFF.hospital.me, selId = ITEMS[0].id, cat = 'All', query = '', view = 'find';

function route(to) {
  const near = (arr, v) => arr.reduce((b, x) => Math.abs(x - v) < Math.abs(b - v) ? x : b, arr[0]), pts = [ME];
  if (SITE_ID === 'warehouse') { if (to[0] < 8) pts.push([to[0], 12]); else { const ax = near([12, 20, 28, 36], to[0]); pts.push([ax, 12], [ax, to[1]]); } }
  else { const d = to[1] < 9 ? TOP_DOORS : to[1] > 15 ? BOT_DOORS : null; if (!d) pts.push([to[0], 12]); else { const dx = near(d, to[0]); pts.push([dx, 12], [dx, to[1] < 9 ? 6 : 18]); } }
  pts.push(to); return pts;
}
function rlen(p) { let s = 0; for (let i = 1; i < p.length; i++) s += Math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1]); return s; }
function itemInfo(it) {
  if (it.live) { const o = frame.out; if (!o) return { pos: [15, 12], zone: 'Locating…', conf: 0, ell: null }; const top = Object.entries(o.rooms).sort((a, b) => b[1] - a[1])[0]; return { pos: o.pos, zone: roomName(top[0]), conf: pct(top[1]), ell: o.ell }; }
  return { pos: it.pos, zone: roomName(roomAt(it.pos[0], it.pos[1])), conf: it.conf, ell: null };
}
const confCls = c => 'pill ' + (c >= 85 ? 'g' : c >= 60 ? 'a' : 'r');

/* ---------- views ---------- */
function setView(v) {
  view = v; ['find', 'map', 'alerts', 'ble'].forEach(k => { const e = $('v-' + k); if (e) e.hidden = k !== v; });
  document.querySelectorAll('.tabbar button').forEach(b => b.classList.toggle('on', b.dataset.v === v));
  $('s-h').textContent = v === 'find' ? STAFF[SITE_ID].head : v === 'map' ? 'Live floor map' : v === 'ble' ? 'Live BLE scan' : 'System health';
  $('sq').hidden = v !== 'find'; $('schips').hidden = v === 'alerts' || v === 'ble';
  if (v === 'alerts') { deadSeen = cfg.dead.size; $('badge').hidden = true; } renderAll();
}
function renderChips() { const b = $('schips'); b.innerHTML = STAFF[SITE_ID].cats.map(c => `<button class="chip" aria-pressed="${c === cat}">${c}</button>`).join(''); b.querySelectorAll('button').forEach(x => x.onclick = () => { cat = x.textContent; renderChips(); renderAll(); }); }
function filtered() { const q = query.trim().toLowerCase(); return ITEMS.filter(i => (cat === 'All' || i.cat === cat) && (!q || (i.name + ' ' + i.cat).toLowerCase().includes(q))); }
function renderList() {
  const box = $('slist'), list = filtered(); box.innerHTML = '';
  if (!list.length) { box.innerHTML = '<p class="empty">No match. Try another word.</p>'; return; }
  list.forEach(it => {
    const sel = it.id === selId, d = document.createElement('div'); d.className = 'item' + (sel ? ' sel' : ''); d.tabIndex = 0; d.setAttribute('role', 'button'); d.dataset.id = it.id;
    d.innerHTML = `<div class="row"><div><b>${it.name}</b><small data-sub></small></div><span data-conf></span></div>` + (sel ? `<canvas class="mini" width="720" height="432"></canvas><button class="go"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round"><path d="M3 11l18-8-8 18-2-8z"/></svg>Navigate to ${it.id}</button>` : '');
    d.onclick = () => { if (selId !== it.id) { selId = it.id; renderList(); } }; d.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); d.click(); } }; box.appendChild(d);
  }); updateLive();
}
function drawMini(c, it, full) {
  const ctx = c.getContext('2d'), s = c.width / FLOOR.w; drawFloor(ctx, { scale: s, noLabels: true });
  ctx.save(); ctx.font = `600 ${Math.round(s * 0.6)}px Figtree`; ctx.fillStyle = 'rgba(11,58,74,.42)'; ctx.textAlign = 'center'; ROOMS.forEach(r => ctx.fillText(r.name, (r.r[0] + r.r[2]) / 2 * s, (SITE_ID === 'warehouse' ? 8.2 : r.r[1] === 0 ? 8.1 : r.r[1] + 1.3) * s)); ctx.restore();
  const sel = ITEMS.find(i => i.id === selId), si = itemInfo(sel), rt = route(si.pos);
  ctx.save(); ctx.setLineDash([8, 7]); ctx.lineWidth = 4; ctx.strokeStyle = C.aqua; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.beginPath(); rt.forEach((p, i) => i ? ctx.lineTo(p[0] * s, p[1] * s) : ctx.moveTo(p[0] * s, p[1] * s)); ctx.stroke(); ctx.restore();
  (full ? filtered() : [it]).forEach(x => {
    const inf = itemInfo(x), on = x.id === selId;
    if (inf.ell) drawEllipse(ctx, inf.ell, inf.pos[0], inf.pos[1], s, 'rgba(16,185,129,.2)', 'rgba(16,185,129,.9)'); else if (on) { ctx.beginPath(); ctx.arc(inf.pos[0] * s, inf.pos[1] * s, 1.2 * s, 0, 7); ctx.fillStyle = 'rgba(16,185,129,.18)'; ctx.fill(); }
    ctx.beginPath(); ctx.arc(inf.pos[0] * s, inf.pos[1] * s, on ? 10 : 7, 0, 7); ctx.fillStyle = on ? C.em : C.emD; ctx.fill(); ctx.strokeStyle = '#fff'; ctx.lineWidth = 3; ctx.stroke();
    if (full) { ctx.fillStyle = C.ink; ctx.font = '700 12px Figtree'; ctx.textAlign = 'center'; ctx.fillText(x.id, inf.pos[0] * s, inf.pos[1] * s - 15); }
  });
  ctx.beginPath(); ctx.arc(ME[0] * s, ME[1] * s, 8, 0, 7); ctx.fillStyle = C.aquaD; ctx.fill(); ctx.strokeStyle = '#fff'; ctx.lineWidth = 3; ctx.stroke(); ctx.fillStyle = C.ink; ctx.font = '700 12px Figtree'; ctx.textAlign = 'left'; ctx.fillText('You', ME[0] * s + 12, ME[1] * s + 4);
}
function updateLive() {
  if (view === 'find') {
    document.querySelectorAll('#slist .item').forEach(d => { const it = ITEMS.find(i => i.id === d.dataset.id), inf = itemInfo(it); d.querySelector('[data-sub]').textContent = inf.zone + ' · about ' + Math.round(rlen(route(inf.pos))) + ' m from you'; const p = d.querySelector('[data-conf]'); p.textContent = inf.conf + '% sure'; p.className = confCls(inf.conf); });
    const c = document.querySelector('#slist canvas.mini'); if (c) drawMini(c, ITEMS.find(i => i.id === selId), false);
  } else if (view === 'map') {
    drawMini($('fmap'), null, true); const it = ITEMS.find(i => i.id === selId), inf = itemInfo(it);
    $('msel').innerHTML = `<div class="row"><div><b>${it.name}</b><small>${inf.zone} · about ${Math.round(rlen(route(inf.pos)))} m from you</small></div><span class="${confCls(inf.conf)}">${inf.conf}% sure</span></div>`;
  } else if (view === 'ble') {
    if (typeof BLE !== 'undefined') BLE.render();
  } else {
    const o = frame.out, online = anchors.length - cfg.dead.size;
    $('hsum').innerHTML = `<b>${online} of ${anchors.length} anchors online</b><small>${cfg.dead.size ? 'Accuracy reduced near offline anchors. Maintenance notified.' : 'All anchors healthy.'}</small>`;
    $('hpill').className = 'pill ' + (cfg.dead.size ? (cfg.dead.size > 2 ? 'r' : 'a') : 'g'); $('hpill').textContent = cfg.dead.size ? 'Degraded' : 'Healthy';
    anchors.forEach((a, i) => { const r = $('an-' + a.id); if (!r) return; const dead = cfg.dead.has(a.id), t = o ? o.trust[i] : 0.8; r.querySelector('.bar i').style.width = (dead ? 100 : Math.max(4, pct(t))) + '%'; r.querySelector('.bar i').style.background = dead ? C.coral : trustCol(t); const p = r.querySelector('.pill'); p.className = 'pill ' + (dead ? 'r' : t > 0.7 ? 'g' : 'a'); p.textContent = dead ? 'Offline' : t > 0.7 ? 'Strong' : 'Weak'; r.querySelector('button').textContent = dead ? 'Bring online' : 'Simulate failure'; r.classList.toggle('dead', dead); });
  }
}
function buildHealth() {
  $('hlist').innerHTML = anchors.map(a => `<div class="item" id="an-${a.id}" style="cursor:default"><div class="row"><div><b>Anchor ${a.id}</b><small>${roomName(roomAt(a.x, a.y))}</small></div><span class="pill g">Strong</span></div><div class="bar"><i></i></div><button class="go ghost">Simulate failure</button></div>`).join('');
  anchors.forEach(a => $('an-' + a.id).querySelector('button').onclick = () => { cfg.dead.has(a.id) ? cfg.dead.delete(a.id) : cfg.dead.add(a.id); onDeadChange(); });
}
let toastT;
function onDeadChange() {
  const d = [...cfg.dead], t = $('toast');
  if (d.length) { t.innerHTML = `<b>Anchor ${d.join(', ')} offline</b><br>Accuracy reduced nearby. Maintenance notified.`; t.classList.add('on'); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove('on'), 5000); } else t.classList.remove('on');
  if (view !== 'alerts' && d.length > deadSeen) { $('badge').hidden = false; $('badge').textContent = d.length - deadSeen; } updateLive(); BE.push();
}
function renderAll() { if (view === 'find') renderList(); else updateLive(); }
function switchSite(id) {
  setSite(id); const S = STAFF[id]; ITEMS = S.items; ME = S.me; selId = ITEMS[0].id; cat = 'All'; query = ''; $('q').value = ''; $('q').placeholder = S.ph; $('tagbtn').firstChild.textContent = S.tag + ' ';
  $('tagbtn').dataset.site = id; cfg.dead.clear(); deadSeen = 0; $('badge').hidden = true; resetSim(); buildHealth(); renderChips(); setView(view); $('toast').classList.remove('on'); BE.push(); if (BE.on && BE.hooks.assets) BE.hooks.assets();
}

/* ---------- wiring ---------- */
$('q').addEventListener('input', e => { query = e.target.value; renderList(); });
document.querySelectorAll('.tabbar button').forEach(b => b.onclick = () => setView(b.dataset.v));
$('tagbtn').onclick = () => switchSite(SITE_ID === 'hospital' ? 'warehouse' : 'hospital');
$('fmap').addEventListener('click', e => { const r = $('fmap').getBoundingClientRect(), x = (e.clientX - r.left) / r.width * FLOOR.w, y = (e.clientY - r.top) / r.height * FLOOR.h; let best = null, bd = 2.5; filtered().forEach(it => { const p = itemInfo(it).pos, d = Math.hypot(p[0] - x, p[1] - y); if (d < bd) { bd = d; best = it; } }); if (best) { selId = best.id; updateLive(); } });

resetSim(); buildHealth(); renderChips(); setView('find');
function loop(now) {
  if (!tPrev) tPrev = now; const d = Math.min(0.35, (now - tPrev) / 1000); tPrev = now; acc += d; let n = 0;
  while (acc >= 0.1 && n < 3) { simStep(); acc -= 0.1; n++; } if (n === 3) acc = 0;
  if (n) updateLive(); requestAnimationFrame(loop);
}
requestAnimationFrame(loop);
if (location.hash === '#wh') switchSite('warehouse');
if (['map', 'alerts'].includes(location.hash.slice(1))) setView(location.hash.slice(1));
