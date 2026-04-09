# ACTIVE.md — Chantier MemOS

## Statut : ✅ P25 DONE, chantier ACTIVE

**Dernière session** : 2026-04-09 — P25 Unified Brain Search
**Version** : 0.41.0
**Tests** : 1450 passed

## Dernière action
- **P25 terminée** : recherche unifiée sur les 3 couches (memories + wiki + KG)
- `src/memos/brain.py` — `BrainSearch`, `BrainSearchResult`, `ScoredMemory`, `WikiHit`, `KGFactHit`
  - Orchestrateur qui interroge memories (`recall`), wiki (`search`), KG (`query`+`search_entities`)
  - Extraction d'entités zero-LLM (PascalCase, quoted, ALLCAPS)
  - Context string prêt-à-injecter dans un prompt (token-efficient)
  - Toggles `include_memories/include_wiki/include_kg` par couche
- CLI : `memos brain-search "<query>" [--top-k N] [--context-only] [--no-memories/--no-wiki/--no-kg]`
- REST : `POST /api/v1/brain/search` body `{"query": "...", "top_k": 10}`
- MCP : `brain_search` tool — retourne le context string directement
- Validation : `python -m pytest -x -q` → **1450 passed** (26 new brain tests)

## Prochaine étape
- **P26 — Entity Detail API + Graph ↔ Wiki Bridge** (vue unifiée par entité, dashboard navigable)
- **P28 — API Authentication** (bloquant V1)
- **P34 — Embeddings intégrés** (friction d'adoption)
