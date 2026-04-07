# MemOS — Memory Operating System for LLM Agents

> A standalone memory layer that gives any LLM agent persistent, smart memory.
> Local-first, framework-agnostic, 5 minutes to start.

## What it does

- **Recall** — semantically retrieve what's relevant for the current task
- **Learn** — automatically extract and store decisions, preferences, patterns
- **Forget** — old memories fade naturally, frequent ones strengthen
- **Sanitize** — built-in security linter prevents prompt injection through memory
- **Monitor** — real-time dashboard of memory health, coverage, and decay

## Quick start

```bash
pip install memos

# Initialize with in-memory backend (default, no dependencies)
memos init

# Initialize with local ChromaDB
memos init --backend chroma --embed-host http://localhost:11434

# Initialize with Qdrant (local or remote)
memos init --backend qdrant --embed-host http://localhost:11434

# Learn something
memos learn "The user prefers concise responses" --tags preference

# Recall what's relevant
memos recall "how should I respond to the user?" --top 5

# See what the agent knows
memos stats

# Start the API server
memos serve --port 8100
```

## API

```python
from memos import MemOS

# In-memory (default)
mem = MemOS()

# ChromaDB backend
mem = MemOS(backend="chroma", embed_host="http://localhost:11434")

# Qdrant backend (local file)
mem = MemOS(backend="qdrant", qdrant_path="/data/memos-qdrant",
            embed_host="http://localhost:11434")

# Qdrant backend (remote server)
mem = MemOS(backend="qdrant", qdrant_host="qdrant.example.com",
            qdrant_port=6333, qdrant_api_key="your-key",
            embed_host="http://localhost:11434")

# Learn
mem.learn("User runs Docker on Raspberry Pi 5", tags=["infra", "preference"])

# Recall
results = mem.recall("What hardware does the user have?")
# => [{"content": "User runs Docker on Raspberry Pi 5", "relevance": 0.94, "age_days": 2}]

# Forget (decay)
mem.prune(threshold=0.3)  # Remove memories below relevance threshold

# Stats
stats = mem.stats()
# => {"total_memories": 142, "avg_relevance": 0.71, "decay_rate": "2.3/week"}
```

## REST API

```
POST /api/v1/learn          {content, tags, importance?}
POST /api/v1/learn/batch    {items: [{content, tags?, importance?}], continue_on_error?}
POST /api/v1/recall         {query, top?, filter?}
GET  /api/v1/recall/stream  {q, top?, filter_tags?, min_score?}  (SSE)
POST /api/v1/prune          {threshold, max_age?}
GET  /api/v1/stats
GET  /api/v1/search         {q, limit?}
DELETE /api/v1/memory/{id}
POST /api/v1/consolidate    {similarity_threshold?, async?, dry_run?}  Sync or async
GET  /api/v1/consolidate    {}                                         List tasks
GET  /api/v1/consolidate/:id {}                                         Task status
GET  /api/v1/export/parquet {include_metadata?, compression?}          Download .parquet
GET  /health
```

### Streaming Recall (SSE)

Get recall results as a live stream of Server-Sent Events — results arrive one at a time as they are found:

```bash
curl -N "http://localhost:8100/api/v1/recall/stream?q=python&top=5"
```

Each event is formatted as:
```
event: recall
data: {"index":1,"id":"abc123","content":"User prefers Python","score":0.94,"tags":["preference"],"match_reason":"semantic","age_days":2.1}

event: done
data: {"type":"done","count":3,"query":"python","elapsed_ms":45.2}
```

Python SDK equivalent:
```python
import asyncio
from memos import MemOS

mem = MemOS()

async def stream_recall():
    async for result in mem.recall_stream("what does the user prefer?", top=5):
        print(f"[{result.score:.2f}] {result.item.content}")

asyncio.run(stream_recall())
```

## Storage Backends

