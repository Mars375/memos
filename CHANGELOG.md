# Changelog

## v2.3.3 (2026-04-20) — Hardening Follow-up

### Security and correctness
- Serialized `/api/v1/mine/conversation` execution to avoid namespace leakage when conversation mining runs against shared `MemOS` state
- Hardened rate-limit bucket eviction against invalid `max_buckets` values and fixed stale-bucket cleanup on short-lived CI runners
- Tightened URL/path safety and public API guardrails introduced during the previous hardening pass

### Architecture and tests
- Finished the `api/routes/memory.py` decomposition into focused helper modules while preserving the stable router entrypoint
- Reduced `wiki_engine.py` to a coordinator facade backed by focused core, update, lint, index, and page helper modules
- Added direct regression coverage for split facades, MCP tools, and wiki modules to reduce reliance on compatibility shims

### Maintenance
- Refreshed contributor/agent/docs metadata to match the split architecture and current Docker/deployment flow
- Re-ran Ruff formatting on the new split modules and regression tests so CI formatting checks stay green

---

## v2.3.2 (2026-04-18) — Core Facades and Scan Reuse

### Core decomposition
- Extracted `FeedbackFacade`, `IOFacade`, `MaintenanceFacade`, `SharingFacade`, and `VersioningFacade` from `core.py`
- Kept `MemOS` focused on its CRUD and orchestration nucleus while moving cross-cutting concerns into dedicated mixins
- Added structural regression tests for the new facades to preserve inherited public APIs

### Performance improvements
- Reused preloaded item lists in context generation and graph responses instead of rescanning the store for statistics
- Threaded filtered item lists through retrieval and consolidation paths to avoid redundant `list_all()` calls in hybrid query and compaction flows

### Verification
- Full test suite green after each extraction and after the performance cleanup

---

## v2.3.1 (2026-04-18) — Cleanup and Consistency

### API consistency
- Standardized validation and error responses across admin and knowledge-facing endpoints
- Split the previous `api/routes/knowledge.py` monolith into focused route modules for KG, brain, palace, context, and wiki APIs
- Added route-level characterization coverage to preserve URLs and behavior during the split

### Knowledge graph lifecycle cleanup
- Made `MemOS` own `kg` and `kg_bridge` explicitly with lazy helpers and startup wiring
- Migrated major KG consumers to public handles instead of relying on private `_kg` / `_kg_bridge` attributes
- Replaced direct `_kg._conn` reads in brain/wiki layers with public `KnowledgeGraph` helper methods

### Performance improvements
- Reduced redundant store rescans in the compaction pipeline by only refreshing between phases when mutations actually occurred
- Reused the dedup index scan for near-duplicate checks instead of rescanning the store during `DedupEngine.check()`

### Tests
- Added and updated regression tests for API validation, route decomposition, KG lifecycle wiring, and full-scan reductions

---

## v2.3.0 (2026-04-17) — Intelligence Layer

Five major feature sets inspired by Karpathy's LLM Wiki, Graphify, and MemPalace.

### Feature 1: Enriched Knowledge Graph Extraction
- **15+ SVO regex patterns** in `kg_bridge.py` — `deployed_on`, `uses`, `runs_on`, `manages`, `depends_on`, `contains`, `located_in`, `part_of`, `connected_to`, `built_with`, `hosts` + general SVO fallback
- **Community detection** — label-propagation clustering on KG adjacency, 60s cache, zero external deps
- **God nodes** — top-degree hub entities with `degree`, `facts_as_subject`, `facts_as_object`, `top_predicates`
- New endpoints: `GET /api/v1/kg/communities`, `GET /api/v1/kg/god-nodes`
- New MCP tools: `kg_communities`, `kg_god_nodes`

### Feature 2: Hybrid Retrieval v2
- **Temporal proximity boosting** — continuous linear decay within configurable window (default 1h), weighted at 0.05
- **Importance-weighted scoring** — memory importance factor wired into retrieval pipeline
- **Preference pattern extraction** — repeated query topics tracked and boosted
- **LLM reranking pipeline** — optional post-retrieval rerank with configurable model, graceful fallback

