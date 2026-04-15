# Codebase Concerns

**Analysis Date:** 2026-04-15

---

## Architecture Concerns

### HIGH — God Class: `MemOS` in `core.py` (1935 Lines)

- **Issue:** `src/memos/core.py` is 1935 lines. The `MemOS` class (line 65–1935) is a god class with 60+ public methods spanning 12+ distinct responsibilities: storage management, retrieval, dedup, decay, versioning/time-travel, sharing, feedback, analytics, events, compaction, compression, and import/export. Single file contains initialization, ACL, event bus, versioning, encryption, dedup, decay, analytics, sharing — all tightly coupled.
- **Files:** `src/memos/core.py`
- **Impact:** Any change to any subsystem requires modifying the same file. High merge conflict rate. Difficult to reason about any single feature in isolation. Every test that touches `MemOS` must load the entire dependency tree. Changes to one feature require understanding entire context.
- **Fix approach:** Decompose into focused mixins or separate service objects (e.g., `MemoryStore`, `MemoryRecall`, `MemoryVersioning`, `MemorySharing`, `MemoryMaintenance`). Keep `MemOS` as a thin facade that composes these services. Use composition instead of inheritance.

### HIGH — Monolithic CLI Parser: `_parser.py` at 1171 Lines

- **Issue:** `src/memos/cli/_parser.py` is a single argparse definition file. Every CLI command's arguments, defaults, and help text are in one place.
- **Files:** `src/memos/cli/_parser.py`
- **Impact:** Adding or modifying a CLI command requires editing a 1171-line file. Easy to introduce merge conflicts.
- **Fix approach:** Split into per-command parser factories or use click/typer with command groups.

### MEDIUM — Monolithic Files: `wiki_living.py`, `commands_memory.py`, `mcp_server.py`

- **Issue:** Three additional files exceed 800 lines: `wiki_living.py` (1078L), `commands_memory.py` (1036L), `mcp_server.py` (850L). Wiki living mixes rendering, logic, and data management. MCP server defines all tool schemas and dispatch logic in one file.
- **Files:** `src/memos/wiki_living.py`, `src/memos/cli/commands_memory.py`, `src/memos/mcp_server.py`
- **Impact:** Same god-class symptoms at smaller scale. Wiki living re-parses all memories on every update (no incremental updates).
- **Fix approach:** Split wiki_living into data/logic/rendering modules. Split MCP server into tool definitions and dispatch. Group CLI memory commands by operation type.

### MEDIUM — API Routes Access Private `_store` and `_decay` Directly

- **Issue:** API route handlers bypass the `MemOS` public API and access internal attributes directly (`memos._store`, `memos._namespace`, `memos._decay`). Encapsulation breach — if the internal storage or decay engine changes, these routes break silently.
- **Files:** `src/memos/api/routes/memory.py` (lines 483–505), `src/memos/api/routes/knowledge.py` (lines 316, 336)
- **Impact:** Makes refactoring core.py riskier. Routes are coupled to implementation details.
- **Fix approach:** Expose public methods on `MemOS` for decay run and reinforce operations. Route handlers should only call public methods.

### MEDIUM — Hub Dependency: 8+ Modules Import from `core.py`

- **Issue:** Eight modules import `MemOS` from `core.py`: `conflict.py:24`, `palace.py:21`, `benchmark.py:24`, `benchmark_quality.py:27`, `context.py:32`, `__init__.py:6`, `api/__init__.py:8`, `cli/_common.py:12`. This creates a hub-and-spoke dependency where `core.py` is a heavy import target.
- **Impact:** Import cycles risk if any of these modules are imported during `core.py` initialization. Slows cold start.
- **Fix approach:** Import `MemOS` only where needed (inside functions/methods) or define protocol/interface classes that these modules can depend on instead.

### MEDIUM — MCP Server Monkey-Patches `memos` Object at Runtime

