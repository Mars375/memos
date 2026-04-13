# Codebase Concerns

**Analysis Date:** 2026-04-13

## Tech Debt

**Single-file JSON backend not suitable for concurrent access:**
- Issue: `src/memos/storage/json_backend.py` uses a process-local `threading.Lock()` for thread-safety, but this is unsafe for multi-process scenarios. The entire store is read into memory, modified, and atomically written back to disk on every mutation.
- Files: `src/memos/storage/json_backend.py` (lines 36-72)
- Impact: Multiple processes (e.g., concurrent API requests, background workers) can corrupt the JSON file if writes collide. No inter-process locking exists.
- Fix approach: For production with concurrent access, force users to use ChromaDB, Qdrant, or Pinecone backends. Document this limitation prominently. Consider adding a warning log when JSON backend is selected with `backend="json"`.

**Embedding cache initialization not validated:**
- Issue: Embedding cache at `src/memos/cache/embedding_cache.py` is created at MemOS init time but may fail silently if the cache path is not writable (e.g., permission denied, disk full).
- Files: `src/memos/core.py` (lines 171-180)
- Impact: Silent cache degradation — queries will work but embeddings won't be cached, causing repeated Ollama calls and poor performance on ARM64.
- Fix approach: Add explicit error handling in `EmbeddingCache.__init__()` and raise loudly on permission/write failures instead of silently catching exceptions.

**Encryption key format not validated at init:**
- Issue: `src/memos/crypto.py` accepts any string as `encryption_key`, derives it via PBKDF2, but doesn't validate that the passphrase meets minimum entropy requirements. Weak passphrases (e.g., "password" or "123456") provide weak encryption.
- Files: `src/memos/crypto.py` (lines 42-51)
- Impact: Users can encrypt sensitive memories with weak passphrases, giving false confidence in security.
- Fix approach: Add optional `min_entropy_bits=64` parameter to `MemoryCrypto.from_passphrase()` and estimate passphrase entropy. Warn if below threshold.

**Qdrant and Pinecone backends have asymmetric feature support:**
- Issue: ChromaDB backend is the most feature-complete. Qdrant has native hybrid search. Pinecone lacks full feature parity (e.g., some filtering options, versioning integration). Code paths diverge without clear documentation of what works where.
- Files: `src/memos/storage/chroma_backend.py`, `src/memos/storage/qdrant_backend.py`, `src/memos/storage/pinecone_backend.py`
- Impact: Features work on ChromaDB but silently degrade or error on other backends. Users may discover incompatibilities late in development.
- Fix approach: Add a feature matrix document (`docs/BACKENDS.md`) clearly listing which features work on each backend. Add runtime validation in MemOS.__init__() to warn about unsupported feature + backend combinations.

## Known Bugs

**Dedup engine doesn't handle concurrent writes:**
- Symptoms: If two processes call `mem.learn()` with duplicate content simultaneously, both may pass dedup checks and insert duplicates.
- Files: `src/memos/dedup.py` (lines 67-80), `src/memos/core.py` (line 194-196)
- Trigger: Run `memos learn "content"` in parallel from two shell sessions with `backend="json"` or in-memory backend.
- Workaround: Use server-backed MemOS (via `memos serve`) with single API entry point, not multiple concurrent CLI calls.

**Knowledge Graph time parsing accepts invalid formats silently:**
- Symptoms: `memos kg-add ... --from 2025-13-45` (invalid month/day) returns success but stores epoch 0 or garbage timestamp.
- Files: `src/memos/knowledge_graph.py` (lines 22-53)
- Trigger: Call `kg_add_fact()` with malformed ISO date like "2025-99-99".
- Workaround: None — caller must validate dates before passing to KG. Add a test for invalid date rejection.

**MCP tools don't validate input schema strictly:**
- Symptoms: Calling `memory_search` with `top_k=-1` or `top_k=999999` succeeds but may cause unexpected behavior (negative results, OOM on large stores).
- Files: `src/memos/mcp_server.py` (lines 44-64), `src/memos/api/routes/memory.py` (lines 18-31)
- Trigger: Send malformed MCP request via HTTP POST to `/mcp` with invalid `top_k`.
- Workaround: API layer doesn't clamp or validate `top_k` bounds. Add request validation in route handlers.

**Encrypted backend doesn't validate decryption failures:**
- Symptoms: If encryption key is wrong but data is decrypted anyway (due to malformed ciphertext), the decrypted value is nonsense but not flagged as corrupt.
- Files: `src/memos/storage/encrypted_backend.py`
- Trigger: Create encrypted store with key A, try to decrypt with key B.
- Workaround: None — add HMAC verification to encrypted_backend to detect wrong key or corruption.

