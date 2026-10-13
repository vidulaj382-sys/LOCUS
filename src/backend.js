/* ================= OPTIONAL BACKEND LINK =================
   Tries to reach the LOCUS backend (python -m backend) over WebSocket on page load. If no backend answers within 1.5 s the page
   keeps running the in-browser simulation exactly as before - silently, nothing is shown except the "Offline simulation" badge.
   Where to look:  ?backend=host:port  >  the origin that served this page  >  localhost:8000.            */
Object.assign(BE, {
  ws: null, base: '', state: null, applying: false, hooks: {}, ind: null,
  setInd(live) {
    if (!BE.ind) {
      BE.ind = document.createElement('span'); BE.ind.id = 'be-ind'; BE.ind.setAttribute('role', 'status');
      BE.ind.style.cssText = 'display:inline-flex;align-items:center;gap:6px;padding:6px 11px;border-radius:999px;font:700 12px Figtree,system-ui,sans-serif;white-space:nowrap;border:1.5px solid';
      (document.querySelector('.hrow') ? document.querySelector('.hrow').insertBefore(BE.ind, document.querySelector('.live')) : document.querySelector('.brand') && document.querySelector('.brand').insertBefore(BE.ind, document.getElementById('tagbtn')));
    }
    BE.ind.innerHTML = '<i style="width:8px;height:8px;border-radius:50%;display:inline-block;background:' + (live ? '#10B981' : '#9BB3BD') + '"></i>' + (live ? 'Live backend' : 'Offline simulation');
    BE.ind.style.color = live ? '#0A6B49' : '#587783'; BE.ind.style.background = live ? '#DDF6EA' : '#F1F6F8'; BE.ind.style.borderColor = live ? '#10B981' : '#D5E3E8';
    BE.ind.title = live ? 'Driven by the shared backend session at ' + BE.base : 'No backend reachable: running the pure in-browser simulation';
  },
  send(o) { if (BE.ws && BE.ws.readyState === 1) BE.ws.send(JSON.stringify(o)); },
  /* push local control state (set by the page via hooks.collect) to the shared session */
  push() { if (BE.on && !BE.applying && BE.hooks.collect) BE.send(Object.assign({ type: 'control' }, BE.hooks.collect())); },
  api(path, opt) { return fetch(BE.base + path, opt).then(r => { if (!r.ok) throw new Error(r.status); return r.headers.get('content-type').includes('json') ? r.json() : r.text(); }); },
  start() {
    BE.setInd(false);
    const q = new URLSearchParams(location.search).get('backend'), http = location.protocol.startsWith('http'), c = [];
    if (q) c.push(q); if (http && !/github\.io$/.test(location.hostname)) c.push(location.host); c.push('localhost:8000');
    const cands = c.filter((x, i) => c.indexOf(x) === i), socks = []; let settled = false;
    const done = () => { settled = true; socks.forEach(s => { if (s !== BE.ws) try { s.close(); } catch (e) { } }); };
    setTimeout(() => { if (!settled) done(); }, 1500);
    cands.forEach(host => {
      let ws; const local = /^(localhost|127\.|\[::1\])/.test(host), sec = location.protocol === 'https:' && (!local || host === location.host);
      try { ws = new WebSocket((sec ? 'wss://' : 'ws://') + host + '/ws'); } catch (e) { return; }
      socks.push(ws);
      ws.onmessage = ev => {
        let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
        if (!BE.ws) {
          if (settled || m.type !== 'hello') return;
          BE.ws = ws; BE.base = (sec ? 'https://' : 'http://') + host; BE.on = true; done(); BE.setInd(true);
          if (BE.hooks.hello) BE.hooks.hello(m); return;
        }
        if (ws !== BE.ws) return;
        if (m.type === 'frame') { if (BE.hooks.frame) BE.hooks.frame(m); }
        else if (m.type === 'state') { BE.state = m.state; if (BE.hooks.state) BE.hooks.state(m.state); }
        else if (m.type === 'hello') { BE.state = m.state; if (BE.hooks.state) BE.hooks.state(m.state); }
      };
      ws.onclose = ws.onerror = () => { if (ws === BE.ws && BE.on) { BE.on = false; BE.ws = null; BE.setInd(false); if (BE.hooks.offline) BE.hooks.offline(); } };
    });
  },
});
