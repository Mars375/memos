# Codebase Structure

**Analysis Date:** 2026-04-13

## Directory Layout

```
memos/
├── src/memos/              # Main package
│   ├── __init__.py         # Public API exports (MemOS, MemoryItem, etc.)
│   ├── core.py             # MemOS orchestrator class
│   ├── models.py           # Data models (MemoryItem, RecallResult, etc.)
│   ├── config.py           # Configuration loading from env
│   ├── api/                # REST API (FastAPI)
│   │   ├── __init__.py     # create_fastapi_app() factory
│   │   ├── auth.py         # APIKeyManager, auth middleware
│   │   ├── ratelimit.py    # RateLimiter, rate-limit middleware
│   │   └── routes/         # API endpoint implementations
│   │       ├── memory.py   # Learn, recall, search, export endpoints
│   │       ├── knowledge.py # KG query, wiki, graph endpoints
│   │       └── admin.py    # Health, stats, config endpoints
│   ├── cli/                # Command-line interface
│   │   ├── __init__.py     # main() entry point, command dispatch
│   │   ├── _parser.py      # argparse setup
│   │   ├── _common.py      # Shared utilities (_get_memos, formatting)
│   │   ├── commands_memory.py       # learn, recall, decay, compress, etc.
│   │   ├── commands_io.py           # export, import, mine, migrate
│   │   ├── commands_knowledge.py    # kg-add, kg-query, wiki commands
│   │   ├── commands_versioning.py   # history, diff, rollback, snapshot-at
│   │   ├── commands_namespace.py    # ns-grant, share-offer, sync
│   │   ├── commands_palace.py       # palace-init, palace-wing-create, etc.
│   │   └── commands_system.py       # serve, mcp-stdio, mcp-serve, config
│   ├── mcp_server.py       # MCP JSON-RPC 2.0 server (stdio and HTTP)
│   ├── storage/            # Storage backends (pluggable)
│   │   ├── base.py         # StorageBackend abstract interface
│   │   ├── memory_backend.py    # In-memory (no persistence)
│   │   ├── json_backend.py      # JSON file persistence
│   │   ├── chroma_backend.py    # ChromaDB + vector embeddings
│   │   ├── qdrant_backend.py    # Qdrant vector database
│   │   ├── pinecone_backend.py  # Pinecone serverless
│   │   ├── encrypted_backend.py # Encryption wrapper (any backend)
│   │   └── async_*.py           # Async wrappers
│   ├── retrieval/          # Hybrid search engine
│   │   ├── engine.py       # RetrievalEngine (semantic + keyword)
│   │   └── scoring.py      # Score breakdown and combination logic
│   ├── decay/              # Memory decay and pruning
│   │   ├── engine.py       # DecayEngine (Ebbinghaus-inspired)
│   │   └── models.py       # DecayConfig, DecayReport
│   ├── versioning/         # Version history and time-travel
│   │   ├── engine.py       # VersioningEngine (high-level API)
│   │   ├── store.py        # In-memory VersionStore
│   │   ├── persistent_store.py  # SQLite PersistentVersionStore
│   │   └── models.py       # MemoryVersion, VersionDiff
│   ├── knowledge_graph.py  # Temporal triple store (SQLite)
│   ├── kg_bridge.py        # KG ↔ Memory integration (fact extraction)
│   ├── palace.py           # Palace index (memory rooms/wings for organization)
│   ├── wiki.py             # Wiki compile (memories → markdown pages)
│   ├── wiki_graph.py       # Wiki graph mode (D3.js graph visualization)
│   ├── wiki_living.py      # Living wiki (entity-based pages with backlinks)
│   ├── cache/              # Embedding cache (persistent)
│   │   └── embedding_cache.py  # EmbeddingCache (optional persistent layer)
│   ├── embeddings/         # Embedding providers
│   │   ├── local_embedder.py   # sentence-transformers (local)
│   │   ├── ollama_embedder.py  # Ollama HTTP client
│   │   └── cache.py            # Caching wrapper
│   ├── ingest/             # Data import (files, URLs, conversations)
│   │   ├── __init__.py
│   │   ├── file_ingest.py      # Import from .txt, .md, .json
│   │   └── url_ingest.py       # Import from URLs (HTTP GET + parse)
│   ├── miner/              # Conversation mining
│   │   ├── __init__.py
│   │   ├── miner.py            # Miner class (chunk conversations)
│   │   └── formats.py          # Parsers for Claude, ChatGPT, Discord, etc.
│   ├── namespaces/         # Multi-namespace (multi-agent)
│   │   └── acl.py          # NamespaceACL (user-role-namespace mapping)
│   ├── sharing/            # Memory sharing across namespaces
│   │   ├── engine.py       # SharingEngine
│   │   └── models.py       # ShareRequest, ShareStatus, SharePermission
│   ├── subscriptions/      # Event subscriptions
│   │   └── engine.py       # SubscriptionEngine (pub/sub)
│   ├── consolidation/      # Memory consolidation (merging similar items)
│   │   └── engine.py       # Consolidation logic
│   ├── compaction/         # Data compaction
│   │   └── engine.py       # Compact representation
│   ├── dedup.py            # Deduplication engine
│   ├── migration.py        # Backend migration (JSON → Qdrant, etc.)
│   ├── compression.py      # Memory compression (encode large content)
│   ├── crypto.py           # Encryption utilities
│   ├── sanitizer.py        # Input validation and HTML stripping
│   ├── tagger.py           # Auto-tagging via embedding similarity
│   ├── context.py          # ContextStack for session context
│   ├── brain.py            # BrainSearch (semantic search with ranking)
│   ├── query.py            # QueryBuilder and QueryEngine (fluent API)
│   ├── skills.py           # Skill extraction from conversations
│   ├── conflict.py         # Conflict detection in contradictory memories
│   ├── analytics.py        # RecallAnalytics (stats tracking)
│   ├── events.py           # EventBus (pub/sub for learn/forget/decay)
│   ├── export_markdown.py  # MarkdownExporter (export to .md)
│   ├── export_obsidian.py  # ObsidianExporter (export to Obsidian format)
│   ├── parquet_io.py       # Parquet backup/restore
│   ├── versioning.py       # Backward-compat re-exports
│   ├── web/                # Web dashboard (static assets)
│   │   ├── dashboard.html  # Main UI HTML
│   │   ├── dashboard.css   # Styling
│   │   └── js/             # JavaScript modules
│   │       ├── state.js    # State management
│   │       ├── api.js      # HTTP client for API
│   │       ├── filters.js  # Query filter UI
│   │       ├── graph.js    # D3.js graph rendering
│   │       ├── utils.js    # Shared utilities
│   │       ├── sidebar.js  # Sidebar component
│   │       ├── panels.js   # Panel UI components
│   │       ├── controls.js # Control UI elements
│   │       ├── wiki.js     # Wiki viewer
│   │       └── palace.js   # Palace UI
│   └── py.typed            # PEP 561 marker (typed package)
├── tests/                  # Test suite (pytest)
│   ├── test_*.py           # Unit/integration tests (1400+ tests)
│   └── conftest.py         # Pytest fixtures and config (if present)
├── pyproject.toml          # Project metadata, dependencies, pytest config
├── docker-compose.yml      # Local dev stack (Ollama, Chroma, Qdrant)
├── Dockerfile              # Production image (Python 3.11, FastAPI)
├── README.md               # Project overview and usage
├── ROADMAP.md              # Feature roadmap
├── PRIORITIES.md           # Current development priorities
├── CONTRIBUTING.md         # Contribution guidelines
├── ACTIVE.md               # Active development notes
├── CHANGELOG.md            # Release history
└── PRD.md                  # Product requirements document
```

