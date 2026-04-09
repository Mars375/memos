# Changelog

## v0.40.0 (2026-04-09) — Memory Compression

### New Features

- **Memory compression for decayed memories**
  - New `MemoryCompressor` groups low-importance memories by shared tags
  - Generates aggregated summary memories with `compressed` metadata and tags
  - Dry-run and apply mode via `MemOS.compress()`
- **New surfaces**
  - CLI: `memos compress [--threshold 0.1] [--dry-run]`
  - API: `POST /api/v1/compress`

### Tests

- 7 focused compression tests added
- Full suite: **1424 tests passing**

## v0.39.0 (2026-04-09) — Auto KG Extraction on Write

### New Features

- **Auto KG extraction in `MemOS.learn()`**
  - New zero-LLM `KGExtractor` with explicit FR/EN relation patterns
  - Automatic fact creation on every write, with `auto_kg=False` escape hatch per call
  - `MEMOS_AUTO_KG` and `MEMOS_KG_DB` config support
- **Preview surfaces**
  - CLI: `memos extract-kg "..."`
  - API: `POST /api/v1/kg/extract`
  - `POST /api/v1/learn` now accepts `auto_kg`
- **KG bridge refresh**
  - `learn_and_extract()` now reuses the shared extractor and avoids duplicate fact insertion

### Tests

- 56 focused extractor/bridge tests added or refreshed
- Full suite: **1416 tests passing**

---

## v0.14.0 (2026-04-07) — Memory Compaction + Embedding Cache

### New Features

- **Memory Compaction Engine** (`memos.compaction`)
  - 4-phase pipeline: dedup → archive → stale merge → cluster compact
  - `MemOS.compact()` with configurable thresholds and dry-run mode
  - Archive old low-relevance memories (tag-based, recoverable)
  - Merge semantically similar stale memories into summaries
  - Cluster compaction for large tag-based groups
  - Budget-per-run limit for safe periodic execution
  - CLI: `memos compact --dry-run --json`

- **Persistent Embedding Cache** (`memos.cache`)
  - SQLite-backed LRU cache for vector embeddings
  - Avoids recomputing embeddings across sessions
  - L1 (in-memory) + L2 (disk) two-tier caching
  - Configurable TTL and max size with eviction
  - Cache hit/miss statistics
  - CLI: `memos cache-stats --clear`

### Tests
- 23 tests for embedding cache (basic, TTL, eviction, stats, persistence)
- 23 tests for compaction engine (archive, stale groups, pipeline, integration)
- Total: **569 tests**

---

## v0.13.0 (2026-04-07) — Persistent Versioning + Namespace Access Control

### New Features

**Persistent Versioning (SQLite)**
- `SqliteVersionStore` — persistent version storage backend using SQLite (zero external deps, Python stdlib)
- `PersistentVersionStore` — abstract interface for pluggable persistent version stores
- `VersioningEngine` now supports `persistent_path` parameter for automatic SQLite persistence
- Version history survives restarts — critical for production deployments
- WAL mode + thread-safe connection-per-thread pattern for concurrency
- `versioning_path` parameter on `MemOS()` constructor
- Auto-GC when max versions per item exceeded

**Namespace Access Control (RBAC)**
- `NamespaceACL` — role-based access control manager for multi-agent memory isolation
- Four roles: `owner` (full control), `writer` (read+write+delete), `reader` (read-only), `denied` (explicit block)
- `MemOS.set_agent_id()` — sets agent identity for ACL enforcement
- ACL checks on `learn()`, `recall()`, `forget()`, `batch_learn()`, `search()`
- Empty namespace or no agent_id → ACL bypassed (backward compatible)
- Policy expiration support (auto-cleanup)
- REST API: `POST /namespaces/{ns}/grant`, `POST /namespaces/{ns}/revoke`, `GET /namespaces/{ns}/policies`
- CLI: `memos ns-grant`, `memos ns-revoke`, `memos ns-policies`, `memos ns-stats`

