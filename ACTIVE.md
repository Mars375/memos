# ACTIVE.md — Chantier MemOS

## Statut : ✅ P25 livrée + P34 embeddings intégrés, chantier ACTIVE

**Dernière session** : 2026-04-10 — P25 Unified Brain Search + P34 Embeddings intégrés
**Version** : 0.38.0
**Tests** : 1345 passed

## Dernière action
- **P25 implémentée** : recherche unifiée mémoire + wiki vivant + graphe de connaissances
- `src/memos/brain.py`
  - nouvelle classe `BrainSearch`
  - résultat structuré `BrainSearchResult` avec `memories`, `wiki_pages`, `kg_facts`, `entities`, `context`
  - détection/expansion d'entités puis fusion score-normalisée avec interleaving pour contexte prêt-à-injecter
- `src/memos/api/__init__.py`
  - nouvel endpoint `POST /api/v1/brain/search`
- `src/memos/mcp_server.py`
  - nouveau tool MCP `brain_search`
- `src/memos/cli.py`
  - nouvelle commande `memos brain-search "<query>"`
- `tests/test_brain_search.py`
  - couverture dédiée BrainSearch + API + MCP + CLI
- **P34 implémentée** : mode local-first sans service externe pour le recall sémantique
- `src/memos/embeddings/local.py`
  - nouveau `LocalEmbedder` lazy basé sur `sentence-transformers`
  - chargement différé du modèle `all-MiniLM-L6-v2`
- `src/memos/core.py`
  - nouveau backend `local` via `MemOS(backend="local")`
  - câblage direct du local embedder dans `RetrievalEngine`
- `src/memos/retrieval/engine.py`
  - support d'un embedder branchable
  - cache persistant aligné sur le vrai nom de modèle
  - recherche hybride corrigée pour respecter le namespace
- **Fix annexe intégré** : `src/memos/knowledge_graph.py` réaligné avec les tests `confidence_label`
- Validation : `python -m pytest -x -q` → **1345 passed**

## Prochaine étape
- reprendre **P26 — Entity Detail API + Graph ↔ Wiki Bridge** pour rendre la couche unifiée navigable dans le dashboard
- après P26, reprendre **P33 — Auto-extraction KG à l'écriture**
