# MemOS — Memory Operating System for AI Agents

> Persistent, structured, self-maintaining memory for any LLM agent.
> Local-first. Framework-agnostic. Connects via MCP to Claude Code, OpenClaw, Cursor, or any HTTP client.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-v0.38.0-purple.svg)](https://github.com/Mars375/memos/releases)
[![Tests](https://img.shields.io/badge/tests-1345_passing-brightgreen.svg)](https://github.com/Mars375/memos/actions)

---

## Installation

```bash
pip install memos
```

With local semantic recall (no external services):
```bash
pip install "memos[local]"    # sentence-transformers, backend="local"
```

With vector backend (recommended for production):
```bash
pip install "memos[chroma]"   # ChromaDB + Ollama embeddings
pip install "memos[qdrant]"   # Qdrant
pip install "memos[all]"      # all backends
```

---

## Quick start

```bash
# Store a memory
memos learn "FastAPI is better than Flask for async workloads" --tags python,backend

# Search semantically
memos recall "which web framework should I use?"

# Start the REST API + dashboard
memos serve --port 8100
# → http://localhost:8100/dashboard
```

---

## Python SDK

```python
from memos import MemOS

# In-memory (zero dependencies, great for testing)
mem = MemOS()

# JSON persistence
mem = MemOS(backend="json", persist_path="~/.memos/store.json")

# Local-first semantic recall, no Ollama/Chroma required
mem = MemOS(backend="local", persist_path="~/.memos/store.json")

# ChromaDB with local Ollama embeddings
mem = MemOS(backend="chroma", embed_host="http://localhost:11434")

# Qdrant
mem = MemOS(backend="qdrant", qdrant_path="/data/memos")

# Store
mem.learn("User prefers dark mode", tags=["preference", "ui"], importance=0.8)

# Recall
results = mem.recall("what does the user like?", top=5)
for r in results:
    print(f"[{r.score:.2f}] {r.item.content}")

# Forget
mem.forget("memory-id")           # by id
mem.delete_tag("old-project")     # all memories with this tag
mem.prune(threshold=0.2)          # decay-based cleanup

# Stats
s = mem.stats()
# MemoryStats(total_memories=142, avg_relevance=0.71, decay_candidates=8)
```

---

## MCP — connect any agent

MemOS exposes a universal MCP endpoint. Any agent that speaks MCP can use it without any code changes.

### HTTP (recommended)

**Claude Code** — add to `~/.claude.json`:
```json
{
  "mcpServers": {
    "memos": { "type": "http", "url": "http://localhost:8100/mcp" }
  }
}
```

**OpenClaw** — add to `~/.openclaw/openclaw.json`:
```json
{
  "mcp": {
    "servers": {
      "memos": { "type": "http", "url": "http://localhost:8100/mcp" }
    }
  }
}
```

**Any MCP client** — `POST http://localhost:8100/mcp` with JSON-RPC 2.0 body.

Discovery: `GET http://localhost:8100/.well-known/mcp.json`

### Stdio (Claude Code local)

```json
{
  "mcpServers": {
    "memos": { "command": "memos", "args": ["mcp-stdio"] }
  }
}
```

Or run standalone: `memos mcp-serve --port 8200`

### Available MCP tools

| Tool | Description |
|------|-------------|
| `memory_search` | Semantic search — `query`, `top_k`, `tags` |
| `memory_save` | Store a memory — `content`, `tags`, `importance` |
| `memory_forget` | Delete by `id` or `tag` |
| `memory_stats` | Counts, avg importance, decay candidates |
| `memory_wake_up` | Identity + top memories ready to inject at session start |
| `memory_context_for` | Context optimised for a specific query |
| `memory_decay` | Run decay cycle (dry-run by default) |
| `memory_reinforce` | Boost a memory's importance score |
| `kg_add_fact` | Add a temporal triple to the Knowledge Graph |
| `kg_query_entity` | All active facts for an entity |
| `kg_timeline` | Chronological fact history for an entity |
| `memory_recall_enriched` | Memories + KG facts in one call |

---

## REST API

Start the server: `memos serve --port 8100`

Interactive docs: `http://localhost:8100/docs`

```
POST   /api/v1/learn                Store a memory
POST   /api/v1/learn/batch          Bulk store
POST   /api/v1/recall               Semantic search
GET    /api/v1/recall/stream        SSE streaming recall
GET    /api/v1/search               Keyword search
GET    /api/v1/stats                Memory statistics
GET    /api/v1/tags                 List all tags
DELETE /api/v1/tags/{tag}           Delete tag from all memories
DELETE /api/v1/memory/{id}          Delete a memory
POST   /api/v1/prune                Decay-based cleanup
GET    /api/v1/graph                Knowledge graph (nodes + edges for D3.js)
GET    /api/v1/export/parquet       Download .parquet backup
POST   /mcp                         MCP JSON-RPC endpoint
GET    /.well-known/mcp.json        MCP discovery
GET    /dashboard                   Second Brain UI
GET    /health                      Health check
```

---

## Configuration

All options can be set via environment variables:

```bash
MEMOS_BACKEND=chroma              # memory | json | chroma | qdrant | pinecone
MEMOS_NAMESPACE=default           # memory namespace (one per agent)
MEMOS_PERSIST_PATH=~/.memos/      # path for json/sqlite storage

# ChromaDB
MEMOS_CHROMA_URL=http://chroma:8000
MEMOS_EMBED_HOST=http://localhost:11434   # Ollama — bypasses server-side ONNX
MEMOS_EMBED_MODEL=nomic-embed-text

# Qdrant
MEMOS_QDRANT_HOST=localhost
MEMOS_QDRANT_PORT=6333

# Pinecone
MEMOS_PINECONE_API_KEY=pc-...
MEMOS_PINECONE_INDEX=agent-memories
```

---

## Docker

Single container (JSON backend, no dependencies):
```bash
docker run -p 8100:8000 \
  -e MEMOS_BACKEND=json \
  -v memos-data:/root/.memos \
  ghcr.io/mars375/memos:latest
```

Full stack with ChromaDB + Ollama embeddings:
```bash
git clone https://github.com/Mars375/memos
cd memos
docker compose up -d
```

Services started:
- `http://localhost:8100` — MemOS API + dashboard (ChromaDB backend)
- `http://localhost:8000` — MemOS (Qdrant backend, secondary)
- `http://localhost:8001` — ChromaDB
- `http://localhost:6333` — Qdrant

---

## Import conversations

Mine your existing conversations into MemOS:

```bash
# Auto-detect format
memos mine conversations.json

# Supported formats
memos mine export.json      --format claude      # Claude Projects export
memos mine conversations.json --format chatgpt   # ChatGPT export
memos mine messages.json    --format discord
memos mine result.json      --format telegram    # Telegram Desktop export
memos mine channel.jsonl    --format slack
memos mine ~/.openclaw/workspace-labs/ --format openclaw

# Options
memos mine ~/notes/ --dry-run --tags project-x --chunk-size 600 --namespace agent-alice
```

Python API:
```python
from memos.ingest.miner import Miner

miner = Miner(mem, chunk_size=800, chunk_overlap=100)
result = miner.mine_auto("conversations/")   # auto-detect
result = miner.mine_claude_export("~/.claude/projects/.../export.json")
# MineResult(imported=127, dupes=12, empty=3, errors=0)
```

---

## Knowledge Graph

Store and query temporal facts between entities:

```bash
memos kg-add "Alice" "works-at" "Acme Corp" --from 2024-01-01
memos kg-query Alice
memos kg-path Alice Carol --max-hops 3
memos kg-neighbors Alice --depth 2
memos kg-timeline Alice
```

```python
from memos.knowledge_graph import KnowledgeGraph

kg = KnowledgeGraph()
kg.add_fact("Alice", "works-at", "Acme Corp", valid_from="2024-01-01")
facts = kg.query("Alice")
paths = kg.find_paths("Alice", "Carol", max_hops=3)
```

---

## Living Wiki

Compile memories into entity-based markdown pages with backlinks:

```bash
memos wiki-living update          # scan memories, create/update entity pages
memos wiki-living read Alice      # print Alice's page
memos wiki-living search "python" # search across all pages
memos wiki-living lint            # find orphans, contradictions, empty pages

memos wiki-compile --tags python  # static tag-based pages (simpler alternative)
```

---

## Memory decay

Memories age automatically. Important ones persist; stale ones fade.

```bash
memos decay --dry-run      # preview what would decay
memos decay --apply        # apply decay
memos prune --threshold 0.1  # delete memories below importance threshold
```

```python
mem.prune(threshold=0.15)
report = mem._decay.run_decay(items, dry_run=True)
# DecayReport(total=142, decayed=23, avg_importance_before=0.51, after=0.47)
```

---

## Versioning and time-travel

Every write is versioned. Query the past, diff changes, roll back.

```bash
memos history <memory-id>
memos diff <memory-id> --latest
memos rollback <memory-id> --version 1 --yes
memos recall-at "user preferences" --at 2d    # as of 2 days ago
memos snapshot-at 1w                          # all memories 1 week ago
```

---

## Multi-namespace (multi-agent)

Each agent gets its own isolated namespace:

```bash
memos --namespace agent-alice learn "Alice's memory"
memos --namespace agent-bob learn "Bob's memory"
memos --namespace agent-alice recall "what do I know?"
```

```python
mem_alice = MemOS(backend="chroma", namespace="agent-alice")
mem_bob   = MemOS(backend="chroma", namespace="agent-bob")
```

---

## Development

```bash
git clone https://github.com/Mars375/memos
cd memos
pip install -e ".[dev]"
pytest -q --tb=no          # 1402 tests
pytest tests/test_core.py  # specific module
```

---

## Architecture

MemOS is built around three core layers (see [PRD.md](PRD.md)):

- **Capture** — Mine conversations and events into structured memory units via the CLI (`memos mine`), SDK, or MCP.
- **Engine** — Storage, recall, decay, reinforcement, versioning, and knowledge graph. Pluggable backends (in-memory, JSON, ChromaDB, Qdrant, Pinecone).
- **Knowledge Surface** — Living wiki, graph view, and context packs (`wake_up`, `context_for`, `recall_enriched`) that serve the right context at the right time.

See [ROADMAP.md](ROADMAP.md) for planned features and current status.

---

## License

MIT — [Mars375](https://github.com/Mars375)