- **Issue:** `src/memos/mcp_server.py` (lines 389, 410, 430, 447, 451, 478) assigns `memos._kg` and `memos._kg_bridge` directly onto the `memos` instance each time a KG tool is called. These ad-hoc attributes are never defined in `MemOS.__init__()` and are never cleaned up. They are not thread-safe and accumulate across calls.
- **Files:** `src/memos/mcp_server.py:389-478`
- **Impact:** Any new `MemOS` attribute name starting with `_kg` could silently conflict. Two concurrent KG calls could assign different `KnowledgeGraph` instances in a race. Difficult to reason about instance state.
- **Fix approach:** Instantiate `KnowledgeGraph` and `KGBridge` once in `MemOS.__init__()` as proper attributes, or pass them explicitly into MCP dispatch rather than caching on the `memos` object.

---

## Code Quality Concerns

### HIGH — Duplicated `_coerce_tags` Function (4 Copies)

- **Issue:** The `_coerce_tags` helper (converts string/list to normalized string list) is defined identically in 4 places: twice in `core.py` (lines 617, 699 as nested functions) and twice in `schemas.py` (lines 22, 81 as class methods).
- **Files:** `src/memos/core.py`, `src/memos/api/schemas.py`
- **Impact:** Any change to tag coercion logic must be applied in 4 places. Inconsistency risk.
- **Fix approach:** Extract to a shared utility function in `utils.py` or a dedicated `tag_utils.py` module.

### MEDIUM — Two Conflicting `RateLimiter` Classes

- **Issue:** Two separate `RateLimiter` classes exist: one in `api/auth.py` (sliding-window, line 21) and one in `api/ratelimit.py` (token-bucket, line 85). Both are instantiated in `api/__init__.py` (lines 62–63). The auth-based limiter's `max_requests` is set to the `rate_limit` parameter, but the token-bucket limiter uses `DEFAULT_RULES`.
- **Files:** `src/memos/api/auth.py:21`, `src/memos/api/ratelimit.py:85`, `src/memos/api/__init__.py:62-63`
- **Impact:** Confusing for developers. Rate-limiting behavior is split across two mechanisms.
- **Fix approach:** Consolidate to a single rate-limiting implementation. Remove the sliding-window limiter from `auth.py` and use only the token-bucket from `ratelimit.py`.

### MEDIUM — Excessive Bare `except Exception:` Handling (54 Occurrences)

- **Issue:** 54 bare `except Exception:` blocks across 22 source files. Many silently swallow errors with `pass` or return empty results. Failures are silently swallowed, making debugging extremely difficult.
- **Files:** `src/memos/core.py` (lines 423, 673), `src/memos/mcp_hooks.py` (5 occurrences), `src/memos/storage/qdrant_backend.py` (10 occurrences), `src/memos/storage/pinecone_backend.py` (7 occurrences), `src/memos/ingest/parsers.py` (3), `src/memos/ingest/miner.py` (2)
- **Impact:** Storage backend errors in Qdrant/Pinecone return empty results instead of surfacing connection/auth problems.
- **Fix approach:** Replace broad `except Exception` with specific exception types. At minimum, always log the error. For storage backends, consider raising or returning error results rather than empty lists.

### MEDIUM — `import asyncio` Inside Function Body

- **Issue:** `core.py` line 749 imports `asyncio` inside the `recall_stream` generator body. Unnecessary lazy import for a stdlib module.
- **Files:** `src/memos/core.py:749`
- **Impact:** Minor performance penalty on every call.
- **Fix approach:** Move `import asyncio` to the module top-level imports.

### MEDIUM — Unused Pydantic Schemas in `schemas.py`

- **Issue:** `src/memos/api/schemas.py` defines schemas that are not used by their corresponding routes: `FactRequest`, `InferRequest`, `PalaceCreateWingRequest`, `PalaceCreateRoomRequest`, `PalaceAssignRequest`, `ContextIdentityRequest`, `IngestURLRequest`, `MineConversationRequest`, `ACLGrantRequest`, `ACLRevokeRequest`, `ShareOfferRequest`, `ShareImportRequest`. These routes use raw `body: dict` instead.
- **Files:** `src/memos/api/schemas.py`, `src/memos/api/routes/knowledge.py`, `src/memos/api/routes/admin.py`
- **Impact:** Dead code that must be maintained. Schemas may drift out of sync with actual API behavior.
- **Fix approach:** Wire the existing schemas into their corresponding routes.

### LOW — `_agent_id` Attribute Set Dynamically Outside `__init__`

