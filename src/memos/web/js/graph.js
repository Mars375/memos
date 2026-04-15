/* ── graph.js ── Force-graph initialization and rendering ─────── */

// ── Compute degree from all edges ────────────────────────────────
function rebuildDegreeMap() {
  Object.keys(degreeMap).forEach(k => delete degreeMap[k]);
  Object.keys(inDegreeMap).forEach(k => delete inDegreeMap[k]);
  Object.keys(outDegreeMap).forEach(k => delete outDegreeMap[k]);
  const all = [...GD.edges, ...GD.kgEdges];
  all.forEach(e => {
    const s = nid(e.source), t = nid(e.target);
    degreeMap[s] = (degreeMap[s] || 0) + 1;
    degreeMap[t] = (degreeMap[t] || 0) + 1;
    outDegreeMap[s] = (outDegreeMap[s] || 0) + 1;
    inDegreeMap[t] = (inDegreeMap[t] || 0) + 1;
  });
}

// ── P1: Detect clusters via connected components + tag grouping ──
function detectClusters() {
  const adj = {};
  // Reset cluster maps
  Object.keys(clusterMap).forEach(k => delete clusterMap[k]);
  Object.keys(clusterColors).forEach(k => delete clusterColors[k]);
  GD.nodes.forEach(n => { adj[n.id] = new Set(); });
  const allE = [...GD.edges, ...GD.kgEdges];
  allE.forEach(e => {
    const s = nid(e.source), t = nid(e.target);
    if (adj[s]) adj[s].add(t);
    if (adj[t]) adj[t].add(s);
  });
  // Virtual namespace edges — nodes sharing a namespace are clustered together
  const nodesByNS = {};
  GD.nodes.forEach(n => {
    const ns = n.namespace || 'default';
    if (!nodesByNS[ns]) nodesByNS[ns] = [];
    nodesByNS[ns].push(n.id);
  });
  Object.values(nodesByNS).forEach(ids => {
    if (ids.length < 2) return;
    const anchor = ids[0];
    ids.slice(1).forEach(id => { adj[anchor].add(id); adj[id].add(anchor); });
  });
  // Virtual primary-tag edges — nodes sharing first tag are clustered together
  const nodesByTag = {};
  GD.nodes.forEach(n => {
    const pt = (n.tags || [])[0];
    if (!pt) return;
    if (!nodesByTag[pt]) nodesByTag[pt] = [];
    nodesByTag[pt].push(n.id);
  });
  Object.values(nodesByTag).forEach(ids => {
    if (ids.length < 2) return;
    const anchor = ids[0];
    ids.slice(1).forEach(id => { adj[anchor].add(id); adj[id].add(anchor); });
  });
  // BFS connected components
  const visited = new Set();
  let cid = 0;
  GD.nodes.forEach(n => {
    if (visited.has(n.id)) return;
    const comp = [];
    const queue = [n.id];
    visited.add(n.id);
    while (queue.length) {
      const cur = queue.shift();
      comp.push(cur);
      (adj[cur] || []).forEach(nb => {
        if (!visited.has(nb)) { visited.add(nb); queue.push(nb); }
      });
    }
    const color = CLUSTER_PALETTE[cid % CLUSTER_PALETTE.length];
    comp.forEach(id => {
      clusterMap[id] = cid;
      clusterColors[cid] = color;
    });
    cid++;
  });
  rebuildLegend();
}

// ── P1: BFS depth-limited neighborhood ──────────────────────────
function bfsNeighbors(startId, maxHops) {
  if (maxHops <= 0 || !fg) return new Set(GD.nodes.map(n => n.id));
  const data = fg.graphData();
  const adj = {};
  GD.nodes.forEach(n => { adj[n.id] = []; });
  data.links.forEach(l => {
    const s = nid(l.source), t = nid(l.target);
    if (!adj[s]) adj[s] = [];
    if (!adj[t]) adj[t] = [];
    adj[s].push(t);
    adj[t].push(s);
  });
  const visited = new Set([startId]);
  const queue = [{ id: startId, hop: 0 }];
  while (queue.length) {
    const { id, hop } = queue.shift();
    if (hop >= maxHops) continue;
    (adj[id] || []).forEach(nb => {
      if (!visited.has(nb)) {
        visited.add(nb);
        queue.push({ id: nb, hop: hop + 1 });
      }
    });
  }
  return visited;
}

