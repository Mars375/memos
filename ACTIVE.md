# ACTIVE.md — Chantier MemOS

## Statut : ✅ P30 DONE, chantier ACTIVE

**Dernière session** : 2026-04-10 — P30 Namespace Management API
**Version** : 0.46.0
**Tests** : 1475 passed

## Dernière action
- **P30 terminée** : gestion complète des namespaces via core + API + CLI + MCP
- `src/memos/namespaces/registry.py` + `src/memos/core.py`
  - registre persistant des namespaces (description, timestamps)
  - `create_namespace()`, `namespace_stats()`, `list_namespace_details()`, `delete_namespace()`, `export_namespace()`, `import_namespace()`
  - `export_json()` / `import_json()` corrigés pour respecter le namespace courant
- `src/memos/api/__init__.py`
  - `GET/POST /api/v1/namespaces`, `GET/DELETE /api/v1/namespaces/{name}`
  - `POST /api/v1/namespaces/{name}/export|import`
  - ACL déplacée sous `/api/v1/namespaces/.../acl/*` avec alias compat
- `src/memos/cli.py` / `src/memos/mcp_server.py`
  - `memos namespaces list|stats|delete --yes`
  - MCP `namespace_list`, `namespace_stats`
- Validation : `python -m pytest -x -q` → **1475 passed**

## Prochaine étape
- **P31 — Advanced Recall Filters** (prochaine priorité OPEN)
- **P32 — PyPI Release + README v1**
- **P34 — Embeddings intégrés** (friction d'adoption)
