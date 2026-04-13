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
