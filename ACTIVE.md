# ACTIVE.md — Chantier MemOS

## Statut : ✅ P29 DONE, chantier ACTIVE

**Dernière session** : 2026-04-11 — P29 Memory Deduplication (DedupEngine + learn() integration + CLI/API)
**Base** : `main` v0.47.0 → branche `feat/p29-memory-dedup`, PR #21
**Validation** : `pytest -q` → **1411 passed** (+27 tests dédiés)

## Dernière action
- P29 implémentée : `DedupEngine` avec SHA-256 exact hash + trigram Jaccard near-duplicate
- `MemOS.learn()` : dédup check avant insertion, `allow_duplicate=True` pour bypass
- CLI : `memos dedup-check`, `memos dedup-scan --fix`
- REST : `POST /api/v1/dedup/check`, `POST /api/v1/dedup/scan`
- PR ouverte : https://github.com/Mars375/memos/pull/21

## OPEN dans PRIORITIES.md
- P26 — Entity Detail API + Graph ↔ Wiki Bridge
- P27 — Knowledge Export Universel (Markdown)
- P28 — API Authentication (Bearer Token) — CRITICAL v1
- P32 — PyPI Release + README v1

## Prochaine étape
- **P28** (API Auth) — CRITICAL bloquant v1, ou **P26** si auth déjà couvert
