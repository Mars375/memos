# Phase 02: Dashboard P1 - Research

**Researched:** 2026-04-13
**Domain:** force-graph Canvas dashboard (JavaScript/HTML — no framework, served by FastAPI)
**Confidence:** HIGH — source code fully read, force-graph API verified against official docs

---

## Summary

This phase adds three capabilities to an already-functional Canvas force-graph dashboard: community-based cluster coloring with a legend, depth/hop-limited subgraph navigation (including a "Local graph" button), and rich hover tooltips with edge highlighting.

The good news: **nearly all scaffolding is already in place.** The codebase has `clusterMap`, `clusterColors`, `colorMode='cluster'`, `detectClusters()`, `bfsNeighbors()`, `depthLimit`, `focusNode`, `onDepthChange()`, `hoverNode`, `showTooltip()`, `hideTooltip()`, `onNodeHover` wired to `showTooltip`, and `highlightLinks`/`highlightNodes` for edge dimming. The variables, the BFS, the color-mode selector, the depth slider, and the basic tooltip HTML element all exist.

What is **missing or incomplete**: (1) `detectClusters()` uses only graph topology (connected components) — DASH-03 requires tags and namespaces as additional signal; (2) `nodeCanvasObject` in `graph.js` ignores `colorMode` — it always draws by namespace, so `colorMode==='cluster'` has no visual effect; (3) the cluster legend is hard-coded as three static edge-type items and never updated for dynamic clusters; (4) `showTooltip()` shows only 120 chars and no in/out degree split (DASH-06 requires 150 chars, tags, namespace, importance, in-degree, out-degree separately); (5) no "Local graph" button exists in the HTML (DASH-05); (6) `onDepthChange()` uses `highlightNodes` (visual dimming) not actual graph data filtering.

**Primary recommendation:** Work file-by-file in small diffs. Every change is isolated JavaScript in `src/memos/web/js/`. No Python backend changes are needed. No new dependencies are needed.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DASH-01 | Graph auto-detects communities and colors nodes by cluster | `colorMode='cluster'` exists; `detectClusters()` runs BFS components — needs fix in `nodeCanvasObject` to respect `colorMode` |
| DASH-02 | Legend shows detected clusters with their colors | `#graph-legend` HTML exists but is hard-coded; needs dynamic rebuild when clusters change |
| DASH-03 | Clustering uses tags and namespaces as signal | `detectClusters()` uses only topology; needs seeding step that pre-groups by (namespace, primary_tag) before running BFS |
| DASH-04 | Depth slider (1-5 hops) filters visible graph | Slider, `depthLimit`, `bfsNeighbors()`, `onDepthChange()` exist; current impl uses visual dimming only — planner may choose visual dimming or structural filtering |
| DASH-05 | "Local graph" button collapses to node + direct neighbors | No button exists in HTML; requires new button + handler calling `fg.graphData({nodes, links})` with 1-hop subgraph |
| DASH-06 | Hover tooltip: snippet (150 chars), tags, namespace, importance, in/out degree | `showTooltip()` exists with basic content; needs: 150-char snippet, distinct in/out degree counts, tags display |
| DASH-07 | Hovered node edges highlighted | `onNodeHover` already populates `highlightLinks`; `linkVisibility` already hides non-highlighted links when `highlightLinks.size > 0` — functionally complete; one bug to fix (hover suppressed when selId set) |
</phase_requirements>

---

## Standard Stack

### Core (already in use — no additions needed)

| Library | Version in use | Purpose | Notes |
|---------|---------------|---------|-------|
| force-graph | 1.43.5 (CDN unpkg) | Canvas force-directed graph | Current npm latest: 1.51.2 — project pins 1.43.5 on CDN, do not upgrade |
| chart.js | 4.4.8 (CDN) | Analytics charts | Not relevant to this phase |
| Vanilla JS | ES2020+ | All dashboard logic | No framework, no build step |

**No new dependencies.** All changes are pure JavaScript edits to existing files in `src/memos/web/js/`.

### Version Note

The project loads force-graph from `https://unpkg.com/force-graph@1.43.5/dist/force-graph.min.js`. The library's current npm version is **1.51.2** but the pinned CDN version must not be changed — the existing Canvas rendering code was written against 1.43.5's API which is stable.

---

## Architecture Patterns

### Existing File Structure (do not reorganize)

