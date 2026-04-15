---
phase: 02
plan: 02
subsystem: dashboard-frontend
tags: [graph, tooltip, hover, local-graph, degree-maps, XSS]
key-decisions:
  - DOM construction instead of innerHTML for tooltip to prevent XSS
  - Separate in/out degree display instead of combined degree
  - toggleLocalGraph uses buildGraphData() for full adjacency not filtered fg.graphData()
metrics:
  duration: 5m
  completed: 2026-04-15
---

# Phase 02 Plan 02: Graph Hover & Local Graph Summary

In/out degree maps with fixed hover edge highlighting, safe DOM tooltip with directional degree display, and 1-hop local graph filter button.

## Changes Made

### Task 1: Add in/out degree maps, fix hover highlight, add mouseleave handler
**Commit:** c334402

- **state.js:** Added `inDegreeMap`, `outDegreeMap` objects and `localGraphMode` boolean
- **graph.js `rebuildDegreeMap()`:** Now tracks directional degrees — `outDegreeMap[source]++` and `inDegreeMap[target]++` for every edge
- **graph.js `onNodeHover`:** Fixed DASH-07 bug — removed the `if (!highlightNodes.size || !selId)` guard that suppressed hover highlighting when a node was selected. Hover now ALWAYS highlights the hovered node's edges
- **graph.js `initGraph`:** Added `mouseleave` handler on container to clear tooltip and reset highlights when cursor leaves the graph
- **graph.js `clearAll`:** Resets `localGraphMode=false` and removes `active` class from local-graph-btn

### Task 2: Upgrade tooltip, add local graph button and handler
**Commit:** 58da812

- **graph.js `showTooltip`:** Replaced innerHTML-based tooltip with DOM createElement/textContent construction (XSS prevention). Shows `in:N out:N` separate degree instead of combined. Snippet length 120→150 chars
- **graph.js `refreshGraph`:** Resets `localGraphMode=false` at start to clear local mode on data refresh
- **filters.js:** Added `toggleLocalGraph()` function — toggles local graph mode for focused node, computes 1-hop neighbors from full `buildGraphData()`, calls `fg.graphData()` to swap to local view, or `initGraph()` to restore full view
- **dashboard.html:** Added `⓬` local-graph-btn button in controls div

## Files Modified

| File | Changes |
|------|---------|
| `src/memos/web/js/state.js` | +3 lines: inDegreeMap, outDegreeMap, localGraphMode |
| `src/memos/web/js/graph.js` | rebuildDegreeMap, onNodeHover fix, mouseleave handler, clearAll reset, showTooltip rewrite, refreshGraph reset |
| `src/memos/web/js/filters.js` | +20 lines: toggleLocalGraph() |
| `src/memos/web/dashboard.html` | +1 line: local-graph-btn |

## Deviations from Plan

None — plan executed exactly as written.

## Verification Results

1. `inDegreeMap`/`outDegreeMap` in state.js: count=2 ✅
2. `slice(0, 150)` in graph.js: present (with space) ✅
3. `toggleLocalGraph` in filters.js: present ✅
4. `local-graph-btn` in dashboard.html: present ✅
5. Bug `!highlightNodes.size||!selId` removed: count=0 ✅
6. `mouseleave` in graph.js: present ✅

## Self-Check: PASSED

All 5 modified files exist. Both commits (c334402, 58da812) verified in git log.
