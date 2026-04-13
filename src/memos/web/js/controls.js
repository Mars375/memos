// ── controls.js — Ribbon, modals, zoom, time-travel, view switching ──

// ── Zoom controls ────────────────────────────────────────────────
function zoomIn(){if(fg)fg.zoom(fg.zoom()*1.4,300);}
function zoomOut(){if(fg)fg.zoom(fg.zoom()*0.7,300);}
function resetZoom(){if(fg)fg.zoomToFit(400,50);}

function setRib(view){
  document.querySelectorAll('.rib-btn').forEach(b=>b.classList.remove('active'));
  const btn=document.getElementById('rib-'+view);if(btn)btn.classList.add('active');
  document.querySelectorAll('.rib-section').forEach(s=>s.style.display='none');
  if(view!=='graph'&&view!=='search'){
    const sec=document.getElementById('sec-'+view);
    if(sec){sec.style.display='';const ch=document.getElementById(view+'-children');const rw=document.getElementById('sec-'+view+'-row');if(ch&&!ch.classList.contains('open')){ch.classList.add('open');if(rw)rw.classList.add('open');}}
  }
}
function focusSearch(){document.getElementById('search-box').focus();}

function openAddModal(){document.getElementById('add-modal').classList.add('open');document.getElementById('new-content').focus();}
function closeAddModal(){document.getElementById('add-modal').classList.remove('open');}
function closeAddModalBg(e){if(e.target===document.getElementById('add-modal'))closeAddModal();}

async function openKGOverlay(label){
  document.getElementById('kg-overlay-title').textContent=label+' Facts';
  const listEl=document.getElementById('kg-facts-list');
  listEl.textContent='Loading\u2026';
  document.getElementById('kg-facts-overlay').style.display='block';
  try{
    const r=await fetch(API+'/kg/labels?label='+encodeURIComponent(label)).then(res=>res.json());
    const facts=r.facts||[];
    listEl.textContent='';
    if(!facts.length){const e=document.createElement('span');e.style.cssText='color:var(--text2);font-size:.8em';e.textContent='No facts with this label.';listEl.appendChild(e);return;}
    facts.forEach(f=>{
      const row=document.createElement('div');row.className='kgf-row';
      const subj=document.createElement('span');subj.className='kgf-subj';subj.textContent=f.subject||'';
      const pred=document.createElement('span');pred.className='kgf-pred';pred.textContent='\u2013'+(f.predicate||'')+'\u2192';
      const obj=document.createElement('span');obj.className='kgf-obj';obj.textContent=f.object||'';
      row.appendChild(subj);row.appendChild(pred);row.appendChild(obj);
      if(f.source){const src=document.createElement('span');src.className='kgf-src';src.textContent=f.source;row.appendChild(src);}
      listEl.appendChild(row);
    });
  }catch(_){listEl.textContent='Error loading facts.';}
}
function closeKGOverlay(){document.getElementById('kg-facts-overlay').style.display='none';}

// ── Time travel ──────────────────────────────────────────────────
let ttActive = false;

function toggleTTPanel() {
  const panel = document.getElementById('tt-panel');
  const btn = document.getElementById('tt-toggle');
  ttActive = !ttActive;
  panel.classList.toggle('open', ttActive);
  btn.classList.toggle('tt-active', ttActive);
  if (ttActive && !document.getElementById('tt-date').value) {
    // Set to today as default
    document.getElementById('tt-date').valueAsDate = new Date();
  }
}

async function applyTimeTravel(dateStr) {
  if (!dateStr) return;
  const ts = new Date(dateStr).getTime() / 1000;
  document.getElementById('tt-info').textContent = 'Showing memories from: ' + dateStr;
  document.getElementById('loading').style.display = 'flex';
  try {
    const gd = await fetch(API + '/graph?created_before=' + ts).then(r => r.json());
    const kgr = await fetch(API + '/kg/labels').then(r => r.json()).catch(() => null);
    const allFacts = [];
    if (kgr && kgr.label_stats) {
      try {
        const [ex, inf, amb] = await Promise.all([
          fetch(API + '/kg/labels?label=EXTRACTED').then(r => r.json()).catch(() => ({ facts: [] })),
          fetch(API + '/kg/labels?label=INFERRED').then(r => r.json()).catch(() => ({ facts: [] })),
          fetch(API + '/kg/labels?label=AMBIGUOUS').then(r => r.json()).catch(() => ({ facts: [] })),
        ]);
        allFacts.push(...(ex.facts || []), ...(inf.facts || []), ...(amb.facts || []));
      } catch(_) {}
    }
    GD.nodes = gd.nodes; GD.edges = gd.edges;
    GD.kgEdges = buildKGEdges(gd.nodes, allFacts);
    const totalLinks = gd.meta.total_edges + GD.kgEdges.length;
    document.getElementById('s-nodes').textContent = gd.meta.total_nodes;
    document.getElementById('s-edges').textContent = totalLinks;
    initGraph();
  } finally {
    document.getElementById('loading').style.display = 'none';
  }
}

async function resetTimeTravel() {
  document.getElementById('tt-date').value = '';
  document.getElementById('tt-info').textContent = 'Showing all memories';
  ttActive = false;
  document.getElementById('tt-panel').classList.remove('open');
  document.getElementById('tt-toggle').classList.remove('tt-active');
  await refreshGraph();
}

// ── Override setRib to handle wiki/palace ─────────────────────────
const _origSetRib = setRib;
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
  // Handle palace specially (stay in sidebar)
  if (view === 'palace') {
    _origSetRib('palace');
    if (!palaceData.wings.length) loadPalace();
    return;
  }
  showNormalSidebar();
  _origSetRib(view);
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
