# ACTIVE.md — Chantier MemOS

## Statut : ✅ P23 DONE, chantier ACTIVE

**Dernière session** : 2026-04-09 — P23 Speaker Ownership
**Version** : 0.38.0
**Tests** : 1364 passed

## Dernière action
- **P23 terminée** : ingestion de transcripts multi-speaker avec attribution par namespace
- `src/memos/ingest/conversation.py` — `ConversationMiner` + `parse_transcript()`
  - Formats supportés : `Speaker: message`, `[HH:MM] Speaker: message`, `**Speaker:**` markdown
  - Mode `per_speaker=True` : namespace = `{prefix}:{speaker_slug}` par speaker
  - Tags auto : `speaker:{name}`, `conversation`, `date:{YYYY-MM-DD}`
  - Namespace restauré après mine (pas de pollution de l'état)
- CLI : `memos mine-conversation <path> [--per-speaker] [--no-per-speaker] [--namespace-prefix PREFIX] [--dry-run]`
- REST : `POST /api/v1/mine/conversation` (body: `text` ou `path`, `per_speaker`, `namespace_prefix`, `tags`, `importance`)
- 22 tests dans `tests/test_conversation_miner.py`

## Prochaine étape
- **P24 — Memory Compression** (AAAK pour mémoires décayées)
- **P33 — Auto-extraction KG à l'écriture** reste critique sprint V1