| Backend | Best for | Install | Config |
|---------|----------|---------|--------|
| **In-memory** | Testing, single-session | `pip install memos` | `backend="memory"` |
| **ChromaDB** | Local development, small-medium datasets | `pip install memos[chroma]` | `backend="chroma"` |
| **Qdrant** | Production, large datasets, hybrid search | `pip install memos[qdrant]` | `backend="qdrant"` |
| **Pinecone** | Cloud-native, serverless, managed | `pip install memos[pinecone]` | `backend="pinecone"` |

### Qdrant Features (v0.7.0+)

- **Native vector search** — delegates to Qdrant's optimized ANN engine
- **Hybrid BM25+vector scoring** — combines keyword precision with semantic understanding
- **Local or remote** — file-based for dev, gRPC for production
- **Namespace isolation** — multi-agent support with separate Qdrant collections
- **Configurable weights** — tune `semantic_weight` (default 0.6) for your use case

```python
# Advanced Qdrant configuration
mem = MemOS(
    backend="qdrant",
    qdrant_host="localhost",
    qdrant_port=6333,
    qdrant_api_key="optional-api-key",
    vector_size=768,
    semantic_weight=0.7,  # 0.7 semantic + 0.3 keyword
    embed_host="http://localhost:11434",
    embed_model="nomic-embed-text",
)
```

### Pinecone Features (v0.9.0+)

- **Serverless or Pod-based** — automatic index creation, AWS/GCP/Azure
- **Native vector search** — Pinecone similarity with score thresholds
- **Batch upsert** — optimized bulk operations (100-item batches)
- **Namespace isolation** — multi-agent support with Pinecone namespaces
- **Fully managed** — no infrastructure to maintain

```python
# Pinecone Serverless (recommended)
mem = MemOS(
    backend="pinecone",
    pinecone_api_key="pc-key-...",
    pinecone_index_name="agent-memories",
    embed_host="http://localhost:11434",
)

# Pinecone Pod-based
mem = MemOS(
    backend="pinecone",
    pinecone_api_key="pc-key-...",
    pinecone_serverless=False,
    pinecone_environment="us-east-1-aws",
)
```

## Batch Learn API (v0.9.0+)

Store multiple memories in a single call — ideal for initial loading, file ingestion, or bulk operations.

```python
result = mem.batch_learn([
    {"content": "User prefers Python", "tags": ["preference"], "importance": 0.8},
    {"content": "Server runs on ARM64", "tags": ["infra"]},
    {"content": "Dark mode enabled", "tags": ["ui"]},
])
# result = {"learned": 3, "skipped": 0, "errors": [], "items": [...]}

# Strict mode — raises on first invalid item
result = mem.batch_learn(items, continue_on_error=False)
```

REST API:
```bash
curl -X POST http://localhost:8100/api/v1/learn/batch \
  -H 'Content-Type: application/json' \
  -d '{"items": [
    {"content": "Memory 1", "tags": ["a"]},
    {"content": "Memory 2", "tags": ["b"]}
  ]}'
```

CLI:
```bash
echo '[{"content": "Batch 1"}, {"content": "Batch 2"}]' | memos batch-learn -
memos batch-learn memories.json --verbose
```

## Parquet Export/Import (v0.10.0+)

Efficient binary serialization for large memory stores — 3-10x smaller than JSON.

```python
# Export to Parquet (compressed binary)
result = mem.export_parquet("backup.parquet", compression="zstd")
# {"total": 500, "size_bytes": 8192, "compression": "zstd"}

# Import with merge strategy
result = mem.import_parquet("backup.parquet", merge="skip", tags_prefix=["backup"])
# {"imported": 500, "skipped": 0, "overwritten": 0}
```

CLI:
```bash
memos export --format parquet -o backup.parquet
memos import backup.parquet --merge skip
```

REST:
```bash
curl -O http://localhost:8100/api/v1/export/parquet
```

Install: `pip install memos[parquet]`

## Async Consolidation (v0.10.0+)

Run memory deduplication in the background without blocking the event loop.

```python
import asyncio

async def background_dedup():
    handle = await mem.consolidate_async(similarity_threshold=0.7)
    # Do other work while consolidation runs...
    status = mem.consolidation_status(handle.task_id)
    print(f"Status: {status['status']}, merged: {status['result']['memories_merged']}")

asyncio.run(background_dedup())
```

