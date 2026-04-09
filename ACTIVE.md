# ACTIVE.md — Chantier MemOS

## Statut : ✅ P26 DONE, chantier ACTIVE

**Dernière session** : 2026-04-10 — P26 Entity Detail API + Graph ↔ Wiki Bridge
**Version** : 0.42.0
**Tests** : 1453 passed

## Dernière action
- **P26 terminée** : vue entité unifiée + dashboard navigable par entités
- `src/memos/brain.py`
  - `entity_detail()` : wiki page enrichie, mémoires liées, faits KG, voisins, backlinks, communauté
  - `entity_subgraph()` : ego network depth=2 prêt pour D3.js
  - `entity_graph()` : graphe d'entités annoté (communautés + god nodes)
- `src/memos/api/__init__.py`
  - `GET /api/v1/brain/entity/{name}`
  - `GET /api/v1/brain/entity/{name}/subgraph`
  - `/api/v1/graph?kind=entity` pour le dashboard
- `src/memos/web/__init__.py`
  - dashboard bascule sur graphe d'entités quand le KG existe
  - slide-in panel wiki/facts/neighbors/backlinks/top memories
  - god nodes mis en évidence visuellement
- `src/memos/wiki_graph.py`
  - nouvelle analyse publique des communautés pour réutilisation API/dashboard
- Validation : `python -m pytest -x -q` → **1453 passed**

## Prochaine étape
- **P27 — Knowledge Export Universel (Markdown interopérable)**
- **P28 — API Authentication** (bloquant V1)
- **P34 — Embeddings intégrés** (friction d'adoption)