## Directory Purposes

**`src/memos/`:**
- Purpose: Main Python package
- Contains: Core logic, storage, retrieval, versioning, CLI, API, MCP
- Key files: `core.py` (orchestrator), `models.py` (data structures)

**`src/memos/api/`:**
- Purpose: REST API implementation (FastAPI)
- Contains: Route handlers, middleware (auth, rate-limit), dashboard integration
- Key files: `__init__.py` (app factory), `routes/memory.py` (CRUD)

**`src/memos/cli/`:**
- Purpose: Command-line interface
- Contains: Argument parsing, command dispatch, output formatting
- Key files: `__init__.py` (main entry point), `commands_memory.py` (learn/recall/decay)

**`src/memos/storage/`:**
- Purpose: Pluggable persistence backends
- Contains: Interface (base.py) and implementations (json, chroma, qdrant, pinecone)
- Key pattern: All inherit from StorageBackend, implement upsert/get/delete/search

**`src/memos/retrieval/`:**
- Purpose: Hybrid search (semantic + keyword)
- Contains: RetrievalEngine (embedding + scoring), score combination logic
- Key files: `engine.py` (main logic)

**`src/memos/decay/`:**
- Purpose: Automatic memory decay and pruning
- Contains: DecayEngine (Ebbinghaus-inspired decay formula), config
- Key files: `engine.py` (decay logic)

