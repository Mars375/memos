---
phase: 02
plan: 01
subsystem: dashboard
tags: [frontend, graph, clustering, canvas, legend]
dependency_graph:
  requires: [state.js globals, force-graph lib]
  provides: [tag/namespace-seeded clusters, dynamic legend, colorMode-aware canvas]
  affects: [graph.js, filters.js, dashboard.css]
tech_stack:
  added: []
  patterns: [virtual adjacency edges, DOM-constructed legend, colorMode branching]
key_files:
  created: []
  modified:
    - src/memos/web/js/graph.js
    - src/memos/web/js/filters.js
    - src/memos/web/dashboard.css
decisions:
  - Virtual edges for namespace/tag use star topology (anchor=node[0]) to keep adjacency sparse
  - Legend capped at 8 cluster entries with "+N more" overflow indicator
  - DOM construction (createElement/textContent) used instead of innerHTML for XSS safety
metrics:
  duration: 3m
  tasks: 2
  files: 3
  completed: "2026-04-15"
---

# Phase 02 Plan 01: Cluster Coloring + Dynamic Legend Summary

Cluster coloring now renders on Canvas via colorMode-aware `nodeCanvasObject`, detectClusters seeds clusters using namespace and primary-tag virtual edges, and a dynamic legend rebuilds on every cluster detection or color mode switch.

## What Changed

### graph.js — detectClusters() upgrade
- **Map reset**: `clusterMap` and `clusterColors` are cleared at the top to prevent stale data on refresh.
- **Virtual namespace edges**: Nodes sharing a namespace get star-topology adjacency links, pulling them into the same BFS component.
- **Virtual primary-tag edges**: Nodes sharing their first tag (`tags[0]`) also get virtual edges, further refining cluster membership.
- **rebuildLegend() call**: Appended at the end so the legend updates after every cluster detection pass.

### graph.js — nodeCanvasObject colorMode fix
- Replaced the hardcoded namespace-only fill block with a `colorMode`-aware branching structure:
  - `cluster` mode → `clusterColors[clusterMap[node.id]]`
  - `tag` mode → `tc(node.primary_tag)`
  - `namespace` mode (default) → original `tc(node.namespace)` behavior
- `nodeColorFn()` was NOT modified — it already handled all modes correctly.

### filters.js — rebuildLegend() + onColorModeChange() hook
- New `rebuildLegend()` function:
  - Clears all legend children via safe DOM manipulation.
  - Rebuilds 3 static edge-type items (memory link, KG relation, highlighted).
  - When `colorMode === 'cluster'`: adds colored dot items for up to 8 clusters, with "+N more" overflow.
- `onColorModeChange()` now calls `rebuildLegend()` after updating the force-graph.

### dashboard.css
- Added `.legend-dot` rule: 10×10px round dot for cluster legend entries.

## Deviations from Plan

None — plan executed exactly as written.

## Verification Results

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| `nodesByNS\|nodesByTag` in graph.js | >= 2 | 8 | PASS |
| `colorMode === 'cluster'` in nodeCanvasObject | matches | matches | PASS |
| `.legend-dot` in CSS | matches | matches | PASS |
| `rebuildLegend` in filters.js | >= 2 | 2 | PASS |
| innerHTML with user data | none | none | PASS |
| No Python/test files touched | true | true | PASS |

## Self-Check: PASSED
