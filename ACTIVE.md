# ACTIVE.md — Chantier MemOS

## Statut : ✅ P33 DONE, chantier ACTIVE

**Dernière session** : 2026-04-09 — P33 Auto-extraction KG à l'écriture
**Version** : 0.39.0
**Tests** : 1416 passed

## Dernière action
- **P33 terminée** : auto-extraction KG au write, sans LLM
- `src/memos/kg_extractor.py` — extracteur FR/EN zéro-LLM
  - Patterns explicites : `works_at`, `is`, `uses`, `deployed_to`, `fixed`
  - Fallback heuristique `AMBIGUOUS` + garde-fous négations/conditionnels
  - NER léger title-case/acronymes + patterns projet configurables
- `MemOS.learn(..., auto_kg=False)` pour désactiver sur un write spécifique
- Config : `MEMOS_AUTO_KG`, `MEMOS_KG_DB`
- CLI : `memos extract-kg "..."`
- REST : `POST /api/v1/kg/extract` + `POST /api/v1/learn` accepte `auto_kg`
- Validation : `python -m pytest -x -q` → **1416 passed**

## Prochaine étape
- **P24 — Memory Compression** (AAAK pour mémoires décayées)
- **P34 — Embeddings intégrés** ensuite, pour réduire la friction d’adoption
