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

Inspiré du graph view Obsidian : fond sombre, nœuds lumineux, liens entre mémoires, clusters par tag.

Stack : FastAPI (déjà présent via `memos serve`) + endpoint `/dashboard` qui sert une SPA légère.
Visualisation : D3.js force-directed graph (CDN, pas de build step).

À implémenter :
- `GET /api/v1/graph` — retourne nodes + edges : chaque mémoire = node, similarité sémantique > seuil = edge
- `GET /dashboard` — sert `web/dashboard.html` (SPA standalone)
- UI dark (background #1a1a2e), nœuds colorés par tag, taille proportionnelle à l'importance
- Click sur un nœud → affiche contenu + tags + date + score
- Zoom/pan natif D3
- Sidebar : stats globales (total mémoires, top tags, decay candidates)
- Recherche : filtre les nœuds en temps réel par contenu ou tag

Validation :
```bash
memos serve --port 8100 &
curl http://localhost:8100/api/v1/graph  # retourne {nodes: [...], edges: [...]}
open http://localhost:8100/dashboard    # graph interactif visible
```

---

## [x] P2 — MCP server (bridge universel agents)
**Objectif** : Exposer MemOS comme serveur MCP pour OpenClaw, Claude Code, Cursor.

À implémenter dans `src/memos/mcp_server.py` :
- `memory_search(query, top_k=5)` → wrappe recall()
- `memory_save(content, tags=[])` → wrappe learn()
- `memory_forget(tag)` → wrappe forget()
- `memory_stats()` → wrappe stats()
- Commande CLI : `memos mcp-serve --port 8200`
- Protocol : JSON-RPC 2.0 (standard MCP)

Validation : `memos mcp-serve &` puis tester les 4 outils via JSON-RPC.

---

## [x] P3 — Wiki compile mode (token optimization)
**Objectif** : Consolider les mémoires en pages synthétisées par tag — moins de tokens au recall.

Inspiré du pattern Karpathy (LLM Wiki) : pages déjà compilées > mémoires brutes top-K.

À implémenter :
- `memos wiki compile` — regroupe par tag, génère une page markdown synthétisée par tag dans `data/wiki/`
- `memos wiki read <tag>` — retourne la page compilée
- `memos wiki list` — liste pages avec metadata

Validation : `memos wiki compile && memos wiki list && memos wiki read <tag>` retourne un résumé cohérent.

---

## [ ] P4 — Script de migration markdown → MemOS
**Objectif** : Importer les mémoires existantes de OpenClaw dans MemOS.

Sources :
- `/home/orion/.claude/projects/-home-orion/memory/*.md`
- `/home/orion/.openclaw/workspace-labs/MEMORY.md`
- `/home/orion/.openclaw/workspace-labs/memory/*.md`

À implémenter dans `tools/migrate_markdown.py` :
- Parse sections H2/H3 comme mémoires séparées
- Tags depuis frontmatter ou nom de fichier
- `batch_learn()` par lots de 20
- Log : N importées, N erreurs

Validation : migrer un fichier test, vérifier recall.