```
src/memos/web/
+-- dashboard.html       # Single-page app shell — HTML structure and script tags
+-- dashboard.css        # All styles
+-- js/
    +-- state.js         # Global vars: GD, fg, clusterMap, clusterColors, colorMode, depthLimit, focusNode, tooltipEl
    +-- utils.js         # tc(), escHtml(), nid(), nr()
    +-- api.js           # refreshGraph(), addMemory(), forgetSelected(), buildKGEdges() — calls detectClusters() and initGraph()
    +-- graph.js         # initGraph(), nodeColorFn(), nodeCanvasObject(), onNodeHover, onNodeClick
    +-- filters.js       # detectClusters(), bfsNeighbors(), onDepthChange(), onColorModeChange(), onSearch()
    +-- controls.js      # Zoom, modals, time-travel, setRib()
    +-- panels.js        # showTooltip(), hideTooltip(), showMemoryDetail(), showImpactAnalysis()
    +-- sidebar.js       # Tag tree, NS tree, KG labels
    +-- wiki.js          # Living wiki view
    +-- palace.js        # Memory palace view
```

### Call Order (important for sequencing)

`refreshGraph()` (api.js) calls in order:
1. Fetch `/api/v1/graph` + `/api/v1/stats` + KG facts
2. `detectClusters()` — must be called AFTER `GD.nodes` and `GD.edges` are set
3. `computeTimeRange()`, `computeLayers()`, `updateHealthPanel()`
4. `initGraph()` — creates the force-graph instance using `buildGraphData()`, which reads `colorMode`, `clusterMap`, `clusterColors`

Implication: cluster detection and color assignment must be complete before `initGraph()` is called.

### Pattern: Canvas Color Rendering — The Core Bug (DASH-01)

`nodeCanvasObject` in `graph.js` is set to `'replace'` mode and draws the full node manually. **The critical bug:** the canvas draw code does not branch on `colorMode`. It always reads `node.namespace` for color. The fix is to add a `colorMode` branch in the canvas draw code, mirroring what `nodeColorFn()` already does:

```javascript
// In nodeCanvasObject, replace the fill color selection block (lines 136-143 of graph.js):
let fillColor;
if (dimmed) {
  fillColor = 'rgba(30,33,56,0.5)';
} else if (colorMode === 'cluster') {
  fillColor = clusterColors[clusterMap[node.id]] || 'rgba(210,218,255,0.88)';
} else if (colorMode === 'tag' && node.primary_tag) {
  fillColor = tc(node.primary_tag);
} else if (colorMode === 'layer') {
  fillColor = LAYER_COLORS[node.layer !== undefined ? node.layer : 2] || '#64748b';
} else {
  // namespace mode (default)
  fillColor = (node.namespace && node.namespace !== 'default')
    ? tc(node.namespace) : 'rgba(210,218,255,0.88)';
}
ctx.fillStyle = fillColor;
```

### Pattern: Cluster Detection with Tag/Namespace Signal (DASH-03)

The current `detectClusters()` uses pure BFS connected-components on graph topology. To incorporate tags/namespace as signal without breaking the algorithm, add virtual adjacency edges before BFS.

**Recommended approach — pre-seeding with virtual edges:**

Before BFS, create temporary virtual edges connecting nodes that share the same namespace AND/OR the same primary tag. Then run BFS on the combined adjacency (real edges + virtual namespace/tag edges). This groups semantically-related nodes even when they have no memory-edge connections.

The adjacency set `adj` is already built in `detectClusters()`. The change is to extend it before the BFS loop:

```javascript
// After building real-edge adjacency, add virtual namespace signal:
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

// Add virtual primary-tag signal:
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
```

Also add a reset of maps at the top of `detectClusters()` to prevent stale entries after node deletions:

```javascript
Object.keys(clusterMap).forEach(k => delete clusterMap[k]);
Object.keys(clusterColors).forEach(k => delete clusterColors[k]);
```

**Why connected components over Louvain/Leiden:** The codebase already has BFS. Louvain would require a new JS library (~50KB) or ~200 lines of custom code. For expected graph sizes (<1000 nodes), BFS with tag/namespace seeding produces meaningful clusters and is deterministic. Leiden/Louvain optimize modularity at scale — overkill here.

### Pattern: Dynamic Cluster Legend (DASH-02)

The `#graph-legend` div is hard-coded with three static items. It must be rebuilt dynamically when clusters are detected and when `colorMode` changes.

Add a `rebuildLegend()` function in `filters.js` (or a new `legend.js`):

