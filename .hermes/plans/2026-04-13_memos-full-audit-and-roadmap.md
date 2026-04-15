# MemOS — Audit Complet & Roadmap

**Date:** 2026-04-13
**Auteur:** Mnēma (audit + synthèse multi-sessions)
**Repo:** `~/.openclaw/workspace-labs/forge/chantiers/memos/`
**Branche:** `main` | **Version pyproject:** `2.2.0` | **GitHub release:** `v1.0.0`

---

## 1. CARTE DE LA CODEBASE

### 1.1 Architecture Générale

```
src/memos/                          # ~19,500 LOC Python
├── core.py              (1,909L)   # MemOS orchestrator — init, learn, recall, search, stats
├── brain.py               (540L)   # Entity brain — subgraph, entity resolution
├── config.py              (153L)   # Settings (pydantic BaseSettings)
├── models.py              (201L)   # Data models — Memory, KGFact, etc.
├── context.py             (299L)   # Context window assembly
│
├── api/                             # REST API (FastAPI)
│   ├── auth.py                      # API key auth
│   ├── ratelimit.py                 # Rate limiting
│   ├── sse.py                       # Server-Sent Events
│   └── routes/
│       ├── admin.py                 # Admin endpoints
│       ├── knowledge.py             # KG endpoints (facts, labels, query, backlinks)
│       └── memory.py                # Memory CRUD + search + analytics
│
├── cli/                  (4,179L)   # CLI (argparse, 7 command modules)
│   ├── _common.py                   # Shared utils (_get_memos, _fmt_ts, etc.)
│   ├── _parser.py                   # Argparse builder
│   ├── commands_io.py               # import, export, ingest, migrate
│   ├── commands_knowledge.py        # kg_*, wiki_*, brain_search
│   ├── commands_memory.py           # learn, recall, search, stats, etc.
│   ├── commands_namespace.py        # ns_*, share_*, sync_*
│   ├── commands_palace.py           # palace_*
│   ├── commands_system.py           # serve, config, mcp
│   └── commands_versioning.py       # history, rollback, diff, snapshot
│
├── storage/              (1,477L)   # Pluggable backends
│   ├── base.py / async_base.py     # Abstract interfaces
│   ├── json_backend.py             # JSON file (standalone)
│   ├── memory_backend.py           # In-memory (tests)
│   ├── chroma_backend.py           # ChromaDB
│   ├── qdrant_backend.py           # Qdrant
│   ├── pinecone_backend.py         # Pinecone
│   ├── encrypted_backend.py        # Encryption wrapper
│   └── async_wrapper.py            # Sync→Async adapter
│
├── retrieval/              (496L)   # Hybrid search
│   ├── engine.py                    # Retrieval orchestrator
│   └── hybrid.py                    # Vector + keyword fusion
│
├── embeddings/             (165L)   # Embedding providers
│   └── local.py                     # sentence-transformers (all-MiniLM-L6-v2)
│
├── knowledge_graph.py      (668L)   # KG engine — facts, inference, query, lint
├── kg_bridge.py                      # KG↔Brain bridge
├── wiki.py / wiki_graph.py / wiki_living.py  (1,800L+)  # Wiki + living docs
│
├── compaction/             (594L)   # Memory compaction
├── consolidation/          (574L)   # Memory consolidation (sync + async)
├── decay/                  (217L)   # Memory decay scoring
├── dedup.py                (263L)   # Deduplication engine
├── conflict.py             (459L)   # Conflict detection
│
├── ingest/               (2,408L)   # Document ingestion pipeline
│   ├── engine.py                    # Pipeline orchestrator
│   ├── chunker.py                   # Text chunking
│   ├── miner.py                     # Knowledge mining
│   ├── parsers.py                   # File format parsers
│   ├── url.py                       # URL ingestion
│   ├── conversation.py              # Conversation ingestion
│   └── cache.py                     # Ingestion cache
│
├── versioning/             (908L)   # Memory versioning (history, rollback, snapshot)
├── namespaces/             (299L)   # Namespace isolation + ACL
├── sharing/                (472L)   # Cross-namespace sharing
├── subscriptions/          (225L)   # Subscription engine
│
├── palace.py               (443L)   # Memory Palace (spatial memory)
├── analytics.py            (246L)   # Usage analytics
├── cache/                  (265L)   # Embedding cache
│
├── mcp_server.py           (851L)   # MCP server (15 tools)
├── mcp_hooks.py            (241L)   # MCP hooks
│
├── export_markdown.py      (315L)   # Markdown export
├── export_obsidian.py               # Obsidian vault export
├── tagger.py               (262L)   # Auto-tagging
├── skills.py               (309L)   # Skills system
├── sanitizer.py            (112L)   # Input sanitization
├── compression.py          (101L)   # Memory compression
├── crypto.py               (113L)   # Encryption
├── parquet_io.py           (173L)   # Parquet import/export
├── migration.py            (202L)   # Data migration
├── events.py               (294L)   # Event system
├── query.py                (182L)   # Query parsing
│
├── benchmark.py            (440L)   # Performance benchmarks
├── benchmark_quality.py    (667L)   # Quality benchmarks
│
└── web/                   (1,823L)  # Dashboard (12 fichiers)
    ├── dashboard.html        (218L)  # Shell HTML
    ├── dashboard.css         (201L)  # Styles
    └── js/
        ├── state.js           (45L)  # État global
        ├── utils.js           (17L)  # Helpers
        ├── filters.js         (84L)  # Filtres (sliders, clustering)
        ├── sidebar.js        (177L)  # Sidebar (tags, NS, KG, analytics)
        ├── panels.js         (150L)  # Panels (détail, entity, tooltip)
        ├── graph.js          (428L)  # Force-graph (vasturiano)
        ├── api.js            (216L)  # API calls + buildGraphData
        ├── wiki.js           (147L)  # Wiki + markdown renderer
        ├── palace.js          (78L)  # Memory Palace treemap
        └── controls.js        (62L)  # Ribbon, modals, zoom
```

