# MemOS Hardening

## What This Is

MemOS is a Memory Operating System for LLM agents — a persistent, queryable memory layer with CLI, REST API, MCP server, and pluggable storage backends (JSON, ChromaDB, Qdrant, Pinecone). This project is a comprehensive hardening initiative: fix security vulnerabilities, refactor god classes into clean modules, resolve performance bottlenecks, achieve professional test coverage, and add missing features to make MemOS production-grade.

## Core Value

MemOS must be **secure by default** — no open API, no broken rate-limiting, no custom crypto, no unvalidated inputs. Everything else (performance, architecture, features) builds on that foundation.

## Requirements

### Validated

- ✓ Pluggable storage backends (JSON, ChromaDB, Qdrant, Pinecone) — existing
- ✓ Hybrid recall (BM25 + semantic) with scoring — existing
- ✓ CLI with full CRUD operations — existing
- ✓ REST API with FastAPI — existing
- ✓ MCP server (stdio + Streamable HTTP) — existing
- ✓ Knowledge graph with temporal triples — existing
- ✓ Memory decay with Ebbinghaus model — existing
- ✓ Namespace isolation with ACL — existing
- ✓ Encryption at rest (XOR cipher, to be replaced) — existing
- ✓ Event bus with WebSocket subscriptions — existing
- ✓ Wiki living pages per entity — existing
- ✓ Memory palace spatial index — existing
- ✓ Brain search (unified memories + wiki + KG) — existing
- ✓ Dedup engine (exact hash + trigram) — existing
- ✓ Versioning with diffs — existing
- ✓ Cross-agent sharing via signed envelopes — existing

### Active

- [ ] Fix rate-limiter middleware (check before handler, not after)
- [ ] Wire Pydantic schemas on all 13 raw `body: dict` endpoints
- [ ] Replace XOR cipher with `cryptography.Fernet` (one-shot migration)
- [ ] Auth enabled by default (startup warning, localhost-only binding)
- [ ] CORS defaults to localhost, not wildcard `*`
- [ ] ACL namespace bypass via empty namespace prevented
- [ ] Refactor MemOS god class (1935L) into composable services/mixins
- [ ] Refactor CLI parser (1171L) into per-command modules
- [ ] Refactor wiki_living.py, mcp_server.py, commands_memory.py (800L+ each)
- [ ] Batch upserts in `recall()` — fix N+1 write pattern
- [ ] Pagination/streaming for `list_all()` and all callers
- [ ] Dedup O(n²) → MinHash approximate similarity
- [ ] Embedding cache: persistent connection pool, not per-op SQLite open
- [ ] Fix dedup race condition on concurrent writes
- [ ] Fix encrypted backend: add HMAC verification for wrong-key detection
- [ ] Fix KG date parsing: reject invalid ISO dates
- [ ] Fix version mismatch (pyproject.toml 1.1.0 vs __init__.py 1.0.0)
- [ ] Eliminate 54 bare `except Exception:` blocks
- [ ] Extract duplicated `_coerce_tags` to shared utility
- [ ] Wire unused Pydantic schemas or delete dead code
- [ ] Initialize `_agent_id` in `__init__`, remove getattr guards
- [ ] Remove self-referential import in `ingest/miner.py`
- [ ] Fix MCP server monkey-patching: init KG/KGBridge in `MemOS.__init__()`
- [ ] Consolidate two conflicting `RateLimiter` classes
- [ ] Add type annotations to API route factory functions
- [ ] NEW: Audit log for all memory mutations (agent_id + timestamp + content hash)
- [ ] NEW: Pagination API on StorageBackend (list with limit/offset/cursor)
- [ ] NEW: ACL `expires_at` enforcement in `_check_acl()`
- [ ] NEW: Backend feature matrix doc + runtime warnings
- [ ] Test coverage: crypto.py, analytics.py, compression.py, cache/, namespaces/
- [ ] Test coverage: API input validation (invalid JSON, type mismatches, overflows)
- [ ] Test coverage: concurrency per backend (Qdrant, Pinecone, encrypted)
- [ ] Test coverage: encryption + versioning interaction
- [ ] Test coverage: multi-namespace adversarial security
- [ ] Add `fail_under = 80` coverage threshold
- [ ] Pin `pinecone-client>=3.0,<4.0`, `chromadb>=0.4,<1.0`

### Out of Scope

- New storage backends (Redis, DynamoDB) — not needed now, address after hardening
- UI/dashboard redesign — functional enough, cosmetic improvements later
- Mobile/native clients — out of scope for a library hardening
- Async-first rewrite of all backends — too disruptive, async wrapper is sufficient
- CI/CD pipeline setup — no CI config detected, separate initiative
- Performance optimization on ARM64/Ollama — hardware constraint, not code issue

## Context

- **Codebase:** Python 3.11+, ~15k LOC across 50+ source files, 77 test files
- **Architecture:** Layered facade pattern with pluggable backends
- **Main pain points:** 1935-line god class, 13 unvalidated API endpoints, broken rate-limiter, custom XOR crypto, 54 silent exception swallowers
- **Environment:** Raspberry Pi 5 (orion-cortex), Docker deployment, Tailscale networking
- **Codebase map:** `.planning/codebase/` (7 documents, refreshed 2026-04-15)

## Constraints

- **Breaking changes:** Allowed — this is a major version bump (→ 2.0.0)
- **Crypto migration:** Full replacement of XOR with Fernet, no dual mode
- **Python version:** 3.11+ minimum (already pinned)
- **No new heavy deps:** Prefer stdlib + existing deps where possible
- **Test threshold:** 80% coverage minimum enforced

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Security first | Broken rate-limiter + no input validation = open attack surface | — Pending |
| Breaking changes OK (→ 2.0.0) | Enables clean refactoring without backward-compat hacks | — Pending |
| Replace XOR entirely | Custom crypto is a liability; Fernet is battle-tested | — Pending |
| Refactor approach: best-fit per module | Mixins for some, services for others — pragmatic over dogmatic | — Pending |
| Fine granularity (8-12 phases) | Many targeted phases for a large cleanup — easier to review and test | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition:**
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone:**
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-15 after initialization*