- **Issue:** `_agent_id` is only set when `set_agent_id()` is called. Four methods use `getattr(self, "_agent_id", "")` as a defensive check (lines 1740, 1759, 1764, 1769). The attribute is not initialized in `__init__`.
- **Files:** `src/memos/core.py`
- **Impact:** Fragile pattern — any method that accesses `_agent_id` without the `getattr` guard will raise `AttributeError`.
- **Fix approach:** Initialize `self._agent_id: str = ""` in `__init__` and remove all `getattr` guards.

### LOW — Self-Referential Import in `ingest/miner.py`

- **Issue:** `src/memos/ingest/miner.py:10` contains `from memos.ingest.miner import Miner` — a self-import of the same module. Works at runtime because Python caches modules, but unnecessary and confusing.
- **Files:** `src/memos/ingest/miner.py:10`
- **Impact:** Code smell. May cause issues with certain import tools or linters.
- **Fix approach:** Remove the self-referential import.

### LOW — `export_json()` Hardcodes Format Version `"0.2.0"`

- **Issue:** `src/memos/core.py:1180`: `export_json()` writes `"version": "0.2.0"` in the export dict. Doesn't match the package version and is not documented as a format version.
- **Files:** `src/memos/core.py:1180`
- **Impact:** Consumers of the export format can't determine compatibility.
- **Fix approach:** Track export format version separately from package version. Document it.

---

## Security Concerns

### HIGH — 13 API Endpoints Accept Raw `body: dict` Without Pydantic Validation

- **Issue:** 13 POST endpoints in `knowledge.py` and `admin.py` accept `body: dict` instead of typed Pydantic models. These endpoints do manual `body.get("field", "")` validation instead of using the existing schemas in `schemas.py`. No automatic field validation, type coercion, or max-length enforcement.
- **Files:** `src/memos/api/routes/knowledge.py` (7 endpoints: `kg_add_fact`, `kg_infer`, `brain_search`, `palace_create_wing`, `palace_create_room`, `palace_assign`, `context_set_identity`), `src/memos/api/routes/admin.py` (6 endpoints: `api_ingest_url`, `api_mine_conversation`, `api_acl_grant`, `api_acl_revoke`, `api_share_offer`, `api_share_import`)
- **Impact:** Malformed or oversized payloads pass through to business logic. The schemas in `schemas.py` (e.g., `FactRequest`, `PalaceCreateWingRequest`) exist but are not used.
- **Fix approach:** Replace `body: dict` with the existing Pydantic schemas from `schemas.py`. Add missing schemas for any uncovered endpoints.

### HIGH — Encryption Uses Custom XOR Cipher Instead of Established Library

- **Risk:** `src/memos/crypto.py` implements a custom XOR-based stream cipher rather than using `cryptography.fernet` or similar. While PBKDF2 key derivation is correct, the XOR cipher may have subtle flaws. Weak passphrases (e.g., "password") are accepted without entropy validation.
- **Files:** `src/memos/crypto.py` (lines 42-51 for passphrase, 57-99 for cipher)
- **Current mitigation:** 600k PBKDF2 iterations make brute-force expensive. HMAC provides integrity check.
- **Recommendations:** (1) Switch to `cryptography.Fernet` (AES-128-CBC + HMAC) for production security. (2) Keep XOR cipher for backwards compatibility but mark as deprecated. (3) Add minimum passphrase entropy validation.

### HIGH — Rate-Limiting Middleware Runs Handler Before Rejecting Over-Limit Requests

- **Issue:** `src/memos/api/auth.py:137-148`: The middleware calls `call_next(request)` (running the full handler) and _then_ checks `if not allowed`. A 429 response is returned only after the handler has already executed and its side effects have occurred (e.g., a memory was written, a KG fact was added).
- **Files:** `src/memos/api/auth.py:136-148`
- **Impact:** Rate-limited clients still trigger all side effects. A burst of requests bypasses rate limiting for all but the final response. This effectively makes the rate limiter a no-op for state-mutating endpoints.
- **Fix approach:** Move the `if not allowed` check _before_ `call_next(request)`. Check counter first, reject early, then call handler only if allowed.

### MEDIUM — Auth Disabled by Default (No API Keys = No Auth)

