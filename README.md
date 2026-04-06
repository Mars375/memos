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

# Initialize with local ChromaDB
memos init --backend chroma --embed-host http://localhost:11434

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

mem = MemOS(backend="chroma", embed_host="http://localhost:11434")

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

## Architecture

```
┌─────────────────────────────────┐
│         SDK / REST API          │
├─────────────────────────────────┤
│     Retrieval Engine            │
│  Embedding + BM25 Hybrid Search │
├──────────┬──────────────────────┤
│  Memory  │  Decay Engine        │
│  Store   │  (forgetting policy) │
├──────────┴──────────────────────┤
│  Sanitizer (injection guard)    │
├─────────────────────────────────┤
│  Storage Backends               │
│  ChromaDB | Qdrant | In-memory  │
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
| Security Sanitizer | memory-sanitization-linter | 100% recall |

## Requirements

- Python 3.11+
- ChromaDB (local) or Qdrant (remote)
- Ollama with nomic-embed-text (local) OR OpenAI API (remote)

## Development

```bash
git clone https://github.com/Mars375/memos
cd memos
pip install -e ".[dev]"
pytest
```

## License

MIT