REST:
```bash
# Start async consolidation
curl -X POST http://localhost:8100/api/v1/consolidate \
  -H 'Content-Type: application/json' \
  -d '{"async": true, "similarity_threshold": 0.7}'
# {"status": "started", "task_id": "abc123"}

# Check status
curl http://localhost:8100/api/v1/consolidate/abc123
```

## Memory Versioning & Time-Travel (v0.11.0+)

Every memory write is automatically versioned. Query the past, diff changes, and roll back.

```python
mem = MemOS()

# Learn and update — each creates a version
mem.learn("User likes dark mode", tags=["preference"])
mem.learn("User likes dark mode with blue accents", tags=["preference", "ui"])

item_id = "the-memory-id"

# Version history
history = mem.history(item_id)
print(f"Memory has {len(history)} versions")
for v in history:
    print(f"  v{v.version_number}: {v.content} ({v.source})")

# Diff between versions
diff = mem.diff(item_id, version_a=1, version_b=2)
if diff:
    print(f"Changed fields: {list(diff.changes.keys())}")

# Diff latest change
diff = mem.diff_latest(item_id)

# Time-travel: recall as it was 1 hour ago
import time
results = mem.recall_at("user preferences", time.time() - 3600)

# Snapshot: all memories at a specific point in time
snapshot = mem.snapshot_at(time.time() - 86400)  # 1 day ago

# Roll back to a previous version
restored = mem.rollback(item_id, version_number=1)
assert restored.tags == ["preference"]  # back to original

# Versioning stats
stats = mem.versioning_stats()
# {"total_items": 42, "total_versions": 87, "avg_versions_per_item": 2.07}

# Garbage collect old versions (keep latest 3 per item)
removed = mem.versioning_gc(max_age_days=90.0, keep_latest=3)
```

### Version Sources

Each version records what caused it:
- `learn` — via `mem.learn()`
- `batch_learn` — via `mem.batch_learn()`
- `rollback` — via `mem.rollback()`
- `upsert` — direct storage operations

### Time-Travel Use Cases

- **"What did I know before the meeting?"** — `recall_at(query, meeting_start_time)`
- **"How has this preference changed?"** — `history(id)` + `diff(id, v1, v2)`
- **"Restore my config from yesterday"** — `snapshot_at(yesterday_ts)` + `rollback(id, v)`
- **Audit trail** — every change to any memory is tracked

### CLI Versioning Commands (v0.12.0+)

All versioning operations are available from the command line:

```bash
# View version history
memos history <item_id>
memos history <item_id> --json

# Diff between versions
memos diff <item_id> --v1 1 --v2 3
memos diff <item_id> --latest

# Roll back to a previous version
memos rollback <item_id> --version 1 --dry-run
memos rollback <item_id> --version 1 --yes

# Time-travel: see all memories at a past time
memos snapshot-at 2026-04-06
memos snapshot-at 1d          # 1 day ago
memos snapshot-at 2h          # 2 hours ago

# Time-travel recall: search memories as they were
memos recall-at "user preferences" --at 1h
memos recall-at "project decisions" --at 2026-04-06T12:00:00

# Versioning maintenance
memos version-stats
memos version-gc --max-age-days 90 --keep-latest 3 --dry-run
```

Timestamps accept: epoch (`1712457600`), ISO 8601 (`2026-04-07T12:00:00`), or relative (`1h`, `30m`, `2d`, `1w`).

### REST Versioning API (v0.12.0+)

