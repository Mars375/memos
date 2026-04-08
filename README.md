# MemOS — Memory Operating System for LLM Agents

> A standalone memory layer that gives any LLM agent persistent, smart, local-first memory.
> Framework-agnostic. 5 minutes to start. 901 tests.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-v0.32.0-purple.svg)](https://github.com/Mars375/memos/releases)

---

## What it does

| Capability | Description |
|------------|-------------|
| **Learn** | Store decisions, preferences, patterns with importance scores |
| **Recall** | Semantic + BM25 hybrid search — retrieve what's actually relevant |
| **Forget** | Decay engine — old memories fade, important ones persist |
| **Mine** | Import Claude, ChatGPT, Discord, Telegram, Slack, OpenClaw conversations |
| **Wiki** | Compile memories into markdown pages per tag for token-efficient recall |
| **Graph** | D3.js second brain dashboard — Obsidian-style knowledge visualization |
| **MCP** | JSON-RPC 2.0 bridge — connect from Claude Code, Cursor, OpenClaw |
| **Sanitize** | Built-in prompt injection guard on every memory write |
| **Version** | Full time-travel — diff, rollback, recall-at any past timestamp |

---

## Quick start

```bash
pip install memos

# Store a memory
memos learn "FastAPI is better than Flask for async workloads" --tags python,api

# Recall what's relevant
memos recall "which web framework should I use?"

# See all memories
memos stats

# Start the API server + dashboard
memos serve --port 8100
# → open http://localhost:8100/dashboard
```

---

## Python API

```python
from memos import MemOS

mem = MemOS()  # in-memory (default, no dependencies)

# Store
mem.learn("User prefers concise responses", tags=["preference"], importance=0.9)

# Recall
results = mem.recall("how should I respond?", top=5)
for r in results:
    print(f"[{r.score:.2f}] {r.item.content}")

# Bulk import
mem.batch_learn([
    {"content": "Docker on Raspberry Pi 5", "tags": ["infra"]},
    {"content": "Dark mode enabled", "tags": ["ui"]},
])

# Forget
mem.prune(threshold=0.3)     # decay-based cleanup
mem.forget("memory-id")       # delete by id
mem.delete_tag("old-tag")     # remove a tag from all memories

# Stats
stats = mem.stats()
# MemoryStats(total_memories=142, avg_relevance=0.71, decay_candidates=8)
```

---

## Storage Backends

| Backend | Best for | Install |
|---------|----------|---------|
| **In-memory** | Testing, single-session | `pip install memos` |
| **JSON file** | Local persistence, CLI use | `pip install memos` |
| **ChromaDB** | Local dev, small-medium datasets | `pip install memos[chroma]` |
| **Qdrant** | Production, large datasets, hybrid search | `pip install memos[qdrant]` |
| **Pinecone** | Cloud-native, serverless, managed | `pip install memos[pinecone]` |

```python
# JSON persistence (default for CLI)
mem = MemOS(backend="json", persist_path="~/.memos/store.json")

# ChromaDB
mem = MemOS(backend="chroma", embed_host="http://localhost:11434")

# Qdrant (local file or remote)
mem = MemOS(backend="qdrant", qdrant_path="/data/memos-qdrant")
mem = MemOS(backend="qdrant", qdrant_host="qdrant.example.com", qdrant_port=6333)

# Pinecone
mem = MemOS(backend="pinecone", pinecone_api_key="pc-key-...", pinecone_index_name="agent-memories")
```

---

## MCP Server — Agent Bridge (v0.30.0)

Connect MemOS to Claude Code, Cursor, OpenClaw, or any MCP-compatible client.

**HTTP (JSON-RPC 2.0)**
```bash
memos mcp-serve --port 8200
```

**Stdio (Claude Code / Cursor direct integration)**
```bash
memos mcp-stdio
```

**Add to Claude Code** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "memos": {
      "command": "memos",
      "args": ["mcp-stdio"]
    }
  }
}
```

**4 MCP tools exposed:**

| Tool | Description |
|------|-------------|
| `memory_search` | Semantic search — `query`, `top_k`, `tags` |
| `memory_save` | Store a new memory — `content`, `tags`, `importance` |
| `memory_forget` | Delete by `id` or `tag` |
| `memory_stats` | Total memories, tags, avg relevance, decay candidates |

---

## Smart Miner — Import from Anywhere (v0.31.0+)

Mine conversations and files with paragraph-aware chunking, SHA-256 deduplication, and auto room detection.

```bash
# Auto-detect format
memos mine ~/my-notes/
memos mine conversations.json            # auto-detects Claude/ChatGPT/Discord/Telegram
memos mine ~/.openclaw/workspace-labs/memory/ --format openclaw