**`src/memos/versioning/`:**
- Purpose: Immutable version history and time-travel
- Contains: VersioningEngine (high-level API), VersionStore (in-memory), PersistentVersionStore (SQLite)
- Key files: `engine.py` (orchestrator), `persistent_store.py` (SQLite backend)

**`src/memos/miner/`:**
- Purpose: Parse and ingest external conversations
- Contains: Miner class (chunks conversations), format parsers (Claude, ChatGPT, Discord, etc.)
- Key files: `miner.py` (main logic), `formats.py` (parsers)

**`src/memos/web/`:**
- Purpose: Web dashboard (static assets served by FastAPI)
- Contains: HTML, CSS, JavaScript modules for UI
- Key files: `dashboard.html` (entry point), `js/api.js` (HTTP client)

**`tests/`:**
- Purpose: Comprehensive test suite (1400+ tests)
- Contains: Unit tests, integration tests, fixtures
- Key pattern: Tests co-located with source in same module naming (`test_core.py`, etc.)

## Key File Locations

**Entry Points:**
- `src/memos/cli/__init__.py`: CLI main() function
- `src/memos/api/__init__.py`: REST API create_fastapi_app() factory
- `src/memos/mcp_server.py`: MCP server (stdio and HTTP routes)
- `src/memos/__init__.py`: Python SDK (MemOS class)

**Configuration:**
- `src/memos/config.py`: Environment variable parsing
- `pyproject.toml`: Project metadata, dependencies, pytest config

**Core Logic:**
- `src/memos/core.py`: MemOS orchestrator
- `src/memos/storage/base.py`: StorageBackend interface
- `src/memos/retrieval/engine.py`: RetrievalEngine (hybrid search)
- `src/memos/decay/engine.py`: DecayEngine (memory decay)
- `src/memos/versioning/engine.py`: VersioningEngine (time-travel)

**Testing:**
- `tests/test_core.py`: Core MemOS tests
- `tests/test_chroma.py`, `test_qdrant.py`, etc.: Backend-specific tests
- `tests/test_mcp_server.py`: MCP protocol tests
- `tests/test_api_*.py`: REST API tests

## Naming Conventions

**Files:**
- `*.py`: Python source files
- `test_*.py`: Test modules (pytest discovers these)
- `conftest.py`: Pytest fixtures and configuration (if present)
- `*_backend.py`: Storage backend implementations
- `*_engine.py`: Processing engines (decay, retrieval, versioning, etc.)
- `commands_*.py`: CLI command modules organized by domain (memory, knowledge, io)
- `dashboard.*`: Web UI files (HTML, CSS)

**Directories:**
- `src/memos/` — Main package (lowercase, no hyphens)
- `api/` — HTTP/REST layer
- `cli/` — Command-line interface
- `storage/` — Persistence backends
- `retrieval/` — Search and ranking
- `decay/` — Automatic degradation
- `versioning/` — History and time-travel
- `miner/` — Ingestion and parsing
- `web/` — Web UI assets
- `tests/` — Test suite
- `tools/` — Utility scripts (e.g., migrate_markdown.py)

