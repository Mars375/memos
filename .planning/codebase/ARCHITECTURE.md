# Architecture

**Analysis Date:** 2026-04-15

## Overview

MemOS is a "Memory Operating System" for LLM agents — a persistent, queryable memory layer that agents can write to, recall from, and manage over time. It is a Python library (`memos-agent`) with multiple access surfaces: a Python API, a CLI, a REST/WebSocket server, and an MCP (Model Context Protocol) server for direct LLM tool integration.

## Pattern

**Layered / Plugin Architecture with a Central Facade**

`MemOS` (in `src/memos/core.py`) acts as the facade: it owns all sub-engine instances and exposes the full public API. Consumers never instantiate sub-engines directly. Storage is pluggable via the `StorageBackend` ABC.

## Layers / Components

**Models Layer**
- Purpose: Pure data definitions shared by all layers.
- Location: `src/memos/models.py`, `src/memos/_constants.py`
- Contains: `MemoryItem`, `RecallResult`, `ScoreBreakdown`, `MemoryStats`, `FeedbackEntry`, `generate_id`, `parse_ttl`
- Depends on: nothing
- Used by: everything

**Storage Layer**
- Purpose: Pluggable persistence backends behind a common interface.
- Location: `src/memos/storage/`
- Contains:
  - `base.py` — `StorageBackend` ABC (upsert, get, delete, list_all, search, list_namespaces)
  - `memory_backend.py` — volatile in-memory dict store
  - `json_backend.py` — file-persisted JSON store (default local backend)
  - `chroma_backend.py` — ChromaDB vector store (optional dep)
  - `qdrant_backend.py` — Qdrant vector store (optional dep)
  - `pinecone_backend.py` — Pinecone vector store (optional dep)
  - `encrypted_backend.py` — transparent encryption wrapper around any backend
  - `async_base.py`, `async_wrapper.py` — async adapters
- Depends on: `models`
- Used by: `core`, `retrieval`

**Retrieval Layer**
- Purpose: Hybrid semantic + keyword recall with scoring.
- Location: `src/memos/retrieval/engine.py`
- Contains: `RetrievalEngine` — BM25 keyword scoring + Ollama/local embedding cosine similarity, combined into a `ScoreBreakdown`
- Embedder protocol: `Embedder` (Protocol) in `retrieval/engine.py`; implementations in `src/memos/embeddings/`
- Caching: `src/memos/cache/embedding_cache.py` — LRU cache for embeddings
- Depends on: `storage`, `models`, `embeddings`, `cache`
- Used by: `core`

**Core Facade**
- Purpose: Orchestrates all sub-engines; the primary public API.
- Location: `src/memos/core.py`
- Contains: `MemOS` class — `learn()`, `recall()`, `forget()`, `prune()`, `consolidate()`, `reinforce()`, and all other public operations
- Sub-engines owned: `RetrievalEngine`, `DecayEngine`, `ConsolidationEngine`, `VersioningEngine`, `SharingEngine`, `IngestEngine`, `DedupEngine`, `AutoTagger`, `MemoryCrypto`, `MemorySanitizer`, `EmbeddingCache`, `RecallAnalytics`, `EventBus`, `NamespaceACL`
- Config: resolved via `src/memos/config.py` (layered: defaults → TOML file → env vars → CLI args)
- Depends on: all sub-engines and storage
- Used by: `api`, `mcp_server`, `cli`

**Memory Lifecycle Sub-Engines**
- `src/memos/decay/engine.py` — `DecayEngine`: Ebbinghaus exponential decay; access-based reinforcement; prune candidates by importance threshold
- `src/memos/consolidation/engine.py` — `ConsolidationEngine`: exact + Jaccard semantic dedup; merges similar memories into one canonical item
- `src/memos/consolidation/async_engine.py` — `AsyncConsolidationHandle`: runs consolidation in background thread
- `src/memos/compaction/` — compaction of memory clusters
- `src/memos/versioning/engine.py` — `VersioningEngine`: stores diffs between memory versions; `src/memos/versioning/models.py` — `MemoryVersion`, `VersionDiff`
- `src/memos/dedup.py` — `DedupEngine`: fast pre-storage duplicate detection
- `src/memos/compression.py` — `MemoryCompressor`: token-budget-aware summarization of memory content

**Knowledge Layer**
- Purpose: Structured relational knowledge separate from freeform memories.
- `src/memos/knowledge_graph.py` — `KnowledgeGraph`: SQLite-backed temporal triple store (subject, predicate, object, valid_from, valid_to)
- `src/memos/kg_bridge.py` — `KGBridge`: bridges MemOS recalls to KG fact extraction and injection
- `src/memos/wiki.py`, `src/memos/wiki_graph.py`, `src/memos/wiki_living.py` — wiki-style compiled/living pages organized by entity/concept (Karpathy-inspired)
- `src/memos/palace.py` — `PalaceIndex`: SQLite-backed "memory palace" spatial index
- `src/memos/brain.py` — `BrainSearch`, `BrainSearchResult`: unified search across memories + wiki + KG in a single ranked result set

**API Layer**
- Purpose: HTTP/WebSocket access surface.
- Location: `src/memos/api/`
- Contains:
  - `__init__.py` — `create_fastapi_app()` factory; wires routers, middleware, MCP routes, static files
  - `routes/memory.py` — memory CRUD and recall endpoints
  - `routes/knowledge.py` — KG, wiki, palace, context endpoints
  - `routes/admin.py` — dashboard HTML, stats, admin endpoints
  - `auth.py` — `APIKeyManager`, auth middleware
  - `ratelimit.py` — `RateLimiter`, rate-limit middleware
  - `sse.py` — SSE streaming helpers
  - `schemas.py` — Pydantic request/response schemas
  - `errors.py` — error handling

