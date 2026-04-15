/* ── filters.js ── Filter controls ────────────────────────────── */

function onEdgeWeightChange(v) {
  minEdgeWeight = parseInt(v);
  document.getElementById('edge-weight-val').textContent = v;
  initGraph();
}

function onDegreeChange(v) {
  minDegree = parseInt(v);
  document.getElementById('degree-val').textContent = v;
  initGraph();
}

function onDepthChange(v) {
  depthLimit = parseInt(v);
  document.getElementById('depth-val').textContent = v === '0' ? '\u221e' : v;
  if (fg && focusNode) {
    // Apply depth filter around focus node
    const neighbors = bfsNeighbors(focusNode, depthLimit);
    highlightNodes = neighbors;
    fg.nodeColor(fg.nodeColor());
  }
}

function onColorModeChange(v) {
  colorMode = v;
  if (fg) {
    fg.nodeColor(fg.nodeColor());
    fg.nodeCanvasObject(fg.nodeCanvasObject());
  }
  rebuildLegend();
}

function rebuildLegend() {
  const legend = document.getElementById('graph-legend');
  while (legend.firstChild) legend.removeChild(legend.firstChild);

  const staticItems = [
    { cls: 'legend-line mem', text: 'Memory link' },
    { cls: 'legend-line kg', text: 'KG relation' },
    { cls: 'legend-line highlight', text: 'Highlighted' }
  ];
  staticItems.forEach(item => {
    const row = document.createElement('div');
    row.className = 'legend-item';
    const line = document.createElement('div');
    line.className = item.cls;
    row.appendChild(line);
    const span = document.createElement('span');
    span.textContent = item.text;
    row.appendChild(span);
    legend.appendChild(row);
  });

  if (colorMode === 'cluster') {
    const seen = new Set();
    const clusterIds = [];
    Object.values(clusterMap).forEach(cid => {
      if (!seen.has(cid)) { seen.add(cid); clusterIds.push(cid); }
    });
    const maxShow = 8;
    clusterIds.slice(0, maxShow).forEach((cid, idx) => {
      const row = document.createElement('div');
      row.className = 'legend-item';
      const dot = document.createElement('div');
      dot.className = 'legend-dot';
      dot.style.background = clusterColors[cid] || '#888';
      row.appendChild(dot);
      const span = document.createElement('span');
      span.textContent = 'Cluster ' + (idx + 1);
      row.appendChild(span);
      legend.appendChild(row);
    });
    if (clusterIds.length > maxShow) {
      const row = document.createElement('div');
      row.className = 'legend-item';
      const span = document.createElement('span');
      span.textContent = '+' + (clusterIds.length - maxShow) + ' more';
      row.appendChild(span);
      legend.appendChild(row);
    }
  }
}

function computeTimeRange() {
  const nodes = GD.nodes;
  if (!nodes.length) { timeRange = [0, 100]; return; }
  const times = nodes.map(n => new Date(n.created_at || 0).getTime()).filter(t => t > 0);
  if (!times.length) { timeRange = [0, 100]; return; }
  timeRange = [Math.min(...times), Math.max(...times)];
}

function onTimeChange(v) {
  timePct = parseInt(v);
  const label = document.getElementById('time-val');
  if (timePct >= 100) { label.textContent = 'All'; initGraph(); return; }
  // Compute cutoff timestamp
  const span = timeRange[1] - timeRange[0] || 1;
  const cutoff = timeRange[0] + (span * timePct / 100);
  const cutoffDate = new Date(cutoff);
  label.textContent = cutoffDate.toLocaleDateString('en', { month: 'short', day: 'numeric' });
  // Rebuild graph with only nodes created before cutoff
  initGraph();
}

function shouldShowNode(n) {
  if (timePct >= 100) return true;
  const t = new Date(n.created_at || 0).getTime();
  const span = timeRange[1] - timeRange[0] || 1;
  const cutoff = timeRange[0] + (span * timePct / 100);
  return t <= cutoff;
}

function toggleNSFilter(ns) {
  if (activeNS.has(ns)) activeNS.delete(ns); else activeNS.add(ns);
  // Update chip UI
  document.querySelectorAll('.ns-chip').forEach(c => {
    c.classList.toggle('active', activeNS.has(c.dataset.ns));
  });
  initGraph();
}

function buildNSChips() {
  const nsSet = new Set(GD.nodes.map(n => n.namespace || 'default'));
  const container = document.getElementById('ns-chips');
  container.textContent = '';
  nsSet.forEach(ns => {
    const chip = document.createElement('span');
    chip.className = 'ns-chip';
    chip.dataset.ns = ns;
    chip.textContent = ns;
    chip.onclick = () => toggleNSFilter(ns);
    container.appendChild(chip);
  });
}

function toggleLocalGraph() {
  if (!focusNode) return;
  localGraphMode = !localGraphMode;
  const btn = document.getElementById('local-graph-btn');
  if (btn) btn.classList.toggle('active', localGraphMode);
  if (localGraphMode) {
    const allData = buildGraphData();
    const adj = {};
    allData.nodes.forEach(n => { adj[n.id] = new Set(); });
    allData.links.forEach(l => {
      const s = nid(l.source), t = nid(l.target);
      if (adj[s]) adj[s].add(t);
      if (adj[t]) adj[t].add(s);
    });
    const neighbors = new Set([focusNode]);
    (adj[focusNode] || new Set()).forEach(nb => neighbors.add(nb));
    const localNodes = allData.nodes.filter(n => neighbors.has(n.id));
    const localLinks = allData.links.filter(l =>
      neighbors.has(nid(l.source)) && neighbors.has(nid(l.target))
    );
    fg.graphData({ nodes: localNodes, links: localLinks });
    setTimeout(() => { if (fg) fg.zoomToFit(400, 40); }, 400);
  } else {
    initGraph();
  }
}
