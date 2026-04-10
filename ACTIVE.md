# ACTIVE.md — Chantier MemOS

## Statut : ✅ P27 DONE, chantier ACTIVE

**Dernière session** : 2026-04-10 — P27 Knowledge Export Universel
**Version** : 0.43.0
**Tests** : 1457 passed

## Dernière action
- **P27 terminée** : export Markdown portable et interopérable du knowledge MemOS
- `src/memos/export_markdown.py`
  - `MarkdownExporter` génère `INDEX.md`, `LOG.md`, pages entités, collections de mémoires et pages communautés
  - frontmatter YAML + inter-liens Markdown standards
  - mode incrémental qui ne réécrit que les pages modifiées
- `src/memos/core.py`
  - `MemOS.export_markdown()` pour l’API et la CLI
- `src/memos/cli.py`
  - `memos export --format markdown --output ./knowledge --update`
- `src/memos/api/__init__.py`
  - `GET /api/v1/export/markdown` → bundle ZIP téléchargeable
- Validation : `python -m pytest -x -q` → **1457 passed**

## Prochaine étape
- **P28 — API Authentication** (bloquant V1)
- **P29 — Memory Deduplication** (bloquant V1)
- **P34 — Embeddings intégrés** (friction d'adoption)