// ── P1: Node color by mode ──────────────────────────────────────
function nodeColorFn(n) {
  if (highlightNodes.size > 0) {
    if (highlightNodes.has(n.id)) return '#a78bfa';
    return '#1e2138';
  }
  if (colorMode === 'cluster') {
    return clusterColors[clusterMap[n.id]] || 'rgba(210,218,255,0.88)';
  }
  if (colorMode === 'tag' && n.primary_tag) {
    return tc(n.primary_tag);
  }
  // namespace mode
  if (n.namespace && n.namespace !== 'default') return tc(n.namespace);
  return 'rgba(210,218,255,0.88)';
}

// ── P1: Hover tooltip ───────────────────────────────────────────
function createTooltip() {
  if (tooltipEl) return tooltipEl;
  tooltipEl = document.createElement('div');
  tooltipEl.id = 'graph-tooltip';
  tooltipEl.style.cssText = 'position:fixed;z-index:10000;pointer-events:none;display:none;' +
    'background:rgba(16,16,31,0.95);border:1px solid rgba(167,139,250,0.3);border-radius:8px;' +
    'padding:10px 14px;max-width:300px;font-size:13px;color:#d2daff;' +
    'box-shadow:0 4px 20px rgba(0,0,0,0.5);line-height:1.5;';
  document.body.appendChild(tooltipEl);
  return tooltipEl;
}

function showTooltip(node, x, y) {
  const tt = createTooltip();
  const inDeg = inDegreeMap[node.id] || 0;
  const outDeg = outDegreeMap[node.id] || 0;
  const imp = (node.importance || 0).toFixed(2);
  const ns = node.namespace || 'default';

  while (tt.firstChild) tt.removeChild(tt.firstChild);

  const titleDiv = document.createElement('div');
  titleDiv.style.cssText = 'color:#a78bfa;font-weight:600;margin-bottom:4px;';
  titleDiv.textContent = (node.content || '').slice(0, 40);
  tt.appendChild(titleDiv);

  const metaDiv = document.createElement('div');
  metaDiv.style.cssText = 'font-size:11px;color:#8b95b0;';
  metaDiv.textContent = ns + ' \u00b7 in:' + inDeg + ' out:' + outDeg + ' \u00b7 imp:' + imp;
  tt.appendChild(metaDiv);

  const tags = (node.tags || []);
  if (tags.length) {
    const tagsDiv = document.createElement('div');
    tagsDiv.style.cssText = 'margin-top:4px;font-size:11px;color:#6ee7b7;';
    tagsDiv.textContent = tags.map(t => '#' + t).join(' ');
    tt.appendChild(tagsDiv);
  }

  const snippet = (node.content || '').slice(0, 150);
  if (snippet.length > 40) {
    const snippetDiv = document.createElement('div');
    snippetDiv.style.cssText = 'margin-top:6px;font-size:12px;color:#9ca3af;';
    snippetDiv.textContent = snippet + ((node.content || '').length > 150 ? '\u2026' : '');
    tt.appendChild(snippetDiv);
  }

  tt.style.display = 'block';
  const px = Math.min(x + 15, window.innerWidth - 320);
  const py = Math.min(y + 15, window.innerHeight - 160);
  tt.style.left = px + 'px';
  tt.style.top = py + 'px';
}

function hideTooltip() {
  if (tooltipEl) tooltipEl.style.display = 'none';
}

// ── Node radius from degree + importance ─────────────────────────
function nr(d) {
  const deg = degreeMap[d.id] || 0;
  if (deg >= 10) return 10;
  if (deg >= 6) return 7;
  if (deg >= 3) return 5;
  return 3 + (d.importance || 0.5) * 2;
}