- **Issue:** `APIKeyManager.validate()` returns `True` when no keys are configured (`src/memos/api/auth.py:89-90`). In the default deployment, authentication is completely disabled — anyone with network access can read/write/delete all memories.
- **Files:** `src/memos/api/auth.py:89-90`
- **Impact:** In a default Docker deployment with port 8100 exposed, the API is open. The dashboard is also served without auth.
- **Recommendations:** Document the security implications prominently. Consider defaulting to localhost-only binding. Add a startup warning log when auth is disabled.

### MEDIUM — CORS Defaults to Wildcard `*`

- **Issue:** `src/memos/mcp_server.py:34` sets `_CORS_ALLOWED_ORIGINS = os.environ.get("MEMOS_CORS_ORIGINS", "*")`. The default allows any origin to make cross-origin requests to the MCP endpoint.
- **Files:** `src/memos/mcp_server.py:34`
- **Impact:** Any website can make requests to the MCP endpoint if the user visits it while MemOS is running locally.
- **Recommendations:** Default to `localhost` origins. Document how to restrict CORS for production.

### MEDIUM — Confusing `hmac.compare_digest` Usage in Auth Validation

- **Issue:** `src/memos/api/auth.py:92`: `hmac.compare_digest(hashed, hashed in self._hashed_keys and hashed or "")`. This is functionally correct but the logic is convoluted and could mask timing-attack vulnerabilities if refactored incorrectly.
- **Files:** `src/memos/api/auth.py:92`
- **Impact:** Readability issue that could lead to a security regression during refactoring.
- **Fix approach:** Simplify to: `return hashed in self._hashed_keys` or use a clearer comparison pattern.

### MEDIUM — Namespace ACL Bypass via Empty Namespace

- **Risk:** `_check_acl()` in `core.py:276-284` is skipped when namespace is empty. An agent can set `namespace=""` to bypass all ACL checks. ACL enforcement is optional (only when `set_agent_id()` is called).
- **Files:** `src/memos/core.py:276-284`, `src/memos/namespaces/acl.py`
- **Current mitigation:** Only enforced if `set_agent_id()` is called first.
- **Recommendations:** (1) Make ACL enforcement mandatory when multi-agent mode is detected. (2) Prevent empty namespace if agents are registered.

### MEDIUM — Pinecone API Key Not Masked in Logs

- **Risk:** `MEMOS_PINECONE_API_KEY` environment variable and `api_key` parameter in `PineconeBackend.__init__()` are never masked or encrypted in logs/errors.
- **Files:** `src/memos/storage/pinecone_backend.py`
- **Current mitigation:** None.
- **Recommendations:** Mask API keys in log messages (e.g., `pk-****...****`). Never print API keys in exception messages.

### LOW — Sanitization Can Be Bypassed via `MEMOS_ENFORCE_SANITIZATION` Env Var

- **Issue:** `src/memos/api/routes/memory.py:40` reads `MEMOS_ENFORCE_SANITIZATION` env var. When set to `"false"`, API-layer sanitization is skipped, but core-layer `MemorySanitizer.check()` may still run. Two layers of sanitization can be desynchronized.
- **Files:** `src/memos/api/routes/memory.py:40`, `src/memos/core.py:357-360`
- **Impact:** Inconsistent protection against prompt injection.
- **Fix approach:** Consolidate sanitization control into a single location.

---

## Performance Concerns

### HIGH — N+1 Write Pattern in `recall()` — Every Result Triggers an Upsert

- **Issue:** `src/memos/core.py:657-659`: After retrieving results, each item's `touch()` method updates it, then `self._store.upsert()` writes it back individually. For a recall returning 50 results, this triggers 50 separate write operations. This makes a read operation into a read+write, which can cause errors on read-only backends and inflates version history.
- **Files:** `src/memos/core.py:657-659`
- **Impact:** On networked backends (ChromaDB, Qdrant, Pinecone), each upsert is a network round-trip. Recall latency scales linearly with result count. Read operations are not idempotent.
- **Fix approach:** Batch the touch+upsert into a single `upsert_batch()` call after the loop. Make touch tracking optional via a parameter.

### MEDIUM — `list_all()` Loads All Memories Into Memory (No Pagination)

