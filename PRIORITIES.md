# PRIORITIES.md — Feuille de route du chantier memos

> Ce fichier est le pilote du cron forge-chantier-memos.
> Le cron lit ce fichier au début de chaque session et travaille sur la première priorité OPEN.
> Si toutes les priorités sont DONE → le cron crée de nouvelles features pertinentes de manière autonome,
> les documente ici en `[x]` une fois complétées, et les commit.
> forge-maintainer peut modifier ce fichier pour orienter le chantier.

## Format
- `[ ]` OPEN — à faire
- `[~]` IN PROGRESS — commencé, continuer
- `[x]` DONE — terminé

---

## [x] P1 — Second Brain Dashboard (style Obsidian graph view)
**Objectif** : Interface web visuelle pour explorer les mémoires MemOS comme un knowledge graph interactif.

Implémenté : D3.js force-directed graph, dark theme #0d0d1a, nœuds colorés par tag, sidebar stats + search.
Routes : `GET /api/v1/graph`, `GET /dashboard`.

---

## [x] P2 — MCP server (bridge universel agents)
**Objectif** : Exposer MemOS comme serveur MCP pour OpenClaw, Claude Code, Cursor.

Implémenté dans `src/memos/mcp_server.py` :
- `memory_search(query, top_k=5)` → wrappe recall()
- `memory_save(content, tags=[])` → wrappe learn()
- `memory_forget(id|tag)` → wrappe forget()
- `memory_stats()` → wrappe stats()
- Commandes CLI : `memos mcp-serve --port 8200` / `memos mcp-stdio`
- Protocol : JSON-RPC 2.0 (standard MCP)
- 11 tests, 2 transports (HTTP + stdio)

---

## [x] P3 — Wiki compile mode (token optimization)
**Objectif** : Consolider les mémoires en pages synthétisées par tag — moins de tokens au recall.

Implémenté dans `src/memos/wiki.py` :
- `memos wiki-compile` — regroupe par tag, génère une page markdown synthétisée par tag dans `~/.memos/wiki/`
- `memos wiki-read <tag>` — retourne la page compilée
- `memos wiki-list` — liste pages avec metadata
- 10 tests

---

## [x] P4 — Script de migration markdown → MemOS
**Objectif** : Importer les mémoires existantes de OpenClaw dans MemOS.

Sources :
- `/home/orion/.claude/projects/-home-orion/memory/*.md`
- `/home/orion/.openclaw/workspace-labs/MEMORY.md`
- `/home/orion/.openclaw/workspace-labs/memory/*.md`

Implémenté dans `tools/migrate_markdown.py` :
- Parse sections H2/H3 comme mémoires séparées
- Tags depuis frontmatter ou nom de fichier
- `batch_learn()` par lots de 20
- Dry-run mode
- Log : N importées, N erreurs
- 18 tests

Validation :
```bash
python tools/migrate_markdown.py ~/.openclaw/workspace-labs/MEMORY.md --dry-run
python tools/migrate_markdown.py ~/.openclaw/workspace-labs/memory/ --tags daily
```