```javascript
function rebuildLegend() {
  const legend = document.getElementById('graph-legend');
  if (!legend) return;
  // Clear and rebuild using DOM methods (avoids XSS risk of innerHTML with user data)
  while (legend.firstChild) legend.removeChild(legend.firstChild);

  // Static edge-type items
  const edgeItems = [
    { cls: 'mem', label: 'Memory link' },
    { cls: 'kg', label: 'KG relation' },
    { cls: 'highlight', label: 'Highlighted' },
  ];
  edgeItems.forEach(({ cls, label }) => {
    const item = document.createElement('div');
    item.className = 'legend-item';
    const line = document.createElement('div');
    line.className = 'legend-line ' + cls;
    const span = document.createElement('span');
    span.textContent = label;
    item.appendChild(line);
    item.appendChild(span);
    legend.appendChild(item);
  });

  // Dynamic cluster items (only when colorMode === 'cluster')
  if (colorMode === 'cluster') {
    const clusterIds = [...new Set(Object.values(clusterMap))];
    const display = clusterIds.slice(0, 8); // cap at 8 for space
    display.forEach(cid => {
      const color = clusterColors[cid] || '#64748b';
      const item = document.createElement('div');
      item.className = 'legend-item';
      const dot = document.createElement('div');
      dot.className = 'legend-dot';
      dot.style.background = color;
      const span = document.createElement('span');
      span.textContent = 'Cluster ' + (cid + 1);
      item.appendChild(dot);
      item.appendChild(span);
      legend.appendChild(item);
    });
    if (clusterIds.length > 8) {
      const more = document.createElement('div');
      more.className = 'legend-item';
      more.style.cssText = 'color:var(--text2);font-size:.8em';
      const span = document.createElement('span');
      span.textContent = '+' + (clusterIds.length - 8) + ' more';
      more.appendChild(span);
      legend.appendChild(more);
    }
  }
}
```

Call `rebuildLegend()` from: (1) end of `detectClusters()`, and (2) `onColorModeChange()`.

Add `.legend-dot` to `dashboard.css`:
```css
.legend-dot { width:10px; height:10px; border-radius:50%; flex-shrink:0; }
```

### Pattern: Depth Filtering — Visual vs. Structural

**Current behavior:** `onDepthChange()` sets `highlightNodes` (visual dimming set). Non-neighbor nodes remain rendered but dimmed. This satisfies DASH-04 at a visual level and is the correct pattern to keep — it matches the existing click-highlight behavior.

**DASH-05 "Local graph" button** requires structural filtering — actually removing non-neighbor nodes and links from `fg.graphData()`. This is distinct from depth dimming.

**Recommended pattern for DASH-05:**

Add a `localGraphMode` boolean to `state.js`. Add a `toggleLocalGraph()` function:

```javascript
// state.js addition
let localGraphMode = false;

// In filters.js or a new file:
function toggleLocalGraph() {
  if (!focusNode) return; // no node selected — button should be disabled
  localGraphMode = !localGraphMode;
  document.getElementById('local-graph-btn').classList.toggle('active', localGraphMode);
  if (localGraphMode) {
    const neighbors = bfsNeighbors(focusNode, 1); // direct neighbors only
    const allData = buildGraphData();             // full filtered dataset
    const localNodes = allData.nodes.filter(n => neighbors.has(n.id));
    const localLinks = allData.links.filter(l =>
      neighbors.has(nid(l.source)) && neighbors.has(nid(l.target))
    );
    fg.graphData({ nodes: localNodes, links: localLinks });
    setTimeout(() => { if (fg) fg.zoomToFit(400, 40); }, 400);
  } else {
    initGraph(); // full rebuild restores all nodes
  }
}
```

**Button placement — in `#controls` in dashboard.html:**

```html
<button class="cb" id="local-graph-btn" title="Local graph — neighbors only"
        onclick="toggleLocalGraph()" style="margin-top:6px">&#x25CE;</button>
```

The button must be disabled/grayed when no node is selected (`!focusNode`). Add a style update in `clearAll()`:
```javascript
const lgBtn = document.getElementById('local-graph-btn');
if (lgBtn) lgBtn.style.opacity = focusNode ? '1' : '0.4';
```

**Important:** `exitLocalGraph()` / `initGraph()` must also be called in `refreshGraph()` to prevent stale local view after auto-refresh. Simplest path: always reset `localGraphMode = false` at the start of `refreshGraph()`.

