# External Integrations

**Analysis Date:** 2026-04-15

## APIs & External Services

**Ollama (local LLM embedding):**
- Purpose: Remote embedding generation via HTTP
- Endpoint: `http://<MEMOS_EMBED_HOST>:<MEMOS_EMBED_PORT>/api/embeddings` (default `localhost:11434`)
- Model: configurable via `MEMOS_EMBED_MODEL` (default `nomic-embed-text`)
- Client: `httpx` — sync POST in `src/memos/retrieval/engine.py`
- Auth: None (local service)
- Docker Compose override: `MEMOS_EMBED_HOST=http://host.docker.internal:11434`

## Databases / Vector Stores

**In-Memory Backend (default):**
- Type: Python dict, no persistence
- Class: `src/memos/storage/memory_backend.py` (`InMemoryBackend`)
- Use: development, testing, ephemeral agents

**JSON File Backend:**
- Type: Local JSON file
- Class: `src/memos/storage/json_backend.py` (`JsonFileBackend`)
- Path: `~/.memos/memories.json` or `MEMOS_PERSIST_PATH`
- Use: standalone/local-first deployment with zero dependencies

**SQLite (Knowledge Graph):**
- Type: Embedded relational DB
- Library: Python stdlib `sqlite3`
- File: configurable `kg_db_path` arg (default `~/.memos/kg.db`)
- Class: `src/memos/knowledge_graph.py` (`KnowledgeGraph`)
- Use: temporal triple store for entity relationships

**ChromaDB (optional):**
- Type: Vector database (HTTP client mode)
- Library: `chromadb >= 0.4` (`[chroma]` extra)
- Connection: `MEMOS_CHROMA_HOST` / `MEMOS_CHROMA_PORT` (default `localhost:8000`)
- Class: `src/memos/storage/chroma_backend.py` (`ChromaBackend`)
- Docker: `chromadb/chroma:1.5.7` in `docker-compose.yml` (`chroma` profile)

**Qdrant (optional):**
- Type: Vector database (gRPC + HTTP client)
- Library: `qdrant-client >= 1.17.1` (`[qdrant]` extra)
- Connection: `MEMOS_QDRANT_HOST` / `MEMOS_QDRANT_PORT` (default `localhost:6333`)
- Auth: `MEMOS_QDRANT_API_KEY` (optional)
- Class: `src/memos/storage/qdrant_backend.py` (`QdrantBackend`)
- Docker: `qdrant/qdrant:v1.17.1` in `docker-compose.yml` (`qdrant` profile)

**Pinecone (optional, cloud):**
- Type: Managed vector database (cloud API)
- Library: `pinecone-client >= 3.0` (`[pinecone]` extra)
- Auth: `MEMOS_PINECONE_API_KEY`
- Config: `MEMOS_PINECONE_INDEX_NAME`, `MEMOS_PINECONE_CLOUD`, `MEMOS_PINECONE_REGION`, `MEMOS_PINECONE_SERVERLESS`
- Class: `src/memos/storage/pinecone_backend.py` (`PineconeBackend`)

## APIs Exposed

**REST API (FastAPI — `[server]` extra):**
- Framework: FastAPI + Uvicorn
- Entry: `src/memos/api/__init__.py` (`create_fastapi_app`)
- Routes: `src/memos/api/routes/`
- Auth: Bearer token via `MEMOS_API_KEY` (`src/memos/api/auth.py`)
- Rate limiting: per-key requests/minute (`src/memos/api/ratelimit.py`)
- Default bind: `0.0.0.0:8000` in Docker, `127.0.0.1:8000` locally

**MCP Server (JSON-RPC 2.0):**
- Spec: MCP 2025-03-26
- Entry: `src/memos/mcp_server.py`
- Transports:
  - `stdio` — for Claude Code / Cursor direct integration
  - Streamable HTTP — POST/GET/OPTIONS `/mcp`, discovery at `GET /.well-known/mcp.json`
- Consumers: OpenClaw, Claude Code, Cursor
- Tools exposed: `memory_search` and others defined in `TOOLS` list

**Server-Sent Events:**
- File: `src/memos/api/sse.py`
- Used for: streaming recall results, MCP SSE keepalive

## URL / Web Ingestion

**httpx-based URL fetcher:**
- File: `src/memos/ingest/url.py`
- Supported sources: arXiv, Twitter/X, PDFs, generic webpages
- Uses: stdlib `html.parser`, `urllib.parse`, regex — no third-party HTML parser

## Notable Third-Party Libraries

| Library | Extra | Purpose | Key files |
|---------|-------|---------|-----------|
| `fastapi` | `[server]` | REST API + MCP HTTP | `src/memos/api/`, `src/memos/mcp_server.py` |
| `uvicorn` | `[server]` | ASGI server | `src/memos/cli/` |
| `httpx` | core | HTTP client (Ollama, URL ingest) | `src/memos/ingest/url.py`, `src/memos/retrieval/engine.py` |
| `sentence-transformers` | `[local]` | Local embeddings (all-MiniLM-L6-v2) | `src/memos/embeddings/local.py` |
| `chromadb` | `[chroma]` | Vector storage | `src/memos/storage/chroma_backend.py` |
| `qdrant-client` | `[qdrant]` | Vector storage | `src/memos/storage/qdrant_backend.py` |
| `pinecone-client` | `[pinecone]` | Cloud vector storage | `src/memos/storage/pinecone_backend.py` |
| `pyarrow` | `[parquet]` | Parquet export/import | `src/memos/parquet_io.py` |

## Authentication & Secrets

**REST API:** `MEMOS_API_KEY` env var — bearer token, optional (disabled when empty)

**Pinecone:** `MEMOS_PINECONE_API_KEY` env var

**Qdrant:** `MEMOS_QDRANT_API_KEY` env var (optional, for cloud/managed deployments)

**Encryption at rest:** passphrase-derived keys via PBKDF2 (stdlib only, no external secrets manager) — `src/memos/crypto.py`, `src/memos/storage/encrypted_backend.py`

---

*Integration audit: 2026-04-15*
