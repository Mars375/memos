# Roadmap: MemOS Hardening

## Overview

MemOS Hardening transforms a working but vulnerable memory system into a production-grade 2.0.0 release. The journey starts by closing security holes (broken rate-limiter, unvalidated endpoints, custom crypto), then fixes bugs that would mask issues during later refactoring, cleans up code quality noise (54 bare excepts, dead code), restructures the architecture (god class decomposition, module splits), optimizes performance (N+1 writes, pagination, dedup), adds missing features (audit log, ACL expiration), expands test coverage on the now-stable codebase, and finishes with a coverage threshold gate and final hardening.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: API Security Hardening** - Fix rate-limiter, wire Pydantic validation, lock down auth/CORS/binding defaults
- [ ] **Phase 2: Crypto and ACL Security** - Replace XOR with Fernet, migrate encrypted data, prevent ACL namespace bypass
- [ ] **Phase 3: Bug Fixes** - Fix dedup races, encrypted backend HMAC, KG date parsing, version mismatch, pseudo-streaming, unbounded feedback
- [ ] **Phase 4: Code Quality Cleanup** - Eliminate bare excepts, extract shared utils, wire or delete dead schemas, fix imports, pin dependencies
- [ ] **Phase 5: Core Architecture Decomposition** - Break MemOS god class into focused services, fix monkey-patching, consolidate rate-limiters, reduce hub deps
- [ ] **Phase 6: Module Decomposition** - Split CLI parser, wiki_living, mcp_server, and commands_memory into focused modules
- [ ] **Phase 7: Performance Optimization** - Batch recall upserts, add pagination to StorageBackend, optimize dedup with MinHash, pool embedding cache
- [ ] **Phase 8: New Features** - Add audit log, streaming pagination API, ACL expiration enforcement, backend feature matrix
- [ ] **Phase 9: Test Coverage Expansion** - Add tests for untested modules, API validation, concurrency, encryption+versioning, adversarial security
- [ ] **Phase 10: Final Hardening** - Enforce 80% coverage threshold, verify all hardening goals met

## Phase Details

### Phase 1: API Security Hardening
**Goal**: The API rejects malformed, unauthorized, and over-rate requests before they reach business logic
**Depends on**: Nothing (first phase)
**Requirements**: SEC-01, SEC-02, SEC-05, SEC-06, SEC-07, SEC-09, SEC-10, SEC-11
**Success Criteria** (what must be TRUE):
  1. A request exceeding rate limits receives 429 BEFORE the handler executes (no side effects)
  2. All 13 POST endpoints reject payloads missing required fields or with wrong types (Pydantic validation errors)
  3. MCP serve fallback uses 127.0.0.1 (not 0.0.0.0); REST serve already correct. Startup logs a warning when no API keys are configured
  4. MCP CORS rejects non-localhost origins by default (REST API has no CORS — more secure)
  5. SecretMaskingFilter installed on pinecone_backend logger (defense-in-depth; keys already never logged)
**Plans**: 3 plans
Plans:
- [ ] 01-01-PLAN.md — Fix rate-limiter, simplify hmac, add auth warning (SEC-01, SEC-05, SEC-11)
- [ ] 01-02-PLAN.md — Wire Pydantic models to all 13 POST endpoints (SEC-02)
- [ ] 01-03-PLAN.md — Fix MCP binding fallback, MCP CORS, key masking filter, sanitization toggle coherence (SEC-06, SEC-07, SEC-09, SEC-10)

### Phase 2: Crypto and ACL Security
**Goal**: All data at rest uses battle-tested encryption, and namespace isolation cannot be bypassed
**Depends on**: Phase 1
**Requirements**: SEC-03, SEC-04, SEC-08
**Success Criteria** (what must be TRUE):
  1. New encrypted memories use Fernet (AES-128-CBC + HMAC), not XOR cipher
  2. A migration command converts all existing XOR-encrypted data to Fernet format in one pass
  3. Attempting to access any namespace with an empty namespace string while agent_id is set raises a clear permission error
**Plans**: TBD

### Phase 3: Bug Fixes
**Goal**: Known bugs that could mask issues or corrupt data during later refactoring are resolved
**Depends on**: Phase 2
**Requirements**: BUG-01, BUG-02, BUG-03, BUG-04, BUG-05, BUG-06
**Success Criteria** (what must be TRUE):
  1. Two concurrent `learn()` calls with identical content do not produce duplicate entries (dedup is race-safe)
  2. Decrypting with the wrong key raises a clear error instead of returning garbage data
  3. `kg_add_fact()` with an invalid date like "2025-99-99" returns a validation error, not silent success
  4. `memos.__version__` and pyproject.toml report the same version (single source of truth via importlib.metadata)
  5. `feedback_stats()` uses a bounded query instead of loading 1M records
**Plans**: TBD

### Phase 4: Code Quality Cleanup
**Goal**: The codebase has consistent error handling, no dead code, and clean imports -- reducing noise for the architecture refactoring ahead
**Depends on**: Phase 3
**Requirements**: QUAL-01, QUAL-02, QUAL-03, QUAL-04, QUAL-05, QUAL-06, QUAL-07, QUAL-08, QUAL-09
**Success Criteria** (what must be TRUE):
  1. Zero bare `except Exception:` blocks remain -- all 54 replaced with specific types and logging
  2. `_coerce_tags` exists in exactly one location (shared utility) and all 4 former copies import it
  3. Every Pydantic schema in schemas.py is either wired to a route or deleted
  4. All API route factory functions have full type annotations
  5. `pinecone-client` and `chromadb` have upper-bound version pins in pyproject.toml
