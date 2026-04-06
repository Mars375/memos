# Changelog

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
