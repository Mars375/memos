# MemOS — Memory Operating System for LLM Agents

## What This Is

MemOS (`memos-agent` on PyPI) is a local-first memory operating system for LLM agents.
It provides persistent, smart memory with hybrid retrieval, a temporal knowledge graph, a living wiki, and a second-brain dashboard — all accessible via REST API, MCP server, CLI, or Python SDK.
Built for developers running agents on their own infrastructure (homelab, cloud VPS, Docker).

## Core Value

An agent that remembers everything relevant without token bloat — recall must be fast, contextual, and explainable.

## Current State

**Shipped: v2.2.0** (2026-04-15)
- 3 phases: Maintenance ✅, Dashboard P1 ✅, Documentation Polish ✅
- 17 requirements verified, 1,738 tests passing, 0 ruff errors
- Cluster-colored force-graph with depth slider, local graph, rich tooltips
- Golden path README + recall API guide + Claude Code & OpenClaw integration examples
- Docker images pinned, CI on 3.11/3.12/3.13, log limits on all services
- See [milestone archive](milestones/v2.2.0-ROADMAP.md) for full details

## Requirements

### Validated (shipped through v2.2.0)

- ✓ Core memory store (learn, recall, forget, prune, reinforce, decay) — v1.0
- ✓ 6 storage backends (memory, JSON, ChromaDB, Qdrant, Pinecone, local sentence-transformers) — v1.0
- ✓ Hybrid retrieval (BM25 + semantic) with score explainability — v1.0
- ✓ Deduplication (SHA-256 exact + Jaccard near-duplicate) — v1.0
- ✓ Versioning & time-travel (history, diff, rollback, snapshot-at) — v1.0
- ✓ Memory compression + compaction engine — v1.0
- ✓ TTL, ACL (RBAC), multi-agent sharing, conflict resolution — v1.0
- ✓ Temporal knowledge graph (SQLite, typed edges, confidence labels) — v1.0 / v2.0
- ✓ Living wiki (update/read/search/lint) + graph-wiki bridge — v2.0
- ✓ Unified brain search (memories + wiki + KG) — v2.0
- ✓ Mine from 7 chat formats + URL ingest + speaker ownership — v1.0 / v2.0
- ✓ Portable markdown export + Parquet export/import — v1.0
- ✓ MCP server (HTTP + stdio, 12 tools) — v1.0
- ✓ REST API (20+ endpoints, SSE streaming, auth, rate limiting) — v1.0
- ✓ CLI (30+ commands) + Python SDK — v1.0
- ✓ Second brain dashboard (Canvas force-graph, clustering, depth, hover) — v2.2.0
- ✓ Docker (all-in-one + multi-profile compose) + CI (3.11/3.12/3.13) — v2.2.0
- ✓ 1,738 tests passing, 0 ruff errors — v2.2.0
- ✓ Golden path README + recall API guide + integration examples — v2.2.0

### Next Milestone Goals (v3.x candidates)

- Progressive `core.py` decomposition (1909L god class → focused modules)
- CLI `_parser.py` modularisation (1171L argparse monolith)
- `wiki_living.py` split (1080L — rendering / logic / data)
- `mcp_server.py` expansion (851L → 20+ tools)
- Temporal intelligence (validity windows, retroactive queries, contradiction detection)
- Harden importers & mining flows

### Out of Scope

- Refactor complet de `core.py` en une seule phase — too risky; progressive refactor
- Federated memory / hosted service — v4+
- OAuth / SSO — Bearer + namespace keys sufficient
- Mobile / desktop client — web-first
- Fine-tuned embedding model — pre-benchmarks LongMemEval

## Context

- **Stack** : Python 3.11+, FastAPI, Uvicorn, sentence-transformers, SQLite (KG/Palace), ChromaDB/Qdrant/Pinecone optionnels
- **Infrastructure** : homelab Raspberry Pi 5 (orion-cortex), Docker, NFS storage, Tailscale
- **Déployé** : `ghcr.io/mars375/memos:latest` — image all-in-one `docker compose up memos-standalone`
- **Tests** : 1,738 tests (pytest), CI GitHub Actions — test matrix 3.11/3.12/3.13, lint ruff, docker multi-arch (amd64+arm64)
- **Codebase map** : `.planning/codebase/` (créé le 13 avril 2026)

## Constraints

- **Tech stack** : Python 3.11+ uniquement — pas de dépendances JS dans le core
- **Compatibilité** : Backward compatible API REST — pas de breaking changes sans bump major
- **Storage** : Volumes Docker sur NFS uniquement (pas SD card) — règle homelab
- **Sécurité** : Aucun secret dans les commits, logs limités (10m/3 fichiers max)
- **Qualité** : Chaque feature = au moins un test. La CI doit passer avant merge.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Canvas force-graph (vs D3 SVG) | Performance sur grands graphes, interactions fluides | ✓ Good |
| Dashboard modulaire (vs monolithique) | Maintenabilité, issues #39/#40 | ✓ Good |
| All-in-one Docker image | Zero-dependency deploy pour les users | ✓ Good |
| JSON backend par défaut | Zéro dépendance externe pour quick start | ✓ Good |
| sentence-transformers local | Pas d'API key requise, fonctionne offline | ✓ Good |
| MCP HTTP + stdio | Compatibilité max (Claude Code, n8n, agents custom) | ✓ Good |
| Connected components (vs Leiden) | Zero-dependency, deterministic, sufficient for current scale | ✓ Good |
| DOM-only tooltip | Zero innerHTML with user data | ✓ Good |

## Evolution

This document evolves at phase transitions and milestone boundaries.

---
*Last updated: 2026-04-15 after v2.2.0 milestone archival*
