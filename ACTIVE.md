# ACTIVE.md — Chantier MemOS


=======
## Statut : ✅ P31 DONE (branche en review), chantier ACTIVE

**Dernière session** : 2026-04-10 — P31 Advanced Recall Filters
**Version** : 0.47.0
**Tests** : 1349 passed

## Dernière action
- **P31 implémentée** : recall structuré par date, importance et logique de tags
- `src/memos/query.py` + `src/memos/core.py`
  - `MemoryQuery` / `QueryEngine`
  - filtres `include` / `require` / `exclude`, bornes d’importance, plage de dates
  - `list_memories()` triable côté core
- `src/memos/api/__init__.py`
  - `POST /api/v1/recall` enrichi (`tags`, `importance`, `created_after|before`, `top_k`, `retrieval_mode`)
  - nouveau `GET /api/v1/memories` avec filtres et tri
- `src/memos/cli.py` / `src/memos/mcp_server.py`
  - `memos recall --min-importance --max-importance --tag-mode --require-tags --exclude-tags`
  - MCP `memory_search` enrichi avec filtres avancés
- stabilité annexe : `src/memos/knowledge_graph.py` réaligné avec les tests labels (`confidence_label`, `query_by_label`, `label_stats`, `infer_transitive`)
- Validation : `python -m pytest -x -q` → **1349 passed**

## Prochaine étape
- **P32 — PyPI Release + README v1**
- **P34 — Embeddings intégrés** (friction d’adoption)
