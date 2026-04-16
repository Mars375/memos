# Requirements: MemOS Hardening

**Defined:** 2026-04-15
**Core Value:** MemOS must be secure by default -- no open API, no broken rate-limiting, no custom crypto, no unvalidated inputs.

## v1 Requirements

### Security

- [ ] **SEC-01**: Rate-limiter middleware rejects over-limit requests BEFORE executing the handler
- [ ] **SEC-02**: All 13 POST endpoints use typed Pydantic models instead of raw `body: dict`
- [ ] **SEC-03**: Encryption uses `cryptography.Fernet` (AES-128-CBC + HMAC) instead of custom XOR cipher
- [ ] **SEC-04**: One-shot migration tool converts existing XOR-encrypted data to Fernet format
- [ ] **SEC-05**: API authentication is enabled by default; startup warning logged when no keys configured
- [ ] **SEC-06**: MCP serve `getattr` fallback is `127.0.0.1`, not `0.0.0.0` (REST serve already defaults to localhost)
- [ ] **SEC-07**: CORS default origin is `http://localhost:*`, not wildcard `*`
- [ ] **SEC-08**: Empty namespace is rejected when agent_id is set (prevents ACL bypass)
- [ ] **SEC-09**: Pinecone API key masking filter installed on logger (defense-in-depth; keys are already never logged today)
- [ ] **SEC-10**: Sanitization toggle coherence — API layer delegates to `memos._sanitize` instead of independent `MEMOS_ENFORCE_SANITIZATION` env var
- [ ] **SEC-11**: `hmac.compare_digest` usage in auth simplified to prevent timing-attack regression

### Architecture Refactoring

- [ ] **ARCH-01**: `MemOS` class (core.py) decomposed into focused service objects; `MemOS` is a thin facade under 300 lines
- [ ] **ARCH-02**: CLI parser (_parser.py) split into per-command modules (one file per command group)
- [ ] **ARCH-03**: `wiki_living.py` split into data, logic, and rendering modules
- [ ] **ARCH-04**: `mcp_server.py` split into tool definitions, dispatch logic, and transport modules
- [ ] **ARCH-05**: `commands_memory.py` split by operation type (CRUD, search, maintenance)
- [ ] **ARCH-06**: KG and KGBridge initialized in `MemOS.__init__()` as proper attributes (no monkey-patching)
- [ ] **ARCH-07**: Two conflicting `RateLimiter` classes consolidated into one implementation
- [ ] **ARCH-08**: Hub dependency on core.py reduced -- modules import protocol/interface, not concrete class

### Performance

- [ ] **PERF-01**: `recall()` batches all touch+upsert into a single `upsert_batch()` call
- [ ] **PERF-02**: `StorageBackend` ABC extended with `list(limit, offset)` pagination method
- [ ] **PERF-03**: All 8 callers of `list_all()` migrated to paginated iteration
- [ ] **PERF-04**: Dedup engine uses MinHash for approximate similarity (replaces O(n^2) trigram scan)
- [ ] **PERF-05**: Embedding cache uses persistent SQLite connection pool (not per-operation open)
- [ ] **PERF-06**: Wiki living supports incremental updates (delta-based, not full re-parse)
- [ ] **PERF-07**: Knowledge graph has composite index on `(subject, valid_from, valid_to)` for temporal queries

### Bug Fixes

- [ ] **BUG-01**: Dedup engine handles concurrent writes safely (file-level or advisory lock)
- [ ] **BUG-02**: Encrypted backend validates decryption with HMAC -- wrong key raises clear error
- [ ] **BUG-03**: KG date parser rejects invalid ISO dates (e.g., `2025-99-99`) with validation error
- [ ] **BUG-04**: Version mismatch fixed -- single source of truth via `importlib.metadata.version()`
- [ ] **BUG-05**: `recall_stream()` documented as pseudo-streaming (or made truly streaming)
- [ ] **BUG-06**: `feedback_stats()` uses bounded query instead of `limit=1_000_000`

### Code Quality

- [ ] **QUAL-01**: All 54 bare `except Exception:` blocks replaced with specific exception types + logging
- [ ] **QUAL-02**: Duplicated `_coerce_tags` (4 copies) extracted to shared `utils.py` function
- [ ] **QUAL-03**: Unused Pydantic schemas wired to their routes or deleted
- [ ] **QUAL-04**: `_agent_id` initialized in `__init__` with `self._agent_id: str = ""`
- [ ] **QUAL-05**: Self-referential import removed from `ingest/miner.py`
- [ ] **QUAL-06**: Export format version (`"0.2.0"`) documented or derived from package version
- [ ] **QUAL-07**: All API route factory functions have full type annotations
- [ ] **QUAL-08**: `import asyncio` in `recall_stream` moved to module top-level
- [ ] **QUAL-09**: Dependencies pinned: `pinecone-client>=3.0,<4.0`, `chromadb>=0.4,<1.0`

### New Features

- [ ] **FEAT-01**: Audit log records all learn/delete/prune/consolidate events with agent_id, timestamp, content hash
- [ ] **FEAT-02**: `StorageBackend` supports `list(limit, offset)` and streaming iterator protocol
- [ ] **FEAT-03**: ACL `expires_at` field enforced in `_check_acl()` -- expired permissions are denied
- [ ] **FEAT-04**: Backend feature matrix document (`docs/BACKENDS.md`) with runtime warnings for unsupported feature+backend combos

### Test Coverage

