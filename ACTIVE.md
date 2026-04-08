# ACTIVE.md — Chantier MemOS

## Statut : ✅ TOUTES PRIORITÉS DONE (P1-P15)

**Dernière session** : 2026-04-08 23:22 — P15 KG Path Queries
**Version** : 0.32.0
**Tests** : 1195 passed (dont 23 P15 kg-paths)

## Dernière action
- **P15 terminée** : Module `KnowledgeGraph.find_paths/shortest_path/neighbors`
- CLI : `memos kg-path`, `memos kg-neighbors`
- REST : `GET /api/v1/kg/paths`, `GET /api/v1/kg/neighbors`
- 23 tests (neighbors, find_paths, shortest_path, CLI)

## Prochaine étape
- Vérifier issues GitHub ouvertes (`gh issue list`)
- Améliorer quality/docs/perf
- Envisager v0.32.0 release tag
- Watchlist items restants: verbatim first mode, Graphify multimodal pipeline