### Pattern: In/Out Degree for Tooltip (DASH-06)

Current `degreeMap` is undirected (counts all edge endpoints). For in/out degree, two new maps are needed.

Add to `state.js`:
```javascript
const inDegreeMap = {};
const outDegreeMap = {};
```

Update `rebuildDegreeMap()` in `graph.js`:
```javascript
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
```

Updated `showTooltip()` in `panels.js` — using safe DOM construction:

```javascript
function showTooltip(node, x, y) {
  const tt = createTooltip();
  const inDeg = inDegreeMap[node.id] || 0;
  const outDeg = outDegreeMap[node.id] || 0;
  const imp = (node.importance || 0).toFixed(2);
  const ns = node.namespace || 'default';

  // Safe DOM construction — no innerHTML with user data
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
    snippetDiv.textContent = snippet + (node.content.length > 150 ? '\u2026' : '');
    tt.appendChild(snippetDiv);
  }

  tt.style.display = 'block';
  const px = Math.min(x + 15, window.innerWidth - 320);
  const py = Math.min(y + 15, window.innerHeight - 160);
  tt.style.left = px + 'px';
  tt.style.top = py + 'px';
}
```

### Pattern: Edge Highlighting on Hover (DASH-07)

**Functionally already implemented.** In `onNodeHover` (graph.js lines 300-323):
- Sets `highlightLinks` to edges adjacent to hovered node
- Sets `highlightNodes` to neighboring node IDs
- Calls `fg.linkColor()` and `fg.nodeColor()` to trigger re-render

In `linkVisibility` (graph.js lines 196-199), non-highlighted links are hidden when `highlightLinks.size > 0`.

**One bug to fix:** The hover handler has this condition (lines 307-308):
```javascript
if (!highlightNodes.size || !selId) {
```

When a node was previously clicked (`selId` is set), hover highlighting is skipped. DASH-07 requires hover to always highlight edges. The fix is to evaluate hover separately from click state — simplest approach: always run the hover-highlight block regardless of `selId`.

```javascript
// Replace the condition with unconditional execution when no active click highlight:
// (Only skip if the clicked node's highlight is still active AND user is hovering same area)
if (node) {
  showTooltip(node, window._lastMouseX || 0, window._lastMouseY || 0);
  // Always update hover edge highlight
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
}
```

Note: this means clicking a node and then hovering a different node will shift the highlight to the hovered node. This is correct behavior for DASH-07.

### Anti-Patterns to Avoid

- **Calling `initGraph()` to re-render color changes:** `initGraph()` destroys and recreates the force-graph instance, losing all node positions. For color-only updates, use `fg.nodeColor(fg.nodeColor())` and `fg.nodeCanvasObject(fg.nodeCanvasObject())` to trigger re-paint without full reset.
- **Adding Louvain/community detection library:** Not needed. BFS with tag/namespace seeding produces good results at expected graph sizes. Adding a library adds a CDN dependency and ~50KB page load.
- **Using innerHTML with user data:** The security hook in this project flags this. Use DOM construction methods (`createElement`, `textContent`) for user-supplied content. `innerHTML` is acceptable only for static template strings with no user data.
- **Modifying `GD.nodes` or `GD.edges` for local graph mode:** These are the source-of-truth arrays. Modify only `fg.graphData()` for local view; `GD` must remain intact for `exitLocalGraph()` to restore.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Community detection at scale | Louvain/Leiden implementation | BFS + tag/namespace seeding | Graph sizes (<1000 nodes) don't justify modularity optimization; BFS already in codebase |
| Canvas tooltip positioning | Custom positioning engine | Extend current `Math.min(x+15, width-320)` pattern | Already works; just extend content |
| Color palette assignment | Custom hash function | Existing `tc()` in utils.js or `CLUSTER_PALETTE` | Both exist and used for tags/namespaces |
| Force simulation wiring | D3-force custom setup | `fg.d3Force()` API on existing instance | Already wired in `initGraph()` with charge/link/center forces |

---

## Common Pitfalls

### Pitfall 1: nodeCanvasObject ignores colorMode

**What goes wrong:** Switching the color-mode selector to "Cluster" has no visual effect even after `detectClusters()` runs correctly.

**Why it happens:** `nodeColorFn()` branches on `colorMode` correctly. But `nodeCanvasObjectMode` is set to `'replace'` — the custom canvas draw code completely overrides default rendering, and that code hard-codes namespace color at lines 138-142 of `graph.js`.