```bash
# Version history
curl http://localhost:8100/api/v1/memory/{id}/history

# Get specific version
curl http://localhost:8100/api/v1/memory/{id}/version/1

# Diff between versions
curl "http://localhost:8100/api/v1/memory/{id}/diff?v1=1&v2=3"
curl "http://localhost:8100/api/v1/memory/{id}/diff?latest=true"

# Rollback
curl -X POST http://localhost:8100/api/v1/memory/{id}/rollback \
  -H 'Content-Type: application/json' \
  -d '{"version": 1}'

# Time-travel snapshot
curl "http://localhost:8100/api/v1/snapshot?at=1712457600"

# Time-travel recall
curl "http://localhost:8100/api/v1/recall/at?q=AI&at=1712457600"

# Streaming time-travel recall (SSE)
curl "http://localhost:8100/api/v1/recall/at/stream?q=AI&at=1712457600"

# Versioning stats
curl http://localhost:8100/api/v1/versioning/stats

# Garbage collect old versions
curl -X POST http://localhost:8100/api/v1/versioning/gc \
  -H 'Content-Type: application/json' \
  -d '{"max_age_days": 90, "keep_latest": 3}'
```

### Persistent Versioning (v0.13.0)

Version snapshots can be persisted to SQLite so they survive restarts:

```python
from memos import MemOS

# Enable persistent versioning
mem = MemOS(backend="memory", versioning_path="./versions.db")
mem.learn("This version history survives restarts")
```

Or via REST:
```bash
# Persistent versioning auto-enabled when versioning_path is set
memos serve --backend memory --versioning-path ./data/versions.db
```

CLI:
```bash
# Version-stats shows backend type
memos version-stats --json
```

### Namespace Access Control (v0.13.0)

RBAC for multi-agent memory isolation:

```python
from memos import MemOS
from memos.namespaces import Role

mem = MemOS(backend="memory")

# Grant roles
mem.grant_namespace_access("agent-alpha", "production", "owner")
mem.grant_namespace_access("agent-beta", "production", "writer")
mem.grant_namespace_access("agent-gamma", "production", "reader")

# Set agent identity for enforcement
mem.set_agent_id("agent-beta")
mem.namespace = "production"

mem.learn("Can write")       # OK — writer
mem.recall("something")       # OK — read+write
mem.forget("some-id")          # OK — writer has delete
```

REST API:
```bash
# Grant access
curl -X POST http://localhost:8100/api/v1/namespaces/production/grant \
  -H 'Content-Type: application/json' \
  -d '{"agent_id": "agent-1", "role": "writer"}'

# Revoke access
curl -X POST http://localhost:8100/api/v1/namespaces/production/revoke \
  -H 'Content-Type: application/json' \
  -d '{"agent_id": "agent-1"}'

# List policies
curl http://localhost:8100/api/v1/namespaces/production/policies

# ACL stats
curl http://localhost:8100/api/v1/namespaces/acl/stats
```

CLI:
```bash
memos ns-grant production --agent agent-1 --role writer
memos ns-revoke production --agent agent-1
memos ns-policies --namespace production
memos ns-stats
```

## Architecture

```
┌─────────────────────────────────┐
│         SDK / REST API          │
├─────────────────────────────────┤
│     Retrieval Engine            │
│  Embedding + BM25 Hybrid Search │
│  (Qdrant-native when available) │
├──────────┬──────────────────────┤
│  Memory  │  Decay Engine        │
│  Store   │  (forgetting policy) │
├──────────┴──────────────────────┤
│  Sanitizer (injection guard)    │
├─────────────────────────────────┤
│  Storage Backends               │
│  Qdrant | ChromaDB | In-memory  │
├─────────────────────────────────┤
│  Embeddings                     │
│  Ollama (local) | OpenAI | etc  │
└─────────────────────────────────┘
```

## Built from real production code

MemOS is assembled from battle-tested components:

| Component | Source | Tests |
|-----------|--------|-------|
| Memory Store + Lifecycle | MemoryForge | 330+ LOC |
| Consolidation Engine | memory-consolidate | 1800+ LOC |
| Retrieval Pipeline | skill-retrieval | 108 LOC |
| ChromaDB Client | chroma-memory-index | 405 LOC |
| Qdrant Backend + Hybrid Search | v0.7.0 new | 37 tests |
| SSE Streaming Recall | v0.8.0 new | 32 tests |
| Pinecone Backend + Batch Upsert | v0.9.0 new | 18 tests |
| Batch Learn API | v0.9.0 new | 12 tests |
| Security Sanitizer | memory-sanitization-linter | 100% recall |