### Tests
- 58 new tests (SqliteVersionStore: 14, VersioningEngine persistent: 4, MemOS persistent: 2, ACL: 25, ACL integration: 13)
- **524 total tests, all passing**

## v0.12.0 (2026-04-07) — CLI Versioning Commands + HTTP Versioning API

### New Features

#### CLI Versioning Commands (7 new commands)
- **`memos history <item_id>`** — show full version history for a memory item
  - `--json` for structured output
- **`memos diff <item_id>`** — show diff between two versions
  - `--v1 N --v2 M` for specific versions, `--latest` for last two
  - Shows content, tags, importance, and metadata changes
- **`memos rollback <item_id> --version N`** — roll back a memory to a previous version
  - `--dry-run` to preview, `--yes` to confirm
- **`memos snapshot-at <timestamp>`** — view all memories as they were at a point in time
  - Supports epoch, ISO 8601, and relative timestamps (e.g. `1h`, `2d`, `1w`)
- **`memos recall-at <query> --at <timestamp>`** — time-travel semantic search
  - Query memories as they existed at any past point
- **`memos version-stats`** — show versioning statistics
  - `--json` for structured output
- **`memos version-gc`** — garbage collect old memory versions
  - `--max-age-days N` and `--keep-latest N` controls
  - `--dry-run` to preview

#### HTTP Versioning API (9 new endpoints)
- `GET /api/v1/memory/{id}/history` — version history for an item
- `GET /api/v1/memory/{id}/version/{n}` — get a specific version
- `GET /api/v1/memory/{id}/diff?v1=N&v2=M` — diff between versions
- `POST /api/v1/memory/{id}/rollback` — roll back to a version
- `GET /api/v1/snapshot?at=<epoch>` — snapshot of all memories at a timestamp
- `GET /api/v1/recall/at?q=<query>&at=<epoch>` — time-travel recall
- `GET /api/v1/recall/at/stream?q=<query>&at=<epoch>` — SSE streaming time-travel recall
- `GET /api/v1/versioning/stats` — versioning statistics
- `POST /api/v1/versioning/gc` — garbage collect old versions

#### Flexible Timestamp Parsing
- Epoch (float/int): `1712457600`
- ISO 8601: `2026-04-07T12:00:00`, `2026-04-07`
- Relative: `1h` (1 hour ago), `30m`, `2d`, `1w`

### Tests
- 53 new tests (34 CLI + 19 API)
- Total: **466 tests** (413 + 53)


## v0.11.0 (2026-04-07) — Memory Versioning & Time-Travel

### New Features

- **Memory Versioning** — every `learn()` and `batch_learn()` automatically creates a version snapshot
  - Version history: `mem.history(item_id)` lists all versions with timestamps
  - Get specific version: `mem.get_version(item_id, version_number)`
  - Version diff: `mem.diff(item_id, v1, v2)` shows changed fields (content, tags, importance, metadata)
  - Latest diff: `mem.diff_latest(item_id)` compares last two versions
  - Version sources: `learn`, `batch_learn`, `rollback`, `upsert`

- **Time-Travel Recall** — query memories as they were at any point in time
  - `mem.recall_at(query, timestamp)` — semantic search reconstructed to past state
  - `mem.snapshot_at(timestamp)` — all memories at a given moment
  - Items that didn't exist at that time are automatically excluded

- **Rollback** — restore a memory to a previous version
  - `mem.rollback(item_id, version_number)` — restores content, tags, importance, metadata
  - Creates a new version with source="rollback" for full audit trail

- **Version GC** — garbage collect old versions while keeping recent ones
  - `mem.versioning_gc(max_age_days=90, keep_latest=3)` — removes stale versions
  - `mem.versioning_stats()` — monitor versioning overhead

- **Versioning Events** — `time_traveled` and `rolled_back` events on the EventBus

### New Module

- `memos.versioning` — `models.py`, `store.py`, `engine.py`

### Tests

- 48 new tests for versioning (models, store, engine, MemOS integration)
- Total: **413 tests** (365 + 48)