**Classes and Functions:**
- `MemOS` — Main orchestrator class (PascalCase)
- `StorageBackend`, `RetrievalEngine`, `DecayEngine` — Abstract/main classes (PascalCase)
- `memos.learn()`, `memos.recall()` — Public SDK methods (snake_case)
- `_get_memos()` — Internal helpers (snake_case with leading underscore)
- `create_fastapi_app()`, `create_memory_router()` — Factory functions (snake_case)

**Modules:**
- `memos.core` — Core orchestrator
- `memos.models` — Data models
- `memos.storage` — Persistence
- `memos.retrieval` — Search
- `memos.decay` — Memory decay
- `memos.versioning` — Version history
- `memos.knowledge_graph` — Triple store
- `memos.mcp_server` — MCP protocol handler
- `memos.cli` — Command-line interface
- `memos.api` — REST API

## Where to Add New Code

**New Feature (e.g., new decay algorithm):**
- Primary code: `src/memos/decay/engine.py` or new module like `src/memos/decay/new_algorithm.py`
- Tests: `tests/test_decay.py` (add new test functions)
- Integration: Wire into MemOS.__init__() if backend selection needed
- Example: DecayEngine is passed to MemOS; alternative implementations can be plugged in

**New Storage Backend (e.g., MongoDB):**
- Implementation: `src/memos/storage/mongodb_backend.py` (inherit from StorageBackend)
- Implement: upsert(), get(), delete(), list_all(), search()
- Tests: `tests/test_mongodb.py` with full backend test suite
- Integration: Add to MemOS.__init__() backend selection logic

**New CLI Command (e.g., memory_audit):**
- Command handler: `src/memos/cli/commands_memory.py` → add `cmd_audit()` function
- Parser setup: `src/memos/cli/_parser.py` → add subcommand
- Dispatch: `src/memos/cli/__init__.py` → add to `commands` dict
- Tests: `tests/test_cli.py` → add test for new command

**New API Endpoint (e.g., /api/v1/search/advanced):**
- Route handler: `src/memos/api/routes/memory.py` → add `@router.post()` function
- Middleware: If needs auth/rate-limit, handled automatically (already in create_fastapi_app)
- Tests: `tests/test_api_*.py` → add endpoint test
- Documentation: Docstring follows REST convention

**New MCP Tool (e.g., memory_analyze):**
- Tool definition: `src/memos/mcp_server.py` → add to TOOLS list (inputSchema + description)
- Implementation: Add handler in `_dispatch()` function
- Tests: `tests/test_mcp_server.py` → add tool test

**New Web UI Component (e.g., memory_editor):**
- Component: `src/memos/web/js/new_component.js` → export component
- Integration: `src/memos/web/js/state.js` → register component
- Styling: `src/memos/web/dashboard.css` → add CSS
- Tests: `tests/test_dashboard.py` (if JavaScript-heavy, may need Playwright)

**Utilities and Helpers:**
- Shared utilities: `src/memos/utils/` (create if needed) or directly in modules
- Example: `sanitizer.py`, `crypto.py` are standalone utility modules
- Reusable functions: Extract to module-level functions, not buried in classes

## Special Directories

**`.memos/`:**
- Purpose: Runtime data directory (user data, cache, config)
- Generated: Yes (created by first `memos serve` or `memos learn`)
- Committed: No — in .gitignore
- Contents: memos.json (memory store), cache/, versions/ (if using SQLite)

**`__pycache__/`:**
- Purpose: Python bytecode cache
- Generated: Yes (by Python interpreter)
- Committed: No — in .gitignore

**`src/memos.egg-info/` and `src/memos_agent.egg-info/`:**
- Purpose: Package metadata (setuptools)
- Generated: Yes (by `pip install -e .`)
- Committed: No — in .gitignore

**`tests/__pycache__/`:**
- Purpose: Pytest bytecode cache
- Generated: Yes
- Committed: No — in .gitignore

**`memory/`:**
- Purpose: Development notes and session memory
- Contains: `.md` files with active development notes (2026-04-07.md, etc.)
- Committed: Yes — project memory
- Use: Reference during development for context and decisions

---

*Structure analysis: 2026-04-13*