- **Issue:** Multiple methods call `self._store.list_all()` which loads the entire memory store into a Python list: `stats()`, `list_tags()`, `rename_tag()`, `delete_tag()`, `forget_tag()`, `prune()`, `prune_expired()`, `get_feedback()`. The `StorageBackend` abstract class only defines `list_all()` with no pagination support.
- **Files:** `src/memos/core.py` (lines 761, 798, 819, 867, 895, 914, 942, 974, 1895), `src/memos/storage/base.py:31`
- **Impact:** With 100K+ memories, each call allocates a large list. Does not scale to large memory stores.
- **Fix approach:** Add streaming/iterator support to `StorageBackend`. Add count-based queries for stats. Add `list(limit, offset)` to the base class.

### MEDIUM — `recall_stream()` Is Not Truly Streaming

- **Issue:** `src/memos/core.py:737-751`: `recall_stream()` calls the synchronous `recall()` method first, then yields results one at a time with `asyncio.sleep(0)`. Full search completes before any result is yielded.
- **Files:** `src/memos/core.py:721-751`
- **Impact:** No actual streaming benefit — the caller waits for full search completion, then receives results slightly delayed.
- **Fix approach:** Implement true streaming in the retrieval engine (yield results as they are scored). For now, document that this is "pseudo-streaming."

### MEDIUM — Embedding Cache Opens New SQLite Connection Per Operation

- **Issue:** `src/memos/cache/embedding_cache.py` and `src/memos/storage/chroma_backend.py` (the `_CachedOllamaEF` class, lines 33-78) open a new SQLite connection per lookup/store cycle. With many concurrent requests, WAL lock contention causes stalls.
- **Files:** `src/memos/cache/embedding_cache.py`, `src/memos/storage/chroma_backend.py:33-78`
- **Cause:** SQLite is single-writer; Ollama embeddings are slow (~15s per embedding on ARM64).
- **Fix approach:** Use a persistent connection pool with `timeout=30`. Move cache writes to a background queue.

### MEDIUM — Dedup Scan Is O(n²) for Large Stores

- **Issue:** `src/memos/dedup.py` (lines 80-150) iterates all memories for exact hash + near-duplicate trigram similarity. With 10k memories, this is 100M comparisons.
- **Files:** `src/memos/dedup.py`
- **Fix approach:** Use MinHash for approximate similarity. Cache trigram sets to avoid recomputation. Add `--quick` mode for exact hash only.

### MEDIUM — Wiki Living Re-parses All Memories on Every Update

- **Issue:** `src/memos/wiki_living.py` (lines 200-500) iterates all memories and tags to rebuild entity pages. Even small edits trigger full scan.
- **Files:** `src/memos/wiki_living.py`
- **Fix approach:** Track delta (new memories since last compile). Only update affected entity pages. Make `update_for_item()` incremental by default.

### MEDIUM — Knowledge Graph Queries Lack Optimal Indexes

- **Issue:** `src/memos/knowledge_graph.py` (lines 180-220) does full table scans for some entity lookups despite having an index on `(subject, predicate, object)`. Temporal queries miss optimal index paths.
- **Files:** `src/memos/knowledge_graph.py`
- **Fix approach:** Add composite index on `(subject, valid_from, valid_to)` for temporal queries. Profile with `EXPLAIN QUERY PLAN`.

### LOW — `feedback_stats()` Loads All Feedback Unbounded

- **Issue:** `src/memos/core.py:1904` calls `self.get_feedback(limit=1_000_000)`, which iterates all items to find those with feedback. No database-level aggregation. Performance degrades with memory count.
- **Files:** `src/memos/core.py:1902-1918`
- **Fix approach:** Use a dedicated feedback store or compute stats incrementally.

---

## Known Bugs

### MEDIUM — Dedup Engine Doesn't Handle Concurrent Writes

- **Symptoms:** If two processes call `mem.learn()` with duplicate content simultaneously, both may pass dedup checks and insert duplicates.
- **Files:** `src/memos/dedup.py` (lines 67-80), `src/memos/core.py` (lines 365-379)
- **Trigger:** Run `memos learn "content"` in parallel from two shell sessions with `backend="json"` or in-memory backend.
- **Workaround:** Use server-backed MemOS (via `memos serve`) with single API entry point.

