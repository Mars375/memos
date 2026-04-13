# Technology Stack

**Analysis Date:** 2026-04-13

## Languages

**Primary:**
- Python 3.11+ - Core MemOS library, CLI, API server, and all backends
- JavaScript/TypeScript - Optional dashboard UI modules (bundled in web distribution)

## Runtime

**Environment:**
- Python 3.11+ required (`requires-python = ">=3.11"` in `pyproject.toml`)
- Docker support: `FROM python:3.11-slim` (see `Dockerfile`)

**Package Manager:**
- pip - Primary package manager
- Lockfile: `pyproject.toml` with `setuptools>=68.0` build system

## Frameworks

**Core:**
- FastAPI 0.104+ - REST API server framework (optional, installed via `memos[server]`)
- Uvicorn 0.24+ - ASGI server for FastAPI deployments (optional, installed via `memos[server]`)

**Vector Search Backends (pluggable):**
- ChromaDB 0.4+ - Production vector database with embedding support (profile: `chroma`)
- Qdrant Client 1.7+ - Vector search and payload storage (profile: `qdrant`)
- Pinecone Client 3.0+ - Serverless cloud vector search (optional)
- Sentence-Transformers 2.7+ - Local embedding generation (optional, installed via `memos[local]`)

**Testing:**
- pytest 7.0+ - Test framework
- pytest-cov 4.0+ - Coverage reporting
- pytest-asyncio 0.23+ - Async test support

**Build/Dev:**
- ruff 0.4+ - Linting and code formatting
- setuptools 68.0+ - Package building

## Key Dependencies

**Critical:**
- httpx 0.25+ - HTTP client for external API calls (Ollama, Qdrant, Pinecone)
  - Used for: Embedding API calls to Ollama, Qdrant HTTP requests, Pinecone API interaction
  - Why it matters: Core integration with vector search backends and embedding models

**Infrastructure:**
- starlette - ASGI toolkit bundled with FastAPI (for static file serving, middleware)
- pyarrow 12.0+ - Parquet file I/O support (optional, installed via `memos[parquet]`)

**Storage & Persistence:**
- SQLite3 (stdlib) - Embedded database for:
  - Knowledge Graph (`src/memos/knowledge_graph.py`) — temporal facts and relationships
  - Embedding cache (`src/memos/cache/embedding_cache.py`) — persistent LRU cache for vector embeddings
  - Palace Index (`src/memos/palace.py`) — context memory structure
- JSON (stdlib) - Default file-based storage backend (`JsonFileBackend`)

## Configuration

**Environment Variables:**
- `MEMOS_BACKEND` - Storage backend selection (memory|local|json|chroma|qdrant|pinecone|encrypted)
- `MEMOS_HOST` - Server bind address (default: 127.0.0.1)
- `MEMOS_PORT` - Server port (default: 8000)
- `MEMOS_CHROMA_URL` - ChromaDB server URL (e.g., http://chroma:8000)
- `MEMOS_QDRANT_HOST` / `MEMOS_QDRANT_PORT` - Qdrant server address
- `MEMOS_QDRANT_API_KEY` - Qdrant authentication
- `MEMOS_EMBED_HOST` - Ollama server URL (default: http://localhost:11434)
- `MEMOS_EMBED_MODEL` - Embedding model name (default: nomic-embed-text)
- `MEMOS_PINECONE_API_KEY` - Pinecone API key
- `MEMOS_API_KEY` - API key for server authentication
- `MEMOS_CONFIG` - Custom config file path (default: ~/.memos.toml)

**Config Files:**
- `~/.memos.toml` - Optional user config (TOML format, section `[memos]`)
- `Dockerfile` environment defaults: `MEMOS_BACKEND=local`, `MEMOS_HOST=0.0.0.0`, `MEMOS_PORT=8000`

**Build Config:**
- `pyproject.toml` - Package metadata, dependencies, build config
- `Dockerfile` - Multi-stage containerization with all optional dependencies

## Platform Requirements

**Development:**
- Python 3.11+ interpreter
- pip or similar package manager
- Optional: Docker/Docker Compose for containerized deployments

**Production:**
- Python 3.11+ runtime
- Optional vector database: ChromaDB, Qdrant, or Pinecone (cloud)
- Optional embedding server: Ollama instance at `MEMOS_EMBED_HOST`
- For CLI usage: ~.memos directory for persistent storage (JSON backend)
- For server: HTTP port (8000 default) and optional database connections

**Docker Deployment:**
- `docker-compose.yml` supports three profiles:
  1. **Standalone** (`memos-standalone`): Single container, zero external dependencies
     - Uses local JSON storage + built-in embeddings (all-MiniLM-L6-v2)
     - Port: 8000
  2. **ChromaDB** (`--profile chroma`): MemOS + ChromaDB server
     - MemOS on port 8100, ChromaDB on port 8001
  3. **Qdrant** (`--profile qdrant`): MemOS + Qdrant server
     - MemOS on port 8000, Qdrant on ports 6333 (HTTP) and 6334 (gRPC)

## Optional Extras

Installation groups (`pip install memos-agent[extra]`):
- `local` - Sentence-transformers for local embeddings (zero external dependencies)
- `chroma` - ChromaDB client
- `qdrant` - Qdrant client
- `pinecone` - Pinecone client
- `parquet` - PyArrow for Parquet export/import
- `server` - FastAPI + Uvicorn for REST API server
- `dev` - Testing and linting tools (pytest, ruff, pytest-asyncio)

---

*Stack analysis: 2026-04-13*
