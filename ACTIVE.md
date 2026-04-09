# ACTIVE.md — Chantier MemOS

## Statut : ✅ P1-P21 DONE

**Dernière session** : 2026-04-09 — P21 Community Wiki
**Version** : 0.33.0
**Tests** : 1334 passed

## Dernière action
- **P21 terminée** : Community Wiki navigable basée sur le knowledge graph
- `src/memos/wiki_graph.py` — `GraphWikiEngine`, détection de communautés, pages markdown, index, log, god-nodes
- CLI : `memos wiki-graph [--output DIR] [--update] [--community ID] [--db PATH]`
- Génération : `index.md`, `log.md`, `god-nodes.md`, `communities/<id>.md`
- Update incrémental : réécrit seulement les pages modifiées, garde un log append-only
- Validation : nouveaux tests `tests/test_wiki_graph.py`, CLI vérifiée, suite complète + smoke test verts

## Prochaine étape
- P22 — URL Ingest (Tweet, arXiv, PDF, Webpage)
- P33 — Auto-extraction KG à l'écriture (NER zéro-LLM) — CRITIQUE sprint V1
