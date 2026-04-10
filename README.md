# MemOS

[![PyPI](https://img.shields.io/pypi/v/memos-agent.svg)](https://pypi.org/project/memos-agent/)
[![Docker](https://github.com/Mars375/memos/actions/workflows/docker.yml/badge.svg)](https://github.com/Mars375/memos/actions/workflows/docker.yml)
[![Coverage](https://img.shields.io/badge/coverage-pytest--cov-brightgreen.svg)](https://github.com/Mars375/memos)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Persistent, local-first memory for LLM agents.

MemOS gives agents one place to write, search, structure, and reuse memory through a Python SDK, CLI, REST API, dashboard, and MCP server.

> PyPI package: `memos-agent`
> Python import: `memos`
> CLI command: `memos`

## Why MemOS

- Persistent memory with in-memory, JSON, ChromaDB, and Qdrant backends
- MCP bridge for OpenClaw, Claude Code, Cursor, and other MCP clients
- Temporal knowledge graph, wiki views, unified brain search, and analytics
- Local-first deployment, from zero-dependency dev mode to Docker and vector backends
- Agent-friendly CLI and REST API, good for both direct use and automation

## Installation

Base install:

```bash
pip install memos-agent
```

With API server support:

```bash
pip install "memos-agent[server]"
```

With semantic/vector backends:

```bash
pip install "memos-agent[chroma,server]"
pip install "memos-agent[qdrant,server]"
pip install "memos-agent[parquet,server]"
```

For development:

```bash
pip install -e ".[dev,server]"
```

## Quick start

Three commands are enough to see the full loop:

```bash
memos learn "Alice works on the billing service" --tags people,billing
memos recall "who works on billing?"
memos serve --port 8100
```

Then open:

- Dashboard: <http://localhost:8100/dashboard>
- Swagger / OpenAPI docs: <http://localhost:8100/docs>
- MCP discovery: <http://localhost:8100/.well-known/mcp.json>

## Python SDK

```python
from memos import MemOS

mem = MemOS(backend="json", persist_path="~/.memos/store.json")

mem.learn(
    "User prefers concise release notes",
    tags=["preference", "writing"],
    importance=0.8,
)

results = mem.recall("how should I write release notes?", top=5)
for result in results:
    print(result.item.content, result.score)
```

## MCP configuration

MemOS can run over HTTP or stdio.

### OpenClaw

Add to `~/.openclaw/openclaw.json`:

```json
{
  "mcp": {
    "servers": {
      "memos": {
        "type": "http",
        "url": "http://localhost:8100/mcp"
      }
    }
  }
}
```

### Claude Code

HTTP mode in `~/.claude.json`:

```json
{
  "mcpServers": {
    "memos": {
      "type": "http",
      "url": "http://localhost:8100/mcp"
    }
  }
}
```

Stdio mode:

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

### Cursor

Project-local config in `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "memos": {
      "url": "http://localhost:8100/mcp"
    }
  }
}
```

## Backends

| Backend | Best for | Notes |
| --- | --- | --- |
| `memory` | Tests, demos, throwaway sessions | Zero persistence, zero setup |
| `json` | Local-first single-user memory | Simple file storage, easy backups |
| `chroma` | Better semantic recall on one machine | Pairs well with Ollama embeddings |
| `qdrant` | Larger or shared vector deployments | Good when you want a dedicated vector DB |

Common environment variables:

```bash
MEMOS_BACKEND=json
MEMOS_NAMESPACE=default
MEMOS_PERSIST_PATH=~/.memos/store.json
MEMOS_EMBED_HOST=http://localhost:11434
MEMOS_EMBED_MODEL=nomic-embed-text
MEMOS_QDRANT_HOST=localhost
MEMOS_QDRANT_PORT=6333
```

## Docker

JSON backend, single container:

```bash
docker run --rm \
  -p 8100:8000 \
  -e MEMOS_BACKEND=json \
  -e MEMOS_PERSIST_PATH=/data/store.json \
  -e MEMOS_NAMESPACE=default \
  -v "$PWD/.memos:/data" \
  ghcr.io/mars375/memos:latest
```

Full stack from the repo:

```bash
git clone https://github.com/Mars375/memos
cd memos
docker compose up -d
```

## Core surfaces

### CLI

A few useful commands:

```bash
memos learn "..."
memos recall "..." --tags project-x --min-importance 0.5
memos brain-search "what do we know about auth?"
memos extract-kg "Alice deployed API to production"
memos namespaces list
memos mcp-serve --port 8100
```

### REST API

Key endpoints:

- `POST /api/v1/learn`
- `POST /api/v1/recall`
- `GET /api/v1/memories`
- `POST /api/v1/brain/search`
- `POST /api/v1/dedup/check`
- `GET /api/v1/auth/whoami`
- `GET /api/v1/namespaces`
- `POST /mcp`

Interactive reference is always available at `/docs` when the server is running.

## Feature snapshot

MemOS includes:

- temporal knowledge graph and graph traversal
- speaker-aware conversation mining
- URL ingest for web, PDFs, arXiv, and X links
- auto KG extraction on write
- memory compression and near-duplicate detection
- namespace management and bearer auth
- advanced recall filters and unified brain search
- living wiki and Markdown export

## Development

Run the test suite:

```bash
python -m pytest -x -q
```

Build distributions locally:

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for releases from `v0.29.0` through `v1.0.0`.
