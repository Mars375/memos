# ACTIVE.md — Chantier MemOS

## Statut : ✅ P28 DONE, chantier ACTIVE

**Dernière session** : 2026-04-10 — P28 API Authentication
**Version** : 0.44.0
**Tests** : 1460 passed

## Dernière action
- **P28 terminée** : auth Bearer + clés de namespace pour l’API REST
- `src/memos/api/__init__.py`
  - `GET /api/v1/auth/whoami`
  - chargement auto `API_KEY` / `MEMOS_NAMESPACE_KEYS`
  - warning explicite si l’API reste en mode open
- `src/memos/api/auth.py`
  - authentification `Authorization: Bearer <token>`
  - clés master + namespace, logs d’accès non autorisés
  - compat legacy `X-API-Key` conservée
- `tests/test_auth.py`
  - couverture master key, namespace key, whoami, open mode, rate limit, isolation namespace
- Validation : `python -m pytest -x -q` → **1460 passed**

## Prochaine étape
- **P29 — Memory Deduplication** (bloquant V1)
- **P30 — Namespace Management API**
- **P34 — Embeddings intégrés** (friction d'adoption)