**Plans**: TBD

### Phase 5: Core Architecture Decomposition
**Goal**: The MemOS god class is a thin facade under 300 lines, composing focused service objects
**Depends on**: Phase 4
**Requirements**: ARCH-01, ARCH-06, ARCH-07, ARCH-08
**Success Criteria** (what must be TRUE):
  1. `core.py` is under 300 lines; `MemOS` delegates to focused service objects (e.g., MemoryStore, MemoryRecall, MemoryVersioning)
  2. KnowledgeGraph and KGBridge are proper attributes initialized in `MemOS.__init__()` -- no monkey-patching anywhere
  3. A single `RateLimiter` class exists (the auth.py sliding-window version is removed)
  4. Modules that previously imported `MemOS` directly now depend on protocol/interface classes
**Plans**: TBD

### Phase 6: Module Decomposition
**Goal**: The four remaining 800+ line modules are split into focused, single-responsibility files
**Depends on**: Phase 5
**Requirements**: ARCH-02, ARCH-03, ARCH-04, ARCH-05
**Success Criteria** (what must be TRUE):
  1. CLI parser is split into per-command modules (no single file over 300 lines for parser definitions)
  2. wiki_living.py is split into data, logic, and rendering modules
  3. mcp_server.py is split into tool definitions, dispatch logic, and transport modules
  4. commands_memory.py is split by operation type (CRUD, search, maintenance)
**Plans**: TBD

### Phase 7: Performance Optimization
**Goal**: Read and write paths scale to large memory stores without N+1 queries or full-table scans
**Depends on**: Phase 6
**Requirements**: PERF-01, PERF-02, PERF-03, PERF-04, PERF-05, PERF-06, PERF-07
**Success Criteria** (what must be TRUE):
  1. `recall()` with 50 results triggers one batch upsert call, not 50 individual upserts
  2. `StorageBackend` ABC has a `list(limit, offset)` method and all 8 callers of `list_all()` use paginated iteration
  3. Dedup engine uses MinHash for approximate similarity (O(n) per check, not O(n^2))
  4. Embedding cache uses a persistent SQLite connection pool (no per-operation open/close)
  5. Wiki living supports incremental delta-based updates (not full re-parse on every change)
**Plans**: TBD

### Phase 8: New Features
**Goal**: MemOS gains audit trail, streaming pagination, ACL expiration, and backend documentation needed for production use
**Depends on**: Phase 7
**Requirements**: FEAT-01, FEAT-02, FEAT-03, FEAT-04
**Success Criteria** (what must be TRUE):
  1. Every learn/delete/prune/consolidate event is recorded in an audit log with agent_id, timestamp, and content hash
  2. StorageBackend supports streaming iterator protocol for large result sets
  3. An ACL grant with `expires_at` in the past is denied; expired permissions no longer grant access
  4. A `docs/BACKENDS.md` feature matrix exists and runtime warnings fire for unsupported feature+backend combinations
**Plans**: TBD

### Phase 9: Test Coverage Expansion
**Goal**: The stabilized codebase has comprehensive test coverage for all critical paths, edge cases, and adversarial scenarios
**Depends on**: Phase 8
**Requirements**: TEST-01, TEST-02, TEST-03, TEST-04, TEST-05, TEST-06, TEST-07, TEST-08, TEST-09
**Success Criteria** (what must be TRUE):
  1. Tests exist and pass for crypto.py, analytics.py, compression.py, cache/embedding_cache.py, and namespaces/acl.py
  2. Parametrized API tests cover invalid JSON, type mismatches, and oversized payloads for all routes
  3. Concurrent write tests pass for Qdrant, Pinecone, and encrypted backends
  4. Encryption + versioning interaction tests verify encrypt-version-decrypt-verify roundtrip
  5. Multi-namespace adversarial tests verify cross-namespace read is denied, empty namespace is blocked, and escalation fails
**Plans**: TBD

### Phase 10: Final Hardening
**Goal**: Coverage gate is enforced and the project is ready for 2.0.0 release
**Depends on**: Phase 9
**Requirements**: TEST-10
**Success Criteria** (what must be TRUE):
  1. `pytest --cov` with `fail_under=80` passes in pyproject.toml configuration
  2. All 55 v1 requirements are verified complete
  3. Version numbers in pyproject.toml and package metadata read 2.0.0
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. API Security Hardening | 0/? | Not started | - |
| 2. Crypto and ACL Security | 0/? | Not started | - |
| 3. Bug Fixes | 0/? | Not started | - |
| 4. Code Quality Cleanup | 0/? | Not started | - |
| 5. Core Architecture Decomposition | 0/? | Not started | - |
| 6. Module Decomposition | 0/? | Not started | - |
| 7. Performance Optimization | 0/? | Not started | - |
| 8. New Features | 0/? | Not started | - |
| 9. Test Coverage Expansion | 0/? | Not started | - |
| 10. Final Hardening | 0/? | Not started | - |
