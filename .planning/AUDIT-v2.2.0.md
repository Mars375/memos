# AUDIT — Milestone v2.2.0

**Date**: 2026-04-15
**Auditeur**: Sisyphus (orchestrateur GSD)
**Scope**: 17 requirements across 3 phases (Maintenance, Dashboard P1, Documentation Polish)

## Verdict: ✅ PASS (after regression fixes)

All 17 requirements verified against live source code. Two regressions found and fixed during audit.

---

## Phase 1 — Maintenance (6 requirements)

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| MAINT-01 | Version sync pyproject.toml + __init__.py | ✅ Fixed | `pyproject.toml: version = "2.2.0"`, `__init__.py: __version__ = "2.2.0"` |
| MAINT-02 | Docker images pinned | ✅ Pass | `docker-compose.yml`: `chromadb/chroma:1.5.7`, `qdrant/qdrant:v1.17.1` |
| MAINT-03 | Log limits on all services | ✅ Pass | 5 services with `max-size: 10m, max-file: 3` |
| MAINT-04 | CI matrix 3.11/3.12/3.13 | ✅ Pass | `.github/workflows/test.yml` line 28: `[3.11, 3.12, 3.13]` |
| MAINT-05 | ACTIVE.md updated | ✅ Fixed | Rewritten to reflect full v2.2.0 milestone completion |
| MAINT-06 | Miner directory removed | ✅ Pass | `src/memos/miner/` absent, no dangling imports |

### Regression Notes

**MAINT-01 REGRESSION (FIXED)**:
- Root cause: Commit `c4b9b8a` ("release: v1.1.0 — hardened & modular") on main overwrote Phase 1 fixes from `eeec861` which were on a separate branch
- `pyproject.toml` was `1.1.0` → fixed to `2.2.0`
- `__init__.py` was `1.0.0` → fixed to `2.2.0`

**MAINT-05 STALE REFERENCES (FIXED)**:
- ACTIVE.md still referenced Phase 1 as "Dernière session" and Phase 2 as "IN PROGRESS"
- Rewritten to reflect all 3 phases complete with full requirement traceability

---

## Phase 2 — Dashboard P1 (7 requirements)

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| DASH-01 | Cluster coloring | ✅ Pass | `graph.js`: connected components → cluster map → color assignment |
| DASH-02 | Dynamic legend | ✅ Pass | `filters.js`: `rebuildLegend()` called on filter change, innerHTML cleared |
| DASH-03 | Tag/NS in tooltip + click filter | ✅ Pass | `graph.js`: tooltip shows tags/NS, `state.js`: seeded filters |
| DASH-04 | Depth slider 1-5 | ✅ Pass | `dashboard.html`: `<input id="depth-slider" min="1" max="5">` |
| DASH-05 | Local graph toggle | ✅ Pass | `state.js`: `localGraphMode`, `filters.js`: `toggleLocalGraph()` |
| DASH-06 | Rich tooltip (degree, tags, NS) | ✅ Pass | `graph.js`: tooltip with in/out degree, tags, namespace |
| DASH-07 | Hover highlight neighbors | ✅ Pass | `graph.js`: `mouseenter` highlight + `mouseleave` reset |

---

## Phase 3 — Documentation Polish (4 requirements)

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| DOC-01 | Golden path in README | ✅ Pass | `README.md` line 65: `## Golden path` — 5-step lifecycle |
| DOC-02 | Recall API comparison guide | ✅ Pass | `README.md` line 156: `## Which recall API should I use?` — table + examples |
| DOC-03 | Claude Code MCP example | ✅ Pass | `examples/claude-code-mcp.md` (118 lines) — config + tool workflows |
| DOC-04 | OpenClaw integration example | ✅ Pass | `examples/openclaw-integration.md` (115 lines) — lifecycle + AGENTS.md |

### Quality Notes (non-blocking)

- **DOC-01 Golden path**: Uses private APIs (`mem._decay.reinforce()`, `mem._store.upsert()`) in step 5 instead of public CLI/MCP interfaces. Cosmetically suboptimal but functionally correct — agents reading the README will understand the concepts.

---

## Summary

| Phase | Total | Pass | Fixed | Fail |
|-------|-------|------|-------|------|
| 1 — Maintenance | 6 | 4 | 2 | 0 |
| 2 — Dashboard P1 | 7 | 7 | 0 | 0 |
| 3 — Documentation | 4 | 4 | 0 | 0 |
| **Total** | **17** | **15** | **2** | **0** |

**Result**: All 17 requirements verified. 2 regressions from branch merge conflict found and fixed during audit.

## Recommendation

Milestone v2.2.0 is ready for archival via `/gsd:complete-milestone v2.2.0`.
