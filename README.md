# MemOS — Memory Operating System for AI Agents

> Persistent, structured, self-organizing memory for any LLM agent.
> Local-first. Framework-agnostic. Connects via MCP to Claude Code, OpenClaw, Cursor, or any HTTP client.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-v0.32.0-purple.svg)](https://github.com/Mars375/memos/releases)
[![Tests](https://img.shields.io/badge/tests-1195_passing-brightgreen.svg)](https://github.com/Mars375/memos/actions)

---

## What it is

MemOS gives any LLM agent a memory layer that behaves like a second brain — memories age and fade, important ones persist, everything is searchable, and the whole thing is visible as a knowledge graph.

```
Agent → learn() / recall() / forget()
           ↓
    ┌──────────────────────────────────────────┐
    │  MemOS                                   │
    │  ├── Memory store  (semantic search)     │
    │  ├── Decay engine  (importance drift)    │
    │  ├── Knowledge Graph (entity facts)      │
    │  ├── Living Wiki  (auto-compiled pages)  │
    │  └── Second Brain (D3.js dashboard)      │
    └──────────────────────────────────────────┘
           ↓
    MCP  ·  REST API  ·  CLI  ·  Python SDK
```

---

## Quick start

```bash
pip install memos

memos learn "FastAPI is better than Flask for async workloads" --tags python
memos recall "which web framework should I use?"
memos serve --port 8100   # API + dashboard at http://localhost:8100
```

---

## Connect via MCP

MemOS exposes a universal MCP endpoint — any agent that speaks MCP can use it.

**Claude Code** — add to `~/.claude.json`:
```json
"mcpServers": {
  "memos": { "type": "http", "url": "http://localhost:8100/mcp" }
}
```

**OpenClaw** — add to `~/.openclaw/openclaw.json`:
```json
"mcp": {
  "servers": {
    "memos": { "type": "http", "url": "http://localhost:8100/mcp" }
  }
}
```

**Cursor / any MCP client** — `POST http://localhost:8100/mcp` (JSON-RPC 2.0)

**Discovery** — `GET http://localhost:8100/.well-known/mcp.json`

**Tools exposed:**

| Tool | What it does |
|------|-------------|
| `memory_search` | Semantic search — `query`, `top_k`, `tags` |
| `memory_save` | Store memory — `content`, `tags`, `importance` |
| `memory_forget` | Delete by `id` or `tag` |
| `memory_stats` | Counts, avg importance, decay candidates |
| `memory_wake_up` | Identity + top memories — inject at session start |
| `memory_context_for` | Optimised context for a specific query |
| `memory_decay` | Apply importance decay (dry-run by default) |
| `memory_reinforce` | Boost a memory's importance |
| `kg_add_fact` | Add temporal triple to Knowledge Graph |
| `kg_query_entity` | All active facts about an entity |
| `kg_timeline` | Chronological fact history for an entity |
| `memory_recall_enriched` | Memories + KG facts in one call |

**Stdio mode** (for local Claude Code integration):
```json
"mcpServers": {
  "memos": { "command": "memos", "args": ["mcp-stdio"] }
}
```

---

## Storage backends

| Backend | Use when | Install |
|---------|----------|---------|
| **Memory** | Tests, single session | `pip install memos` |
| **JSON** | Local persistence, CLI | `pip install memos` |
| **ChromaDB** | Local dev, Pi5 + Ollama embeddings | `pip install memos[chroma]` |
| **Qdrant** | Production, large datasets | `pip install memos[qdrant]` |
| **Pinecone** | Cloud-native, managed | `pip install memos[pinecone]` |

```bash
# env-based config (no code changes)
MEMOS_BACKEND=chroma
MEMOS_EMBED_HOST=http://localhost:11434
MEMOS_EMBED_MODEL=nomic-embed-text
```

---

## Docker (recommended for production)

```bash
docker run -p 8100:8000 \
  -e MEMOS_BACKEND=chroma \
  -e MEMOS_CHROMA_URL=http://chroma:8000 \
  -e MEMOS_EMBED_HOST=http://host:11434 \
  -v memos-data:/root/.memos \
  ghcr.io/mars375/memos:latest
```

Full stack (with ChromaDB + Qdrant):
```bash
git clone https://github.com/Mars375/memos
docker compose up -d
# API on http://localhost:8100
# Dashboard on http://localhost:8100/dashboard
```

---

## Mine conversations

Import Claude, ChatGPT, Discord, Telegram, Slack, OpenClaw conversations directly:

```bash
memos mine conversations.json          # auto-detects format
memos mine ~/.openclaw/workspace-labs/ --format openclaw
memos mine ~/notes/ --dry-run          # preview without importing
```

---

## Python SDK

```python
from memos import MemOS

mem = MemOS()                          # in-memory, no deps
mem = MemOS(backend="chroma", embed_host="http://localhost:11434")

mem.learn("User prefers dark mode", tags=["preference"], importance=0.8)
results = mem.recall("UI preferences", top=5)
mem.prune(threshold=0.2)              # decay-based cleanup
```

---

## Roadmap to v1.0.0

MemOS is being built toward a single coherent goal: **a production-ready second brain for AI agents**, accessible from any agent via MCP, with Obsidian-quality knowledge navigation.

The roadmap is organized in three phases. An autonomous cron agent works through open items continuously.

### Phase 1 — Foundation ✅
*Core memory layer, all interfaces, production infrastructure.*

- [x] Memory store — learn, recall, forget, decay, versioning
- [x] Multi-backend — memory / JSON / ChromaDB / Qdrant / Pinecone
- [x] Full CLI + REST API (83 endpoints) + Python SDK
- [x] MCP server — stdio + universal HTTP (Streamable HTTP 2025-03-26)
- [x] Second Brain dashboard — D3.js force-directed graph
- [x] Knowledge Graph — temporal facts, multi-hop path queries
- [x] Living Wiki — entity pages, backlinks, auto-updated on ingest
- [x] Smart Miner — 6 conversation formats, semantic chunking
- [x] Memory decay & reinforcement engine
- [x] Hierarchical Palace — wings, rooms, namespace isolation
- [x] Benchmark suite — Recall@K, MRR, NDCG@K, 34 reproducible tests
- [x] Memory conflict resolution — multi-instance sync with merge strategies

### Phase 2 — Intelligence 🔄
*Smarter memory: richer metadata, better retrieval, autonomous maintenance.*

- [ ] Auto-tagger — zero-LLM type tags (decision / preference / milestone / problem)
- [ ] KG confidence labels — EXTRACTED / INFERRED / AMBIGUOUS on every fact
- [ ] Incremental miner — SHA-256 cache, skip already-mined files
- [ ] Hybrid retrieval — BM25 + semantic reranking, −30% recall noise
- [ ] Community wiki — Leiden graph clustering, navigable community index
- [ ] URL ingest — arXiv, tweets, PDF, any webpage → `memos ingest-url <url>`
- [ ] Speaker attribution — per-speaker namespace in conversation miner
- [ ] Memory compression — aggregate decayed memories, free storage

### Phase 3 — Second Brain 🔮
*Unified experience: memories, wiki, and graph as one navigable knowledge space.*

- [ ] **Unified Brain Search** — one query spans memories + wiki pages + KG facts
- [ ] **Graph ↔ Wiki Bridge** — click a D3.js node → open its wiki page + KG neighbors
- [ ] **Obsidian Vault Export** — `memos export --format obsidian` → `[[wikilinks]]` vault

### Phase 4 — Production v1 🚀
*What's needed before tagging v1.0.0 and publishing to PyPI.*

- [ ] **API Authentication** — bearer token + per-namespace keys, zero breaking change
- [ ] **Memory Deduplication** — exact + near-duplicate (Jaccard) detection on every write
- [ ] **Namespace Management API** — REST CRUD for agent isolation
- [ ] **Advanced Recall Filters** — date range, importance range, tag AND/OR logic
- [ ] **PyPI release** — `pip install memos-agent`, proper classifiers, CI publish workflow

> When Phase 4 is complete → `git tag v1.0.0`.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Interfaces                                                 │
│  CLI  ·  REST API (FastAPI)  ·  MCP HTTP  ·  Python SDK    │
├─────────────────────────────────────────────────────────────┤
│  Ingest Layer                                               │
│  Miner (Claude / ChatGPT / Discord / Telegram / Slack / OC)│
│  URL ingestor · Smart chunking · SHA-256 dedup             │
├─────────────────────────────────────────────────────────────┤
│  Memory Core                                                │
│  Learn · Recall · Forget · Decay · Reinforce · Prune       │
│  Versioning (time-travel) · Namespace ACL · Sharing        │
├─────────────────────────────────────────────────────────────┤
│  Knowledge Layer                                            │
│  Knowledge Graph (temporal facts, multi-hop paths)         │
│  Living Wiki (entity pages, backlinks, community index)    │
│  Hybrid Retrieval (semantic + BM25)                        │
├─────────────────────────────────────────────────────────────┤
│  Storage Backends                                           │
│  ChromaDB  ·  Qdrant  ·  Pinecone  ·  JSON  ·  In-memory  │
├─────────────────────────────────────────────────────────────┤
│  Presentation                                               │
│  D3.js Second Brain Dashboard · Swagger /docs              │
└─────────────────────────────────────────────────────────────┘
```

---

## Development

```bash
git clone https://github.com/Mars375/memos
cd memos
pip install -e ".[dev]"
pytest -q --tb=no    # 1195 tests
```

---

## License

MIT — [Mars375](https://github.com/Mars375)
