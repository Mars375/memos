# MemOS Codebase Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve MemOS maintainability, API consistency, and performance through incremental, low-risk cleanup and refactors.

**Architecture:** Start with behavior-preserving consistency and validation fixes at the API boundary, then remove cross-module lifecycle anti-patterns and full-scan performance traps, and only then split the largest monoliths. Each phase should leave the test suite greener and the public surface unchanged unless explicitly called out.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, pytest, Chroma/Qdrant/Pinecone storage backends, SQLite-backed subsystems.

---

## Phase 0 — Quick Wins and Safety Net

**Focus:** clean easy debt before structural work.

**Files:**
- Modify: `src/memos/api/routes/knowledge.py`
- Modify: `src/memos/api/routes/admin.py`
- Modify: `src/memos/api/schemas.py`
- Modify: `src/memos/namespaces/acl.py`
- Modify: `src/memos/mcp_hooks.py`
- Modify: `src/memos/cli/commands_memory.py`
- Modify: `src/memos/cli/commands_knowledge.py`
- Modify: `tests/test_api_admin.py`
- Create/Modify: targeted API tests for knowledge/admin routes

- [ ] Normalize API error payloads to `errors.py` helpers and consistent HTTP status codes.
- [ ] Replace `body: dict` request parsing in high-traffic admin/knowledge endpoints with existing or new Pydantic schemas.
- [ ] Remove obvious no-op/dead stubs and inline import clutter.
- [ ] Deduplicate obvious duplicated CLI command entry points.

**Why first:** lowest-risk changes with immediate DX and correctness payoff; creates safer footing for later refactors.

---

## Phase 1 — Remove `memos._kg` Lifecycle Anti-Pattern

**Focus:** make KG a first-class dependency instead of ad-hoc private attribute mutation.

**Files:**
- Modify: `src/memos/core.py`
- Modify: `src/memos/utils.py`
- Modify: `src/memos/brain.py`
- Modify: `src/memos/mcp_server.py`
- Modify: `src/memos/mcp_hooks.py`
- Modify: `src/memos/export_markdown.py`
- Modify: `src/memos/api/__init__.py`
- Test: affected API / MCP / brain tests

- [ ] Introduce explicit KG/KGBridge ownership on `MemOS`.
- [ ] Remove `getattr(memos, "_kg", None)` and `memos._kg = ...` patterns.
- [ ] Keep lazy initialization only if needed behind one explicit helper.

**Why second:** removes hidden coupling that blocks clean routing and MCP cleanup.

---

## Phase 2 — Split `api/routes/knowledge.py`

**Focus:** separate KG, brain, palace, wiki/context concerns.

**Files:**
- Modify: `src/memos/api/routes/knowledge.py`
- Create: `src/memos/api/routes/kg.py`
- Create: `src/memos/api/routes/brain.py`
- Create: `src/memos/api/routes/palace.py`
- Create: `src/memos/api/routes/wiki.py`
- Modify: `src/memos/api/__init__.py`
- Test: route-specific tests

- [ ] Move endpoints without changing URLs.
- [ ] Co-locate request schemas and helpers by route group where useful.
- [ ] Keep app assembly thin and explicit.

**Why here:** after response/schema cleanup, route extraction becomes mostly mechanical and safer.

---

## Phase 3 — Reduce `list_all()` Full-Scan Hotspots

**Focus:** remove avoidable whole-store scans and repeated materialization.

**Files:**
- Modify: `src/memos/core.py`
- Modify: `src/memos/compaction/engine.py`
- Modify: `src/memos/dedup.py`
- Modify: `src/memos/storage/base.py`
- Modify: selected storage backends under `src/memos/storage/`
- Test: compaction, dedup, stats, recall performance-sensitive tests

- [ ] Add more targeted backend query/touch APIs with backward-compatible defaults.
- [ ] Remove repeated `list_all()` within a single operation.
- [ ] Batch touch/update writes where possible.

**Why here:** gives concrete perf wins before touching monolith structure.

---

## Phase 4 — Split `core.py`

**Focus:** turn `MemOS` into a coordinator over focused subsystems.

**Files:**
- Modify: `src/memos/core.py`
- Create: `src/memos/core_store.py` (or package equivalent)
- Create: `src/memos/core_lifecycle.py`
- Create: `src/memos/core_io.py`
- Create: `src/memos/core_versioning.py`
- Create: `src/memos/core_sharing.py`
- Create: `src/memos/core_feedback.py`
- Test: `tests/test_core.py` and related integration coverage

- [ ] Extract by responsibility, preserving public API.
- [ ] Keep constructor wiring explicit.
- [ ] Move one concern at a time, with tests after each extraction.

**Why later:** highest-value architectural change, but easier once API and backend edges are cleaner.

---

## Phase 5 — Split `wiki_living.py`

**Focus:** separate SQLite access, extraction, rendering, and orchestration.

**Files:**
- Modify: `src/memos/wiki_living.py`
- Create package modules for renderer/db/extractor/engine
- Expand tests around wiki rendering, lint, index, and activity log

- [ ] Extract pure helpers first.
- [ ] Preserve on-disk schema and output paths.
- [ ] Increase test coverage before risky movement.

---

## Phase 6 — Clean up `mcp_server.py`

**Focus:** remove giant dispatch/schema duplication.

**Files:**
- Modify: `src/memos/mcp_server.py`
- Create tool registry / dispatch helpers / transport helpers as needed
- Test: MCP handler tests

- [ ] Keep transport behavior unchanged.
- [ ] Make schema definition and handler registration share one source of truth.

---

## Phase 7 — CLI and Secondary Monolith Cleanup

**Focus:** trim parser/command sprawl after domain boundaries are cleaner.

**Files:**
- Modify: `src/memos/cli/_parser.py`
- Modify: `src/memos/cli/commands_memory.py`
- Modify: `src/memos/cli/commands_knowledge.py`
- Create dedicated command modules as needed

- [ ] Move wiki/brain/dedup/benchmark commands into focused modules.
- [ ] Keep CLI command names stable.

---

## Execution Order Summary

1. API consistency + schemas + quick wins
2. `memos._kg` lifecycle cleanup
3. `knowledge.py` route split
4. `list_all()` / batch operation performance cleanup
5. `core.py` split
6. `wiki_living.py` split
7. `mcp_server.py` cleanup
8. CLI/parser cleanup

## Highest-ROI Phase to Start Immediately

**Start now with Phase 0: API response/error consistency and request schema cleanup in `knowledge.py` and `admin.py`.**

Why:
- visible user-facing improvement
- low architectural risk
- removes inconsistent HTTP 200 error responses
- leverages existing `errors.py` and `schemas.py` instead of inventing new abstractions
- creates cleaner boundaries for later route splitting
