/* LOCUS service worker: offline app shell. Same file works on GitHub Pages (any sub-path) and when served by the backend.
   - HTML: network-first (so a rebuilt page is picked up), cached copy when offline
   - icons / manifests / fonts: cache-first, refreshed in the background
   - never touches /api/*, /ws or non-GET requests, so the live backend link and BLE ingest are unaffected */
const CACHE = 'locus-shell-v1';
const SHELL = ['./', './LOCUS-Dashboard.html', './LOCUS-Staff-App.html', './manifest-dashboard.json', './manifest-staff.json',
  './icons/icon-192.png', './icons/icon-512.png', './icons/maskable-512.png', './icons/apple-touch-icon.png', './icons/favicon.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => Promise.all(SHELL.map(u => c.add(new Request(u, { cache: 'reload' })).catch(() => { })))).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith('locus-shell-') && k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== 'GET' || (url.origin === location.origin && /\/(api|ws)(\/|$)/.test(url.pathname))) return;
  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).then(r => { if (r.ok) { const cp = r.clone(); caches.open(CACHE).then(c => c.put(req, cp)); } return r; })
      .catch(() => caches.match(req).then(m => m || caches.match(/staff/i.test(url.pathname) ? './LOCUS-Staff-App.html' : './LOCUS-Dashboard.html'))));
    return;
  }
  const font = /fonts\.(googleapis|gstatic)\.com$/.test(url.hostname);
  if (url.origin !== location.origin && !font) return;
  e.respondWith(caches.match(req).then(hit => {
    const net = fetch(req).then(r => { if (r.ok || r.type === 'opaque') { const cp = r.clone(); caches.open(CACHE).then(c => c.put(req, cp)); } return r; }).catch(() => hit);
    return hit || net;
  }));
});
