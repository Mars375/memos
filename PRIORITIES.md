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
D3.js force-directed, dark theme, `/api/v1/graph`, sidebar stats+search. (v0.29.0)

## [x] P2 — MCP server (bridge universel agents)
`memos mcp-serve` + `memos mcp-stdio`, JSON-RPC 2.0, 4 outils, 11 tests. (v0.30.0)

## [x] P3 — Wiki compile mode
`memos wiki-compile/list/read`, pages markdown par tag, 10 tests. (v0.30.0)

## [x] P4 — Script de migration markdown → MemOS
`tools/migrate_markdown.py`, H2/H3 parsing, frontmatter tags, dry-run, 18 tests. (v0.30.0)

---

## [x] P5 — Temporal Knowledge Graph (inspiré MemPalace)
Implémenté v0.30.0 — KnowledgeGraph SQLite, CLI kg-add/query/timeline/invalidate/stats, REST /api/v1/kg/*, MCP kg_add_fact/kg_query_entity/kg_timeline.
**Objectif** : Stocker des faits typés avec fenêtres temporelles — permet le raisonnement historique.

Inspiré de MemPalace : SQLite triples `(subject, predicate, object)` avec `valid_from / valid_to`.

À implémenter dans `src/memos/knowledge_graph.py` :
- `KnowledgeGraph` classe avec SQLite backend (`~/.memos/kg.db`)
- `add_fact(subject, predicate, object, valid_from=None, valid_to=None, confidence=1.0, source=None)`
- `query(entity, time=None, direction='both')` → tous les faits liés à une entité à un instant T
- `query_predicate(predicate)` → tous les triples d'un type de relation
- `timeline(entity)` → séquence chronologique des faits sur une entité
- `invalidate(fact_id, reason=None)` → marquer un fait comme expiré
- CLI : `memos kg-add <subj> <pred> <obj>`, `memos kg-query <entity>`, `memos kg-timeline <entity>`
- REST : `POST /api/v1/kg/facts`, `GET /api/v1/kg/query?entity=X&time=Y`
- MCP tools : `kg_add_fact`, `kg_query_entity`, `kg_timeline`

Use cases : "Qui travaillait sur ce projet en Q1 2025 ?" / "Quelle était la stack en mars ?"

Validation :
```bash
memos kg-add "Alice" "works_on" "ProjectX" --from 2025-01-01 --to 2025-06-30
memos kg-query Alice  # retourne tous les faits sur Alice
memos kg-timeline Alice  # chronologie
curl .../api/v1/kg/query?entity=Alice&time=2025-03-15
```

---

## [x] P6 — Hierarchical Palace (Wings/Rooms)
Implémenté v0.30.0 — PalaceIndex SQLite, Wings/Rooms CRUD, palace-assign/recall, REST /api/v1/palace/*, auto-detect from tags.
**Objectif** : Organisation hiérarchique à 3 niveaux — mesure +34% de précision du recall vs tags plats.

Inspiré de MemPalace : Wings (person/project) → Rooms (topic) → Memories.

À implémenter dans `src/memos/palace.py` :
- `PalaceIndex` : index SQLite des wings + rooms + memberships
- `Wing` : domaine de haut niveau (personne, projet, agent)
- `Room` : catégorie thématique dans un wing (auth, deployment, billing...)
- `memos palace-init` — crée le schéma palace
- `memos palace-assign <id> --wing <w> --room <r>` — assigner une mémoire
- `memos palace-recall <query> --wing <w> --room <r>` — recall scopé
- REST : `GET /api/v1/palace/wings`, `GET /api/v1/palace/rooms?wing=X`
- `GET /api/v1/palace/recall?query=X&wing=Y&room=Z`
- Dashboard : afficher wings/rooms dans le graph D3 (clusters visuels)
- Auto-detect rooms depuis les tags existants (migration transparente)

Avantage : recall scopé "dans le wing 'OpenClaw', room 'devops'" réduit le bruit sémantique.

Validation :
```bash
memos palace-init
memos palace-assign abc123 --wing openclaw --room devops
memos palace-recall "deployment pipeline" --wing openclaw
```

---

## [x] P7 — Multi-layer Context (Wake-up / L0-L1-L2-L3)
Implémenté v0.30.0 — ContextStack, wake-up, identity, recall_l2/l3, context-for, MCP memory_wake_up/memory_context_for.
**Objectif** : Récupération étagée pour optimiser les tokens — identité toujours chargée, détail à la demande.

Inspiré de MemPalace MemoryStack :
- **L0** (~100 tokens) : identité agent, toujours injecté (`~/.memos/identity.txt`)
- **L1** (~700 tokens) : top-K mémoires par importance, "wake-up" de session
- **L2** (~300 tokens) : recall filtré par wing/room quand topic détecté
- **L3** : full semantic search sans contrainte

À implémenter dans `src/memos/context.py` :
- `ContextStack` classe
- `wake_up(agent_id=None)` → retourne L0 + L1 comme string injectible dans un system prompt
- `recall_l2(query, wing=None, room=None, top=10)` → recall scopé
- `recall_l3(query, top=50)` → full search
- `set_identity(content)` → écrire/lire `~/.memos/identity.txt`
- CLI : `memos wake-up`, `memos identity set`, `memos identity show`
- MCP tools : `memory_wake_up`, `memory_context_l2`, `memory_context_l3`

Use case : en début de session Claude Code, `memos wake-up` injecte le contexte sans requête.

Validation :
```bash
memos identity set "Je suis Orion, dev full-stack. Projets: heartbeat, memos, openclaw."
memos wake-up  # retourne L0 + top-15 mémoires en <800 tokens
```

---

## [x] P8 — Smart Chunking + Multi-format Import
Implémenté v0.30.0 — chunk_text paragraph-aware, content_hash dedup, mine --format claude/chatgpt/slack/discord/telegram/openclaw, auto-detect.
**Objectif** : Chunking respectueux des paragraphes + import Claude/ChatGPT/Slack.

Inspiré de MemPalace miner :
- Chunks de 800 chars avec overlap 100, coupure aux limites de paragraphe
- Évite les doublons via hash du contenu
- Formats : Claude JSON exports, ChatGPT exports, Slack JSONL, fichiers markdown

À implémenter dans `src/memos/ingest/` (module déjà présent, étendre) :
- `chunk_text(text, size=800, overlap=100)` — chunking paragraph-aware
- `ingest_claude_export(path)` — parse Claude conversation JSON
- `ingest_chatgpt_export(path)` — parse ChatGPT zip/JSON
- `ingest_slack_export(path)` — parse Slack JSONL exports
- `deduplicate(items)` — hash SHA256 du contenu, ignore les doublons
- CLI : `memos ingest --format claude|chatgpt|slack <file>`
- Intégrer dans `tools/migrate_markdown.py` pour compléter la migration

Validation :
```bash
memos ingest --format claude ~/.claude/projects/.../conversation.json
memos ingest --format chatgpt ~/Downloads/chatgpt-export.zip
```
