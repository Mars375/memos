# ACTIVE.md — Chantier MemOS

## Statut : ✅ P25 livrée, PR #12 ouverte, chantier ACTIVE

**Dernière session** : 2026-04-10 — P25 Unified Brain Search
**Version** : 0.37.1
**Tests** : 1346 passed

## Dernière action
- **P25 implémentée** : recherche unifiée mémoire + wiki vivant + graphe de connaissances
- `src/memos/brain.py`
  - nouvelle classe `BrainSearch`
  - résultat structuré `BrainSearchResult` avec `memories`, `wiki_pages`, `kg_facts`, `entities`, `context`
  - détection/expansion d’entités puis fusion score-normalisée avec interleaving pour contexte prêt-à-injecter
- `src/memos/api/__init__.py`
  - nouvel endpoint `POST /api/v1/brain/search`
- `src/memos/mcp_server.py`
  - nouveau tool MCP `brain_search`
- `src/memos/cli.py`
  - nouvelle commande `memos brain-search "<query>"`
- `tests/test_brain_search.py`
  - couverture dédiée BrainSearch + API + MCP + CLI
- **Fix annexe intégré sur main avant branche** : support `confidence_label` dans `KnowledgeGraph`, ce qui répare le crash `test_kg_bridge`
- Validation : `python -m pytest -x -q` → **1346 passed**

## Prochaine étape
- suivre la review de la **PR #12 — P25 Unified Brain Search**
- ensuite reprendre **P26 — Entity Detail API + Graph ↔ Wiki Bridge** pour rendre la couche unifiée navigable dans le dashboard
