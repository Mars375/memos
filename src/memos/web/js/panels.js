/* ── panels.js ── Panel management ────────────────────────────── */

function showMemoryDetail(d) {
  const rp = document.getElementById('right-panel');
  const title = document.getElementById('rp-title');
  const subtitle = document.getElementById('rp-subtitle');
  const body = document.getElementById('rp-body');

  title.textContent = (d.content || '').slice(0, 45) || d.id.slice(0, 8) + '...';
  subtitle.textContent = 'Memory \u00b7 ' + (d.namespace || 'default');

  body.textContent = '';

  // Content block
  const contentDiv = document.createElement('div');
  contentDiv.className = 'dc-content';
  contentDiv.textContent = d.content || '';
  body.appendChild(contentDiv);

  // Tags
  const tagsDiv = document.createElement('div');
  tagsDiv.style.marginBottom = '10px';
  if (d.tags && d.tags.length) {
    d.tags.forEach(t => {
      const sp = document.createElement('span');
      sp.className = 'badge';
      sp.style.background = tc(t) + '22';
      sp.style.color = tc(t);
      sp.style.border = '1px solid ' + tc(t) + '44';
      sp.textContent = '#' + t;
      tagsDiv.appendChild(sp);
    });
  } else {
    const empty = document.createElement('span');
    empty.style.cssText = 'color:var(--text2);font-size:.8em';
    empty.textContent = 'No tags';
    tagsDiv.appendChild(empty);
  }
  body.appendChild(tagsDiv);

  // Meta grid
  const metaDiv = document.createElement('div');
  metaDiv.className = 'dc-meta';
  [['Importance', (d.importance * 100).toFixed(0) + '%'], ['Age', (d.age_days || 0) + 'd'],
   ['Accessed', (d.access_count || 0) + '\u00d7'], ['ID', d.id.slice(0, 8) + '...']].forEach(([l, v]) => {
    const sp = document.createElement('span');
    const strong = document.createElement('strong');
    strong.textContent = l;
    sp.appendChild(strong);
    sp.appendChild(document.createTextNode(v));
    metaDiv.appendChild(sp);
  });
  body.appendChild(metaDiv);

  // Forget button
  const forgetBtn = document.createElement('button');
  forgetBtn.className = 'btn btn-danger';
  forgetBtn.textContent = '\uD83D\uDDD1 Forget';
  forgetBtn.onclick = forgetSelected;
  body.appendChild(forgetBtn);

  // Entity extra placeholder
  const extra = document.createElement('div');
  extra.id = 'entity-extra';
  extra.style.marginTop = '16px';
  body.appendChild(extra);

  rp.classList.add('open');
}

function closeRightPanel() { document.getElementById('right-panel').classList.remove('open'); }

function openAddModal() { document.getElementById('add-modal').classList.add('open'); document.getElementById('new-content').focus(); }
function closeAddModal() { document.getElementById('add-modal').classList.remove('open'); }
function closeAddModalBg(e) { if (e.target === document.getElementById('add-modal')) closeAddModal(); }

function closeKGOverlay() { document.getElementById('kg-facts-overlay').style.display = 'none'; }

// ── Ribbon / view switching ──────────────────────────────────────
function setRib(view) {
  // Toggle views
  const graphArea = document.getElementById('graph-area');
  const wikiArea = document.getElementById('wiki-area');
  if (view === 'wiki') {
    graphArea.style.display = 'none';
    wikiArea.classList.add('active');
    document.querySelectorAll('.rib-btn').forEach(b => b.classList.remove('active'));
    document.getElementById('rib-wiki').classList.add('active');
    // Show wiki page list in sidebar
    if (!wikiPages.length) loadWikiPagesList().then(goWikiHome);
    else goWikiHome();
    // Swap sidebar body to show wiki list
    showWikiSidebar();
    return;
  }
  // For any non-wiki view, ensure graph is visible
  graphArea.style.display = '';
  wikiArea.classList.remove('active');

  // Handle basic ribbon UI (buttons + sidebar sections)
  document.querySelectorAll('.rib-btn').forEach(b => b.classList.remove('active'));
  const btn = document.getElementById('rib-' + view); if (btn) btn.classList.add('active');
  document.querySelectorAll('.rib-section').forEach(s => s.style.display = 'none');
  if (view !== 'graph' && view !== 'search') {
    const sec = document.getElementById('sec-' + view);
    if (sec) {
      sec.style.display = '';
      const ch = document.getElementById(view + '-children');
      const rw = document.getElementById('sec-' + view + '-row');
      if (ch && !ch.classList.contains('open')) { ch.classList.add('open'); if (rw) rw.classList.add('open'); }
    }
  }

  // Handle palace specially (stay in sidebar)
  if (view === 'palace') {
    if (!palaceData.wings.length) loadPalace();
    return;
  }

  showNormalSidebar();
}

function showWikiSidebar() {
  // Show wiki-specific sidebar
  document.querySelectorAll('.ft-section').forEach(s => s.style.display = 'none');
  let wikiSec = document.getElementById('wiki-sidebar-section');
  if (!wikiSec) {
    wikiSec = document.createElement('div');
    wikiSec.id = 'wiki-sidebar-section';
    wikiSec.className = 'ft-section';
    const header = document.createElement('div');
    header.className = 'ft-row open'; header.style.cssText = 'font-weight:600;color:var(--text)';
    const icon = document.createElement('span'); icon.className = 'ft-icon'; icon.textContent = '\uD83D\uDCD6';
    const label = document.createElement('span'); label.className = 'ft-label'; label.textContent = 'Pages';
    const count = document.createElement('span'); count.className = 'ft-count'; count.id = 'wiki-page-count'; count.textContent = wikiPages.length;
    header.appendChild(icon); header.appendChild(label); header.appendChild(count);
    const list = document.createElement('div'); list.id = 'wiki-sidebar-list'; list.className = 'ft-children open';
    wikiSec.appendChild(header); wikiSec.appendChild(list);
    document.getElementById('ft-body').appendChild(wikiSec);
  }
  document.getElementById('wiki-sidebar-section').style.display = '';
  document.getElementById('wiki-page-count').textContent = wikiPages.length;
  buildWikiPageList();
}

function showNormalSidebar() {
  const wikiSec = document.getElementById('wiki-sidebar-section');
  if (wikiSec) wikiSec.style.display = 'none';
  document.querySelectorAll('.ft-section:not(#wiki-sidebar-section)').forEach(s => s.style.display = '');
}