### Bug Fixes

- Fixed potential deadlock in VersionStore (Lock → RLock for reentrant access)
- Fixed GC logic to correctly keep latest N versions per item

## v0.10.0 (2026-04-06) — Async Consolidation + Parquet Export/Import

### New Features

#### Async Consolidation
- **`await mem.consolidate_async()`** — Run consolidation in the background without blocking the event loop.
  - Returns an `AsyncConsolidationHandle` with `task_id`, `status`, and result polling.
  - Consolidation runs in a thread pool executor for non-blocking operation.
  - Events: `consolidation_started`, `consolidation_completed`, `consolidation_failed`.
  - Status polling: `mem.consolidation_status(task_id)` and `mem.consolidation_tasks()`.
- **`POST /api/v1/consolidate`** — REST endpoint supporting both sync and async modes.
  - `?async=true` starts background consolidation, returns `task_id`.
  - `GET /api/v1/consolidate/{task_id}` polls status.
  - `GET /api/v1/consolidate` lists all tasks.

#### Parquet Export/Import
- **`mem.export_parquet(path)`** — Export all memories to an Apache Parquet file.
  - Columnar binary format: 3-10x smaller than JSON, faster to read/write.
  - Configurable compression: zstd (default), snappy, gzip, none.
  - Optional metadata column (JSON-encoded).
- **`mem.import_parquet(path)`** — Import memories from Parquet with merge strategies.
  - Supports `skip`, `overwrite`, `duplicate` merge modes.
  - `tags_prefix` for tagging imported batches.
  - `dry_run` mode for validation without storage.
- **CLI**: `memos export --format parquet -o file.parquet` and `memos import file.parquet` (auto-detects `.parquet` extension).
- **REST**: `GET /api/v1/export/parquet` downloads a Parquet file.
- **Optional dependency**: `pip install memos[parquet]` (requires `pyarrow>=12.0`).

### SDK Usage
```python
# Parquet export (binary, compressed)
result = mem.export_parquet("memories.parquet", compression="zstd")
# {"total": 150, "size_bytes": 8192, "compression": "zstd"}

# Parquet import with merge
result = mem.import_parquet("backup.parquet", merge="skip", tags_prefix=["backup"])

# Async consolidation
handle = await mem.consolidate_async(similarity_threshold=0.7)
status = mem.consolidation_status(handle.task_id)
```

### Tests
- 38 new tests covering:
  - Parquet export: creates file, metadata, compression, empty store, parent dirs, field preservation (7 tests)
  - Parquet import: roundtrip count/content/tags/importance, skip, overwrite, tags_prefix, dry_run, file not found, empty (10 tests)
  - Parquet metadata: roundtrip with/without metadata (2 tests)
  - Parquet CLI: export/import via CLI (2 tests)
  - Parquet IO unit: special chars, large export (2 tests)
  - Async consolidation handle: initial state, to_dict (3 tests)
  - Async consolidation engine: start+complete, dry_run, get_status, list_tasks, clear_completed, events, empty store (7 tests)
  - MemOS async integration: consolidate_async, consolidation_status, tasks list (5 tests)
- Total test suite: **365 tests, all passing**

### Files Added
- `src/memos/parquet_io.py` — Parquet export/import module
- `src/memos/consolidation/async_engine.py` — Async consolidation engine
- `tests/test_parquet.py` — Parquet tests (23 tests)
- `tests/test_async_consolidation.py` — Async consolidation tests (15 tests)

### Files Modified
- `src/memos/core.py` — Added `export_parquet()`, `import_parquet()`, `consolidate_async()`, `consolidation_status()`, `consolidation_tasks()`
- `src/memos/cli.py` — Added `--format`, `--compression` flags; auto-detect `.parquet` on import
- `src/memos/api/__init__.py` — Added Parquet export endpoint, async consolidation endpoints
- `pyproject.toml` — Added `parquet` optional dep, bumped to v0.10.0

---

