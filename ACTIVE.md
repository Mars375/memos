# ACTIVE.md — Chantier MemOS

## Statut : ✅ P29 DONE, chantier ACTIVE

**Dernière session** : 2026-04-10 — P29 Memory Deduplication
**Version** : 0.45.0
**Tests** : 1470 passed

## Dernière action
- **P29 terminée** : dédup exacte + near-duplicate avant insertion
- `src/memos/dedup.py`
  - `DedupEngine` (SHA-256 sur contenu normalisé + Jaccard sur trigrams)
  - scan global avec groupes exacts / near-dup et mode `--fix`
- `src/memos/core.py`
  - `learn(..., allow_duplicate=True)` pour bypass explicite
  - `dedup_check()` et `dedup_scan()` branchés au cœur MemOS
- `src/memos/cli.py` / `src/memos/api/__init__.py`
  - `memos dedup-check`, `memos dedup-scan [--fix]`
  - `POST /api/v1/dedup/check`
- `tests/test_dedup.py`
  - couverture moteur, core, CLI, API, et réalignement versioning avec `allow_duplicate`
- Validation : `python -m pytest -x -q` → **1470 passed**

## Prochaine étape
- **P30 — Namespace Management API** (bloquant V1 multi-agent)
- **P31 — Advanced Recall Filters**
- **P34 — Embeddings intégrés** (friction d'adoption)