## Security Considerations

**Encryption uses custom XOR cipher instead of established library:**
- Risk: `src/memos/crypto.py` implements a custom XOR-based stream cipher rather than using `cryptography.fernet` or similar. While PBKDF2 key derivation is correct, the XOR cipher may have subtle flaws.
- Files: `src/memos/crypto.py` (lines 57-71, 73-99)
- Current mitigation: 600k PBKDF2 iterations make brute-force expensive. HMAC provides integrity check.
- Recommendations: (1) Switch to `cryptography.Fernet` (AES-128-CBC + HMAC) for production security. (2) Keep XOR cipher for backwards compatibility if needed, but mark as deprecated. (3) Add security audit note in README.

**API doesn't enforce rate limiting on recall/learn endpoints:**
- Risk: `/api/v1/recall` and `/api/v1/learn` endpoints accept unlimited requests. A malicious client can spam embeddings (expensive on ARM64) or exhaust storage.
- Files: `src/memos/api/routes/memory.py` (lines 18-31, 68-120)
- Current mitigation: None. `src/memos/api/ratelimit.py` exists but may not be wired into all routes.
- Recommendations: (1) Implement token-bucket rate limiting (e.g., 10 recalls/min, 5 learns/min). (2) Add API key validation if exposed to untrusted networks. (3) Document rate limits in API docs.

**Namespace ACL doesn't prevent privilege escalation:**
- Risk: `src/memos/namespaces/acl.py` enforces role-based access but the `_check_acl()` call in MemOS is skipped if namespace is empty. An agent can set `namespace=""` to bypass all ACL checks.
- Files: `src/memos/core.py` (lines 244-249), `src/memos/namespaces/acl.py`
- Current mitigation: Only enforced if `set_agent_id()` is called first (optional).
- Recommendations: (1) Make ACL enforcement mandatory when multi-agent mode is detected. (2) Prevent empty namespace if agents are registered. (3) Add tests for privilege escalation scenarios.

**Pinecone API key in env or memory unencrypted:**
- Risk: `MEMOS_PINECONE_API_KEY` environment variable and `api_key` parameter in `PineconeBackend.__init__()` are never masked or encrypted in logs/errors.
- Files: `src/memos/storage/pinecone_backend.py` (lines 26-99)
- Current mitigation: None.
- Recommendations: (1) Mask API keys in log messages (e.g., `pk-****...****`). (2) Never print API keys in exception messages. (3) Use `.env` files (not committed) for sensitive config.

## Performance Bottlenecks

**Embedding cache uses single-threaded SQLite with no WAL contention handling:**
- Problem: `src/memos/cache/embedding_cache.py` opens a new SQLite connection per lookup/store cycle. With many concurrent requests, WAL lock contention causes stalls.
- Files: `src/memos/cache/embedding_cache.py` (lines 30-44), `src/memos/storage/chroma_backend.py` (lines 30-44)
- Cause: SQLite is single-writer; Ollama embeddings are slow (~15s per embedding on ARM64). Every request waits for embedding, then cache writes it synchronously.
- Improvement path: (1) Use a persistent connection pool with `timeout=30`. (2) Move cache writes to a background queue to unblock requests. (3) Consider Redis cache for multi-process scenarios.

**Dedup scan is O(n²) for large stores:**
- Problem: `src/memos/dedup.py` (lines 80-150) iterates all memories for exact hash + near-duplicate trigram similarity. With 10k memories, this is 100M comparisons.
- Files: `src/memos/dedup.py`
- Cause: Trigram Jaccard similarity is computed on-the-fly for every pair. No spatial indexing or approximation.
- Improvement path: (1) Use MinHash for approximate similarity (reduces complexity to O(k) where k is sketch size). (2) Cache trigram sets to avoid recomputation. (3) Add `--quick` mode that only checks exact hash.

**Knowledge Graph queries don't use indexes:**
- Problem: `src/memos/knowledge_graph.py` (lines 180-220) does full table scans for entity lookups. With 100k triples, this is slow.
- Files: `src/memos/knowledge_graph.py`
- Cause: SQLite schema has a `CREATE INDEX IF NOT EXISTS` on `(subject, predicate, object)` but queries sometimes miss optimal index paths.
- Improvement path: (1) Add composite index on `(subject, valid_from, valid_to)` for temporal queries. (2) Profile with EXPLAIN QUERY PLAN. (3) Add query result caching for repeated queries.