### 1.2 Stack Technique

| Couche | Techno |
|--------|--------|
| Backend | Python 3.11+, FastAPI, uvicorn |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) / Ollama (nomic-embed-text) |
| Vector DB | JSON (local) / ChromaDB / Qdrant / Pinecone |
| Dashboard | Vanilla JS, Canvas2D (force-graph vasturiano), CSS |
| CLI | argparse, rich |
| MCP | JSON-RPC over stdio |
| CI | GitHub Actions (ruff, pytest, Docker multi-arch) |
| Docker | python:3.11-slim, ~1GB+ (torch), amd64+arm64 |
| Package | setuptools, PyPI (trusted publisher) |

### 1.3 CI/CD — 3 Workflows

| Workflow | Trigger | Jobs |
|----------|---------|------|
| `test.yml` | push/PR main | Ruff lint + format, pytest (3.11/3.12/3.13), codecov |
| `docker.yml` | push main, tags v* | Build multi-arch → GHCR (`ghcr.io/mars375/memos:latest`) |
| `publish.yml` | release published | Test + build + publish PyPI |

### 1.4 Tests — 1,731 tests, 76 fichiers

**Couverture par module :**
- ✅ core, brain, config, context, conflict, dedup, tagger, analytics, palace, skills
- ✅ compression, crypto, sanitizer, events, query, migration, parquet_io
- ✅ cli (general + versioning), benchmark + benchmark_quality
- ✅ api (auth, ratelimit, streaming, websocket, versioning)
- ✅ storage (json, chroma, qdrant, pinecone, encrypted)
- ✅ embeddings, cache, ingest (engine, miner, cache, conversation, url)
- ✅ compaction, consolidation (sync + async), decay
- ✅ retrieval, versioning, namespaces/ACL, sharing, subscriptions
- ✅ knowledge_graph, wiki, kg_bridge, export, dashboard (static)
- ✅ mcp_server, mcp_hooks

**Modules sans tests dédiés (couverture indirecte) :**
- ⚠️ `api/routes/admin.py` — couvert via test_api ou test_admin
- ⚠️ `api/sse.py` — couvert via test_streaming
- ⚠️ `storage/async_wrapper.py` — couvert via test_async

---

## 2. CE QUI A ÉTÉ FAIT (chronologie multi-sessions)

### Session 1 — Déploiement initial (12 avril, ~23h)
- ✅ Repo identifié : `Mars375/memos` (pas `LoicPsi/MemOS`)
- ✅ Docker pull + deploy sur Cortex (RPi5, ARM64)
- ✅ Fix crash `FileNotFoundError: dashboard.html` (image stale)
- ✅ Fix Docker bridge gateway IP (`172.23→172.24`) + UFW rule `172.16.0.0/12→11434`
- ✅ API REST vérifiée : `/api/v1/learn`, `/api/v1/recall`
- ✅ MCP endpoint vérifié : 15 tools fonctionnels
- ✅ Dashboard accessible via Tailscale (`cortex.goby-aeolian.ts.net:8100`)
- ✅ KG peuplé : 13 facts (Mnēma↔Cortex, MemOS↔ChromaDB, etc.)
- ⚠️ Memory migration partielle (5/36 chunks des agent MEMORY.md)
- 🐛 Bug découvert : sidebar "Links" counter = 0 malgré 13 KG facts