// ── Build graph data for force-graph ─────────────────────────────
function buildGraphData() {
  rebuildDegreeMap();
  // Filter edges by weight threshold
  const memEdges = GD.edges.filter(e => (e.weight || 1) >= minEdgeWeight);
  // Combine memory edges + KG edges (KG always shown)
  const allLinks = [
    ...memEdges.map(e => ({ ...e, _type: 'mem' })),
    ...GD.kgEdges.map(e => ({ ...e, _type: 'kg' }))
  ];
  // Filter nodes by degree
  const nodeSet = new Set();
  allLinks.forEach(e => { nodeSet.add(nid(e.source)); nodeSet.add(nid(e.target)); });
  const filteredNodes = minDegree > 0
    ? GD.nodes.filter(n => (degreeMap[n.id] || 0) >= minDegree)
    : GD.nodes;
  // Ensure all linked nodes are included even with degree filter
  const nodeIds = new Set(filteredNodes.map(n => n.id));
  allLinks.forEach(e => {
    if (!nodeIds.has(nid(e.source))) nodeIds.add(nid(e.source));
    if (!nodeIds.has(nid(e.target))) nodeIds.add(nid(e.target));
  });
  const finalNodes = GD.nodes.filter(n => nodeIds.has(n.id));
  // Time filter — only show nodes created before cutoff
  let timeFiltered = timePct >= 100 ? finalNodes : finalNodes.filter(n => shouldShowNode(n));
  // Namespace filter
  let nodes = timeFiltered, links = allLinks;
  if (activeNS.size > 0) {
    const nsSet = new Set();
    timeFiltered.forEach(n => {
      if (activeNS.has(n.namespace || 'default')) nsSet.add(n.id);
    });
    nodes = timeFiltered.filter(n => nsSet.has(n.id));
    links = allLinks.filter(e => nsSet.has(nid(e.source)) && nsSet.has(nid(e.target)));
  }
  // Ensure links only reference visible nodes
  const visibleIds = new Set(nodes.map(n => n.id));
  links = links.filter(e => visibleIds.has(nid(e.source)) && visibleIds.has(nid(e.target)));
  return { nodes, links };
}

