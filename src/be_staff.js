/* ===== staff app <-> backend wiring (only active when BE.on; otherwise nothing here runs) ===== */
(function () {
  let lastCtl = '', lastIds = '';
  BE.hooks.collect = () => ({ site: SITE_ID, dead: [...cfg.dead] });

  /* equipment list from the backend; the hard-coded STAFF table stays as the offline fallback */
  function loadAssets() {
    BE.api('/api/assets?site=' + SITE_ID).then(d => {
      if (!d || !d.items || !d.items.length) return;
      STAFF[SITE_ID] = { tag: d.lvl, head: d.head, ph: d.ph, cats: d.cats, me: d.me, items: d.items };
      const S = STAFF[SITE_ID]; ITEMS = S.items; ME = S.me; if (!ITEMS.some(i => i.id === selId)) selId = ITEMS[0].id;
      $('q').placeholder = S.ph; $('tagbtn').firstChild.textContent = S.tag + ' '; renderChips(); setView(view);
    }).catch(() => { });
  }
  BE.hooks.assets = loadAssets;

  function sync(st) {
    BE.applying = true;
    try {
      if (st.site !== SITE_ID && (st.site === 'hospital' || st.site === 'warehouse')) switchSite(st.site);
      cfg.dead = new Set(st.dead); lastCtl = st.dead + '';
      onDeadChange();
    } finally { BE.applying = false; }
  }
  BE.hooks.state = st => sync(st);

  BE.hooks.frame = f => {
    if (f.site !== SITE_ID) { BE.applying = true; try { switchSite(f.site); } finally { BE.applying = false; } lastIds = ''; }
    const ids = f.anchors.map(a => a.id).join(',');
    if (ids && ids !== lastIds) { lastIds = ids; anchors = f.anchors.map(a => ({ id: a.id, x: a.x, y: a.y })); buildHealth(); }
    if (f.ctl.dead + '' !== lastCtl) { lastCtl = f.ctl.dead + ''; BE.applying = true; try { cfg.dead = new Set(f.ctl.dead); onDeadChange(); } finally { BE.applying = false; } }
    if (!f.est) return;
    frame = { truth: f.truth || f.est, out: { pos: f.est, ell: f.ell, rooms: f.rooms, trust: f.anchors.map(a => a.trust), reasons: f.anchors.map(a => a.reason), usable: f.anchors.map(a => a.usable) } };
    updateLive();
  };
  BE.hooks.offline = () => { resetSim(); buildHealth(); lastIds = ''; };
  BE.hooks.hello = m => { BE.state = m.state; lastIds = ''; sync(m.state); loadAssets(); };
  BE.start();
})();