### Session 2 — Issue #36 : Graph Visualization (13 avril, ~00h)
- ✅ Issue #36 lue et analysée (P0: SVG→Canvas, KG edges, filtering)
- ✅ Dashboard HTML analysé (1,342L D3 SVG force graph)
- ✅ Library `force-graph` (vasturiano) researchée — API docs extraites
- ✅ Commencé implémentation canvas force-graph
- ⏳ Non terminé dans cette session

### Session 3 — Implementation #36-#40 (13 avril, suite)
- ✅ **#36 Canvas Graph** : SVG→Canvas avec force-graph, KG edges (purple arrows), node glow, zoom-to-fit
- ✅ **#38 Clustering** : BFS connected-components, color modes (NS/Cluster/Tag/Layer)
- ✅ **#39 P2/P3** : Time-lapse slider, 4-layer memory stack, health dashboard, blast radius
- ✅ **#40 Split** : 1,768L monolith → 12 fichiers modulaires (HTML 218L + CSS 201L + 10 JS)
- ✅ Tests créés : 13 tests static file serving (16 total)
- ✅ Issues #31-40 toutes fermées, 0 open issues, 0 open PRs
- ✅ Merge feat branch → main

### Session 4 — QA Dogfood + Lint Fix (13 avril, ~20h)
- 🐛 **Bug critique découvert** : Docker image ne contenait PAS les fichiers JS/CSS splités
  - Cause : fichiers jamais commités sur la branche feat
  - Résolu : commit + merge sur main
- ✅ 13 tests static file serving ajoutés (`test_dashboard_static.py`)
- ✅ **506 erreurs Ruff fixées** (397 auto, 39 unsafe, 70 manuel)
- ✅ **126 fichiers reformatés** (`ruff format`)
- ✅ **1,549 tests passent** (0 échoué)
- ✅ CI Tests passe ✅ (ruff check + format + pytest)
- ⏳ CI Docker build en cours

### Session 5 — En cours (13 avril, ~21h)
- ✅ Lint restant fixé (1 import sorting dans `cli/__init__.py`)
- ✅ Ruff format appliqué (126 fichiers)
- ✅ Push final → CI Tests ✅ passé
- ⏳ CI Docker build en cours (run 24366972982, ~25min)

---

## 3. CE QU'IL RESTE À FAIRE

### 3.1 BLOCKER — Déploiement (immédiat)

| # | Tâche | Statut | Priorité |
|---|-------|--------|----------|
| D1 | Attendre CI Docker build (run 24366972982) | ⏳ en cours | P0 |
| D2 | `docker compose pull && docker compose up -d memos-standalone` | 🔲 pending | P0 |
| D3 | Re-seed données si volume perdu | 🔲 pending | P0 |

### 3.2 QA Dogfood — Tests en situation réelle

| # | Scénario de test | Ce qu'on vérifie | Statut |
|---|------------------|-------------------|--------|
| Q1 | **Dashboard charge** | HTML + CSS + 10 JS modules servis via `/static/` | 🔲 |
| Q2 | **Graph force-layout** | Canvas force-graph rend des nodes colorés | 🔲 |
| Q3 | **KG edges** | Flèches purple entre nodes (Mnēma→Cortex, etc.) | 🔲 |
| Q4 | **Normal edges** | Lignes standard entre nodes partageant des tags | 🔲 |
| Q5 | **Clustering** | BFS clusters avec couleurs par NS/Cluster/Tag | 🔲 |
| Q6 | **Filtres** | Depth slider, edge weight slider, degree filter | 🔲 |
| Q7 | **Time-lapse** | Slider temporel filtre les nodes par date | 🔲 |
| Q8 | **Sidebar** | Tags, namespaces, KG tree, analytics se mettent à jour | 🔲 |
| Q9 | **Memory detail** | Click sur node → panel avec contenu mémoire | 🔲 |
| Q10 | **Wiki view** | Wiki articles render avec markdown | 🔲 |
| Q11 | **Palace treemap** | Treemap wings→rooms→memories s'affiche | 🔲 |
| Q12 | **Health dashboard** | Score, orphans, staleness, contradictions | 🔲 |
| Q13 | **4-Layer stack** | L0-L3 badges et filtres | 🔲 |
| Q14 | **Blast radius** | Impact analysis modal sur suppression | 🔲 |
| Q15 | **Search-to-focus** | Recherche → zoom sur le node | 🔲 |
| Q16 | **Namespace chips** | Filtrer par namespace | 🔲 |
| Q17 | **API REST complète** | learn, recall, search, forget, stats, analytics | 🔲 |
| Q18 | **MCP tools** | 15 tools via `/mcp` endpoint | 🔲 |
| Q19 | **Multi-nodes** | Ajouter 50+ memories, vérifier perfs | 🔲 |
| Q20 | **Responsive** | Dashboard utilisable sur mobile/tablette | 🔲 |

### 3.3 Bugs & Dettes Techniques

