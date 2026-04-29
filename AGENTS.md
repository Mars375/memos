# MemOS — Memory Operating System for AI Agents

## Project Overview
Persistent, structured, local-first memory backend for LLM agents. Python 3.11+, FastAPI server, MCP endpoint, pluggable storage backends, and a lightweight dashboard.

**Version:** 2.3.8
**Author:** Mars375
**License:** MIT

## Stack
- **Runtime:** Python 3.11+
- **Server:** FastAPI + Uvicorn
- **Default API port:** 8000 inside the process / 8100 in the documented Docker run example
- **Vector DB:** ChromaDB (default production backend), Qdrant, Pinecone (optional)
- **Embeddings:** local sentence-transformers and Ollama-backed integrations
- **Frontend:** Vanilla HTML/CSS/JS dashboard served by FastAPI
- **Deploy:** GHCR image + `docker run` (compose file is no longer committed in the repo)

## Commands
```bash
# Install (dev)
pip install -e ".[local,chroma,server,dev]"

# Run server
python -m memos serve --port 8100

# Tests
python -m pytest tests/ -q
python -m pytest tests/test_core.py -q
python -m pytest tests/ -q --tb=short

# Lint
ruff check src/ tests/
ruff format src/ tests/
```

## Project Structure
```text
src/memos/
├── core.py                  # MemOS orchestration nucleus
├── _*_facade.py             # extracted facades (dedup, feedback, ingest, io, maintenance,
│                            # memory CRUD, namespace, sharing, tag, versioning)
├── api/                     # FastAPI app wiring, auth, schemas, routes, SSE
│   └── routes/
│       ├── admin.py
│       ├── brain.py
│       ├── context.py
│       ├── kg.py
│       ├── knowledge.py
│       ├── memory.py        # thin memory router composer
│       ├── _memory_*.py     # focused memory route modules + compatibility aggregators
│       ├── palace.py
│       └── wiki.py
├── cli/                     # CLI entrypoint + split parser/command modules
│   ├── _parser/
│   ├── commands_*.py
│   └── _common.py
├── mcp_server.py            # thin MCP transport wrapper
├── mcp_tools/               # MCP tool registry + domain tool modules
├── wiki_engine.py           # living wiki coordinator
├── wiki_entities.py         # entity extraction / stopwords
├── wiki_models.py           # wiki dataclasses
├── wiki_templates.py        # wiki frontmatter / templates
├── wiki_living.py           # backward-compat shim re-exporting wiki modules
├── knowledge_graph.py       # backward-compat KG shim; implementation in _kg_core + _kg_* helpers
├── brain.py                 # backward-compat brain shim; implementation in _brain_facade + _brain_* helpers
├── ingest/                  # miner, parsers, chunker, URL ingest, cache
├── retrieval/               # hybrid retrieval engine
├── storage/                 # backend abstraction + concrete backends
├── versioning/              # versioning engine + models
├── sharing/                 # sharing engine + models
├── subscriptions/           # event subscriptions
├── namespaces/              # ACL and namespace policy logic
├── embeddings/              # embedding providers
├── decay/                   # decay engine
├── compaction/              # memory compaction
├── consolidation/           # memory consolidation
├── cache/                   # cache implementations
├── web/                     # dashboard assets
└── benchmark*.py            # benchmark entrypoints
```

## Code Conventions
- Type hints on all public functions
- Docstrings in Google style
- 4-space indentation
- `ruff` for linting and formatting
- Tests in `tests/` mirroring `src/memos/` where practical
- Public compatibility shims are kept when large refactors split modules
- Storage backends inherit from `storage/base.py`

## Architecture Notes
- `core.py` now coordinates focused facades instead of owning every concern directly
- The CLI parser is split into `cli/_parser/` per domain
- MCP transport lives in `mcp_server.py`, while tool implementations live in `mcp_tools/`
- The living wiki was split into engine/entities/models/templates while keeping `wiki_living.py` as a shim
- Storage is pluggable: in-memory, JSON, ChromaDB, Qdrant, Pinecone, encrypted wrapper, async wrapper
- Dashboard assets are served from `web/` via FastAPI

## Current Refactor Hotspots
The previous high-value hotspots have been split: memory routes, `core.py`, ingest miner, compaction engine, palace, and benchmark quality now route through focused modules or compatibility façades. No Python source file currently exceeds 500 lines.

Remaining 400–500 line files are acceptable watchlist items rather than urgent split targets:

1. `src/memos/wiki_entities.py` and `src/memos/wiki_graph.py` — split only if entity extraction or graph update logic grows again.
2. `src/memos/ingest/parsers.py` and `src/memos/ingest/url.py` — split only when adding more parser families or URL providers.
3. `src/memos/conflict.py` and `src/memos/consolidation/engine.py` — split only if conflict or consolidation workflows gain new responsibilities.
4. `src/memos/storage/qdrant_backend.py` and `src/memos/cli/commands_io.py` — split only with backend/provider churn.

## Frontend Considerations
- Current UI is vanilla HTML/CSS/JS served by FastAPI
- Dashboard JS is already modularized under `src/memos/web/js/`
- A future dedicated SPA remains possible, but today the dashboard ships with the API server

## Docker / Deployment
- Image: `ghcr.io/mars375/memos:latest`
- Recommended quickstart: `docker run -p 8100:8000 ...`
- If you need ChromaDB/Qdrant alongside MemOS, use your own compose/orchestrator setup; the repo no longer ships a root `docker-compose.yml`

## Testing Rules
- Every new feature needs tests
- Run the full suite before merging to `main`
- Current suite size is roughly 2400 tests
- Keep direct tests on new split modules, not just legacy compatibility shims
