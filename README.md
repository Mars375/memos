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
POST /api/v1/learn     {content, tags, importance?}
POST /api/v1/recall    {query, top?, filter?}
POST /api/v1/prune     {threshold, max_age?}
GET  /api/v1/stats
GET  /api/v1/search    {q, limit?}
DELETE /api/v1/memory/{id}
```

## Storage Backends

| Backend | Best for | Install | Config |
|---------|----------|---------|--------|
| **In-memory** | Testing, single-session | `pip install memos` | `backend="memory"` |
| **ChromaDB** | Local development, small-medium datasets | `pip install memos[chroma]` | `backend="chroma"` |
| **Qdrant** | Production, large datasets, hybrid search | `pip install memos[qdrant]` | `backend="qdrant"` |

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

## License

MIT
