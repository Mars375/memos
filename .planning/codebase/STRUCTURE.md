# Codebase Structure

**Analysis Date:** 2026-04-15

## Directory Layout

```
memos/
├── src/
│   └── memos/                    # Main package
│       ├── __init__.py           # Public API surface (MemOS, BrainSearch, ...)
│       ├── _constants.py         # All tuneable constants and defaults
│       ├── core.py               # MemOS facade — central entry point
│       ├── models.py             # Data models (MemoryItem, RecallResult, ...)
│       ├── config.py             # Layered config resolution (TOML + env + CLI)
│       ├── events.py             # EventBus + MemoryEvent (pub/sub)
│       ├── brain.py              # BrainSearch — unified cross-source search
│       ├── knowledge_graph.py    # Temporal KG (SQLite triple store)
│       ├── kg_bridge.py          # KGBridge — memory ↔ KG integration
│       ├── wiki.py               # Wiki compiler (tag-based pages)
│       ├── wiki_graph.py         # GraphWikiEngine
│       ├── wiki_living.py        # LivingWikiEngine (entity-organized pages)
│       ├── palace.py             # PalaceIndex (SQLite spatial memory index)
│       ├── context.py            # ContextStack
│       ├── query.py              # MemoryQuery, QueryEngine
│       ├── tagger.py             # AutoTagger
│       ├── sanitizer.py          # MemorySanitizer
│       ├── analytics.py          # RecallAnalytics
│       ├── crypto.py             # MemoryCrypto (Fernet-based)
│       ├── compression.py        # MemoryCompressor (token budget)
│       ├── dedup.py              # DedupEngine
│       ├── conflict.py           # Conflict detection
│       ├── skills.py             # Skills / procedural memory
│       ├── migration.py          # MigrationEngine (backend-to-backend)
│       ├── parquet_io.py         # Parquet import/export
│       ├── export_markdown.py    # MarkdownExporter
│       ├── export_obsidian.py    # Obsidian vault export
│       ├── benchmark.py          # Benchmark utilities
│       ├── benchmark_quality.py  # Quality benchmark
│       ├── mcp_hooks.py          # MCP hook helpers
│       ├── mcp_server.py         # MCP server (stdio + Streamable HTTP)
│       ├── storage/              # Storage backends
│       │   ├── base.py           # StorageBackend ABC
│       │   ├── memory_backend.py # In-memory (volatile)
│       │   ├── json_backend.py   # JSON file (default local)
│       │   ├── chroma_backend.py # ChromaDB (optional)
│       │   ├── qdrant_backend.py # Qdrant (optional)
│       │   ├── pinecone_backend.py  # Pinecone (optional)
│       │   ├── encrypted_backend.py # Transparent encryption decorator
│       │   ├── async_base.py     # Async backend interface
│       │   └── async_wrapper.py  # Sync-to-async adapter
│       ├── retrieval/            # Hybrid recall engine
│       │   └── engine.py         # RetrievalEngine (BM25 + embeddings)
│       ├── embeddings/           # Embedding providers
│       │   └── __init__.py       # LocalEmbedder (sentence-transformers)
│       ├── cache/                # Caching layer
│       │   └── embedding_cache.py  # LRU embedding cache
│       ├── decay/                # Memory aging
│       │   └── engine.py         # DecayEngine (Ebbinghaus)
│       ├── consolidation/        # Dedup & merge
│       │   ├── engine.py         # ConsolidationEngine
│       │   └── async_engine.py   # AsyncConsolidationHandle
│       ├── compaction/           # Memory cluster compaction
│       ├── versioning/           # Memory version history
│       │   ├── engine.py         # VersioningEngine
│       │   ├── models.py         # MemoryVersion, VersionDiff
│       │   ├── store.py          # Version store
│       │   └── persistent_store.py  # Persistent version store
│       ├── namespaces/           # Multi-agent isolation
│       │   └── acl.py            # NamespaceACL + Role enum
│       ├── sharing/              # Cross-agent memory sharing
│       │   ├── engine.py         # SharingEngine
│       │   └── models.py         # MemoryEnvelope, SharePermission, ...
│       ├── subscriptions/        # EventBus subscription registry
│       ├── ingest/               # File / URL ingestion
│       │   └── engine.py         # IngestEngine (markdown/JSON chunking)
│       ├── api/                  # FastAPI REST server
│       │   ├── __init__.py       # create_fastapi_app() factory
│       │   ├── auth.py           # APIKeyManager, auth middleware
│       │   ├── ratelimit.py      # RateLimiter, rate-limit middleware
│       │   ├── sse.py            # SSE streaming helpers
│       │   ├── schemas.py        # Pydantic schemas
│       │   ├── errors.py         # Error handling
│       │   └── routes/
│       │       ├── memory.py     # Memory CRUD + recall endpoints
│       │       ├── knowledge.py  # KG + wiki + palace + context endpoints
│       │       └── admin.py      # Dashboard + stats + admin endpoints
│       ├── cli/                  # Command-line interface
│       │   ├── __init__.py       # main() entry point
│       │   ├── _parser.py        # argparse parser builder
│       │   ├── _common.py        # Shared helpers (_get_memos, _get_kg, ...)
│       │   ├── commands_memory.py   # Memory management commands
│       │   ├── commands_io.py       # Import/export/ingest/mine commands
│       │   └── commands_knowledge.py  # KG + wiki commands
│       └── web/                  # Dashboard static assets
│           ├── dashboard.html
│           ├── dashboard.css
│           └── js/
├── tests/                        # All tests (co-located in one directory)
│   ├── conftest.py               # Shared fixtures
│   └── test_*.py                 # One test file per module
├── tools/                        # Development/maintenance scripts
├── memory/                       # Dogfood: project's own memory store
├── dogfood-output/               # Dogfood screenshots and artifacts
├── .memos/                       # Local runtime data (store.json, etc.)
├── .planning/                    # GSD planning documents
│   ├── codebase/                 # Codebase analysis (these docs)
│   ├── phases/                   # Phase-by-phase implementation plans
│   ├── REQUIREMENTS.md
│   ├── ROADMAP.md
│   └── STATE.md
├── pyproject.toml                # Build config, deps, tool config
├── Dockerfile                    # Container image
├── docker-compose.yml            # Local dev stack
├── AGENTS.md                     # Agent-specific working contract
├── ACTIVE.md                     # Current active work
├── PRD.md                        # Product Requirements Document
├── CHANGELOG.md                  # Version history
└── README.md
```

