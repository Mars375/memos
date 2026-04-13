/* ── controls.js ── Graph controls & init entry point ─────────── */

// ── Zoom controls ────────────────────────────────────────────────
function zoomIn() { if (fg) fg.zoom(fg.zoom() * 1.4, 300); }
function zoomOut() { if (fg) fg.zoom(fg.zoom() * 0.7, 300); }
function resetZoom() { if (fg) fg.zoomToFit(400, 50); }

// ── Time-travel controls ─────────────────────────────────────────
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
      } catch (_) {}
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

// ── Init entry point ─────────────────────────────────────────────
refreshGraph();
setInterval(refreshGraph, 60000);
