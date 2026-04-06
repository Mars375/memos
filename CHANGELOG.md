# Changelog

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