**MCP Server**
- Purpose: JSON-RPC 2.0 bridge exposing MemOS tools to LLM clients (Claude Code, OpenClaw, Cursor).
- Location: `src/memos/mcp_server.py`
- Transports: `stdio` (direct pipe to LLM) and Streamable HTTP (`POST /mcp`, `GET /mcp`, `OPTIONS /mcp`, `GET /.well-known/mcp.json`)
- Tools exposed: `memory_search`, `memory_save`, and others
- MCP spec version: 2025-03-26

**CLI Layer**
- Purpose: Command-line interface for all MemOS operations.
- Location: `src/memos/cli/`
- Entry point: `memos` script → `memos.cli:main`
- Contains: `_parser.py` (argparse), `commands_memory.py`, `commands_io.py`, `commands_knowledge.py`, `_common.py` (shared helpers)
- Depends on: `core`, `knowledge_graph`, `wiki_living`, `config`

**Event Bus**
- Purpose: In-process pub/sub for real-time memory change notifications.
- Location: `src/memos/events.py`
- Contains: `EventBus`, `MemoryEvent`
- Event types: `learned`, `recalled`, `forgotten`, `pruned`, `consolidated`
- Supports: async handlers, WebSocket client queues, filtered subscriptions
- Depends on: `subscriptions` (`src/memos/subscriptions/`)

**Namespace / ACL Layer**
- Purpose: Multi-agent memory isolation with RBAC.
- Location: `src/memos/namespaces/acl.py`
- Roles: `owner`, `writer`, `reader`, `denied`
- All `StorageBackend` methods accept a `namespace` parameter; the ACL layer gates access in `MemOS`.

**Sharing Layer**
- Purpose: Cross-agent memory sharing via signed envelopes.
- Location: `src/memos/sharing/`
- Contains: `engine.py` — `SharingEngine`; `models.py` — `MemoryEnvelope`, `SharePermission`, `ShareRequest`, `ShareScope`, `ShareStatus`

**Web / Dashboard**
- Purpose: Static HTML dashboard served at `/` by the FastAPI app.
- Location: `src/memos/web/` — `dashboard.html`, `dashboard.css`, `js/`
- Served as static files via Starlette `StaticFiles`

## Data Flow

**Learn (write) path:**
1. Caller → `MemOS.learn(content, tags, importance, namespace, ...)`
2. `MemorySanitizer` sanitizes content
3. `AutoTagger` adds inferred tags
4. `DedupEngine` checks for near-duplicates before storage
5. `StorageBackend.upsert(item, namespace=...)` persists the item
6. `VersioningEngine` records a diff if the item already existed
7. `EventBus.emit_sync("learned", ...)` fires change notification
8. Returns the new `MemoryItem`

**Recall (read) path:**
1. Caller → `MemOS.recall(query, top_k, tags, namespace, retrieval_mode, ...)`
2. `NamespaceACL.check(agent_id, namespace, "read")` enforces RBAC
3. `RetrievalEngine.search()` runs hybrid BM25 + semantic scoring against `StorageBackend`
4. `EmbeddingCache` is consulted before calling Ollama/LocalEmbedder
5. Results ranked by `ScoreBreakdown` (semantic + keyword + importance + recency + tag bonus)
6. TTL-expired items filtered out
7. `MemoryItem.touch()` updates `accessed_at` / `access_count`
8. `EventBus.emit_sync("recalled", ...)` fires change notification
9. Returns `list[RecallResult]`

**Decay / prune path:**
1. `MemOS.prune(threshold)` or scheduled cron
2. `DecayEngine.run_decay(items)` applies exponential decay to `importance` scores
3. Items below `threshold` and older than `min_age_days` are candidates
4. `StorageBackend.delete(item_id)` removes pruned items
5. `EventBus.emit_sync("pruned", ...)` fires notification

**Ingest path:**
1. `memos ingest <file>` or `MemOS.ingest(path)`
2. `IngestEngine` parses markdown/JSON into chunks
3. Each chunk passed through the learn path above

## Key Design Decisions

1. **Facade pattern on `MemOS`** — all sub-engines created in `__init__`, never exposed directly. Consumers get a single object with a stable API.

2. **`StorageBackend` ABC** — pluggable backends with a uniform interface. Encryption is a transparent decorator (`EncryptedStorageBackend`), not a backend-specific feature.

3. **Optional heavy dependencies** — vector store clients (chromadb, qdrant-client, pinecone-client), sentence-transformers, FastAPI, and pyarrow are all optional extras. The core works with only `httpx`.

4. **MCP as first-class surface** — the MCP server (`mcp_server.py`) is not just a wrapper; it implements the full MCP 2025-03-26 spec with two transports (stdio + Streamable HTTP) and is mounted directly into the FastAPI app.

5. **Layered config** — `config.py` merges defaults → `~/.memos.toml` → `MEMOS_*` env vars → CLI args. No global singletons.

6. **Namespace-scoped operations** — all `StorageBackend` methods accept `namespace="..."`. Multi-agent isolation is a first-class concern, not an afterthought.

7. **Sync `MemOS` with async event bus** — `MemOS` methods are synchronous for simplicity. `EventBus.emit_sync()` safely bridges sync code to async WebSocket handlers.

---

*Architecture analysis: 2026-04-15*
