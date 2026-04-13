# Requirements: MemOS

**Defined:** 2026-04-13
**Core Value:** Un agent qui se souvient de tout ce qui est pertinent sans token bloat — le recall doit être rapide, contextuel et explicable.

---

## v1 Requirements (scope actif — T1 + T2 + T3)

### Maintenance

- [ ] **MAINT-01**: La version dans `pyproject.toml` est synchronisée avec `__init__.__version__`
- [ ] **MAINT-02**: Les images Docker tierces (`chromadb/chroma`, `qdrant/qdrant`) sont épinglées à une version concrète dans `docker-compose.yml`
- [ ] **MAINT-03**: `docker-compose.yml` inclut des log limits JSON (`max-size: 10m, max-file: 3`) sur tous les services
- [ ] **MAINT-04**: La CI GitHub Actions teste Python 3.11, 3.12 et 3.13
- [ ] **MAINT-05**: `ACTIVE.md` reflète l'état réel du projet (commits du 11-13 avril intégrés)
- [ ] **MAINT-06**: `src/memos/miner/` est soit supprimé, soit ses fonctions uniques migrées dans `src/memos/ingest/`

### Dashboard — Clustering

- [ ] **DASH-01**: Le graphe détecte automatiquement des communautés (Leiden ou connected components) et colore les nœuds par cluster
- [ ] **DASH-02**: La légende affiche les clusters détectés avec leurs couleurs
- [ ] **DASH-03**: Le clustering tient compte des tags et namespaces existants comme signal

### Dashboard — Navigation

- [ ] **DASH-04**: Un slider "Profondeur" (1-5 hops) filtre le graphe autour du nœud sélectionné ou du graphe entier
- [ ] **DASH-05**: Un bouton "Local graph" centre la vue sur le nœud cliqué et n'affiche que ses voisins directs

### Dashboard — Hover

- [ ] **DASH-06**: Un hover sur un nœud affiche un tooltip riche : content snippet (150 chars), tags, namespace, importance, degree (in/out)
- [ ] **DASH-07**: Le hover met en surbrillance les arêtes du nœud survolé

### Documentation

- [ ] **DOC-01**: README documenté avec le golden path complet (`learn → recall → context_for → wake_up → reinforce/decay`)
- [ ] **DOC-02**: Section "Quand utiliser quoi" clarifiant `recall` vs `search` vs `memory_context_for` vs `memory_recall_enriched`
- [ ] **DOC-03**: Exemple d'intégration minimal Claude Code / MCP (code fonctionnel)
- [ ] **DOC-04**: Exemple d'intégration OpenClaw / orchestrateur

---

## v2 Requirements (déférés — v3.0 features)

### Temporal Intelligence

- **TEMP-01**: Les edges KG ont des fenêtres de validité (`valid_from`, `valid_to`)
- **TEMP-02**: `kg_query_as_of(entity, ts)` — retroactive queries
- **TEMP-03**: Détection de contradictions — scan sémantique sur mémoires et KG
- **TEMP-04**: Blast radius / impact analysis (`memory_impact(id)`)
- **TEMP-05**: God nodes detection (rank par degree centrality)

### Agent Architecture

- **AGNT-01**: Per-agent namespaces avec identité et historique (agent diaries)
- **AGNT-02**: Rationale extraction pipeline (`because`, `in order to` → KG triples)
- **AGNT-03**: `memos compile` — recompilation hebdomadaire de l'intégralité du wiki

### MCP & API

- **MCP-01**: `memory_compare(A, B)` — analyse de tradeoffs structurée
- **MCP-02**: `memory_detect_contradictions()` — retourne les paires contradictoires
- **MCP-03**: `memory_suggest_next()` — gap analysis
- **MCP-04**: Extension MCP server de 12 à 20+ outils

### Multimodal

- **MULTI-01**: Ingestion d'images via vision API
- **MULTI-02**: Ingestion audio/vidéo via Whisper local
- **MULTI-03**: Ingestion code AST via Tree-sitter (14 langages)

### Dashboard v3

- **DASH3-01**: Wiki graph (nœuds = pages wiki, arêtes = wikilinks)
- **DASH3-02**: Palace map (spatial wings → rooms → memories)
- **DASH3-03**: Time-travel comparison (diff deux snapshots côte à côte)
- **DASH3-04**: Recall logs (quelles mémoires ont répondu à une query récente)

---

## Out of Scope

| Feature | Reason |
|---------|--------|
| Refactor complet de `core.py` en une seule phase | Trop risqué ; refactor progressif au fil des features v3 |
| Federated memory / hosted service | v4+ — hors périmètre homelabs |
| OAuth / SSO | Auth Bearer + namespace keys suffisants pour le cas d'usage actuel |
| Mobile / desktop client | Web-first, aucune demande identifiée |
| Fine-tuned embedding model | R&D — pas avant benchmarks LongMemEval |

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| MAINT-01 | Phase 1 | Pending |
| MAINT-02 | Phase 1 | Pending |
| MAINT-03 | Phase 1 | Pending |
| MAINT-04 | Phase 1 | Pending |
| MAINT-05 | Phase 1 | Pending |
| MAINT-06 | Phase 1 | Pending |
| DASH-01 | Phase 2 | Pending |
| DASH-02 | Phase 2 | Pending |
| DASH-03 | Phase 2 | Pending |
| DASH-04 | Phase 2 | Pending |
| DASH-05 | Phase 2 | Pending |
| DASH-06 | Phase 2 | Pending |
| DASH-07 | Phase 2 | Pending |
| DOC-01 | Phase 3 | Pending |
| DOC-02 | Phase 3 | Pending |
| DOC-03 | Phase 3 | Pending |
| DOC-04 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 17 total
- Mapped to phases: 17
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-13*
*Last updated: 2026-04-13 after initialization*
