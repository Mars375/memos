# MemOS — Memory Operating System for AI Agents

> The memory layer every agent should have by default.
> Persistent, structured, self-maintaining. Local-first. Connects to any agent via MCP.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-v0.32.0-purple.svg)](https://github.com/Mars375/memos/releases)
[![Tests](https://img.shields.io/badge/tests-1195_passing-brightgreen.svg)](https://github.com/Mars375/memos/actions)

---

## The problem

LLM agents forget everything between sessions. Solutions today are either too simple (flat vector store), too heavy (full RAG pipeline), or require an external cloud service. None of them give an agent a *brain* — something that learns, organizes, ages, and surfaces the right memory at the right time.

MemOS solves this. It synthesizes the best ideas from current memory research into one coherent system:

| Research insight | Source | What MemOS does with it |
|---|---|---|
| Verbatim storage beats LLM extraction — 96.6% recall accuracy | mempalace | Store content as-is, no summarization on write |
| Community-first wiki reduces context by 71× | Karpathy LLM wiki | Living wiki organized by entity + community, not just tags |
| Confidence labels make knowledge trustworthy | graphify | EXTRACTED / INFERRED / AMBIGUOUS on every KG fact |
| Graph navigation makes memory explorable | Obsidian graph model | D3.js force graph, click-through to entity pages, backlinks |

The result is not a clone of any of these — it's the memory system you'd build if you read all of them and started from scratch.

---

## What it does

```
                         ┌─────────────────────────────────────┐
                         │  MemOS                              │
                         │                                     │
  Agent writes ───────►  │  Memory store   ◄──► KG facts      │
  Agent recalls ◄──────  │  Decay engine        Confidence     │
  Agent browses ───────►  │  Living wiki    ◄──► Backlinks     │
                         │  Hybrid search       Communities    │
                         └─────────────────────────────────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              ▼                        ▼                        ▼
          MCP HTTP              REST API (83 endpoints)      CLI / SDK
    (Claude Code, OpenClaw,     (Docker, self-hosted)      (local use)
     Cursor, any agent)
```

**Memories age.** Importance drifts down over time. Accessed memories are reinforced. Forgotten ones compress. The agent's memory reflects what actually matters.

**Knowledge is structured.** Facts between entities live in a temporal Knowledge Graph — not just embeddings. You can query "what was true about Project X in March?" or "how are Alice and Bob connected?".

**Context is token-efficient.** The living wiki compiles memories into entity pages with backlinks. Agents inject a community index, not a raw dump. 71× fewer tokens than naive retrieval.

---

## Quick start

```bash
pip install memos

memos learn "FastAPI is better than Flask for async workloads" --tags python
memos recall "which web framework should I use?"
memos serve --port 8100   # API + dashboard → http://localhost:8100
```

---

## Connect via MCP

MemOS exposes a universal MCP endpoint compatible with any MCP 2025-03-26 client.

**Claude Code** — `~/.claude.json`:
```json
"mcpServers": {
  "memos": { "type": "http", "url": "http://localhost:8100/mcp" }
}
```

**OpenClaw** — `~/.openclaw/openclaw.json`:
```json
"mcp": {
  "servers": { "memos": { "type": "http", "url": "http://localhost:8100/mcp" } }
}
```

**Any HTTP client** — `POST http://localhost:8100/mcp` (JSON-RPC 2.0)
**Discovery** — `GET http://localhost:8100/.well-known/mcp.json`

MCP tools available: `memory_search`, `memory_save`, `memory_forget`, `memory_stats`,
`memory_wake_up`, `memory_context_for`, `memory_decay`, `memory_reinforce`,
`kg_add_fact`, `kg_query_entity`, `kg_timeline`, `memory_recall_enriched`

**Stdio mode** (Claude Code local):
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
| **ChromaDB** | Local dev, edge devices (Pi5 + Ollama) | `pip install memos[chroma]` |
| **Qdrant** | Production, large datasets | `pip install memos[qdrant]` |
| **Pinecone** | Cloud-native, managed | `pip install memos[pinecone]` |

```bash
# Configure via env — no code changes needed
MEMOS_BACKEND=chroma
MEMOS_EMBED_HOST=http://localhost:11434   # Ollama — bypasses ONNX, ~1s on ARM64
MEMOS_EMBED_MODEL=nomic-embed-text
```

---

## Docker

```bash
docker run -p 8100:8000 \
  -e MEMOS_BACKEND=chroma \
  -e MEMOS_CHROMA_URL=http://chroma:8000 \
  -e MEMOS_EMBED_HOST=http://host:11434 \
  -v memos-data:/root/.memos \
  ghcr.io/mars375/memos:latest
```

Full stack: `git clone https://github.com/Mars375/memos && docker compose up -d`

---

## Import conversations

```bash
memos mine conversations.json          # auto-detects Claude / ChatGPT / Discord / Telegram
memos mine ~/.openclaw/workspace-labs/ --format openclaw
memos mine ~/notes/ --dry-run          # preview without importing
```

---

## Python SDK

```python
from memos import MemOS

mem = MemOS()                          # in-memory, zero deps
mem = MemOS(backend="chroma", embed_host="http://localhost:11434")

mem.learn("User prefers dark mode", tags=["preference"], importance=0.8)
results = mem.recall("UI preferences", top=5)
mem.prune(threshold=0.2)
```

---

## Roadmap to v1.0.0

MemOS is being built toward one goal: **the best agent memory system that exists** — usable by any agent, production-safe, with the kind of recall quality that makes a real difference.

An autonomous cron agent works through open items continuously. Phases are sequential — each one makes the next possible.

---

### Phase 1 — Foundation ✅
*A solid, tested core that works today.*

- [x] Memory store — learn, recall, forget, decay, reinforcement, versioning
- [x] Five backends — memory / JSON / ChromaDB / Qdrant / Pinecone
- [x] Full CLI + REST API (83 endpoints) + Python SDK
- [x] Universal MCP endpoint — stdio + Streamable HTTP 2025-03-26
- [x] Second Brain dashboard — D3.js force-directed graph
- [x] Temporal Knowledge Graph — facts, multi-hop path queries
- [x] Living Wiki — entity pages, backlinks, auto-updated on ingest (Karpathy-inspired)
- [x] Smart Miner — 6 conversation formats, semantic chunking
- [x] Memory decay engine — importance drift + reinforcement
- [x] Hierarchical Palace — wings, rooms, namespace isolation
- [x] Benchmark suite — Recall@K, MRR, NDCG@K, 34 reproducible tests
- [x] Multi-instance conflict resolution — sync with merge strategies

---

### Phase 2 — Memory Quality 🔄
*Make the memory smarter, without LLM extraction on every write.*

The core insight from mempalace: verbatim storage + good retrieval beats complex extraction pipelines. This phase pushes recall quality to match that benchmark.

- [ ] Zero-LLM auto-tagger — classify `decision / preference / milestone / problem` via regex patterns
- [ ] KG confidence labels — tag every fact `EXTRACTED / INFERRED / AMBIGUOUS` (graphify approach)
- [ ] Incremental miner — SHA-256 cache, skip already-mined files
- [ ] Hybrid BM25 + semantic reranking — top-50 semantic → BM25 rerank → −30% noise
- [ ] Community wiki — Leiden graph clustering → community index → god nodes (Karpathy approach)
- [ ] URL ingest — `memos ingest-url <url>` for arXiv, tweets, PDFs, web pages
- [ ] Speaker attribution — per-speaker namespace in conversation miner
- [ ] Memory compression — aggregate heavily decayed memories to free storage

---

### Phase 3 — Unified Knowledge Layer 🔮
*Memories, KG facts, and wiki pages become one queryable brain — not three separate systems.*

The synthesis: take mempalace's storage quality + Karpathy's community navigation + graphify's confidence model + graph-based entity traversal, and expose them through a single interface. An agent should not need to know whether the answer lives in a memory, a KG fact, or a wiki page.

- [ ] **Unified Brain Search** — `POST /api/v1/brain/search` returns memories + wiki hits + KG facts ranked together, entities detected automatically
- [ ] **Entity Detail API** — `GET /api/v1/brain/entity/{name}` → wiki page + top memories + KG facts + graph neighbors + backlinks in one response
- [ ] **Graph ↔ Wiki Bridge** — D3.js node click opens entity detail panel inline; wiki pages auto-link to graph neighbors; backlinks surface related entities

---

### Phase 4 — Production v1 🚀
*What's needed before tagging v1.0.0 and publishing to PyPI.*

- [ ] **API Authentication** — bearer token + per-namespace keys; no-auth mode for local use (backward compat)
- [ ] **Memory Deduplication** — exact-match (SHA-256) + near-duplicate (Jaccard trigrams) on every write; `allow_duplicate=True` escape hatch
- [ ] **Namespace Management API** — REST CRUD for agent isolation; today namespaces exist in CLI only
- [ ] **Advanced Recall Filters** — date range, importance range, tag AND/OR logic in `POST /api/v1/recall`
- [ ] **PyPI release** — `pip install memos-agent`, classifiers, CI publish on `v1.*` tag

> When Phase 4 is complete → `git tag v1.0.0`.

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│  Interfaces                                                    │
│  CLI  ·  REST API (FastAPI)  ·  MCP HTTP  ·  Python SDK       │
├────────────────────────────────────────────────────────────────┤
│  Ingest                                                        │
│  Miner (Claude/ChatGPT/Discord/Telegram/Slack/OpenClaw)       │
│  URL ingestor · Semantic chunking · SHA-256 dedup             │
├────────────────────────────────────────────────────────────────┤
│  Memory Core                                                   │
│  Learn · Recall · Forget · Decay · Reinforce · Versions       │
│  Namespace ACL · Multi-instance sync · Conflict resolution    │
├────────────────────────────────────────────────────────────────┤
│  Knowledge Layer                                               │
│  Knowledge Graph — temporal facts, confidence labels, paths   │
│  Living Wiki — entity pages, community index, backlinks       │
│  Hybrid Retrieval — BM25 + semantic, zero-LLM auto-tagging    │
├────────────────────────────────────────────────────────────────┤
│  Storage                                                       │
│  ChromaDB  ·  Qdrant  ·  Pinecone  ·  JSON  ·  In-memory     │
└────────────────────────────────────────────────────────────────┘
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