## Key Files

**Entry Points:**
- `src/memos/__init__.py` — package public surface; imports `MemOS`, `BrainSearch`, exporters
- `src/memos/core.py` — `MemOS` class; the only class consumers need to instantiate
- `src/memos/cli/__init__.py` — `main()` function; wired to the `memos` CLI script
- `src/memos/api/__init__.py` — `create_fastapi_app()` factory; used to start the HTTP server
- `src/memos/mcp_server.py` — `run_stdio()` for Claude Code integration; `create_mcp_app()` for HTTP

**Configuration:**
- `src/memos/config.py` — config resolution; reads `~/.memos.toml` + `MEMOS_*` env vars
- `src/memos/_constants.py` — all magic numbers and defaults; edit here before anywhere else
- `pyproject.toml` — project metadata, optional dep groups, ruff/pytest config

**Core Logic:**
- `src/memos/core.py` — main facade; follow imports here to find any sub-engine
- `src/memos/storage/base.py` — `StorageBackend` ABC; implement this to add a new backend
- `src/memos/retrieval/engine.py` — hybrid recall scoring; `ScoreBreakdown` fields drive ranking
- `src/memos/models.py` — `MemoryItem` definition; all fields with their semantics

**Knowledge:**
- `src/memos/knowledge_graph.py` — self-contained KG; no MemOS dep required
- `src/memos/brain.py` — unified cross-source search (`BrainSearch`)
- `src/memos/wiki_living.py` — living wiki with entity extraction

**Testing:**
- `tests/conftest.py` — shared pytest fixtures
- `tests/test_*.py` — per-module test files; coverage is extensive

## Module Organization

Each major capability lives in its own sub-package or top-level module:

