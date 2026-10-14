/* ===== PWA: register the service worker (needs https:// or localhost; silently skipped on file:// and plain-http LAN addresses) ===== */
if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
  window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => { }));
}