### MEDIUM — Encrypted Backend Doesn't Validate Decryption Failures

- **Symptoms:** If encryption key is wrong but data is decrypted anyway (due to malformed ciphertext), the decrypted value is nonsense but not flagged as corrupt.
- **Files:** `src/memos/storage/encrypted_backend.py`
- **Trigger:** Create encrypted store with key A, try to decrypt with key B.
- **Workaround:** None — add HMAC verification to detect wrong key or corruption.

### MEDIUM — Knowledge Graph Time Parsing Accepts Invalid Formats Silently

- **Symptoms:** `memos kg-add ... --from 2025-13-45` (invalid month/day) returns success but stores epoch 0 or garbage timestamp.
- **Files:** `src/memos/knowledge_graph.py` (lines 22-53)
- **Trigger:** Call `kg_add_fact()` with malformed ISO date like "2025-99-99".
- **Workaround:** Caller must validate dates before passing to KG.

---

## Maintenance Concerns

### HIGH — Version Mismatch: `pyproject.toml` 1.1.0 vs `__init__.py` 1.0.0

- **Issue:** `pyproject.toml:7` declares `version = "1.1.0"`, but `src/memos/__init__.py:3` declares `__version__ = "1.0.0"`. The API's OpenAPI version (served at `/docs`) uses the `__init__.py` version, so it reports 1.0.0 while the package is published as 1.1.0.
- **Files:** `src/memos/__init__.py:3`, `pyproject.toml:7`
- **Impact:** Version reporting is wrong in the API dashboard and any code that imports `memos.__version__`. Can cause confusion in bug reports and version-dependent logic.
- **Fix approach:** Use a single source of truth. Read version from `pyproject.toml` at build time (via `importlib.metadata.version("memos-agent")`) or use a `version.py` generated by the build system.

### MEDIUM — Single-File JSON Backend Not Suitable for Concurrent Access

- **Issue:** `src/memos/storage/json_backend.py` uses a process-local `threading.Lock()` for thread-safety, but this is unsafe for multi-process scenarios. The entire store is read into memory, modified, and atomically written back to disk on every mutation.
- **Files:** `src/memos/storage/json_backend.py` (lines 36-72)
- **Impact:** Multiple processes (e.g., concurrent API requests, background workers) can corrupt the JSON file if writes collide. No inter-process locking exists.
- **Fix approach:** Document this limitation prominently. Consider adding a warning log when JSON backend is selected. For production, force users to use ChromaDB, Qdrant, or Pinecone.

### MEDIUM — Storage Backend Interface Has No Async Consistency

- **Issue:** Sync and async interfaces exist in parallel at `src/memos/storage/base.py`, `src/memos/storage/async_wrapper.py`. Async wrapper delegates to sync methods via thread pool. If a backend overrides one but not the other, they may diverge.
- **Files:** `src/memos/storage/base.py`, `src/memos/storage/async_wrapper.py`
- **Impact:** Behavior may differ between sync and async paths. Pinecone async is untested.
- **Fix approach:** Make all backends async-first. Provide sync adapter that wraps async. Add tests for both paths.

### MEDIUM — API Route Factory Functions Not Type-Annotated

- **Issue:** Router factory functions use untyped parameters: `create_memory_router(memos, _kg_bridge)`, `create_knowledge_router(memos, _kg, _palace, _context_stack)`, `create_admin_router(memos, _kg, key_manager, rate_limiter, MEMOS_VERSION: str, DASHBOARD_HTML: str)`. Most parameters lack type hints.
- **Files:** `src/memos/api/routes/memory.py:43`, `src/memos/api/routes/knowledge.py:11`, `src/memos/api/routes/admin.py:14`
- **Impact:** No IDE autocompletion or type-checking for route handlers. Easy to pass wrong argument types.
- **Fix approach:** Add type annotations to all router factory parameters.

### MEDIUM — Qdrant and Pinecone Backends Have Asymmetric Feature Support

