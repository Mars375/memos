# Architecture

**Analysis Date:** 2026-04-13

## Pattern Overview

**Overall:** Three-layer memory system with pluggable storage, hybrid retrieval engine, and unified interface (CLI/REST/MCP).

**Key Characteristics:**
- **Pluggable storage backends** (in-memory, JSON, ChromaDB, Qdrant, Pinecone) — swappable without changing core logic
- **Hybrid retrieval** combining semantic embeddings (Ollama) with keyword search (BM25)
- **Multi-namespace isolation** for multi-agent scenarios with ACL-based sharing
- **Temporal versioning** — all writes are immutable; time-travel queries supported
- **Decay engine** — automatic importance degradation (Ebbinghaus-inspired) + manual reinforcement
- **Knowledge graph** — separate SQLite triple store for facts with temporal validity bounds
- **MCP-first design** — native JSON-RPC 2.0 for OpenClaw/Claude Code integration

## Layers

**Core Memory Engine (`MemOS`):**
- Purpose: Main entry point and orchestration for learn/recall/forget operations
- Location: `src/memos/core.py`
- Contains: Memory lifecycle management, backend initialization, decay/versioning wiring
- Depends on: All subsystems below
- Used by: CLI, REST API, MCP server

**Storage Layer (`StorageBackend`):**
- Purpose: Persistence abstraction — insert/update/delete/search operations
- Location: `src/memos/storage/base.py` (interface), implementations in same directory
- Contains: 
  - Abstract base: `base.py`
  - In-memory: `memory_backend.py`
  - JSON file: `json_backend.py`
  - Vector DBs: `chroma_backend.py`, `qdrant_backend.py`, `pinecone_backend.py`
  - Encryption wrapper: `encrypted_backend.py`
  - Async wrapper: `async_wrapper.py`
- Depends on: None (storage is leaf layer)
- Used by: RetrievalEngine, MemOS core

**Retrieval Engine (`RetrievalEngine`):**
- Purpose: Hybrid search combining semantic similarity + keyword ranking
- Location: `src/memos/retrieval/engine.py`
- Contains: Embedding coordination (Ollama or local), BM25 scoring, score combination logic
- Depends on: StorageBackend, embedding cache, Ollama HTTP API
- Used by: MemOS.recall() flow, API routes

**Decay Engine (`DecayEngine`):**
- Purpose: Automatic memory decay + explicit reinforcement
- Location: `src/memos/decay/engine.py`
- Contains: Ebbinghaus-inspired decay formula, access-based boosting, pruning logic
- Depends on: None (pure function on MemoryItem)
- Used by: MemOS.decay(), MemOS.prune(), optional auto-reinforce on recall

**Versioning Engine (`VersioningEngine`):**
- Purpose: Immutable version history + time-travel queries
- Location: `src/memos/versioning/engine.py`
- Contains: Version recording on upsert, history traversal, snapshot restoration
- Supports: In-memory store or persistent SQLite backend
- Depends on: StorageBackend (for snapshots)
- Used by: MemOS core (transparent wrapping), CLI versioning commands

**Knowledge Graph (`KnowledgeGraph`):**
- Purpose: Temporal triple store for facts (subject-predicate-object with valid_from/valid_to)
- Location: `src/memos/knowledge_graph.py`
- Contains: SQLite schema for facts, entity/relation queries, path-finding
- Standalone: No dependency on MemOS; can be used separately
- Used by: KGBridge (integration point), API routes, CLI

**Knowledge Bridge (`KGBridge`):**
- Purpose: Integration layer — extract facts from memory content and link to KG
- Location: `src/memos/kg_bridge.py`
- Contains: learn_and_extract() method, fact extraction logic
- Depends on: MemOS core, KnowledgeGraph
- Used by: API learn/extract endpoint, enriched recall

**Interface Layers:**
- **CLI:** `src/memos/cli/` — command-line interface via argparse
- **REST API:** `src/memos/api/` with routers for memory, knowledge, admin
- **MCP Server:** `src/memos/mcp_server.py` — JSON-RPC 2.0 for Claude Code/OpenClaw

## Data Flow

**Learn Flow (Capture):**

1. User calls `memos.learn(content, tags, importance)`
2. MemOS creates MemoryItem (with id, timestamp, metadata)
3. Sanitizer cleans content if enabled
4. Item passed to StorageBackend.upsert()
5. RetrievalEngine.index() pre-computes embedding (cached)
6. VersioningEngine.record_version() appends to version history
7. Return item ID to caller

**Recall Flow (Retrieval):**

1. User calls `memos.recall(query, top=5, tags=[...])`
2. RetrievalEngine performs hybrid search:
   a. Encode query to embedding (via Ollama or local embedder)
   b. Backend.search() returns keyword matches
   c. Score breakdown: semantic + keyword + importance + recency + tag bonus
   d. Combine scores (semantic_weight=0.6, keyword_weight=0.4)
3. Results ranked by combined score
4. Optional: auto-reinforce top results if decay.auto_reinforce=True
5. Optional: enrich with KG facts via KGBridge
6. Return list of RecallResult (item + score + match_reason)

**Decay Cycle (Maintenance):**

1. User runs `memos decay --dry-run` or `decay --apply`
2. DecayEngine.run_decay(items) processes all memories:
   a. Filter by age (skip if < decay_min_age_days)
   b. Apply formula: `importance *= (1 - rate)^age_days`
   c. Add access bonus: `+ log(access_count + 1) * access_boost`
   d. Clamp to importance_floor