**How to avoid:** Always update both `nodeColor` function AND the fill logic inside `nodeCanvasObject` when adding a new color mode.

### Pitfall 2: initGraph() resets all node positions

**What goes wrong:** Calling `initGraph()` to "refresh" the graph after a color-mode change causes all nodes to jump back to random starting positions and re-run the force simulation.

**Why it happens:** `initGraph()` calls `fg._destructor()` and creates a brand new ForceGraph instance. The simulation re-runs from scratch.

**How to avoid:** For visual-only changes (color, highlight), use reactive update:
- Color-only: `fg.nodeColor(fg.nodeColor())` triggers re-paint
- Custom draw update: `fg.nodeCanvasObject(fg.nodeCanvasObject())`
- Link color: `fg.linkColor(fg.linkColor())`
- Graph data change (add/remove nodes): `fg.graphData({nodes, links})` preserves existing positions for retained nodes

### Pitfall 3: Cluster legend overflows on small screens

**What goes wrong:** If the graph has 15+ connected components, the legend renders 15+ color chips and overflows the `#graph-legend` container, overlapping graph controls.

**How to avoid:** Cap cluster legend at 8-10 entries, show "+N more" label. Add `max-height` and `overflow-y: auto` to `#graph-legend` in CSS if needed.

### Pitfall 4: Hover tooltip persists when mouse leaves graph

**What goes wrong:** If the mouse moves quickly from a node to outside the graph container, `onNodeHover(null)` may not fire. The tooltip stays visible indefinitely.

**Why it happens:** force-graph's hover detection relies on `mousemove` events within the canvas. Fast mouse movement to outside the container skips the null-node event.

**How to avoid:** Add a `mouseleave` listener on `#graph-container` in `initGraph()`:
```javascript
container.addEventListener('mouseleave', () => {
  hideTooltip();
  if (!selId) clearAll();
});
```

### Pitfall 5: bfsNeighbors uses fg.graphData() — stale after local-graph mode

**What goes wrong:** After applying a local-graph view (structurally filtered), `bfsNeighbors()` called on the filtered graph returns fewer hops than expected, because it uses `fg.graphData().links` (the filtered set) not `GD.edges`.

**Why it happens:** `bfsNeighbors()` in `filters.js` line 44 calls `fg.graphData()` — which returns whatever data was last pushed to the instance.

**How to avoid:** For the `toggleLocalGraph()` implementation, compute BFS using `buildGraphData().links` (which reads from `GD`) before calling `fg.graphData()` to apply the filter. Never call `bfsNeighbors()` after `fg.graphData()` has been structurally filtered.

### Pitfall 6: detectClusters() accumulates stale entries

**What goes wrong:** After `refreshGraph()`, `detectClusters()` adds new entries to `clusterMap` and `clusterColors` but old entries accumulate if node IDs change (e.g., after `forgetSelected()` deletes a node). Orphaned entries cause stale colors.

**How to avoid:** Reset the maps at the start of `detectClusters()`:
```javascript
Object.keys(clusterMap).forEach(k => delete clusterMap[k]);
Object.keys(clusterColors).forEach(k => delete clusterColors[k]);
```

---

## Code Examples

### Verified: force-graph nodeColor reactive update (no full reset)

```javascript
// Source: force-graph README / graph.js existing pattern (lines 291-294)
// Triggers re-paint of node colors without destroying the instance
fg.linkColor(fg.linkColor());
fg.nodeColor(fg.nodeColor());
// For custom canvas draw updates:
fg.nodeCanvasObject(fg.nodeCanvasObject());
```

### Verified: force-graph structural graph data update

```javascript
// Source: force-graph README — graphData() setter
// Retains positions of nodes with matching IDs
fg.graphData({ nodes: filteredNodes, links: filteredLinks });
```

### Verified: onNodeHover callback signature

```javascript
// Source: force-graph README
// node is the hovered node object, or null when mouse leaves all nodes
.onNodeHover(node => {
  hoverNode = node;
  container.style.cursor = node ? 'pointer' : null;
  if (node) {
    showTooltip(node, window._lastMouseX || 0, window._lastMouseY || 0);
    // populate highlightLinks...
  } else {
    hideTooltip();
    if (!selId) clearAll();
  }
})
```

### Verified: linkVisibility for edge highlighting

