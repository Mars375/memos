# ACTIVE.md — Chantier MemOS

## Statut : ✅ P24 DONE, chantier ACTIVE

**Dernière session** : 2026-04-09 — P24 Memory Compression
**Version** : 0.40.0
**Tests** : 1424 passed

## Dernière action
- **P24 terminée** : compression des mémoires très décayées
- `src/memos/compression.py` — `MemoryCompressor` + `CompressionResult`
  - Groupement par tags communs dominants
  - Résumés agrégés avec metadata `compression`
  - Mode concat zéro-LLM, dry-run ou apply via `MemOS.compress()`
- CLI : `memos compress [--dry-run] [--threshold 0.1]`
- REST : `POST /api/v1/compress`
- Validation : `python -m pytest -x -q` → **1424 passed**

## Prochaine étape
- **P25 — Unified Brain Search** (une requête → tout le savoir)
- **P34 — Embeddings intégrés** reste prioritaire produit pour réduire la friction d’adoption
