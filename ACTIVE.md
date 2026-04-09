# ACTIVE.md — Chantier MemOS

## Statut : ✅ P22 DONE, chantier ACTIVE

**Dernière session** : 2026-04-09 — P22 URL Ingest
**Version** : 0.37.0
**Tests** : 1342 passed

## Dernière action
- **P22 terminée** : ingestion d'URL multi-source sans setup manuel
- `src/memos/ingest/url.py` — `URLIngestor` avec routing arXiv, X/Twitter, PDF et webpage HTML
- Core : `MemOS.ingest_url()`
- CLI : `memos ingest-url <url> [--tags ...] [--dry-run]`
- REST : `POST /api/v1/ingest/url`
- Support PDF : extraction via PyMuPDF si dispo, fallback zéro-dépendance pour PDFs simples
- Validation : `python -m pytest -x -q` → **1342 passed**

## Prochaine étape
- **P23 — Speaker Ownership** (prochaine priorité OPEN dans `PRIORITIES.md`)
- **P33 — Auto-extraction KG à l'écriture** reste critique sprint V1 et doit être tirée très haut dans les prochaines sessions