- **Issue:** ChromaDB backend is the most feature-complete. Qdrant has native hybrid search. Pinecone lacks full feature parity. Code paths diverge without clear documentation of what works where.
- **Files:** `src/memos/storage/chroma_backend.py`, `src/memos/storage/qdrant_backend.py`, `src/memos/storage/pinecone_backend.py`
- **Impact:** Features work on ChromaDB but silently degrade or error on other backends.
- **Fix approach:** Add a feature matrix document (`docs/BACKENDS.md`). Add runtime validation in `MemOS.__init__()` to warn about unsupported feature + backend combinations.

---

## Scaling Limits

### MEDIUM — JSON Backend Can't Handle >100k Memories

- **Current capacity:** Tested up to 10k in-memory; 100k JSON file is ~50MB and takes 5s to load.
- **Limit:** At 1M memories, JSON load/save is 500MB and 50+ seconds.
- **Scaling path:** Migrate to Chroma/Qdrant for large stores. Add sharding docs (one JSON file per namespace/shard).

### MEDIUM — Ollama Embeddings Saturate at ~4 req/min on ARM64

- **Current capacity:** ARM64 Ollama (no GPU) embeds at ~1 per 15s = 4 req/min.
- **Limit:** More than 5 concurrent recall requests queue up. P99 latency > 60s.
- **Scaling path:** Run Ollama with GPU support. Use cloud embeddings. Add embedding batch queue.

### LOW — Encryption Overhead Scales Linearly

- **Current capacity:** 10k memories = ~1s. 100k = ~10s.
- **Scaling path:** Per-namespace encryption keys. Streaming encryption for large stores.

---

## Dependencies at Risk

### MEDIUM — Sentence-Transformers Optional But Required for Local-First

- **Risk:** `pip install memos-agent` (no `[local]`) doesn't include sentence-transformers. Local embeddings silently fail.
- **Impact:** Users expecting local-first are surprised when recall doesn't work without Ollama.
- **Migration plan:** Make sentence-transformers a core dependency, or catch import errors and raise clear error at first local-embedder call.

### MEDIUM — Pinecone Client Version Not Upper-Bounded

- **Risk:** `pinecone-client>=3.0` is unpinned on the upper end. Pinecone SDK is rapidly evolving.
- **Files:** `src/memos/storage/pinecone_backend.py`, `pyproject.toml:27`
- **Impact:** Pinecone version bump breaks MemOS without warning.
- **Migration plan:** Pin to `pinecone-client>=3.0,<4.0`.

### LOW — ChromaDB API Changes in 1.x

- **Risk:** `chromadb>=0.4` is compatible, but Chroma 1.x changed collection API significantly.
- **Migration plan:** Pin to `chromadb>=0.4,<1.0` for now. Plan Chroma 1.x migration.

---

## Missing Critical Features

### MEDIUM — ACL `expires_at` Field Not Enforced

- **Problem:** `NamespacePolicy.expires_at` field exists but `_check_acl()` doesn't validate expiration. Agents keep access forever.
- **Files:** `src/memos/namespaces/acl.py`, `src/memos/core.py:276-284`
- **Blocks:** Multi-agent systems can't enforce temporary permissions.
- **Implementation:** Add expiration check in `_check_acl()`. Add CLI `memos acl grant ... --expires-in 24h`.

### MEDIUM — No Audit Log for Memory Mutations

- **Problem:** No record of who modified/deleted what and when. Useful for compliance, debugging, and multi-agent accountability.
- **Blocks:** Enterprise deployments need audit trails.
- **Implementation:** Add audit logger to `EventBus`. Log all learn/delete/prune events with agent_id, timestamp, content hash.

---

## Test Coverage Gaps

### HIGH — No Test Files for Several Source Modules

- **What's not tested:** `src/memos/crypto.py` (encryption), `src/memos/skills.py`, `src/memos/export_obsidian.py`, `src/memos/mcp_hooks.py` (5 exception handlers untested), `src/memos/analytics.py`, `src/memos/compression.py`, `src/memos/cache/` (embedding cache), `src/memos/namespaces/` (namespace isolation), `src/memos/subscriptions/`, `src/memos/versioning/persistent_store.py`, `src/memos/wiki.py`
- **Files:** No corresponding `tests/test_*.py` for these modules
- **Risk:** Untested modules may contain regressions. Crypto, analytics, and compression are particularly risk-prone.
- **Priority:** High for `crypto.py`, `compression.py`, `analytics.py`. Medium for the rest.