| # | Problème | Détail | Priorité |
|---|----------|--------|----------|
| B1 | **KG entity matching fragile** | Multi-tag memories cassent `buildKGEdges` (s===t filtré) | P1 |
| B2 | **Old multi-tag memories** | 13 anciens nodes multi-tags polluent le graphe — à supprimer | P1 |
| B3 | **Version mismatch** | pyproject.toml dit `2.2.0`, release GitHub dit `v1.0.0`, `__init__.py` ? | P1 |
| B4 | **Sidebar "Links" counter** | Montrait 0 même avec KG facts — à retester après fix B1+B2 | P2 |
| B5 | **PyPI package outdated** | PyPI a `0.1.0`, le code est `1.0.0+` — needs `publish.yml` | P2 |
| B6 | **Docker image ~1GB+** | sentence-transformers/torch très lourd — explorer ONNX ou miniLM | P3 |
| B7 | **Pas d'authentification** | Dashboard accessible sans auth sur Tailscale | P3 |

### 3.4 Fonctionnalités Futures (post-v1.0.0)

| # | Feature | Description | Priorité |
|---|---------|-------------|----------|
| F1 | **Memory migration complète** | Ingest les 36 chunks MEMORY.md des 5 agents OpenClaw | P1 |
| F2 | **MemOS↔Hermes integration** | Hermes utilise MemOS comme backend mémoire persistant | P1 |
| F3 | **Authentification dashboard** | Basic auth ou API key pour le dashboard | P2 |
| F4 | **Leiden clustering** | Remplacer BFS par Leiden algorithm (meilleur) | P2 |
| F5 | **WebSocket realtime** | Dashboard se met à jour en temps réel sans refresh | P2 |
| F6 | **Export/Import dashboard config** | Sauver/charger layouts, filtres, préférences | P3 |
| F7 | **Mobile-responsive** | Dashboard utilisable sur petit écran | P3 |
| F8 | **ONNX embeddings** | Remplacer sentence-transformers par ONNX (image ~200MB vs ~1GB) | P3 |
| F9 | **Multi-user** | Auth + namespaces utilisateur | P4 |

---

## 4. PLAN D'ACTION IMMÉDIAT

### Phase 1 — Déployer & Vérifier (aujourd'hui)
1. ✅ Lint fix + format + push → CI Tests ✅
2. ⏳ CI Docker build → pull → deploy sur Cortex
3. 🔲 Re-seed memories (12 single-tag + 13 KG facts si volume perdu)
4. 🔲 QA Dogfood Q1-Q20 (tests en situation réelle via browser)

### Phase 2 — Fix Bugs (après QA)
5. 🔲 Fix B1+B2 : nettoyer multi-tag memories → KG edges fonctionnels
6. 🔲 Fix B3 : aligner version (pyproject + release + __init__)
7. 🔲 Re-tester B4 (sidebar Links counter)

### Phase 3 — Stabilisation
8. 🔲 Memory migration complète (F1)
9. 🔲 Tag git `v2.2.0` + GitHub release (si version confirmée)
10. 🔲 Fix B5 : publish PyPI via workflow

### Phase 4 — Evolution
11. 🔲 MemOS↔Hermes integration (F2)
12. 🔲 Auth dashboard (F3)
13. 🔲 Optimisations (F8 ONNX, F6 responsive)

---

## 5. MÉTRIQUES CLÉS

| Métrique | Valeur |
|----------|--------|
| LOC Python source | ~19,500 |
| LOC Dashboard (HTML+CSS+JS) | 1,823 |
| Fichiers source Python | 78 |
| Fichiers test | 76 |
| Total tests | 1,731 |
| Issues GitHub | 0 open, 9 closed |
| CI Workflows | 3 |
| Backends storage | 5 (JSON, Memory, Chroma, Qdrant, Pinecone) |
| MCP tools | 15 |
| Erreurs Ruff | 0 ✅ |
| Docker image size | ~1GB+ (torch) |
| Plateformes Docker | amd64 + arm64 |

---

## 6. LEÇONS APPRISES (multi-sessions)

1. **Toujours vérifier l'image Docker matche le source** — Session entière perdue sur des bugs causés par une image stale
2. **`ruff check` ≠ `ruff format`** — CI fait les DEUX. Fixer l'un sans l'autre = CI red build
3. **`let`/`const` au top-level ne vont pas sur `window`** — Piège JS classique dans les modules <script>
4. **Multi-tag memories cassent le KG entity matching** — Un node tagué `[Mnēma, Cortex]` fait que les deux entités pointent vers le même node → `s===t` → edge filtrée
5. **Docker bridge IP change** — Ne pas hardcoder, utiliser `host.docker.internal` ou `extra_hosts`
6. **Fichiers split doivent être commités ET dans pyproject.toml package-data** — Sinon absents de l'image Docker