## v0.9.0 (2026-04-06) — Batch Learn API + Pinecone Backend

### New Features

#### Batch Learn API
- **`MemOS.batch_learn()`** — Store multiple memories in a single call with validation, sanitization, and error handling.
  - Accepts list of dicts: `content` (required), `tags`, `importance`, `metadata`
  - `continue_on_error` mode: skip invalid items vs raise on first error
  - Returns detailed result: `learned`, `skipped`, `errors` counts + item details
  - Emits `batch_learned` event on the event bus
  - Optimized for backends with `upsert_batch()` support
- **`POST /api/v1/learn/batch`** — REST endpoint for batch learning
  - Accepts up to 1000 items per request
  - Configurable error handling via `continue_on_error` param
- **`memos batch-learn`** — CLI command for batch learning from JSON files
  - Supports stdin (`-`) for piping data
  - `--strict` mode for fail-fast behavior
  - `--verbose` for detailed output

#### Pinecone Storage Backend
- **`PineconeBackend`** — Full `StorageBackend` implementation with:
  - Pinecone Serverless (recommended) and Pod-based index support
  - Native vector similarity search via `vector_search()`
  - Batch upsert (`upsert_batch()`) for efficient bulk operations (100-item batches)
  - Automatic index creation on first use
  - Namespace isolation via Pinecone namespaces
  - Embedding computation and caching (Ollama-compatible)
  - Keyword fallback search when vectors unavailable
  - Configurable: `cloud`, `region`, `metric`, `vector_size`, `index_name`
- **`pip install memos[pinecone]`** — Optional dependency
- **MemOS integration** — `MemOS(backend="pinecone", pinecone_api_key="...")`

### SDK Usage
```python
# Batch learn
result = mem.batch_learn([
    {"content": "User prefers Python", "tags": ["preference"]},
    {"content": "Server on ARM64", "tags": ["infra"]},n    {"content": "Dark mode enabled", "tags": ["ui"]},
])
# result = {"learned": 3, "skipped": 0, "errors": [], "items": [...]}

# Pinecone backend
mem = MemOS(
    backend="pinecone",
    pinecone_api_key="pc-key-...",
    pinecone_index_name="my-agent-memories",
)
```

### Tests
- 30 new tests covering:
  - Batch learn core: basic, importance, empty content, strict mode, sanitization, dedup, metadata, integration, large batch (11 tests)
  - Batch learn events: emit verification, empty batch (2 tests)
  - Pinecone backend unit: ID conversion, metadata serialization, upsert, batch upsert, delete, get, list, search, namespaces (15 tests)
  - Pinecone integration: MemOS init with Pinecone, batch learn via Pinecone (2 tests)
- Total test suite: **327 tests, all passing**

### Files Added
- `src/memos/storage/pinecone_backend.py` — Pinecone backend (300+ LOC)
- `tests/test_batch_learn.py` — Batch learn tests (120+ LOC)
- `tests/test_pinecone.py` — Pinecone backend tests (250+ LOC)

### Files Modified
- `src/memos/core.py` — Added `batch_learn()` method + Pinecone backend init
- `src/memos/api/__init__.py` — Added `POST /api/v1/learn/batch` endpoint
- `src/memos/cli.py` — Added `batch-learn` subcommand + Pinecone backend choices
- `pyproject.toml` — Added `pinecone` optional dependency
- `README.md` — Updated with batch learn + Pinecone docs
- `CHANGELOG.md` — This entry

---

## v0.8.0 (2026-04-06) — SSE Streaming Recall API

### New Features
- **Streaming recall API** (`GET /api/v1/recall/stream`) — Server-Sent Events endpoint that streams recall results as they are found, allowing LLM agents to start processing partial results before the full search completes.
- **Async `recall_stream()` generator** — `MemOS.recall_stream()` is an async generator that yields `RecallResult` objects one at a time with proper event loop yielding for concurrent processing.
- **SSE utilities module** (`memos.api.sse`) — Reusable SSE event formatting:
  - `SSEEvent` dataclass with wire-format encoding
  - `format_recall_event()`, `format_done_event()`, `format_error_event()` helpers
  - `sse_stream()` async wrapper that turns any async iterator into SSE output