### HIGH — API Input Validation Not Comprehensively Tested

- **What's not tested:** Invalid JSON, missing required fields, type mismatches, negative/overflowing numbers, very long strings (>1MB) sent to API endpoints.
- **Files:** `tests/test_api_*.py` (primarily happy path tests)
- **Risk:** Malformed requests may crash API or expose internal errors.
- **Priority:** High — add parametrized tests for invalid inputs to all routes.

### HIGH — Concurrency Tests Don't Cover All Backends

- **What's not tested:** Concurrent learn/recall against Qdrant, Pinecone, and encrypted backends.
- **Files:** `tests/test_async.py`, `tests/test_async_consolidation.py`
- **Risk:** Race conditions in Pinecone (async client library). Encryption + versioning concurrency untested.
- **Priority:** High — add tests for each backend with concurrent writers.

### MEDIUM — No Enforced Coverage Threshold

- **Issue:** 77 test files exist, but `pyproject.toml` only configures display options under `[tool.coverage.report]`. No `fail_under` enforcement.
- **Files:** `pyproject.toml:49-53`
- **Risk:** Coverage can drop without CI detection.
- **Fix approach:** Add `fail_under = 80` to `[tool.coverage.report]`.

### MEDIUM — Encryption + Versioning Interactions Untested

- **What's not tested:** Learn encrypted memory → create version → decrypt → verify content matches.
- **Files:** `tests/test_api_versioning.py` (doesn't test with encryption enabled)
- **Risk:** Silent data loss if versioning engine doesn't preserve encrypted payloads correctly.

### MEDIUM — Multi-Namespace Security Not Tested Adversarially

- **What's not tested:** Agent A tries to read Agent B's namespace; agent escalation via empty namespace; concurrent namespace creation/deletion.
- **Files:** `tests/test_auth.py` (37 tests but limited scope)
- **Risk:** ACL bypass or namespace collision.

### MEDIUM — Knowledge Graph Temporal Queries Lack Edge Cases

- **What's not tested:** Queries with overlapping validity windows, null valid_from/valid_to, timezone conversions.
- **Files:** `tests/test_knowledge_graph.py` (~100 tests but temporal logic sparse)
- **Risk:** Subtle bugs in date logic affect historical queries.

### LOW — MCP Tool Count Assertion Will Break When Tools Are Added

- **Issue:** `tests/test_mcp_server.py:21` hardcodes `assert len(TOOLS) == 15`. Any addition of a new MCP tool will cause this test to fail with a confusing assertion error rather than a meaningful message.
- **Files:** `tests/test_mcp_server.py:21`
- **Fix approach:** Remove the count assertion. Test for specific tool names instead (which the test already does on the next lines).

---

## Priority Order

| Priority | Concern | Impact |
|----------|---------|--------|
| 1 | **Rate-limiting middleware runs handler before rejecting** | Security: state mutations bypass rate limit |
| 2 | **13 API endpoints accept raw `body: dict`** | Security: no input validation |
| 3 | **Custom XOR encryption cipher** | Security: cryptographic weakness |
| 4 | **Auth disabled by default** | Security: open API in default deployment |
| 5 | **N+1 writes in `recall()`** | Performance: every search triggers N upserts |
| 6 | **`MemOS` god class (1935L)** | Maintainability: all changes touch one file |
| 7 | **Version mismatch `pyproject.toml` vs `__init__.py`** | Reliability: wrong version reported everywhere |
| 8 | **No test coverage for `crypto.py`, `analytics.py`, `compression.py`** | Reliability: undetected regressions |
| 9 | **MCP server monkey-patches `memos` at runtime** | Maintainability: hidden state, thread safety |
| 10 | **`list_all()` loads entire store** | Performance: doesn't scale past ~100k memories |
| 11 | **CORS defaults to wildcard `*`** | Security: any website can call MCP endpoint |
| 12 | **ACL `expires_at` not enforced** | Feature gap: temporary permissions don't work |
| 13 | **Dedup O(n²) scan** | Performance: unusable with large stores |
| 14 | **54 bare `except Exception` blocks** | Reliability: silent failures |
| 15 | **Pinecone client unpinned** | Reliability: silent breakage on version bump |

---

*Concerns audit: 2026-04-15*
