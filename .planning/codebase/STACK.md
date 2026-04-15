# Technology Stack

**Analysis Date:** 2026-04-15

## Languages & Runtimes

**Primary:**
- Python 3.11+ — entire codebase (source, tests, tooling)

**Runtime:**
- CPython 3.11 (minimum required, pinned in `pyproject.toml` and `Dockerfile`)

## Package Management

- **Build system:** setuptools >= 68.0 with wheel
- **Package definition:** `pyproject.toml` (PEP 517/518)
- **Lockfile:** None — dependencies are range-pinned in `pyproject.toml`
- **Install extras:** `local`, `chroma`, `qdrant`, `pinecone`, `parquet`, `server`, `dev`

## Frameworks & Libraries

**Web / API (optional — `[server]` extra):**
- `fastapi >= 0.104` — REST API and MCP HTTP server (`src/memos/api/__init__.py`, `src/memos/mcp_server.py`)
- `uvicorn >= 0.44.0` — ASGI server (`src/memos/cli/`)

**HTTP Client:**
- `httpx >= 0.25` — URL ingestion, Ollama embedding calls, Pinecone/Qdrant HTTP calls (`src/memos/ingest/url.py`, `src/memos/retrieval/engine.py`)

**Embeddings (optional — `[local]` extra):**
- `sentence-transformers >= 2.7` — local embedding without any external service; default model `all-MiniLM-L6-v2` (`src/memos/embeddings/local.py`)

**Vector Stores (all optional):**
- `chromadb >= 0.4` (`[chroma]`) — ChromaDB HTTP client (`src/memos/storage/chroma_backend.py`)
- `qdrant-client >= 1.17.1` (`[qdrant]`) — Qdrant gRPC/HTTP client (`src/memos/storage/qdrant_backend.py`)
- `pinecone-client >= 3.0` (`[pinecone]`) — Pinecone serverless/pod client (`src/memos/storage/pinecone_backend.py`)

**Data Export (optional — `[parquet]` extra):**
- `pyarrow >= 12.0` — Parquet import/export (`src/memos/parquet_io.py`)

**Cryptography:**
- Python stdlib `hashlib` — PBKDF2-HMAC-SHA256 key derivation; Fernet-style AES encryption implemented without third-party `cryptography` library (`src/memos/crypto.py`)

**Knowledge Graph / Persistence:**
- Python stdlib `sqlite3` — temporal knowledge graph triple store (`src/memos/knowledge_graph.py`)

**Configuration:**
- Python 3.11 stdlib `tomllib` (with `tomli` fallback for older Pythons) — TOML config file parsing (`src/memos/config.py`)

## Build & Tooling

**Linter / Formatter:**
- `ruff >= 0.15.10` — lint (E, F, W, I rules) + import sorting; line length 120; target Python 3.11 (`pyproject.toml` `[tool.ruff]`)

**Testing:**
- `pytest >= 7.0`
- `pytest-asyncio >= 0.23` — async test support
- `pytest-cov >= 4.0` — coverage reporting
- `freezegun >= 1.2` — time mocking in tests

**Containerization:**
- Docker — `Dockerfile` based on `python:3.11-slim`, installs `[server,chroma,local,dev]` extras
- Docker Compose — `docker-compose.yml` with three profiles: standalone (default), `chroma`, `qdrant`

**Distribution:**
- Package published to GitHub Container Registry as `ghcr.io/mars375/memos:latest`
- No CI config file detected in workspace root

## Key Config Files

- `pyproject.toml` — project metadata, dependencies, pytest/ruff/coverage config
- `Dockerfile` — container build definition
- `docker-compose.yml` — multi-profile deployment (standalone, chroma, qdrant)
- `~/.memos.toml` (runtime) — user config file (TOML); path overridable via `MEMOS_CONFIG` env var

## Environment Variables

All configuration via `MEMOS_*` env vars (see `src/memos/config.py` `ENV_MAP`):
- `MEMOS_BACKEND` — storage backend: `memory`, `json`, `chroma`, `qdrant`, `pinecone`
- `MEMOS_HOST` / `MEMOS_PORT` — API server bind address (default `127.0.0.1:8000`)
- `MEMOS_CHROMA_HOST` / `MEMOS_CHROMA_PORT` / `MEMOS_CHROMA_URL`
- `MEMOS_QDRANT_HOST` / `MEMOS_QDRANT_PORT` / `MEMOS_QDRANT_API_KEY` / `MEMOS_QDRANT_PATH`
- `MEMOS_EMBED_HOST` / `MEMOS_EMBED_MODEL` / `MEMOS_EMBED_TIMEOUT`
- `MEMOS_PINECONE_API_KEY` / `MEMOS_PINECONE_INDEX_NAME` / `MEMOS_PINECONE_CLOUD` / `MEMOS_PINECONE_REGION` / `MEMOS_PINECONE_SERVERLESS`
- `MEMOS_API_KEY` — REST API authentication key
- `MEMOS_PERSIST_PATH` — JSON backend file path
- `MEMOS_CORS_ORIGINS` — CORS allowed origins for MCP HTTP server (default `*`)

---

*Stack analysis: 2026-04-15*