# Force format
memos mine export.json --format claude
memos mine result.json --format telegram
memos mine discord.json --format discord
memos mine channel.jsonl --format slack

# Options
memos mine ~/notes/ --dry-run --tags project-x --chunk-size 600
```

**Python API:**
```python
from memos.ingest.miner import Miner

miner = Miner(memos, chunk_size=800, chunk_overlap=100, dry_run=False)

result = miner.mine_claude_export("~/.claude/projects/.../export.json")
result = miner.mine_chatgpt_export("~/Downloads/conversations.json")
result = miner.mine_discord_export("discord_export.json")
result = miner.mine_telegram_export("result.json")    # Telegram Desktop export
result = miner.mine_slack_export("general.jsonl")
result = miner.mine_openclaw("~/.openclaw/workspace-labs/memory/")
result = miner.mine_auto("anything/")                 # auto-detect

print(result)
# MineResult(imported=127, dupes=12, empty=3, errors=0)
```

**Chunking strategy (MemPalace-inspired):**
- 800-char chunks with 100-char overlap
- Never cuts mid-paragraph — respects semantic boundaries
- SHA-256 dedup — rerun on same files without creating duplicates
- Room auto-detection: path → filename → keyword frequency (12 domains)

---

## Wiki Compile Mode (v0.30.0)

Consolidate memories into per-tag markdown pages — efficient context injection.

```bash
memos wiki-compile              # compile all tags
memos wiki-compile --tags python,devops  # specific tags only
memos wiki-list                 # list pages with stats
memos wiki-read python          # print a compiled page
```

```python
from memos.wiki import WikiEngine

wiki = WikiEngine(memos, wiki_dir="~/.memos/wiki")
pages = wiki.compile()          # returns list of WikiPage
content = wiki.read("python")   # markdown string, ready to inject
```

**Output format:**
```markdown
# python

> Compiled from 12 memories · 2026-04-08 12:00

## ★★★★ · tags: api, dev

FastAPI is a modern async Python web framework with excellent performance.

## ★★★ · tags: async

Use async/await for all IO-bound operations — it's not optional in production.
```

---

## Second Brain Dashboard (v0.29.0)

Obsidian-style knowledge graph — visual exploration of your memory space.

```bash
memos serve --port 8100
# open http://localhost:8100/dashboard
# or http://localhost:8100/  (same)
```

- **D3.js force-directed graph** — nodes colored by tag, size = importance
- **Sidebar** — stats chips, tag filters, search, detail panel, add memory form
- **Click node** → full content + tags + date
- **Zoom/pan** — native D3 interactions
- **Auto-refresh** every 60s

**Graph API:**
```bash
curl http://localhost:8100/api/v1/graph
# {"nodes": [...], "edges": [...], "meta": {"total_nodes": 15, "total_edges": 32}}
```

---

## REST API

```
POST   /api/v1/learn              Store a memory
POST   /api/v1/learn/batch        Bulk store
POST   /api/v1/recall             Semantic search
GET    /api/v1/recall/stream      SSE streaming recall
GET    /api/v1/search             Keyword search
GET    /api/v1/stats              Memory statistics
GET    /api/v1/graph              Knowledge graph (nodes + edges)
GET    /api/v1/tags               List all tags
POST   /api/v1/tags/rename        Rename a tag
DELETE /api/v1/tags/{tag}         Delete tag from all memories
DELETE /api/v1/memory/{id}        Delete a memory
POST   /api/v1/prune              Decay-based cleanup
POST   /api/v1/consolidate        Dedup + merge similar memories
GET    /api/v1/export/parquet     Download .parquet backup
GET    /api/v1/events/stream      Live SSE event stream
GET    /dashboard                 Second Brain UI
GET    /health                    Health check
```

Full versioning, namespace ACL, sharing, and rate-limit endpoints also available — see [CHANGELOG](CHANGELOG.md).

---

## Memory Versioning & Time-Travel (v0.11.0+)

Every write is automatically versioned. Query the past, diff changes, roll back.

```python
# Time-travel recall
results = mem.recall_at("user preferences", time.time() - 3600)

