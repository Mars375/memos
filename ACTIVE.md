# ACTIVE.md — Chantier MemOS

## Statut : ✅ P1-P20 DONE

**Dernière session** : 2026-04-09 — P20 Hybrid Retrieval
**Version** : 0.36.0
**Tests** : 165 passed

## Dernière action
- **P20 terminée** : Hybrid Retrieval — Semantic + BM25 keyword re-ranking
- `src/memos/retrieval/hybrid.py` — BM25 (in-house, 0 deps), HybridRetriever, keyword_score
- `MemOS.recall()` : nouveau param `retrieval_mode` ("semantic" | "hybrid" | "keyword")
  - `hybrid` : semantic top-50 → BM25 rerank → blend alpha*semantic + (1-alpha)*bm25 → top-K
  - `keyword` : pure TF overlap scoring sur tous les items
- API `POST /api/v1/recall` : accepte `retrieval_mode`
- CLI : `memos recall "<query>" --mode hybrid|keyword|semantic`
- 25 nouveaux tests (BM25, tokenizer, normalize, keyword_score, HybridRetriever)

## Prochaine étape
- P21 — Community Wiki (Leiden Graph + Index Navigable)
- P33 — Auto-extraction KG à l'écriture (NER zéro-LLM) — CRITIQUE sprint V1
