# Roadmap: MemOS

## Overview

MemOS v2.2.0 is in production with 1534 passing tests. This roadmap covers three focused phases of improvement: first clearing the maintenance debt that blocks clean releases, then shipping the P1 dashboard features that make the second-brain experience genuinely useful, and finally polishing documentation so developers can onboard without friction.

## Phases

- [ ] **Phase 1: Maintenance** - Clear release blockers and infrastructure debt (version drift, Docker hygiene, orphaned code)
- [ ] **Phase 2: Dashboard P1** - Cluster detection, depth navigation, and rich hover previews for the Canvas force-graph
- [ ] **Phase 3: Documentation Polish** - Golden path README, decision guide for recall APIs, and working integration examples

## Phase Details

### Phase 1: Maintenance
**Goal**: The codebase is clean, releasable, and safe to run in production without silent failures or version confusion
**Depends on**: Nothing (first phase)
**Requirements**: MAINT-01, MAINT-02, MAINT-03, MAINT-04, MAINT-05, MAINT-06
**Success Criteria** (what must be TRUE):
  1. `pyproject.toml` version and `__init__.__version__` are identical — `pip show memos-agent` returns the correct version
  2. Docker Compose pins `chromadb/chroma` and `qdrant/qdrant` to concrete versions — `latest` tag is gone
  3. All services in `docker-compose.yml` have `max-size: 10m, max-file: 3` log limits — SD card is protected
  4. CI matrix passes on Python 3.11, 3.12, and 3.13 — no green-but-missing-version illusion
  5. `ACTIVE.md` reflects commits through April 13, 2026 — no stale state
  6. `src/memos/miner/` is either removed or its unique logic migrated to `src/memos/ingest/` — no orphaned dead code in the repo
**Plans:** 1/2 plans executed
Plans:
- [x] 01-01-PLAN.md — Version sync, Docker pinning, log limits, CI matrix expansion
- [ ] 01-02-PLAN.md — ACTIVE.md update and orphaned miner/ removal

### Phase 2: Dashboard P1
**Goal**: Users can explore the memory graph with meaningful cluster visualization, depth-controlled navigation, and instant node context on hover
**Depends on**: Phase 1
**Requirements**: DASH-01, DASH-02, DASH-03, DASH-04, DASH-05, DASH-06, DASH-07
**Success Criteria** (what must be TRUE):
  1. Nodes are colored by detected community — the force-graph visually separates clusters without manual configuration
  2. A legend shows each detected cluster with its color — the user can orient without inspecting individual nodes
  3. Cluster detection uses existing tags and namespaces as a signal — grouping reflects the user's own organization
  4. A depth slider (1-5 hops) filters the visible graph around the selected node or the full graph — the user can reduce noise for dense graphs
  5. Clicking "Local graph" on a node collapses the view to that node and its direct neighbors — the user can focus without losing the full graph
  6. Hovering any node shows a tooltip with: content snippet (150 chars), tags, namespace, importance score, and in/out degree — the user gets context without clicking
  7. The hovered node's edges are highlighted — the user can trace connections at a glance
**Plans**: TBD
**UI hint**: yes

### Phase 3: Documentation Polish
**Goal**: A developer can go from zero to a working MemOS integration in one sitting using only the README and provided examples
**Depends on**: Phase 2
**Requirements**: DOC-01, DOC-02, DOC-03, DOC-04
**Success Criteria** (what must be TRUE):
  1. The README contains a complete golden path walkthrough (`learn → recall → context_for → wake_up → reinforce/decay`) with runnable code — no guessing required
  2. A "When to use what" section explains the difference between `recall`, `search`, `memory_context_for`, and `memory_recall_enriched` with concrete examples for each
  3. A working Claude Code / MCP integration example exists in the repo — copy-paste produces a functional result
  4. A working OpenClaw / orchestrator integration example exists — agents running on Tachikoma can adopt MemOS without reverse-engineering the MCP server
**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Maintenance | 1/2 | In Progress|  |
| 2. Dashboard P1 | 0/? | Not started | - |
| 3. Documentation Polish | 0/? | Not started | - |
