# ACTIVE.md — Chantier MemOS

## Statut : ✅ P28 DONE, chantier ACTIVE

**Dernière session** : 2026-04-11 — P28 API Authentication (Bearer + Namespace Keys)
**Base** : `main` v0.47.0 → branche `feat/p28-api-authentication`, PR #15
**Validation** : `pytest -q` → **1389 passed** (25 tests auth dédiés)

## Dernière action
- P28 implémentée : `APIKeyManager` avec master key + namespace-scoped keys
- Middleware FastAPI : Bearer token + X-API-Key, namespace forcing, rate limiting
- `GET /api/v1/auth/whoami` — identité + permissions
- Mode open (pas de clé) = backward compatible avec log warning
- PR rebasée sur main, conflit résolu : https://github.com/Mars375/memos/pull/15

## OPEN dans PRIORITIES.md
- P26 — Entity Detail API + Graph ↔ Wiki Bridge
- P27 — Knowledge Export Universel (Markdown)
- P32 — PyPI Release + README v1
- P33 — Auto-extraction KG (NER zéro-LLM)

## IN PROGRESS / IN REVIEW
- P25 [~] — Unified Brain Search (PR #12)
- P31 [~] — Advanced Recall Filters (PR #9, merged sur main)
- P34 [~] — Embeddings intégrés (PR #11)

## Prochaine étape
- **P32** (PyPI Release) ou **P26** (Entity Detail API) — selon priorité forge
