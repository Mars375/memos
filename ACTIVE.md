# ACTIVE.md — Chantier MemOS

## Statut : ✅ P1-P19 DONE

**Dernière session** : 2026-04-09 — P19 Miner Incrémental
**Version** : 0.35.0
**Tests** : 140 passed (test_knowledge_graph.py + test_miner.py + test_mine_cache.py)

## Dernière action
- **P19 terminée** : Miner Incrémental — SHA-256 Cache + --update + --diff
- `src/memos/ingest/cache.py` — `MinerCache` SQLite (`~/.memos/mine-cache.db`)
  - `is_fresh(path, sha256)`, `record()`, `get()`, `remove()`, `list_all()`, `stats()`
  - `get_chunk_hashes()` pour mode --diff
- `Miner`: `cache=`, `update=` params; `mine_file()` check/record cache; `_flush_batch()` collecte les memory_ids
- `MineResult`: `skipped_cached` + `memory_ids` fields
- CLI: `mine --update` (re-mine + remplace), `mine --diff` (nouveaux chunks seulement), `mine --no-cache`, `mine-status`
- 19 nouveaux tests

## Prochaine étape
- P20 — Hybrid Retrieval (Semantic + Keyword BM25)
- P33 — Auto-extraction KG à l'écriture (NER zéro-LLM) — CRITIQUE sprint V1
