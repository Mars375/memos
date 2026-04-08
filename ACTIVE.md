# ACTIVE.md — Chantier MemOS

## Statut : ✅ TOUTES PRIORITÉS DONE (P1-P14)

**Dernière session** : 2026-04-08 — P12 Memory Conflict Resolution
**Version** : 0.31.0
**Tests** : 1172 passed (dont 31 P12 conflict)

## Dernière action
- **P12 terminée** : Module `src/memos/conflict.py` avec ConflictDetector
- CLI : `memos sync-check`, `memos sync-apply`
- REST : `POST /api/v1/sync/check`, `POST /api/v1/sync/apply`
- MCP : `memory_sync_check`, `memory_sync_apply`
- 31 tests, merge strategy (union tags, most recent content, max importance)

## Prochaine étape
- Vérifier issues GitHub ouvertes (`gh issue list`)
- Améliorer quality/docs/perf
- Envisager v0.32.0 release
