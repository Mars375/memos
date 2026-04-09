# ACTIVE.md — Chantier MemOS

## Statut : ✅ P1-P18 DONE

**Dernière session** : 2026-04-09 — P18 Confidence Labels KG
**Version** : 0.34.0
**Tests** : 72 passed (test_knowledge_graph.py) — +14 P18 tests

## Dernière action
- **P18 terminée** : Confidence Labels KG — EXTRACTED / INFERRED / AMBIGUOUS
- `KnowledgeGraph.query_by_label()`, `label_stats()`, `infer_transitive()` — déjà présents
- `KGBridge.infer()` ajouté — wraps `infer_transitive()` pour règles d'inférence transitives
- Dashboard : panel "KG Confidence Labels" avec chips colorés + overlay facts par label
- REST `/api/v1/kg/labels` — label_stats + facts par label (déjà présent)
- 14 nouveaux tests : label validation, query_by_label, label_stats, infer_transitive

## Prochaine étape
- P19 — Miner Incrémental (SHA-256 Cache + --update)
- P33 — Auto-extraction KG à l'écriture (NER zéro-LLM) — CRITIQUE sprint V1
