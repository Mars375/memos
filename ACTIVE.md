# ACTIVE.md — Chantier MemOS

## Statut : ✅ Milestone v2.2.0 COMPLÈTE — audit finalisé

**Dernière session** : 2026-04-15 — Audit milestone v2.2.0
**Base** : `main` v2.2.0 — branche `main` (stable)
**Validation** : `pytest -q` → **1534+ passed**

## Milestone v2.2.0 — Toutes phases complètes

### Phase 1 — Maintenance ✅
- **MAINT-01** ✅ — Version synchro : `pyproject.toml` + `__init__.py` = `2.2.0`
- **MAINT-02** ✅ — Images Docker épinglées : `chromadb/chroma:1.5.7`, `qdrant/qdrant:v1.17.1`
- **MAINT-03** ✅ — Log limits JSON sur les 5 services (`max-size: 10m, max-file: 3`)
- **MAINT-04** ✅ — CI matrix étendue à Python 3.11 / 3.12 / 3.13
- **MAINT-05** ✅ — `ACTIVE.md` mis à jour
- **MAINT-06** ✅ — `src/memos/miner/` supprimé (413 lignes orphelines, zéro import cassé)

### Phase 2 — Dashboard P1 ✅
- **DASH-01** ✅ — Community detection + cluster coloring (connected components)
- **DASH-02** ✅ — Legend dynamique (rebuild on filter change)
- **DASH-03** ✅ — Tags et namespace dans le tooltip + filtre par clic
- **DASH-04** ✅ — Depth slider (1-5 hops)
- **DASH-05** ✅ — Local graph toggle (nœuds à 1-2 sauts)
- **DASH-06** ✅ — Rich tooltip (content, tags, namespace, in/out degree)
- **DASH-07** ✅ — Hover highlight (voisins mis en évidence, autres estompés)

### Phase 3 — Documentation Polish ✅
- **DOC-01** ✅ — Golden path (lifecycle complet dans README)
- **DOC-02** ✅ — Recall API guide (tableau comparatif des 4 APIs)
- **DOC-03** ✅ — Claude Code MCP integration example (`examples/claude-code-mcp.md`)
- **DOC-04** ✅ — OpenClaw integration example (`examples/openclaw-integration.md`)

## Prochaine étape
- Archivage milestone v2.2.0 (`/gsd:complete-milestone v2.2.0`)
- Planification v3.x : refactor core.py, CLI split, wiki split