- [ ] **TEST-01**: Tests for `crypto.py` -- encryption, decryption, key derivation, wrong-key detection
- [ ] **TEST-02**: Tests for `analytics.py` -- recall analytics tracking and reporting
- [ ] **TEST-03**: Tests for `compression.py` -- memory compression within token budget
- [ ] **TEST-04**: Tests for `cache/embedding_cache.py` -- LRU behavior, cache hits/misses, persistence
- [ ] **TEST-05**: Tests for `namespaces/acl.py` -- RBAC enforcement, role hierarchy, expiration
- [ ] **TEST-06**: Parametrized API tests for invalid inputs (bad JSON, type mismatches, oversized payloads)
- [ ] **TEST-07**: Concurrent write tests for Qdrant, Pinecone, and encrypted backends
- [ ] **TEST-08**: Encryption + versioning interaction tests (encrypt -> version -> decrypt -> verify)
- [ ] **TEST-09**: Multi-namespace adversarial tests (cross-namespace read, empty namespace, escalation)
- [ ] **TEST-10**: Coverage threshold enforced at 80% via `fail_under` in pyproject.toml

## v2 Requirements

### Scaling

- **SCALE-01**: JSON backend auto-sharding (one file per namespace/shard)
- **SCALE-02**: Embedding batch queue for high-throughput ingestion
- **SCALE-03**: True streaming recall (yield results as scored, not pseudo-streaming)

### Observability

- **OBS-01**: Structured logging (JSON format) across all modules
- **OBS-02**: OpenTelemetry tracing for recall/learn paths
- **OBS-03**: Prometheus metrics endpoint

### Developer Experience

- **DX-01**: Migration CLI for version upgrades (`memos migrate 1.x -> 2.0`)
- **DX-02**: Plugin system for custom storage backends
- **DX-03**: Type stubs for public API (`py.typed` marker)

## Out of Scope

| Feature | Reason |
|---------|--------|
| New storage backends (Redis, DynamoDB) | Address after hardening is complete |
| UI/dashboard redesign | Functional enough; cosmetic improvements are a separate initiative |
| Mobile/native clients | Library hardening scope, not consumer-facing |
| Async-first rewrite of all backends | Too disruptive; async wrapper pattern is sufficient |
| CI/CD pipeline setup | No CI config exists; separate initiative |
| ARM64/Ollama performance tuning | Hardware constraint, not addressable via code changes |
| Real-time collaborative editing | Not in the memory OS use case |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SEC-01 | Phase 1 | Pending |
| SEC-02 | Phase 1 | Pending |
| SEC-03 | Phase 2 | Pending |
| SEC-04 | Phase 2 | Pending |
| SEC-05 | Phase 1 | Pending |
| SEC-06 | Phase 1 | Pending |
| SEC-07 | Phase 1 | Pending |
| SEC-08 | Phase 2 | Pending |
| SEC-09 | Phase 1 | Pending |
| SEC-10 | Phase 1 | Pending |
| SEC-11 | Phase 1 | Pending |
| ARCH-01 | Phase 5 | Pending |
| ARCH-02 | Phase 6 | Pending |
| ARCH-03 | Phase 6 | Pending |
| ARCH-04 | Phase 6 | Pending |
| ARCH-05 | Phase 6 | Pending |
| ARCH-06 | Phase 5 | Pending |
| ARCH-07 | Phase 5 | Pending |
| ARCH-08 | Phase 5 | Pending |
| PERF-01 | Phase 7 | Pending |
| PERF-02 | Phase 7 | Pending |
| PERF-03 | Phase 7 | Pending |
| PERF-04 | Phase 7 | Pending |
| PERF-05 | Phase 7 | Pending |
| PERF-06 | Phase 7 | Pending |
| PERF-07 | Phase 7 | Pending |
| BUG-01 | Phase 3 | Pending |
| BUG-02 | Phase 3 | Pending |
| BUG-03 | Phase 3 | Pending |
| BUG-04 | Phase 3 | Pending |
| BUG-05 | Phase 3 | Pending |
| BUG-06 | Phase 3 | Pending |
| QUAL-01 | Phase 4 | Pending |
| QUAL-02 | Phase 4 | Pending |
| QUAL-03 | Phase 4 | Pending |
| QUAL-04 | Phase 4 | Pending |
| QUAL-05 | Phase 4 | Pending |
| QUAL-06 | Phase 4 | Pending |
| QUAL-07 | Phase 4 | Pending |
| QUAL-08 | Phase 4 | Pending |
| QUAL-09 | Phase 4 | Pending |
| FEAT-01 | Phase 8 | Pending |
| FEAT-02 | Phase 8 | Pending |
| FEAT-03 | Phase 8 | Pending |
| FEAT-04 | Phase 8 | Pending |
| TEST-01 | Phase 9 | Pending |
| TEST-02 | Phase 9 | Pending |
| TEST-03 | Phase 9 | Pending |
| TEST-04 | Phase 9 | Pending |
| TEST-05 | Phase 9 | Pending |
| TEST-06 | Phase 9 | Pending |
| TEST-07 | Phase 9 | Pending |
| TEST-08 | Phase 9 | Pending |
| TEST-09 | Phase 9 | Pending |
| TEST-10 | Phase 10 | Pending |

**Coverage:**
- v1 requirements: 55 total
- Mapped to phases: 55
- Unmapped: 0

---
*Requirements defined: 2026-04-15*
*Last updated: 2026-04-15 after roadmap creation*
