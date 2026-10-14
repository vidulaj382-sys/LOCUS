/* ===== Live BLE tab (staff app) - OPTIONAL, OFF BY DEFAULT =====
   Passively collects BLE advertisement RSSI with Web Bluetooth and forwards readings of PAIRED devices to the backend
   (POST /api/ingest), which feeds the same engine pipeline the simulator feeds. Nothing here runs until the user flips the switch.
   Web Bluetooth facts the UI is honest about: Chrome on Android / desktop only (never iOS/Safari); needs https or localhost;
   requestLEScan() (continuous scan of many beacons) is behind chrome://flags/#enable-experimental-web-platform-features;
   browsers hide the Bluetooth MAC, so a device is identified by its per-origin device.id + advertised name.
   No real anchors exist yet: this is untested against real beacons.                                                          */
const BLE = (function () {
  const LS = 'locus.ble.pairs';
  let pairs = {}; try { pairs = JSON.parse(localStorage.getItem(LS) || '{}'); } catch (e) { }
  const seen = {}, last = {}, choice = {}; let enabled = false, scanning = false, scanObj = null, single = null, sent = 0, queue = {}, flushT = null, mode = '', msgExtra = '';

  function support() {
    const ua = navigator.userAgent || '';
    if (!navigator.bluetooth) return { ok: false, msg: /iPhone|iPad|iPod/.test(ua) ? 'Live BLE needs Chrome on Android (or desktop Chrome): iPhone/iPad browsers cannot do Web Bluetooth.' : 'Live BLE needs Chrome on Android (or desktop Chrome); this browser has no Web Bluetooth.' };
    if (!window.isSecureContext) return { ok: false, msg: 'Web Bluetooth needs https:// or localhost: open the app via “python -m backend --https” (see SETUP.md).' };
    if (typeof navigator.bluetooth.requestLEScan !== 'function') return { ok: true, scan: false, msg: 'Continuous scanning is off: enable chrome://flags/#enable-experimental-web-platform-features, relaunch Chrome, or use “Pick one device” below.' };
    return { ok: true, scan: true, msg: 'Ready. Continuous scan available.' };
  }

  function onAdv(ev) {
    const d = ev.device || {}, id = d.id || ev.deviceId; if (!id) return;
    const s = seen[id] || (seen[id] = { id, name: '', rssi: null, n: 0, t: 0 });
    s.name = d.name || ev.name || s.name; s.rssi = ev.rssi; s.n++; s.t = Date.now();
    const p = pairs[id]; if (enabled && p && typeof ev.rssi === 'number') { queue[p.anchor] = { anchor_id: p.anchor, rssi: ev.rssi, timestamp: Date.now() / 1000 }; last[p.anchor] = { rssi: ev.rssi, t: Date.now() }; }
  }
  function flush() {
    const items = Object.values(queue); queue = {}; if (!items.length) return;
    if (!BE.on) { mode = 'local'; return; }
    BE.api('/api/ingest', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ readings: items }) }).then(() => { sent += items.length; mode = 'live'; }).catch(() => { mode = 'error'; });
  }

  async function startScan() {
    msgExtra = '';
    try {
      scanObj = await navigator.bluetooth.requestLEScan({ acceptAllAdvertisements: true, keepRepeatedDevices: true });
      navigator.bluetooth.addEventListener('advertisementreceived', onAdv); scanning = true;
    } catch (e) { msgExtra = 'Scan could not start: ' + (e && e.message || e); }
    render();
  }
  async function pickOne() {
    msgExtra = '';
    try {
      const dev = await navigator.bluetooth.requestDevice({ acceptAllDevices: true });
      if (typeof dev.watchAdvertisements !== 'function') { msgExtra = 'This Chrome cannot watch a single device’s advertisements, so no RSSI is available (needs a newer Chrome or the flag above).'; render(); return; }
      dev.addEventListener('advertisementreceived', onAdv); await dev.watchAdvertisements(); single = dev; scanning = true;
      seen[dev.id] = seen[dev.id] || { id: dev.id, name: dev.name || '', rssi: null, n: 0, t: 0 };
    } catch (e) { if (!(e && e.name === 'NotFoundError')) msgExtra = 'Could not watch device: ' + (e && e.message || e); }
    render();
  }
  function stopAll() {
    try { if (scanObj && scanObj.active) scanObj.stop(); } catch (e) { }
    try { navigator.bluetooth && navigator.bluetooth.removeEventListener('advertisementreceived', onAdv); } catch (e) { }
    try { if (single) { single.removeEventListener('advertisementreceived', onAdv); single.unwatchAdvertisements && single.unwatchAdvertisements(); } } catch (e) { }
    scanObj = single = null; scanning = false; queue = {};
  }
  function setEnabled(on) {
    enabled = on; if (!on) { stopAll(); clearInterval(flushT); flushT = null; } else if (!flushT) flushT = setInterval(flush, 100);
    render();
  }
  const save = () => localStorage.setItem(LS, JSON.stringify(pairs));
  const ago = t => t ? Math.max(0, (Date.now() - t) / 1000).toFixed(1) + ' s ago' : '–';
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  let root;
  function build() {
    const body = document.createElement('div'); body.className = 'body'; body.id = 'v-ble'; body.hidden = true;
    body.innerHTML = `<style>#v-ble .sw{display:flex;align-items:center;justify-content:space-between;gap:12px}#v-ble .tg{width:52px;height:30px;border-radius:99px;background:#CFE1E7;position:relative;flex:none}#v-ble .tg::after{content:'';position:absolute;top:3px;left:3px;width:24px;height:24px;border-radius:50%;background:#fff;transition:.2s;box-shadow:0 1px 4px rgba(0,0,0,.25)}#v-ble .tg[aria-pressed=true]{background:var(--em)}#v-ble .tg[aria-pressed=true]::after{left:25px}#v-ble .msg{font-size:13px;line-height:1.4;color:var(--ink2)}#v-ble .msg.warn{color:#8A5A00}#v-ble .btns{display:flex;gap:8px;flex-wrap:wrap}#v-ble .btns button{height:42px;padding:0 14px;border-radius:999px;border:1.5px solid var(--aqua-l);background:#fff;font-weight:700;font-size:13px}#v-ble .btns button:disabled{opacity:.4}#v-ble .btns button.pri{background:var(--em-d);border-color:var(--em-d);color:#fff}#v-ble select{height:38px;border-radius:12px;border:1.5px solid var(--aqua-l);padding:0 8px;font:600 13px Figtree;background:#fff;max-width:100px}#v-ble .dev{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:10px 0;border-top:1px solid var(--line)}#v-ble .dev:first-child{border-top:0}#v-ble small{display:block;color:var(--ink3);font-size:12px;word-break:break-all}</style>
      <div class="panel"><div class="sw"><div><b>Use real BLE readings</b><small>Off by default. No real anchors yet: this is ready for when beacons exist.</small></div><button class="tg" id="ble-sw" aria-pressed="false" aria-label="Use real BLE readings"></button></div><p class="msg" id="ble-msg" style="margin-top:10px"></p></div>
      <div class="panel" id="ble-ctl"><div class="btns"><button class="pri" id="ble-scan">Start scan</button><button id="ble-one">Pick one device</button><button id="ble-stop">Stop</button></div><p class="msg" id="ble-stat" style="margin-top:10px"></p></div>
      <div class="panel"><b>Nearby devices</b><div id="ble-devs" style="margin-top:6px"></div></div>
      <div class="panel"><b>Paired anchors</b><div id="ble-pairs" style="margin-top:6px"></div><p class="msg" style="margin-top:8px">Browsers hide the Bluetooth MAC address, so a beacon is identified by the browser’s device id for this site plus its advertised name.</p></div>`;
    document.querySelector('.tabbar').before(body);
    const tab = document.createElement('button'); tab.dataset.v = 'ble';
    tab.innerHTML = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 7l10 10-5 5V2l5 5L7 17"/></svg>BLE';
    tab.onclick = () => setView('ble'); document.querySelector('.tabbar').appendChild(tab);
    root = body;
    $('ble-sw').onclick = () => setEnabled(!enabled);
    $('ble-scan').onclick = startScan; $('ble-one').onclick = pickOne; $('ble-stop').onclick = () => { stopAll(); render(); };
  }

  function render() {
    if (!root || root.hidden) return;
    const sp = support();
    $('ble-sw').setAttribute('aria-pressed', enabled); $('ble-sw').disabled = !sp.ok && !enabled && false;
    const m = $('ble-msg'); m.textContent = sp.msg + (msgExtra ? ' ' + msgExtra : ''); m.className = 'msg' + (sp.ok && sp.scan ? '' : ' warn');
    $('ble-scan').disabled = !(enabled && sp.ok && sp.scan && !scanning); $('ble-one').disabled = !(enabled && sp.ok && !scanning); $('ble-stop').disabled = !scanning;
    const fwd = !enabled ? 'Off: nothing is scanned or sent.' : !BE.on ? 'Backend not connected: readings stay on this phone and are not used by the engine.' : sent ? 'Forwarded ' + sent + ' readings to the backend' + (BE.lastMode === 'live' ? ' · engine is using LIVE readings' : '') + '.' : 'Backend connected. Pair a device to start forwarding.';
    $('ble-stat').textContent = (scanning ? 'Scanning… ' : '') + fwd;
    const devs = Object.values(seen).sort((a, b) => (a.name + a.id < b.name + b.id ? -1 : 1)).slice(0, 12);
    $('ble-devs').innerHTML = devs.length ? devs.map(d => `<div class="dev" data-id="${esc(d.id)}"><div><b style="font-size:14px">${esc(d.name || '(no name)')}</b><small>${esc(d.id.slice(0, 18))} · ${d.rssi == null ? '–' : d.rssi + ' dBm'} · ${ago(d.t)}</small></div><div style="display:flex;gap:6px"><select aria-label="Anchor">${anchors.map(a => `<option value="${a.id}"${(choice[d.id] || (pairs[d.id] || {}).anchor) === a.id ? ' selected' : ''}>${a.id}</option>`).join('')}</select><button class="pr" style="height:38px;padding:0 12px;border-radius:12px;background:var(--em-d);color:#fff;font-weight:700;font-size:13px">Pair</button></div></div>`).join('') : '<p class="empty" style="padding:14px 0">No devices yet. Start a scan.</p>';
    $('ble-devs').querySelectorAll('.dev').forEach(el => { el.querySelector('select').onchange = e => { choice[el.dataset.id] = e.target.value; }; el.querySelector('.pr').onclick = () => { const id = el.dataset.id; pairs[id] = { anchor: el.querySelector('select').value, name: (seen[id] || {}).name || '' }; save(); render(); }; });
    const pk = Object.entries(pairs);
    $('ble-pairs').innerHTML = pk.length ? pk.map(([id, p]) => `<div class="dev" data-id="${esc(id)}"><div><b style="font-size:14px">${esc(p.anchor)} ← ${esc(p.name || '(no name)')}</b><small>${esc(id.slice(0, 18))} · ${last[p.anchor] ? last[p.anchor].rssi + ' dBm · ' + ago(last[p.anchor].t) : 'no reading yet'}</small></div><button class="up" style="height:38px;padding:0 12px;border-radius:12px;border:1.5px solid var(--aqua-l);font-weight:700;font-size:13px">Unpair</button></div>`).join('') : '<p class="empty" style="padding:14px 0">Nothing paired.</p>';
    $('ble-pairs').querySelectorAll('.dev').forEach(el => { el.querySelector('.up').onclick = () => { delete pairs[el.dataset.id]; save(); render(); }; });
  }

  build();
  const pf = BE.hooks.frame; BE.hooks.frame = f => { BE.lastMode = f.mode; pf && pf(f); };
  setInterval(() => { if (root && !root.hidden) render(); }, 700);
  return { render, setEnabled, onAdv, _state: () => ({ enabled, pairs, sent }) };
})();