| Capability | Location |
|---|---|
| Storage backends | `src/memos/storage/` |
| Retrieval / ranking | `src/memos/retrieval/` |
| Memory decay / aging | `src/memos/decay/` |
| Consolidation / dedup | `src/memos/consolidation/` |
| Versioning | `src/memos/versioning/` |
| Namespace RBAC | `src/memos/namespaces/` |
| Memory sharing | `src/memos/sharing/` |
| Knowledge graph | `src/memos/knowledge_graph.py` (standalone) |
| Wiki / living docs | `src/memos/wiki.py`, `wiki_living.py`, `wiki_graph.py` |
| File ingestion | `src/memos/ingest/` |
| Embedding cache | `src/memos/cache/` |
| Embedders | `src/memos/embeddings/` |
| REST API | `src/memos/api/` |
| MCP server | `src/memos/mcp_server.py` |
| CLI | `src/memos/cli/` |
| Dashboard assets | `src/memos/web/` |
| Event bus | `src/memos/events.py` |
| Subscriptions | `src/memos/subscriptions/` |

## Naming Conventions

**Files:**
- Snake_case module files: `json_backend.py`, `embedding_cache.py`
- `_prefix` for internal helpers: `_constants.py`, `_common.py`, `_parser.py`
- `test_` prefix for test files: `test_core.py`, `test_api_memory.py`

**Classes:**
- PascalCase: `MemOS`, `StorageBackend`, `RetrievalEngine`, `DecayEngine`
- Engine suffix for sub-engines: `ConsolidationEngine`, `VersioningEngine`, `SharingEngine`
- Backend suffix for storage implementations: `JsonFileBackend`, `ChromaBackend`
- Result suffix for result dataclasses: `IngestResult`, `ConsolidationResult`, `RecallResult`

**Functions:**
- Snake_case: `learn()`, `recall()`, `prune()`, `generate_id()`
- `_prefix` for internal helpers: `_bm25_score()`, `_chunk_markdown()`

## Where to Add New Code

**New storage backend:**
- Implement `StorageBackend` ABC in `src/memos/storage/<name>_backend.py`
- Add optional dep group in `pyproject.toml`
- Register backend string in `MemOS.__init__` backend selection block in `src/memos/core.py`
- Add tests at `tests/test_<name>.py`

**New memory lifecycle operation (e.g., new form of pruning):**
- Create `src/memos/<feature>/engine.py` with an `Engine` class
- Instantiate in `MemOS.__init__` and expose via a new `MemOS` method in `src/memos/core.py`
- Wire CLI command in `src/memos/cli/commands_memory.py`
- Add REST endpoint in `src/memos/api/routes/memory.py`
- Add MCP tool definition in `src/memos/mcp_server.py` `TOOLS` list

**New API endpoint:**
- Add to the appropriate router: `src/memos/api/routes/memory.py` (memory ops), `src/memos/api/routes/knowledge.py` (KG/wiki), `src/memos/api/routes/admin.py` (admin/stats)
- Add Pydantic schema in `src/memos/api/schemas.py`

**New CLI command:**
- Add parser subcommand in `src/memos/cli/_parser.py`
- Implement handler in the appropriate commands file (`commands_memory.py`, `commands_io.py`, `commands_knowledge.py`)
- Wire dispatch in `src/memos/cli/__init__.py`

**New constant / tunable:**
- Add to `src/memos/_constants.py` only; import from there everywhere else

**Tests:**
- Always add `tests/test_<module>.py` matching the module under test
- Use fixtures from `tests/conftest.py`

## Special Directories

**`.memos/`:**
- Purpose: Runtime data directory — default `store.json`, wiki output, living wiki SQLite
- Generated: yes (at runtime)
- Committed: no (in `.gitignore`)

**`.planning/`:**
- Purpose: GSD planning docs (requirements, roadmap, phase plans, codebase analysis)
- Generated: by GSD agent commands
- Committed: yes

**`memory/`:**
- Purpose: Project's own dogfood memory store (MemOS eating its own memories about itself)
- Generated: yes
- Committed: yes

**`dogfood-output/`:**
- Purpose: Screenshots and artifacts from dogfood runs
- Generated: yes
- Committed: yes

**`tools/`:**
- Purpose: Developer scripts and maintenance utilities
- Generated: no
- Committed: yes

---

*Structure analysis: 2026-04-15*