# Snapshot all memories at a past point
snapshot = mem.snapshot_at(time.time() - 86400)  # yesterday

# Diff and rollback
history = mem.history("memory-id")
diff = mem.diff("memory-id", version_a=1, version_b=2)
restored = mem.rollback("memory-id", version_number=1)
```

```bash
memos history <id>
memos diff <id> --latest
memos rollback <id> --version 1 --yes
memos snapshot-at 1d           # 1 day ago
memos recall-at "query" --at 2h
memos version-stats
memos version-gc --keep-latest 3
```

---

## Namespace Access Control (v0.13.0+)

RBAC for multi-agent memory isolation:

```python
mem.grant_namespace_access("agent-alpha", "production", "owner")
mem.grant_namespace_access("agent-beta", "production", "writer")
mem.set_agent_id("agent-beta")
mem.namespace = "production"
mem.learn("scoped to production namespace")
```

---

## Multi-Agent Memory Sharing (v0.16.0+)

Agents can share memories across instances via cryptographically-signed envelopes:

```python
# Offer a memory to another agent
req = mem.offer_share("memory-id", target_agent="agent-beta", permission="read")

# Export/import memory packages
envelope = mem.export_shared(req.id)
# → transfer envelope to agent-beta
imported = mem.import_shared(envelope)
```

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  Interfaces                                          │
│  CLI  ·  REST API  ·  MCP Server  ·  Python SDK     │
├──────────────────────────────────────────────────────┤
│  Ingest Layer                                        │
│  Miner (Claude/ChatGPT/Discord/Telegram/Slack/OC)   │
│  Smart chunking · SHA-256 dedup · room detection    │
├──────────────────────────────────────────────────────┤
│  Memory Core                                        │
│  Learn · Recall · Forget · Prune · Stats            │
│  Versioning · Namespace ACL · Sharing               │
├──────────────────────────────────────────────────────┤
│  Retrieval Engine                                   │
│  Embedding + BM25 Hybrid Search                     │
│  Decay Engine · Sanitizer (injection guard)         │
├──────────────────────────────────────────────────────┤
│  Storage Backends                                   │
│  Qdrant  ·  ChromaDB  ·  Pinecone  ·  JSON  ·  RAM  │
├──────────────────────────────────────────────────────┤
│  Wiki Engine  ·  Knowledge Graph API  ·  Dashboard  │
└──────────────────────────────────────────────────────┘
```

---

## Changelog (major releases)

| Version | Feature |
|---------|---------|
| v0.32.0 | Discord, Telegram, OpenClaw importers |
| v0.31.0 | Smart miner — paragraph-aware chunking, SHA-256 dedup, 6 formats |
| v0.30.0 | MCP server · Wiki compile · Markdown migration |
| v0.29.0 | Second Brain Dashboard (D3.js, Obsidian-style) |
| v0.28.0 | Tags delete |
| v0.27.0 | Tags rename |
| v0.26.0 | Tags list |
| v0.24.0 | stdin pipe support |
| v0.22.0 | JSON output + relevance feedback |
| v0.21.0 | Recall CLI filters (--tags, --after, --before) |
| v0.18.0 | Persistent CLI storage (JSON backend) |
| v0.16.0 | Multi-agent memory sharing |
| v0.15.0 | Rate limiting + benchmarks |
| v0.14.0 | Memory compaction + embedding cache |
| v0.13.0 | Persistent versioning (SQLite) + namespace ACL |
| v0.12.0 | CLI versioning commands + HTTP versioning API |
| v0.11.0 | Memory versioning & time-travel |
| v0.10.0 | Async consolidation + Parquet export/import |
| v0.9.0  | Batch learn + Pinecone backend |
| v0.8.0  | SSE streaming recall |
| v0.7.0  | Qdrant backend + hybrid BM25 search |
| v0.6.0  | Initial release |

---

## Development

```bash
git clone https://github.com/Mars375/memos
cd memos
pip install -e ".[dev]"
pytest              # 901 tests
pytest -q --tb=no  # quick run
```

---

## License

MIT — [Mars375](https://github.com/Mars375)