**Wiki living compilation re-parses all memories on every update:**
- Problem: `src/memos/wiki_living.py` (lines 200-500) iterates all memories and tags to rebuild entity pages. With 10k memories, this is expensive on every learn() call.
- Files: `src/memos/wiki_living.py`
- Cause: No incremental updates — always full recompile. Even small edits trigger full scan.
- Improvement path: (1) Track delta (new memories since last compile). (2) Only update affected entity pages. (3) Add `--full-rebuild` flag to force recompilation; make `update_for_item()` incremental by default.

## Fragile Areas

**Core MemOS learn/recall methods are 1800+ lines:**
- Files: `src/memos/core.py` (1816 lines total)
- Why fragile: Single file contains initialization, ACL, event bus, versioning, encryption, dedup, decay, analytics, sharing — all tightly coupled. Changes to one feature (e.g., adding a new hook) require understanding entire context. No clear dependency order.
- Safe modification: (1) Split into logical modules: `_MemOSCore` (learn/recall), `_MemOSVersioning`, `_MemOSSharing`, etc. (2) Use composition instead of inheritance. (3) Add integration tests for cross-module interactions (e.g., encryption + versioning).
- Test coverage: 30+ tests in `test_core.py`, but many only test happy path. Edge cases (e.g., encryption + versioning + dedup) lack coverage.

**API routes don't validate input consistently:**
- Files: `src/memos/api/routes/memory.py` (542 lines), `src/memos/api/routes/knowledge.py` (366 lines), `src/memos/api/routes/admin.py` (333 lines)
- Why fragile: Each route has ad-hoc validation (some check types, some don't; some clamp values, some don't). No shared request/response schema validation.
- Safe modification: (1) Add Pydantic models for all request bodies (e.g., `LearnRequest`, `RecallRequest`). (2) Use FastAPI dependency injection for ACL checks. (3) Add request/response middleware to enforce schema.
- Test coverage: 15+ API tests, but missing: negative cases (invalid JSON, missing fields), edge cases (empty lists, negative numbers), concurrent requests.

**Storage backend interface has no async consistency:**
- Files: `src/memos/storage/base.py`, `src/memos/storage/async_base.py`, `src/memos/storage/async_wrapper.py`
- Why fragile: Sync and async interfaces exist in parallel. Async wrapper delegates to sync methods via thread pool. If a backend overrides one but not the other, they may diverge.
- Safe modification: (1) Make all backends async-first. (2) Provide sync adapter that wraps async. (3) Add tests that run both sync and async paths in parallel to detect divergence.
- Test coverage: `test_async.py` and `test_async_consolidation.py` exist, but don't test all backends. Pinecone async is untested.

## Scaling Limits

**JSON backend can't handle >100k memories:**
- Current capacity: Tested up to 10k in-memory; 100k JSON file is ~50MB and takes 5s to load.
- Limit: At 1M memories, JSON load/save is 500MB and 50+ seconds. Single-threaded JSON parsing becomes bottleneck.
- Scaling path: (1) Migrate to Chroma/Qdrant for large stores. (2) Add sharding docs (one JSON file per namespace/shard).

**Ollama embeddings with single instance saturate at ~10 req/s:**
- Current capacity: ARM64 Ollama (no GPU) embeds at ~1 embedding per 15s = 4 req/min.
- Limit: More than 5 concurrent recall requests queue up waiting for embeddings. P99 latency > 60s.
- Scaling path: (1) Run Ollama with GPU support. (2) Use cloud embeddings (Pinecone, etc.). (3) Add embedding batch queue to amortize latency.

**Encryption overhead scales with memory size:**
- Current capacity: Encrypting 10k memories takes ~1s. 100k memories takes ~10s (linear).
- Limit: At 1M memories, encryption becomes noticeable (~100s startup time).
- Scaling path: (1) Support per-namespace encryption keys (encrypt only sensitive namespaces). (2) Use streaming encryption for large stores instead of whole-file.

**Knowledge Graph SQLite doesn't index temporal queries:**
- Current capacity: KG with 100k triples, queries return in <100ms.
- Limit: At 1M triples, temporal queries (range on valid_from/valid_to) are slow without composite indexes.
- Scaling path: (1) Add indexes as noted above. (2) Consider time-series DB (InfluxDB, TimescaleDB) for temporal facts.

## Dependencies at Risk