3. Optional: auto-prune if importance < threshold
4. Write back to storage
5. Return DecayReport (counts, before/after stats)

**State Management:**

- **Memories:** Live in StorageBackend; each item has: id, content, tags, importance, timestamps, metadata
- **Versions:** Parallel VersionStore (in-memory or SQLite) tracks immutable snapshots
- **KG Facts:** Separate SQLite DB (one global, or per-namespace)
- **Embedding Cache:** Optional persistent cache in EmbeddingCache, else in-memory
- **Namespaces:** Query filtering; ACL managed in NamespaceACL
- **Subscriptions:** Optional event listeners (in-memory queue)

## Key Abstractions

**StorageBackend Protocol:**
- Purpose: Pluggable persistence
- Examples: `JsonFileBackend`, `ChromaBackend`, `QdrantBackend`, `PineconeBackend`
- Pattern: All implement `upsert()`, `get()`, `delete()`, `list_all()`, `search()`

**Embedder Protocol:**
- Purpose: Pluggable semantic encoding
- Examples: Ollama (HTTP), sentence-transformers (local), ONNX (Chroma built-in)
- Pattern: Provide `encode(text) -> list[float]` and `model_name` property

**QueryBuilder (`MemoryQuery`):**
- Purpose: Fluent API for complex recalls with filters
- Example: `MemoryQuery().content("python").tags(["backend"], require=True).importance_min(0.6).recall(memos)`
- Pattern: Builder pattern, converts to backend-native filters

**MemoryItem (`models.py`):**
- Purpose: Single memory unit
- Attributes: id, content, tags, importance (0.0-1.0), created_at, accessed_at, access_count, ttl, metadata
- Methods: `touch()` (increment access), `is_expired`, `expires_at`

**RecallResult:**
- Purpose: Search result with metadata
- Contains: item (MemoryItem), score (0.0-1.0), match_reason ("semantic"|"keyword"|"recent"|"tag"), score_breakdown (optional)
- Pattern: Transparent to caller; score_breakdown exposes hybrid scoring

## Entry Points

**CLI Entry Point:**
- Location: `src/memos/cli/__init__.py` — `main(argv=None)`
- Triggers: `memos` command or `python -m memos.cli`
- Responsibilities: Parse args, dispatch to command handlers (learn, recall, decay, etc.), format output

**REST API Entry Point:**
- Location: `src/memos/api/__init__.py` — `create_fastapi_app(memos=None, **kwargs)`
- Triggers: Uvicorn server startup (e.g., `memos serve --port 8100`)
- Responsibilities: Initialize MemOS, wire middleware (auth, rate-limit), include routers
- Routers mounted at `/api/v1/` and special endpoints (`/mcp`, `/.well-known/mcp.json`, `/dashboard`)

**MCP Server Entry Point:**
- Location: `src/memos/mcp_server.py` — two modes:
  - `run_stdio()` for Claude Code local integration
  - `add_mcp_routes(app, memos)` for HTTP (JSON-RPC 2.0 over FastAPI)
- Triggers: `memos mcp-stdio` or `POST /mcp` in REST API
- Responsibilities: Translate MCP calls to MemOS methods, stream responses (SSE for HTTP)
- Tools exposed: memory_search, memory_save, memory_forget, memory_stats, kg_add_fact, etc.

**Python SDK Entry Point:**
- Location: `src/memos/__init__.py` exports `MemOS` class
- Usage: `from memos import MemOS`
- Initialization: `mem = MemOS(backend="chroma")` with backend selection and config
- Responsibilities: Orchestrate all subsystems, provide sync API

## Error Handling

**Strategy:** Layered validation with meaningful errors, graceful degradation on embedding service outage.

**Patterns:**

- **Content validation** (MemorySanitizer): Strip HTML, validate length, reject empty content
- **Backend failures**: If Ollama unreachable, fall back to keyword-only search
- **Storage errors**: Propagate as ValueError with context, transaction rollback on failure
- **API layer**: Return JSON error responses with status 400/500 and message
- **Version conflicts**: On concurrent writes, last-write-wins with version tracking for audit trail
- **TTL expiry**: Lazily filtered during recall; no cleanup daemon (explicit prune only)

## Cross-Cutting Concerns

**Logging:** Python stdlib logging configured via `src/memos/__init__.py`; loggers named per module.

**Validation:** MemorySanitizer cleans user input; StorageBackend enforces schema (MemoryItem fields); API layer validates JSON schema.

**Authentication:** APIKeyManager in `src/memos/api/auth.py` — optional; supports multiple keys with rate-limiting per key.

**Encryption:** EncryptedStorageBackend wraps any backend; encryption_key passed to MemOS.__init__().

**Rate Limiting:** RateLimiter in `src/memos/api/ratelimit.py` — configurable rules per endpoint; integrated as middleware.

**Namespacing:** All storage operations accept optional `namespace` parameter (scoped queries); NamespaceACL enforces permissions (user-role-namespace mapping).

**Sharing:** ShareEngine in `src/memos/sharing/` — share memories across namespaces via ShareRequest/ShareStatus (pending/accepted/rejected).

**Caching:** EmbeddingCache in `src/memos/cache/` — optional persistent cache for embeddings; avoids re-computing same queries.

**Analytics:** RecallAnalytics tracks recall patterns (frequency, avg score, tag distribution); optional telemetry.

**Subscriptions:** EventBus in `src/memos/events.py` — in-memory pub/sub for learn/forget/decay events; used by live dashboards.

---

*Architecture analysis: 2026-04-13*
