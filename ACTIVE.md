# ACTIVE.md — Chantier MemOS

## Statut : ✅ P32 livrée (branche en review), chantier ACTIVE

**Dernière session** : 2026-04-10 — P32 PyPI Release + README v1
**Version** : 1.0.0
**Tests** : 1482 passed

## Dernière action
- **P32 implémentée** : préparation release `memos-agent` pour PyPI + documentation v1
- `pyproject.toml` + `src/memos/__init__.py`
  - renommage package PyPI en `memos-agent`
  - bump version `1.0.0`
  - metadata complétée (`classifiers`, `keywords`, `project.urls`)
  - packaging `src/` réaligné via `tool.setuptools`
- `.github/workflows/publish.yml`
  - build + `twine check` + publication PyPI sur tags `v1.*`
  - mode trusted publishing prêt côté GitHub Actions
- `README.md` + `CHANGELOG.md`
  - README réécrit comme doc de référence (quick start, MCP, backends, Docker, API)
  - changelog consolidé de `v0.29.0` à `v1.0.0`
- Validation : `python -m pytest -x -q` → **1482 passed**
- Validation packaging : `python -m build` → wheel + sdist **OK**

## Prochaine étape
- **P34 — Embeddings intégrés** (friction d’adoption, bloque l’onboarding sans services externes)
- puis finaliser la séquence release/merge/tag v1 après review