### Feature 3: Wiki Auto-Compilation (Karpathy-inspired)
- **Auto-update on learn/ingest** — every `learn()` triggers wiki page creation/update for extracted entities
- **Karpathy-style index.md** — categorized (Entities, Concepts, Sources, Topics), freshness indicators (🟢🟡🔴), relevance sorting, statistics header, recent changes
- **Query answers → wiki pages** — brain search results optionally filed as wiki pages
- **Wiki lint** — orphan pages, missing cross-references, stale pages (>30d), empty pages, contradiction detection ("X is Y" vs "X is not Y")
- New endpoints: `POST /api/v1/wiki/regenerate-index`, `GET /api/v1/wiki/lint`, `GET /api/v1/wiki/log`
- New MCP tools: `wiki_regenerate_index`, `wiki_lint`

### Feature 4: Agent Diaries
- **Agent wing auto-provisioning** — `ensure_agent_wing()` creates `agent:<name>` wing with `diary`, `context`, `learnings` rooms (idempotent)
- **Diary append/read** — per-agent journal entries with tags, ordered newest-first
- **Agent discovery** — `palace_list_agents` MCP tool for cross-agent awareness without prompt bloat
- New endpoints: `POST /api/v1/palace/agents`, `GET /api/v1/palace/agents`, `POST /api/v1/palace/diary`, `GET /api/v1/palace/diary/{agent}`
- New MCP tools: `palace_diary_append`, `palace_diary_read`, `palace_list_agents`

### Feature 5: Dashboard Intelligence
- **Surprising connections** — cross-domain KG edges scored by community distance × confidence × predicate rarity
- **Suggested questions** — auto-generated from god nodes, small communities, ambiguous facts, wiki-sparse entities
- New endpoints: `GET /api/v1/brain/connections`, `GET /api/v1/brain/suggestions`

### Bug Fixes (from v2.2.0 audit)
- **Parquet export** — graceful error when `pyarrow` missing instead of 500 crash
- **Wiki LivingPage** — fixed missing `slug` attribute, added `POST /api/v1/wiki/pages`
- **URL sanitizer** — less aggressive regex, `skip_sanitization` parameter for trusted sources
- **Palace recall** — `query` parameter now optional when `wing` + `room` provided
- **Snapshot** — `at` parameter now defaults to current time
- **Dashboard KG coverage** — fixed always-0% metric

### Stats
- **1975 tests** passing (+265 from v2.2.0)
- 10 new API endpoints, 7 new MCP tools
- 23 commits since v2.2.0

---

## v2.2.0 (2026-04-16) — Standalone Stability

### Improvements
- Standalone Docker image with zero external dependencies (JSON + MiniLM)
- Health check endpoint, rate limiting, Swagger UI
- Memory CRUD, Knowledge Graph, Context system, Memory Palace, Brain search
- Dashboard with force-graph, wiki view, palace view, timeline

---

## v1.1.0 (2026-04-15) — Hardened & Modular

### Security
- **WebSocket auth hardening** — proper origin validation, CORS defaults, public properties exposure fixed
- **API request validation** — Pydantic schemas for all endpoints, proper HTTP status codes
- Silent `except` blocks replaced with explicit logging (no more swallowed errors)

### API
- **Pydantic request schemas** — structured validation with `memory_search`, `memory_save`, `recall` schemas
- **Unified error responses** — consistent JSON error format across all endpoints
- Named constants extracted from magic strings across the codebase

