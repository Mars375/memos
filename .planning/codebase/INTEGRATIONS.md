# External Integrations

**Analysis Date:** 2026-04-13

## APIs & External Services

**Embedding Models:**
- Ollama - Local embedding server for vector generation
  - SDK/Client: httpx (HTTP requests)
  - URL: `MEMOS_EMBED_HOST` (default: http://localhost:11434)
  - Endpoint: `/api/embed` (POST)
  - Model: `MEMOS_EMBED_MODEL` (default: nomic-embed-text)
  - Timeout: `MEMOS_EMBED_TIMEOUT` (default: 30s)
  - Alternative: Sentence-Transformers library for local embeddings (no external API)

## Data Storage

**Vector Databases (pluggable backends):**

1. **ChromaDB** (Production vector search)
   - Type: Vector database with metadata filtering
   - Connection: HTTP to ChromaDB server
   - Config: `MEMOS_CHROMA_HOST` / `MEMOS_CHROMA_PORT` (default: localhost:8000)
   - Client: chromadb Python client
   - File: `src/memos/storage/chroma_backend.py`
   - Features: Embedding caching via SQLite, Ollama EmbeddingFunction integration

2. **Qdrant** (Vector search with native gRPC/HTTP)
   - Type: Vector database with payload storage
   - Connection: HTTP or gRPC
   - Config: `MEMOS_QDRANT_HOST` / `MEMOS_QDRANT_PORT` (default: localhost:6333)
   - Auth: Optional `MEMOS_QDRANT_API_KEY`
   - Client: qdrant-client Python SDK
   - File: `src/memos/storage/qdrant_backend.py`
   - Features: Native vector search, namespace support, gRPC acceleration

3. **Pinecone** (Serverless cloud vector search)
   - Type: Cloud-managed vector database
   - Auth: `MEMOS_PINECONE_API_KEY` (required)
   - Config: 
     - `MEMOS_PINECONE_INDEX_NAME` (default: memos)
     - `MEMOS_PINECONE_CLOUD` (default: aws)
     - `MEMOS_PINECONE_REGION` (default: us-east-1)
     - `MEMOS_PINECONE_SERVERLESS` (default: true)
   - Client: pinecone-client SDK
   - File: `src/memos/storage/pinecone_backend.py`
   - Features: Serverless index management, automatic scaling

**Relational/Embedded Databases:**

- **SQLite3** (Embedded)
  - Knowledge Graph: `~/.memos/knowledge.db` (temporal facts, entities, relationships)
  - Embedding Cache: `~/.memos/embedding-cache.db` (vector embeddings with timestamps)
  - Palace Index: `~/.memos/palace.db` (context memory structure)
  - Files:
    - `src/memos/knowledge_graph.py` - Fact/entity storage with temporal queries
    - `src/memos/cache/embedding_cache.py` - LRU embedding cache with SQLite backend
    - `src/memos/palace.py` - Memory palace structure and recall

**File Storage:**

- **Local Filesystem Only** - No cloud storage integration
  - Default storage path: `~/.memos/` (configurable via `MEMOS_PERSIST_PATH`)
  - Files managed:
    - `store.json` - Memory items (JsonFileBackend)
    - `knowledge.db` - Knowledge graph (SQLite)
    - `embedding-cache.db` - Embedding cache (SQLite)
    - `palace.db` - Palace index (SQLite)

**Caching:**

- **Embedding Cache** (persistent SQLite-backed)
  - Location: `src/memos/cache/embedding_cache.py`
  - Purpose: Avoid re-embedding identical text (critical on ARM64/low-resource systems)
  - LRU eviction strategy
  - In-process L1 cache (dict) + L2 disk cache (SQLite)

## Authentication & Identity

**API Authentication:**

- **Custom API Key Authentication** - Optional bearer token validation
  - Header: `Authorization: Bearer <api_key>`
  - Env: `MEMOS_API_KEY` (single key for server)
  - Implementation: `src/memos/api/auth.py`
  - Features:
    - SHA256 hashing of keys in memory
    - Per-key rate limiting
    - Can be disabled (no keys = no auth required)
  - FastAPI middleware integration for HTTP routes

**No OAuth/OIDC Integration** - Not applicable to this codebase

## Monitoring & Observability

**Error Tracking:**
- Not detected - No error tracking service integration (Sentry, DataDog, etc.)

**Logs:**
- Console/stdout logging via Python's logging module
- Uvicorn/FastAPI auto-logging in server mode
- No structured logging service integration

**Metrics:**
- No external metrics/observability integration
- Internal statistics available via CLI: `memos stats` command
- Rate limiting metrics accessible via FastAPI middleware

## CI/CD & Deployment

**Hosting:**
- Docker Compose - Local containerization (see `docker-compose.yml`)
- No cloud platform integration (no AWS/GCP/Azure SDK)
- Manual deployment or container orchestration (Kubernetes, Podman, etc.)

**CI Pipeline:**
- Not detected in codebase - No GitHub Actions, GitLab CI, or Jenkins integration

**Docker Images:**
- Container registry: ghcr.io (GitHub Container Registry)
- Image: `ghcr.io/mars375/memos:latest`
- Profiles:
  - `memos-standalone` - Zero dependencies, local storage
  - `memos` (with chroma profile) - Production ChromaDB setup
  - `memos-qdrant` (with qdrant profile) - Qdrant vector search

## Environment Configuration

**Required env vars (variable by backend):**

For standalone/local:
- `MEMOS_BACKEND=local` (or `memory`, `json`)
- `MEMOS_EMBED_HOST` (if using local embeddings, not needed)

For ChromaDB:
- `MEMOS_BACKEND=chroma`
- `MEMOS_CHROMA_URL` or `MEMOS_CHROMA_HOST` + `MEMOS_CHROMA_PORT`
- `MEMOS_EMBED_HOST` (Ollama for embeddings)

For Qdrant:
- `MEMOS_BACKEND=qdrant`
- `MEMOS_QDRANT_HOST` + `MEMOS_QDRANT_PORT`
- `MEMOS_QDRANT_API_KEY` (if secured)

For Pinecone:
- `MEMOS_BACKEND=pinecone`
- `MEMOS_PINECONE_API_KEY` (required)
- `MEMOS_PINECONE_INDEX_NAME`, `MEMOS_PINECONE_CLOUD`, `MEMOS_PINECONE_REGION`

**Secrets location:**
- Environment variables only (no .env file reading in core library)
- Docker: passed via `.env` file in compose directory
- CLI: `MEMOS_CONFIG` TOML file (home directory, user-readable)
- No secrets vault integration (HashiCorp Vault, AWS Secrets Manager, etc.)

## Webhooks & Callbacks

**Incoming Webhooks:**
- Not detected - No webhook receiver endpoints

**Outgoing Webhooks:**
- Not detected - No outbound webhook triggers

**Event Streaming:**
- Internal event system via `ContextStack` (`src/memos/context.py`)
- API endpoint: `/api/v1/events` (SSE - Server-Sent Events)
- For memory updates, not external integrations

## MCP (Model Context Protocol) Integration

**MCP Server:**
- Transport modes: stdio and Streamable HTTP (MCP 2025-03-26 spec)
- Endpoints:
  - POST `/mcp` - JSON-RPC 2.0 call
  - GET `/mcp` - SSE keepalive stream
  - OPTIONS `/mcp` - CORS preflight
  - GET `/.well-known/mcp.json` - Discovery
- CORS: Configurable via `MEMOS_CORS_ORIGINS` env var (default: *)
- File: `src/memos/mcp_server.py`
- Tools exposed:
  - `memory_search` - Semantic + filtered search
  - `memory_save` - Persist new memories
  - `memory_forget` - Delete by ID or tag
  - `kg_add_fact` - Knowledge graph facts
  - And 15+ other memory/knowledge management tools

## Rate Limiting

**Built-in Rate Limiter:**
- Middleware: `src/memos/api/ratelimit.py`
- Per-API-key sliding window (default: 60 seconds)
- Configurable per endpoint via `EndpointRule` patterns
- Default limits:
  - `/api/v1/learn`: 30 req/min
  - `/api/v1/search`: 60 req/min
  - `/api/v1/consolidate`: 5 req/min
- Response headers: X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset
- Can be disabled if no API keys configured

---

*Integration audit: 2026-04-13*