// ── Initialize force-graph (Canvas) ─────────────────────────────
function initGraph() {
  const container = document.getElementById('graph-container');
  if (!container) return;
  // Destroy previous instance
  if (fg) { fg._destructor(); fg = null; }

  // Track mouse for tooltip positioning
  container.addEventListener('mousemove', e => {
    window._lastMouseX = e.clientX;
    window._lastMouseY = e.clientY;
  });
  container.addEventListener('mouseleave', () => {
    hideTooltip();
    if (!selId) clearAll();
  });
  const data = buildGraphData();

  fg = ForceGraph()(container)
    .graphData(data)
    .backgroundColor('#0d0e1b')
    .nodeId('id')
    .nodeVal(n => nr(n))
    .nodeLabel(n => {
      const snip = (n.content || '').slice(0, 80);
      const tags = (n.tags || []).slice(0, 3).map(t => '#' + t).join(' ');
      return snip + (tags ? ' | ' + tags : '');
    })
    .nodeColor(n => nodeColorFn(n))
    .nodeCanvasObject((node, ctx, globalScale) => {
      const r = nr(node);
      const isHigh = highlightNodes.has(node.id);
      const isHover = hoverNode && hoverNode.id === node.id;
      const dimmed = highlightNodes.size > 0 && !isHigh;

      // Glow for highlighted or hub nodes
      if ((isHigh || (degreeMap[node.id] || 0) >= 6) && !dimmed) {
        ctx.save();
        ctx.shadowBlur = isHigh ? 18 : 8;
        ctx.shadowColor = isHigh ? '#a78bfa' : 'rgba(210,218,255,0.4)';
        ctx.beginPath();
        ctx.arc(node.x, node.y, r, 0, Math.PI * 2);
        ctx.fillStyle = 'transparent';
        ctx.fill();
        ctx.restore();
      }

      // Main circle
      ctx.beginPath();
      ctx.arc(node.x, node.y, r, 0, Math.PI * 2);
      let fillColor;
      if (dimmed) {
        fillColor = 'rgba(30,33,56,0.5)';
      } else if (colorMode === 'cluster') {
        fillColor = clusterColors[clusterMap[node.id]] || 'rgba(210,218,255,0.88)';
      } else if (colorMode === 'tag' && node.primary_tag) {
        fillColor = tc(node.primary_tag);
      } else {
        fillColor = (node.namespace && node.namespace !== 'default')
          ? tc(node.namespace) : 'rgba(210,218,255,0.88)';
      }
      ctx.fillStyle = fillColor;
      ctx.fill();

      // Hub ring
      if ((degreeMap[node.id] || 0) >= 4 && !dimmed) {
        ctx.strokeStyle = 'rgba(255,255,255,0.3)';
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      // Hover ring
      if (isHover && !dimmed) {
        ctx.strokeStyle = '#a78bfa';
        ctx.lineWidth = 2;
        ctx.stroke();
      }

      // Label at zoom
      if (globalScale > 1.2 && !dimmed) {
        const label = (node.content || '').slice(0, 20);
        ctx.font = `${Math.max(8, 10 / globalScale)}px -apple-system,sans-serif`;
        ctx.fillStyle = 'rgba(200,204,216,0.8)';
        ctx.textAlign = 'center';
        ctx.fillText(label, node.x, node.y + r + 10 / globalScale);
      }
    })
    .nodeCanvasObjectMode(() => 'replace')
    .linkSource('source')
    .linkTarget('target')
    .linkVisibility(link => {
      if (highlightLinks.size > 0 && !highlightLinks.has(link)) return false;
      return true;
    })
    .linkColor(link => {
      if (highlightLinks.has(link)) return 'rgba(167,139,250,0.9)';
      if (highlightNodes.size > 0) return 'rgba(30,33,56,0.15)';
      if (link._type === 'kg') return 'rgba(167,139,250,0.7)';
      const w = link.weight || 1;
      const alpha = Math.min(0.12 + w * 0.06, 0.5);
      return `rgba(140,155,210,${alpha})`;
    })
    .linkWidth(link => {
      if (highlightLinks.has(link)) return 2.5;
      if (link._type === 'kg') return 1.5;
      return 1;
    })
    .linkLineDash(link => link._type === 'kg' ? [6, 3] : null)
    .linkDirectionalArrowLength(link => link._type === 'kg' ? 8 : 0)
    .linkDirectionalArrowColor(link => 'rgba(167,139,250,0.85)')
    .linkDirectionalArrowRelPos(0.85)
    .linkDirectionalParticles(link => link._type === 'kg' ? 2 : 0)
    .linkDirectionalParticleWidth(3)
    .linkDirectionalParticleColor(() => 'rgba(167,139,250,0.7)')
    .linkDirectionalParticleSpeed(0.008)
    .linkCanvasObjectMode(() => 'replace')
    .linkCanvasObject((link, ctx, globalScale) => {
      // Draw predicate label for KG edges at high zoom
      if (link._type === 'kg' && globalScale > 0.8 && link.predicate) {
        const midX = (link.source.x + link.target.x) / 2;
        const midY = (link.source.y + link.target.y) / 2;
        ctx.save();
        ctx.font = `${Math.max(7, 9 / globalScale)}px -apple-system,sans-serif`;
        ctx.fillStyle = 'rgba(167,139,250,0.7)';
        ctx.textAlign = 'center';
        ctx.fillText(link.predicate, midX, midY - 4 / globalScale);
        ctx.restore();
      }
    })
    .onNodeClick(node => {
      selId = node.id;
      focusNode = node.id; // P1: set focus for depth filtering
      // Compute neighborhood
      const data2 = fg.graphData();
      highlightLinks = new Set();
      const conn = new Set([node.id]);
      data2.links.forEach(l => {
        const s = nid(l.source), t = nid(l.target);
        if (s === node.id) { conn.add(t); highlightLinks.add(l); }
        if (t === node.id) { conn.add(s); highlightLinks.add(l); }
      });
      // Apply depth limit if set
      if (depthLimit > 0) {
        const depthSet = bfsNeighbors(node.id, depthLimit);
        highlightNodes = depthSet;
      } else {
        highlightNodes = conn;
      }
      fg.linkColor(fg.linkColor());
      fg.nodeColor(fg.nodeColor());
      showMemoryDetail(node);
      const entities = extractEntitiesFromNode(node);
      if (entities.length) fetchEntityExtra(entities[0]);
    })
    .onNodeHover(node => {
      hoverNode = node;
      container.style.cursor = node ? 'pointer' : null;
      if (node) {
        showTooltip(node, window._lastMouseX || 0, window._lastMouseY || 0);
        // Always update hover edge highlight (DASH-07)
        highlightLinks = new Set();
        const conn = new Set([node.id]);
        const data2 = fg.graphData();
        data2.links.forEach(l => {
          const s = nid(l.source), t = nid(l.target);
          if (s === node.id) { conn.add(t); highlightLinks.add(l); }
          if (t === node.id) { conn.add(s); highlightLinks.add(l); }
        });
        highlightNodes = conn;
        fg.linkColor(fg.linkColor());
        fg.nodeColor(fg.nodeColor());
      } else {
        hideTooltip();
        if (!selId) clearAll();
      }
    })
    .onBackgroundClick(() => {
      clearAll();
    })
    .linkHoverPrecision(5)
    .warmupTicks(120)
    .cooldownTicks(300)
    .d3AlphaDecay(0.03)
    .d3VelocityDecay(0.3);

  // Auto-fit graph to viewport after simulation settles
  setTimeout(() => { if (fg) fg.zoomToFit(400, 40); }, 3500);

  // Configure force strengths — strong repulsion for readable spread
  const chargeForce = fg.d3Force('charge');
  if (chargeForce) {
    chargeForce.strength(d => {
      const deg = degreeMap[d.id] || 0;
      return deg >= 6 ? -400 : deg >= 3 ? -200 : -100;
    }).distanceMax(600);
  }
  const linkForce = fg.d3Force('link');
  if (linkForce) linkForce.distance(60);
  const centerForce = fg.d3Force('center');
  if (centerForce) centerForce.strength(0.05);
}

function clearAll() {
  selId = null;
  focusNode = null;
  localGraphMode = false;
  const lgBtn = document.getElementById('local-graph-btn');
  if (lgBtn) lgBtn.classList.remove('active');
  highlightNodes = new Set();
  highlightLinks = new Set();
  hideTooltip();
  if (fg) {
    fg.linkColor(fg.linkColor());
    fg.nodeColor(fg.nodeColor());
  }
}

async function refreshGraph() {
  localGraphMode = false;
  document.getElementById('loading').style.display = 'flex';
  try {
    const [gd, st, an, kgr] = await Promise.all([
      fetch(API + '/graph').then(r => r.json()),
      fetch(API + '/stats').then(r => r.json()),
      fetch(API + '/analytics/summary?days=14').then(r => r.json()).catch(() => null),
      fetch(API + '/kg/labels').then(r => r.json()).catch(() => null),
    ]);
    GD.nodes = gd.nodes; GD.edges = gd.edges;
    // Build KG edges from active KG facts
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
    GD.kgEdges = buildKGEdges(gd.nodes, allFacts);

    const totalLinks = gd.meta.total_edges + GD.kgEdges.length;
    document.getElementById('s-nodes').textContent = gd.meta.total_nodes;
    document.getElementById('s-tags').textContent = gd.meta.total_tags;
    document.getElementById('s-edges').textContent = totalLinks;
    document.getElementById('s-decay').textContent = st.decay_candidates ?? 0;
    renderAnalytics(an);
    buildTagTree();
    await buildNSTree();
    await loadKGLabels();
    buildNSChips();
    detectClusters(); // P1: detect connected components
    computeTimeRange(); // P2: compute min/max timestamps
    updateHealthPanel(); // P2: health dashboard
    initGraph();
  } finally {
    document.getElementById('loading').style.display = 'none';
  }
}