### Dashboard
- **Canvas force-graph** — replaced D3 SVG with force-graph Canvas renderer (fixes #36)
  - Clustering, depth filter, hover tooltips, color modes
  - Time-lapse slider, health panel, link visibility controls
- **Modular frontend** — monolithic 1768L dashboard split into 12 JS modules (#40)
- **P2/P3 features** — wiki view, palace view, time-travel, KG edges (issue #39)

### Codebase
- **Shared test fixtures** — reusable pytest fixtures for API, query engine, and storage tests
- **Test suite modernized** — `freezegun` for time-dependent tests, `tmp_path` for file tests
- **Ruff zero errors** — 506 lint errors fixed, formatting applied across 126 files
- **CI expanded** — Python 3.13 added to test matrix, `docker/metadata-action` bumped v5→v6
- Extracted shared constants and utility functions from `core.py`

### Bug Fixes
- **KG edge matching** — tag matching now prioritized over content words in `buildKGEdges`
- **Import sorting** — fixed across all modules
- Orphaned `src/memos/miner/` directory removed
- Dependabot bumps: `setup-python` v6, `uvicorn` ≥0.44.0, `qdrant-client` ≥1.17.1, `ruff` ≥0.15.10, `codecov-action` v6

### Docker
- All-in-one Docker image with standalone compose profile
- Pinned image versions + log limits in compose

### Stats
- **1710 tests** passing
- 44 commits since v1.0.0
- Dependencies all current

---

## v1.0.0 (2026-04-11) — Stable Release

- **Package renamed to `memos-os`** for PyPI publication
- Deduplication enabled by default with smart comparison
- Lazy imports for all optional backends (Qdrant, Pinecone, ChromaDB)
- **1434 tests passing**

---

## v0.47.0 — Advanced Recall Filters (P31)

- Ship P31 advanced recall filters — extended query predicates for fine-grained memory retrieval

## v0.46.0 — Namespace Management API (P30)

- Ship P30 namespace management API — CRUD endpoints for namespace lifecycle

## v0.45.0 — Memory Deduplication (P29)

- Ship P29 memory deduplication — automatic detection and merging of duplicate memories

## v0.44.0 — API Auth (P28)

- Complete P28 API authentication — token-based auth layer for all REST endpoints

## v0.43.0 — Universal Markdown Export (P27)

- Ship P27 universal markdown export — export entire brain as structured markdown

## v0.42.0 — Entity Graph Dashboard Bridge (P26)

- Deliver P26 entity graph dashboard bridge — live KG visualization in web UI

## v0.41.0 — Unified Brain Search (P25)

- P25 Unified Brain Search — one query across memories, wiki, and knowledge graph

## v0.40.0 — Memory Compression (P24)

- Ship P24 memory compression — reduce storage footprint for large memory stores

## v0.39.0 — Auto KG Extraction (P33)

- Ship P33 auto knowledge-graph extraction — entities and relations mined from memories automatically

## v0.38.0 — Speaker Ownership (P23)

- Conversation miner with per-speaker namespaces — attribute memories to individual speakers

## v0.37.0 — URL Ingest (P22)

- P22 URL ingest support — `memos learn <url>` fetches and stores web content

## v0.36.0 — Hybrid Retrieval Semantic + BM25 (P20)

- P20 hybrid retrieval combining semantic embeddings and BM25 scoring in a single pipeline

## v0.35.0 — Miner Incremental SHA-256 Cache (P19)

- P19 incremental mining cache — SHA-256 content hashing skips already-imported paragraphs

## v0.34.0 — Confidence Labels KG (P18)

- P18 confidence labels on knowledge-graph edges — trust scoring for extracted relations

## v0.33.0 — Zero-LLM Auto-Tagger (P17)

- Zero-LLM auto-tagger for memory type classification — rule-based tagging without API calls

## v0.32.0 — Analytics, KG Bridge, KG Path Queries

- Analytics dashboard improvements and KG bridge fixes
- Living wiki mode — auto-regenerating wiki from memory changes
- **KG Path Queries** — multi-hop graph traversal (P15)
- Universal MCP HTTP endpoint + P16-P24 priority planning

## v0.31.0 — Memory Decay & Reinforcement Engine (P9)

- P9 memory decay and reinforcement — memories weaken over time unless reinforced by access

## v0.30.0 — MCP Server, Wiki Compile, Markdown Migration, Smart Miner

- **MCP server** — JSON-RPC 2.0 bridge for agent tool use (P2)
- **Wiki compile mode** — per-tag markdown pages (P3)
- **Markdown migration tool** — import existing `.md` notes into MemOS (P4)
- **Smart memory miner** — multi-format import with paragraph-aware chunking (P8)
- Discord, Telegram, OpenClaw importers (P8+)

## v0.29.0 — Second Brain Graph Dashboard

- Interactive graph dashboard + `/api/v1/graph` endpoint for memory relationship visualization

## v0.28.0 — Delete Tag

- `delete_tag` — remove a tag from all memories without deleting the memories themselves

## v0.27.0 — Tags Rename

- `tags rename` — rename a tag across all memories (core + CLI + REST, 13 tests)

## v0.26.0 — Tags List

- `memos tags list` — CLI command, core method, and REST endpoint for listing all tags

## v0.25.0 — Search CLI Command

- `memos search` CLI command — keyword-only search mirroring the REST API

## v0.24.0 — Pipe Support for CLI

- `memos learn --stdin` — pipe content into learn from stdin

## v0.23.0 — Get by ID + TTL Fix

- `memos get <id>` — retrieve a specific memory by ID
- Fix TTL persistence in JSON backend

## v0.22.0 — JSON Output + Relevance Feedback

- `recall --format json` — structured JSON output for recall
- Relevance feedback loop for improving retrieval quality

## v0.21.0 — Recall CLI Filters

- `recall` CLI filters: `--tags`, `--after`, `--before` for scoped retrieval

## v0.20.0 — Per-Memory TTL

- Per-memory TTL (time-to-live) with automatic expiry

## v0.19.0 — Backend Migration Engine

- Backend migration command and engine — move data between storage backends

## v0.18.0 — JSON File Backend + Tag-Based Bulk Forget

- **JsonFileBackend** — CLI data now persists across invocations
- Tag-based bulk forget — delete all memories matching a tag set

## v0.17.0 — Filtered Subscriptions & Live Events

- Filtered subscriptions and live event streams on the EventBus

## v0.16.0 — Multi-Agent Memory Sharing

- Multi-agent memory sharing protocol — agents can share and access each other's memories

## v0.15.0 — Per-Endpoint Rate Limiting

- Per-endpoint rate limiting + performance benchmarks

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
- **`memos diff <item_id>`** — show diff between two versions
- **`memos rollback <item_id> --version N`** — roll back a memory to a previous version
- **`memos snapshot-at <timestamp>`** — view all memories as they were at a point in time
- **`memos recall-at <query> --at <timestamp>`** — time-travel semantic search
- **`memos version-stats`** — show versioning statistics
- **`memos version-gc`** — garbage collect old memory versions

#### HTTP Versioning API (9 new endpoints)
- `GET /api/v1/memory/{id}/history` — version history
- `GET /api/v1/memory/{id}/version/{n}` — get a specific version
- `GET /api/v1/memory/{id}/diff?v1=N&v2=M` — diff between versions
- `POST /api/v1/memory/{id}/rollback` — roll back to a version
- `GET /api/v1/snapshot?at=<epoch>` — snapshot at timestamp
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
- Total: **466 tests**

## v0.11.0 (2026-04-07) — Memory Versioning & Time-Travel

### New Features

- **Memory Versioning** — every `learn()` and `batch_learn()` automatically creates a version snapshot
- **Time-Travel Recall** — query memories as they were at any point in time
- **Rollback** — restore a memory to a previous version
- **Version GC** — garbage collect old versions while keeping recent ones
- **Versioning Events** — `time_traveled` and `rolled_back` events on the EventBus

### New Module

- `memos.versioning` — `models.py`, `store.py`, `engine.py`

### Tests
- 48 new tests for versioning
- Total: **413 tests**

## v0.10.0 (2026-04-06) — Async Consolidation + Parquet Export/Import

### New Features

#### Async Consolidation
- **`await mem.consolidate_async()`** — Run consolidation in the background without blocking the event loop.
- **`POST /api/v1/consolidate`** — REST endpoint supporting both sync and async modes.

#### Parquet Export/Import
- **`mem.export_parquet(path)`** — Export all memories to Apache Parquet (3-10x smaller than JSON).
- **`mem.import_parquet(path)`** — Import with merge strategies (`skip`, `overwrite`, `duplicate`).
- CLI: `memos export --format parquet` and `memos import file.parquet`
- REST: `GET /api/v1/export/parquet`

### Tests
- 38 new tests
- Total: **365 tests**

---

## v0.9.0 (2026-04-06) — Batch Learn API + Pinecone Backend

### New Features

#### Batch Learn API
- **`MemOS.batch_learn()`** — Store multiple memories in a single call
- **`POST /api/v1/learn/batch`** — REST endpoint (up to 1000 items)
- **`memos batch-learn`** — CLI command for batch learning from JSON files

#### Pinecone Storage Backend
- **`PineconeBackend`** — Full `StorageBackend` implementation
- Serverless and Pod-based index support
- Batch upsert for efficient bulk operations

### Tests
- 30 new tests
- Total: **327 tests**

---

## v0.8.0 (2026-04-06) — SSE Streaming Recall API

### New Features
- **Streaming recall API** (`GET /api/v1/recall/stream`) — Server-Sent Events
- **Async `recall_stream()` generator** — yields results as they are found
- **SSE utilities module** (`memos.api.sse`)

### Tests
- 32 new tests
- Total: **297 tests**

---

## v0.7.0 (2026-04-06) — Qdrant Backend + Hybrid Search

### New Features
- **Qdrant storage backend** — full `StorageBackend` implementation
- Native vector similarity search via Qdrant client
- Hybrid BM25+vector scoring with configurable weights
- Docker Compose Qdrant profile

### Tests
- 37 new tests
- Total: **265 tests**

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