```javascript
// Source: graph.js lines 196-199 (existing, confirmed working)
.linkVisibility(link => {
  if (highlightLinks.size > 0 && !highlightLinks.has(link)) return false;
  return true;
})
```

---

## State of the Art

| Old Approach | Current Approach | Status | Impact |
|--------------|------------------|--------|--------|
| SVG graphs (D3, Sigma) | Canvas force-graph | Already using Canvas | Canvas has no DOM per node — tooltip must be a positioned div outside canvas |
| Louvain community detection | BFS connected components | BFS is the right choice at this scale | No JS Louvain library needed |
| initGraph() for all updates | Reactive fg.nodeColor() / fg.graphData() | Must use reactive updates for color changes | Prevents simulation restart |

---

## Open Questions

1. **DASH-04: depth as visual dim vs. structural filter**
   - What we know: Current `onDepthChange()` dims non-neighbors. DASH-04 says "filters visible graph" which could mean structural or visual.
   - Recommendation: Implement as visual dimming (current pattern) since it preserves graph context and matches existing highlight patterns. DASH-05 handles structural filtering via the Local Graph button.

2. **DASH-03: namespace as cluster signal — strength**
   - What we know: Star-topology virtual edges will force all nodes in the same namespace into one component regardless of graph topology.
   - Recommendation: Only add virtual namespace edges if the namespace has 3+ nodes AND those nodes have no existing edges connecting them. This prevents namespace from overriding meaningful topology when nodes are already connected across namespaces.

3. **"Local graph" button — state persistence on refresh**
   - What we know: `exitLocalGraph()` calls `initGraph()` which rebuilds from `GD` arrays.
   - Recommendation: Reset `localGraphMode = false` at the start of `refreshGraph()`. Always exit local mode on auto-refresh. Simpler and predictable.

---

## Environment Availability

Step 2.6: SKIPPED — no external tool dependencies. All changes are static JavaScript files served by the existing FastAPI static file mount. No build step, no npm install, no CLI tooling required.

---

## Validation Architecture

`nyquist_validation` is set to `false` in `.planning/config.json`. This section is skipped.

---

## Project Constraints (from CLAUDE.md)

These directives apply to all work in this phase:

- **No CommonJS:** ES Modules only. Dashboard JS uses vanilla globals (no module system) — maintain current pattern, do not add `type="module"` or import statements to dashboard HTML.
- **No jQuery, no moment.js, no lodash:** Confirmed — existing code uses only native DOM APIs. Do not add any of these.
- **Async/await everywhere:** Not directly applicable to Canvas callbacks (synchronous), but any new fetch calls must use async/await.
- **Max ~40 lines per function:** Existing `initGraph()` violates this (350 lines) — pre-existing tech debt, do not fix in this phase. New functions added in this phase should respect the 40-line guidance.
- **Ask before adding a new dependency:** This phase adds zero new dependencies.
- **Prefer native browser/Node APIs for simple use cases:** Confirmed — all implementations use native DOM and Canvas APIs.
- **Plan first, implement focused minimal changes:** The planner will sequence tasks. Each task should be a single-file edit with a clear scope.

---

## Sources

### Primary (HIGH confidence)
- Full source read: `src/memos/web/js/graph.js` — Canvas draw code, force-graph init, onNodeHover, onNodeClick
- Full source read: `src/memos/web/js/filters.js` — detectClusters(), bfsNeighbors(), onDepthChange()
- Full source read: `src/memos/web/js/panels.js` — showTooltip(), showMemoryDetail()
- Full source read: `src/memos/web/js/state.js` — all global variables
- Full source read: `src/memos/web/js/api.js` — refreshGraph() call order
- Full source read: `src/memos/web/dashboard.html` — existing HTML structure, legend, controls
- force-graph README (GitHub WebFetch): confirmed nodeColor, nodeCanvasObject, onNodeHover, linkVisibility, graphData() API signatures
- npm registry: force-graph latest = 1.51.2; project pins 1.43.5

### Secondary (MEDIUM confidence)
- force-graph API behavioral notes (WebFetch from GitHub README) — confirmed callback signatures match code in use

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies, existing library confirmed via source
- Architecture: HIGH — full source read, all patterns verified against existing working code
- Pitfalls: HIGH — derived from direct code inspection, not guesswork
- Community detection approach: HIGH — BFS is already in codebase; tag/namespace seeding is a standard pattern for small semantic graphs

**Research date:** 2026-04-13
**Valid until:** 2026-10-13 (force-graph API is stable; pinned version will not change)