### SSE Endpoint
```
GET /api/v1/recall/stream?q=<query>&top=5&filter_tags=tag1,tag2&min_score=0.0
```
Returns `text/event-stream` with:
- `event: recall` — one per result, with `id`, `content`, `score`, `tags`, `match_reason`, `age_days`
- `event: done` — completion summary with `count`, `query`, `elapsed_ms`
- `event: error` — error details if something fails mid-stream

### Tests
- 32 new streaming tests covering:
  - SSE wire format encoding (7 tests)
  - Format helpers (5 tests)
  - recall_stream() async generator (7 tests)
  - sse_stream() wrapper (6 tests)
  - Integration: recall_stream → sse_stream pipeline (3 tests)
  - Edge cases: unicode, special chars, concurrent streams (4 tests)
- Total test suite: **297 tests, all passing**

### Files Added
- `src/memos/api/sse.py` — SSE event utilities (130 LOC)
- `tests/test_streaming.py` — Streaming tests (400+ LOC)

### Files Modified
- `src/memos/core.py` — Added `recall_stream()` async generator
- `src/memos/api/__init__.py` — Added `GET /api/v1/recall/stream` endpoint + StreamingResponse import

---

## v0.7.0 (2026-04-06) — Qdrant Backend + Hybrid Search

### New Features
- **Qdrant storage backend** (`QdrantBackend`) — full `StorageBackend` implementation with:
  - Native vector similarity search via Qdrant client
  - Hybrid BM25+vector scoring with configurable weights
  - Local (file-based) and remote (HTTP/gRPC) connection modes
  - Namespace isolation via separate Qdrant collections
  - Automatic embedding computation and caching
  - Original ID preservation in payload (survives UUID roundtrip)
- **Enhanced retrieval engine** — `RetrievalEngine.search()` now:
  - Auto-detects `QdrantBackend` and delegates to native hybrid search
  - Supports configurable `semantic_weight` (default 0.6) for hybrid scoring
  - Passes namespace through to all search paths
- **Config additions**: `qdrant_host`, `qdrant_port`, `qdrant_api_key`, `qdrant_path`, `vector_size`, `semantic_weight`
- **Docker Compose Qdrant profile** — `docker compose --profile qdrant up`

### Tests
- 37 new Qdrant-specific tests (mocked client, no server needed)
- Total test suite: **265 tests, all passing**
- Coverage: upsert/get/delete/list_all/search/vector_search/hybrid_search/namespaces/lazy-init/ID-conversion

### Files Added
- `src/memos/storage/qdrant_backend.py` — 340+ LOC
- `tests/test_qdrant.py` — 400+ LOC

### Files Modified
- `src/memos/core.py` — Qdrant backend support + kwargs passthrough
- `src/memos/retrieval/engine.py` — Qdrant-native hybrid search delegation
- `src/memos/config.py` — Qdrant configuration keys
- `src/memos/storage/__init__.py` — Lazy Qdrant import
- `docker-compose.yml` — Qdrant service profile
- `README.md` — Updated docs with Qdrant section
- `pyproject.toml` — qdrant optional dep already present from v0.6.0

---

## v0.6.0 (2026-04-06) — Initial Public Release

- Core memory system: learn, recall, forget, prune
- In-memory and ChromaDB backends
- BM25 + embedding hybrid retrieval
- Decay engine with importance-aware forgetting
- Memory sanitizer (prompt injection guard)
- Encrypted storage wrapper
- Consolidation engine (duplicate merging)
- File ingestion (Markdown, JSON, TXT)
- Export/Import (JSON)
- REST API with auth
- WebSocket event bus
- CLI with init/learn/recall/prune/stats/serve
- Web dashboard
- Docker support
- 228 tests, 5515 LOC, 46 files