**Sentence-transformers dependency is optional but impacts feature parity:**
- Risk: `pip install memos-agent` (no `[local]`) doesn't include sentence-transformers. Local embeddings silently fail with warning log.
- Impact: Users expecting local-first are surprised when recall doesn't work without Ollama.
- Migration plan: (1) Make sentence-transformers a core dependency (not optional). (2) Or, catch import errors and raise clear error at first local-embedder call. (3) Document feature + dependency mapping in README.

**Pinecone client version locked to >=3.0 but API may change:**
- Risk: Pinecone SDK is rapidly evolving. `src/memos/storage/pinecone_backend.py` assumes specific API (ServerlessSpec, Pod Index names, etc.).
- Impact: Pinecone version bump breaks MemOS without warning.
- Migration plan: (1) Add `pip install "pinecone-client>=3.0,<4.0"` to pin minor version. (2) Add integration tests that run against live Pinecone to catch regressions.

**Chroma client has been deprecated in favor of new API:**
- Risk: `chromadb>=0.4` is compatible, but Chroma 1.x changed collection API significantly.
- Impact: Future Chroma upgrades may require MemOS refactor.
- Migration plan: (1) Pin to `chromadb>=0.4,<1.0` for now. (2) Plan Chroma 1.x migration. (3) Add CI test against both versions.

## Missing Critical Features

**No backup/restore mechanism beyond parquet export:**
- Problem: `memos export parquet` works, but there's no `memos import parquet` to restore. Users who lose their store have no recovery path.
- Blocks: Production deployments require backup strategy.
- Implementation: Add `memos import parquet <file>` with conflict resolution (skip/merge/overwrite). Add `memos backup` cron helper. Document 3-2-1 backup strategy in README.

**ACL doesn't support temporary access grants (expiration):**
- Problem: `NamespacePolicy.expires_at` field exists but `_check_acl()` doesn't validate expiration. Agents keep access forever even if `expires_at` is set.
- Blocks: Multi-agent systems can't enforce temporary permissions (e.g., "read access for 24 hours").
- Implementation: Add expiration check in `_check_acl()`. Add CLI `memos acl grant ... --expires-in 24h`. Add tests.

**No audit log for memory mutations:**
- Problem: No record of who modified/deleted what and when. Useful for compliance, debugging, and multi-agent accountability.
- Blocks: Enterprise deployments need audit trails.
- Implementation: Add audit logger to `EventBus`. Log all learn/delete/prune events with agent_id, timestamp, content hash. Export to syslog or file.

## Test Coverage Gaps

**Concurrency tests don't cover all backends:**
- What's not tested: Concurrent learn/recall against Qdrant, Pinecone, and encrypted backends.
- Files: `tests/test_async.py` (64 lines), `tests/test_async_consolidation.py` (160 lines)
- Risk: Race conditions lurk in Pinecone (async client library). Encryption + versioning concurrency untested.
- Priority: High — add tests for each backend with 10 concurrent writers.

**API input validation is not comprehensive:**
- What's not tested: Invalid JSON, missing required fields, type mismatches, negative/overflowing numbers, very long strings (>1MB).
- Files: `tests/test_api_*.py` (only happy path tests exist)
- Risk: Malformed requests may crash API or expose internal errors.
- Priority: High — add parametrized tests for invalid inputs to all routes.

**Encryption + versioning interactions untested:**
- What's not tested: Learn encrypted memory → create version → decrypt → verify content matches.
- Files: `tests/test_api_versioning.py` (doesn't test with encryption enabled)
- Risk: Silent data loss if versioning engine doesn't preserve encrypted payloads correctly.
- Priority: Medium — add `test_versioning_with_encryption()`.

**Multi-namespace isolation not tested for security:**
- What's not tested: Agent A tries to read Agent B's namespace; agent escalation via empty namespace; concurrent namespace creation/deletion.
- Files: `tests/test_auth.py` (37 tests but limited scope)
- Risk: ACL bypass or namespace collision.
- Priority: High — add adversarial tests for ACL enforcement.

**Knowledge Graph temporal queries lack edge cases:**
- What's not tested: Queries with overlapping validity windows, null valid_from/valid_to, timezone conversions, relative date parsing ("2d" means different values in different tests).
- Files: `tests/test_knowledge_graph.py` (~100 tests but temporal logic sparse)
- Risk: Subtle bugs in date logic affect historical queries.
- Priority: Medium — add temporal query matrix tests.

---

*Concerns audit: 2026-04-13*
