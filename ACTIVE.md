# ACTIVE.md — Chantier MemOS

## Statut : ✅ P32 livrée (branche en review), chantier ACTIVE

**Dernière session** : 2026-04-11 — P32 follow-up publish workflow
**Version** : 1.0.0
**Tests** : 1482 passed

## Dernière action
- **P32 follow-up** : correctif du workflow PyPI sur `fix/p32-pypi-publish-fallback`
- `.github/workflows/publish.yml`
  - suppression de `environment: pypi`
  - but : éviter un claim OIDC trop spécifique (`repo:Mars375/memos:environment:pypi`) qui bloquait Trusted Publishing sur le tag `v1.0.0`
- `PRIORITIES.md`
  - note de suivi ajoutée pour documenter le blocage réel et le correctif appliqué
- Validation : `pytest -q` → **1482 passed in 59.35s**
- Validation packaging : `python -m build` → wheel + sdist **OK**
- Validation distribution : `python -m twine check dist/*` → **PASSED** (via venv local)

## Prochaine étape
- merger ce correctif dans la PR P32 puis revalider la publication PyPI sur tag
- ensuite reprendre **P34 — Embeddings intégrés** pour réduire la friction d’adoption sans services externes