## Requirements

- Python 3.11+
- **ChromaDB**: `pip install memos[chroma]` (local)
- **Qdrant**: `pip install memos[qdrant]` (local or remote)
- **Embeddings**: Ollama with nomic-embed-text (local) OR OpenAI API (remote)

## Development

```bash
git clone https://github.com/Mars375/memos
cd memos
pip install -e ".[dev]"
pytest
```

## Compaction & Garbage Collection (v0.14.0)

Memos includes a full-lifecycle compaction engine to keep memory stores healthy as they grow:

```python
# Run compaction (dry-run first to preview)
report = memos.compact(dry_run=True)
print(f"Would archive {report['archived']} memories")
print(f"Would merge {report['stale_merged']} stale memories")

# Run for real
report = memos.compact(
    archive_age_days=90,      # Archive memories older than 90 days
    importance_floor=0.3,     # Never archive above this importance
    stale_threshold=0.25,     # Decay score below which a memory is "stale"
    max_per_run=200,          # Cap modifications per run
)
```

Compaction pipeline:
1. **Dedup** — Remove exact/near-duplicates
2. **Archive** — Tag old low-relevance memories as `archived`
3. **Stale merge** — Group and merge semantically similar stale memories
4. **Cluster compact** — Compress large clusters into summaries

CLI:
```bash
memos compact --dry-run           # Preview
memos compact --archive-age 60    # Run with custom thresholds
memos compact --json              # JSON output
```

## Embedding Cache (v0.14.0)

Persistent disk-backed embedding cache avoids recomputing embeddings across sessions:

```python
mem = MemOS(cache_enabled=True)  # Enable persistent cache

# Or with custom settings
mem = MemOS(
    cache_enabled=True,
    cache_path="~/.memos/embeddings.db",
    cache_max_size=50_000,
    cache_ttl=0,  # 0 = no expiry
)

# Check cache performance
stats = mem.cache_stats()  # {'hits': 42, 'misses': 5, 'hit_rate': 0.894, ...}
mem.cache_clear()  # Clear all cached embeddings
```

CLI:
```bash
memos cache-stats          # Show cache statistics
memos cache-stats --clear  # Clear the cache
```

## Rate Limiting (v0.15.0)

MemOS includes per-endpoint rate limiting using a token bucket algorithm:

```python
from memos.api.ratelimit import RateLimiter, EndpointRule, create_rate_limit_middleware

# Custom rules per endpoint
rules = [
    EndpointRule(pattern="/api/v1/learn", max_requests=30, window_seconds=60),
    EndpointRule(pattern="/api/v1/recall", max_requests=120, window_seconds=60),
    EndpointRule(pattern="/api/v1/export", max_requests=10, window_seconds=60),
]
limiter = RateLimiter(default_max=100, rules=rules)

# Apply to your FastAPI app
app.middleware("http")(create_rate_limit_middleware(limiter))
```

Default rules are applied automatically when using `create_fastapi_app()`.
All responses include rate limit headers:
- `X-RateLimit-Limit` — maximum requests in the window
- `X-RateLimit-Remaining` — remaining tokens
- `X-RateLimit-Window` — window in seconds
- `X-RateLimit-Policy` — matched endpoint rule

Check current status: `GET /api/v1/rate-limit/status`

## Performance Benchmarking (v0.15.0)

Measure throughput and latency of core operations:

```bash
# Quick benchmark
memos benchmark

# Custom size with JSON output
memos benchmark --size 5000 --recall-queries 200 --json
```

Programmatic API:

```python
from memos.benchmark import run_benchmark
from memos import MemOS

memos = MemOS(backend="memory")
report = run_benchmark(memos=memos, memories=1000)

# Access results
for result in report.results:
    print(f"{result.operation}: {result.ops_per_second:.0f} ops/s, p50={result.latency_p50_ms:.1f}ms")

# JSON export
import json
print(json.dumps(report.to_dict(), indent=2))
```

Output includes learn, recall, search, stats, and prune benchmarks with
latency percentiles (p50, p95, p99).

## License

MIT
