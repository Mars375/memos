# MemOS — Memory Operating System for LLM Agents

## What This Is

MemOS (`memos-agent` on PyPI) is a local-first memory operating system for LLM agents.
It provides persistent, smart memory with hybrid retrieval, a temporal knowledge graph, a living wiki, and a second-brain dashboard — all accessible via REST API, MCP server, CLI, or Python SDK.
Built for developers running agents on their own infrastructure (homelab, cloud VPS, Docker).

## Core Value

An agent that remembers everything relevant without token bloat — recall must be fast, contextual, and explainable.

## Requirements

### Validated

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
- ✓ Second brain dashboard (Canvas force-graph, KG edges, Wiki view, Palace view, time-travel slider) — v2.0
- ✓ Docker (all-in-one image + multi-profile compose) + CI (tests + PyPI publish) — v1.0 / v2.0
- ✓ 1534 tests passing — v2.0

### Active

#### Tier 1 — Maintenance (priorité bloquante)
- [ ] Synchroniser version `pyproject.toml` (1.0.0) ↔ `__init__.py` (2.2.0) — bloque release PyPI propre
- [ ] Épingler images Docker tiers (`chromadb/chroma:latest`, `qdrant/qdrant:latest`) à une version concrète
- [ ] Ajouter log limits JSON au `docker-compose.yml` (SD card protection)
- [ ] Ajouter Python 3.13 au matrix CI
- [ ] Mettre à jour `ACTIVE.md` (8 commits de retard depuis le 11 avril)
- [ ] Vérifier et supprimer/intégrer `src/memos/miner/` orphelin (413 lignes non utilisées par core)

#### Tier 2 — Dashboard P1 (impact utilisateur immédiat)
- [ ] Community detection + nœuds colorés par cluster (Leiden ou connected components)
- [ ] Depth filter / local graph (slider 1-5 hops + bouton "focus sur node")
- [ ] Hover preview riche (content snippet, tags, namespace, degree)

#### Tier 3 — v1.1 Polish & Docs
- [ ] README et docs golden path (`learn → recall → context_for → wake_up → reinforce/decay`)
- [ ] Clarifier quand utiliser `recall` vs `search` vs `memory_context_for` vs `memory_recall_enriched`
- [ ] Exemple d'intégration Claude Code / MCP minimal
- [ ] Exemple d'intégration OpenClaw / orchestrateur
- [ ] Harden importers & mining flows

### Out of Scope

- Refactor complet de `core.py` (v3 feature dev) — trop risqué avant tests v3 ; refactor progressif au fil des phases
- v3.0 features (temporal validity windows, blast radius, specialist agents, multimodal) — après T1-T3
- Federated memory / hosted service — v4+

## Context

- **Stack** : Python 3.11+, FastAPI, Uvicorn, sentence-transformers, SQLite (KG/Palace), ChromaDB/Qdrant/Pinecone optionnels
- **Infrastructure** : homelab Raspberry Pi 5 (orion-cortex), Docker, NFS storage, Tailscale
- **Déployé** : `ghcr.io/mars375/memos:latest` — image all-in-one `docker compose up memos-standalone`
- **Tests** : 1534 tests (pytest), CI GitHub Actions — test matrix 3.11/3.12, lint ruff, docker multi-arch (amd64+arm64)
- **Codebase map** : `.planning/codebase/` (créé le 13 avril 2026)
- **Problème connu** : `core.py` est un god object (1816 lignes, 78 méthodes) — à refactorer progressivement
- **Problème connu** : `src/memos/miner/` est orphelin (413 lignes, non importé par core ou tests)
- **Version drift** : `pyproject.toml` = 1.0.0, `__init__.py` = 2.2.0 — à corriger avant prochaine release

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

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-13 after initialization (brownfield — v2.2.0 in production)*
