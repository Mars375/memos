# MemOS — Memory Operating System for AI Agents

## Project Overview
Persistent, smart, local-first memory backend for LLM agents. Python 3.11+, FastAPI server, ChromaDB default backend, MCP endpoint.

**Version:** 1.1.0
**Author:** Mars375
**License:** MIT

## Stack
- **Runtime:** Python 3.11+
- **Server:** FastAPI + Uvicorn (port 8100)
- **Vector DB:** ChromaDB (default), Qdrant, Pinecone (optional)
- **Embeddings:** sentence-transformers (MiniLM default)
- **Frontend:** Vanilla HTML/CSS/JS — force-graph + Chart.js
- **Deploy:** Docker via GHCR (ARM64 homelab), docker-compose volume mount

## Commands
```bash
# Install (dev)
pip install -e ".[local,chroma,server,dev]"

# Run server
python -m memos serve --port 8100

# Tests
python -m pytest tests/ -q                    # Full suite (~1700+ tests)
python -m pytest tests/test_core.py -q        # Single file
python -m pytest tests/ -q --tb=short         # With short tracebacks

# Lint
ruff check src/ tests/
ruff format src/ tests/
```

## Project Structure
```
src/memos/
├── core.py              # MemOS main class (1909L — MONOLITH, needs split)
├── brain.py             # Brain/entity resolution (540L)
├── config.py            # Configuration
├── models.py            # Data models
├── context.py           # Context management
├── tagger.py            # Auto-tagging
├── dedup.py             # Deduplication
├── sanitizer.py         # Input sanitization
├── conflict.py          # Conflict resolution (459L)
├── parquet_io.py        # Parquet import/export
├── api/                 # FastAPI routes
│   ├── routes/
│   │   ├── memory.py    # Memory CRUD (616L)
│   │   ├── knowledge.py # KG endpoints (433L)
│   │   └── admin.py     # Admin/stats (398L)
│   ├── auth.py          # API key auth
│   ├── ratelimit.py     # Rate limiting
│   └── sse.py           # Server-sent events
├── cli/                 # CLI commands
│   ├── _parser.py       # Argparse setup (1171L — MONOLITH)
│   ├── commands_memory.py   # Memory commands (1036L — large)
│   ├── commands_knowledge.py # KG commands (452L)
│   └── commands_io.py   # Import/export (406L)
├── storage/             # Backend abstraction
│   ├── base.py          # Abstract base
│   ├── chroma_backend.py
│   ├── json_backend.py
│   ├── qdrant_backend.py
│   ├── pinecone_backend.py
│   ├── memory_backend.py
│   ├── encrypted_backend.py
│   └── async_wrapper.py
├── consolidation/       # Memory consolidation engine
├── retrieval/           # Hybrid retrieval engine
├── ingest/              # Document ingestion
│   ├── miner.py         # Text mining (657L)
│   └── parsers.py       # File parsers (460L)
├── compaction/          # Memory compaction (578L)
├── web/                 # Dashboard frontend
│   ├── dashboard.html   # Entry point (218L — already split)
│   ├── dashboard.css
│   └── js/              # 10 modular JS files
├── knowledge_graph.py   # KG engine (668L)
├── kg_bridge.py         # KG↔MemOS bridge
├── wiki_living.py       # Living wiki (1080L — MONOLITH)
├── wiki_graph.py        # Wiki graph (450L)
├── palace.py            # Memory palace (443L)
├── mcp_server.py        # MCP server (851L)
├── benchmark.py         # Performance benchmarks
└── benchmark_quality.py # Quality benchmarks (657L)
```

## Code Conventions
- Type hints on all public functions
- Docstrings in Google style
- 4-space indentation
- `ruff` for linting and formatting
- Tests in `tests/` mirroring `src/memos/` structure
- All API handlers return JSON strings
- Storage backends inherit from `storage/base.py`

## Architecture Decisions
- `core.py` is the god-class — all major operations flow through `MemOS` class
- Storage is pluggable: JSON (dev), ChromaDB (default), Qdrant/Pinecone (cloud)
- KG facts auto-extracted from memories via `knowledge_graph.py`
- MCP server exposes full API for AI agents
- Dashboard served from `web/` via FastAPI static files

## Known Monoliths (Split Priority)
1. **`core.py` (1909L)** — God class, needs decomposition into focused modules
2. **`cli/_parser.py` (1171L)** — Argparse monolith, should be modular
3. **`wiki_living.py` (1080L)** — Wiki engine, can split rendering/logic/data
4. **`cli/commands_memory.py` (1036L)** — Memory CLI commands, group by operation
5. **`mcp_server.py` (851L)** — MCP endpoints, split by resource type

## Frontend Considerations
- Current: vanilla HTML/CSS/JS served by FastAPI
- Dashboard already split into 12 modular JS files
- Potential migration to: Next.js / Vercel for proper SPA
- API would stay on FastAPI, front becomes separate deployment

## Docker Deployment
- Image: `ghcr.io/mars375/memos:latest`
- Compose: `workspace-labs/forge/chantiers/memos/docker-compose.yml`
- Volume mount for `src/memos/web/` to serve dashboard
- Port: 8100

## Testing Rules
- Every new feature needs tests
- Test files mirror source structure: `tests/test_foo.py` for `src/memos/foo.py`
- Use pytest fixtures for temp directories and mock backends
- Run full suite before merging to main
