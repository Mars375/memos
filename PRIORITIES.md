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
`tools/migrate_markdown.py`, H2/H3 parsing, frontmatter tags, dry-run, 16 tests. (v0.30.0)

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

---

## [x] P9 — Memory Decay & Reinforcement Engine
Implémenté v0.31.0 — DecayEngine.reinforce(), run_decay(), CLI decay/reinforce, REST /api/v1/decay/run + /memories/{id}/reinforce, MCP memory_decay/memory_reinforce, 36 tests.
**Objectif** : Simulation organique de l'oubli — les mémoires inutilisées déclinent, les fréquemment rappelées se renforcent.

Le cerveau humain oublie naturellement ce qui n'est pas utilisé. Memos a déjà `importance` et `prune_expired`, mais pas de mécanisme de **décroissance temporelle** ni de **renforcement par rappel**.

À implémenter dans `src/memos/decay.py` :
- `DecayEngine` classe avec politiques configurables
- `decay_policy` : Ebbinghaus forgetting curve (exponential decay : `importance *= e^(-λt)`)
- `reinforce(memory_id, strength=0.1)` — bump importance quand un recall touche cette mémoire
- `auto_reinforce=True` — chaque recall renforce automatiquement les résultats
- `run_decay(min_age_days=7, floor=0.1)` — applique la décroissance à toutes les mémoires
- Integration dans `recall()` : si `auto_reinforce=True`, chaque résultat de recall gagne +0.05 importance
- Integration dans `stats()` : afficher `avg_reinforcements`, `total_decayed`, `reinforced_count`
- CLI : `memos decay --apply`, `memos decay --dry-run`, `memos reinforce <id>`
- REST : `POST /api/v1/decay/run`, `POST /api/v1/memories/{id}/reinforce`
- MCP tools : `memory_decay`, `memory_reinforce`

Config dans `~/.memos/memos.json` :
```json
{
  "decay": {
    "enabled": true,
    "lambda": 0.01,
    "min_age_days": 7,
    "floor": 0.1,
    "auto_reinforce": true,
    "reinforce_strength": 0.05
  }
}
```

Validation :
```bash
memos learn "important fact" --importance 0.9
memos recall "important"  # auto-reinforce bumps importance
memos decay --dry-run     # shows what would decay
memos decay --apply       # applies decay
memos stats               # shows decay metrics
```

---

## [x] P10 — Knowledge Graph ↔ Memory Bridge
**Objectif** : Connecter le Knowledge Graph (faits typés) aux mémoires (texte libre) pour un rappel enrichi.

Actuellement, le KG et les mémoires sont deux mondes séparés. Le bridge permet :
- Quand on `recall`, les faits KG liés aux entités mentionnées sont aussi retournés
- Quand on `learn`, on peut optionnellement extraire des faits (subject-predicate-object) via patterns

À implémenter dans `src/memos/kg_bridge.py` :
- `KGBridge` classe qui connecte `MemOS` + `KnowledgeGraph`
- `recall_enriched(query, top=10)` → recall normal + faits KG liés aux top entités détectées
- `learn_and_extract(content, tags=None)` → learn + heuristique d'extraction de faits
  - Pattern : `"X is Y"`, `"X works at Y"`, `"X → Y"`, `"from: X to: Y"`
  - Stocke les faits extraits dans le KG avec `source=memos:{memory_id}`
- `link_fact_to_memory(fact_id, memory_id)` → jointure explicite
- CLI : `memos recall --enriched "Alice"` (retourne mémoires + faits KG)
- REST : `GET /api/v1/recall/enriched?q=X`
- MCP tool : `memory_recall_enriched`

Validation :
```bash
memos learn "Alice leads the infrastructure team at Acme Corp since January"
memos kg-add "Alice" "leads" "infrastructure-team" --source auto
memos recall --enriched "Alice"  # retourne mémoires + faits KG en un seul call
```

Implemented v0.31.1 — KGBridge, enriched recall, learn+extract, explicit memory links, REST `/api/v1/recall/enriched` + `/api/v1/learn/extract`, MCP `memory_recall_enriched`.

---

## [x] P11 — Recall Analytics Dashboard
**Objectif** : Tableau de bord d'analyse des patterns de rappel — quoi, quand, succès/échec.

À implémenter dans `src/memos/analytics.py` :
- `RecallAnalytics` classe avec SQLite backend (`~/.memos/analytics.db`)
- `track_recall(query, results, latency_ms)` — log chaque recall
- `top_recalled(n=20)` — mémoires les plus rappelées
- `recall_success_rate(days=7)` — % de recalls qui retournent au moins 1 résultat
- `query_patterns(n=20)` — queries les plus fréquentes
- `latency_stats()` — p50, p95, p99 des temps de recall
- `daily_activity(days=30)` — recalls par jour (pour sparkline)
- `zero_result_queries(n=20)` — queries sans résultat (candidats pour learn)
- CLI : `memos analytics top`, `memos analytics patterns`, `memos analytics latency`
- REST : `GET /api/v1/analytics/top`, `GET /api/v1/analytics/patterns`, etc.
- Dashboard : section analytics dans la page web existante (chart.js)
- Auto-track : intégrer dans `MemOS.recall()` si analytics activé

Implemented in this session:
- SQLite analytics store at `~/.memos/analytics.db`
- CLI `memos analytics top|patterns|latency|success-rate|daily|zero|summary`
- REST analytics endpoints under `/api/v1/analytics/*`
- Dashboard analytics summary + Chart.js sparkline

Config :
```json
{
  "analytics": {
    "enabled": true,
    "retention_days": 90
  }
}
```

Validation :
```bash
memos recall "test query 1"
memos recall "test query 2"
memos analytics top        # shows most recalled memories
memos analytics patterns   # shows query patterns
memos analytics latency    # shows p50/p95/p99
```

---

---

## 📡 External Intelligence Watch

> Projets et patterns à surveiller pour améliorer MemOS.
> Le cron forge-scout-signals et forge-scout-needs alimentent cette veille.
> Date de création : 2026-04-08

### 🔍 Graphify (https://github.com/safishamsi/graphify)
- **Ce qu'il fait** : graphe de connaissances multimodal (code, docs, PDFs, images) avec visualisation
- **À récupérer pour MemOS :**
  - [ ] Pipeline d'extraction graphe depuis PDFs/images/code (multimodal)
  - [ ] Requêtes de chemin (path queries : `A → B`) et explication de liens
  - [ ] Wiki auto-généré par communautés du graphe (pas juste par tags)
  - [ ] Mode watch/update incrémental sur corpus
- **Faisabilité :** moyen/difficile
- **Priorité :** P2 (après wiki vivant)

### 📝 LLM Wiki Pattern (Andrej Karpathy)
- **Ce qu'il fait** : wiki markdown persistant maintenu par l'agent, 3 couches (raw → wiki → schema)
- **À récupérer pour MemOS :**
  - [ ] Wiki vivant incrémental par entités/concepts (notre wiki compile est par tag, pas par concept)
  - [ ] `index.md` + `log.md` comme primitives de navigation
  - [ ] Workflow "ingest → update pages existantes → lint contradictions/orphans"
  - [ ] Schéma YAML frontmatter standardisé pour chaque page wiki
- **Faisabilité :** facile/moyen
- **Priorité :** **P1** — complément naturel de wiki-compile

### 🏰 MemPalace (https://github.com/milla-jovovich/mempalace)
- **Ce qu'il fait** : mémoire agent avec wings/rooms, KG temporel, verbatim recall, benchmarks
- **Déjà intégré dans MemOS :** Palace, KG temporel, context stack, miner, KG bridge
- **À récupérer encore :**
  - [ ] Mode **verbatim first** explicite (stockage brut avant synthèse)
  - [ ] Suite de benchmarks reproductibles type LongMemEval intégrée au repo
- **Faisabilité :** facile
- **Priorité :** P1 — benchmarks = crédibilité projet

---

## [x] P13 — Wiki Vivant (Karpathy-inspired)
Implemented v0.31.2 — LivingWikiEngine, CLI `memos wiki-living`, index/log/read/search/list/stats, entity extraction, backlinks, lint, 6 tests.
**Objectif :** Compléter wiki-compile avec un wiki incrémental par entités/concepts.

Notre wiki-compile actuel génère des pages par tag (snapshot statique). Le pattern Karpathy propose un wiki *vivant* :
- Pages créées par entité/concept (pas par tag)
- `index.md` = catalogue auto-généré
- `log.md` = journal d'activité (append-only)
- À chaque ingest : update des pages existantes + lint contradictions
- Frontmatter YAML standardisé

À implémenter :
- Mode `wiki --living` dans wiki engine
- Entity extraction basique (noms propres, concepts récurrents)
- Page templates par type (person, project, concept, decision)
- Auto-link entre pages (backlinks)
- Lint : orphelins, contradictions, pages vides

### ---

## [x] P14 — Benchmark Suite (MemPalace-inspired)
Implemented v0.31.2 — QualityBenchmarkSuite, CLI `memos benchmark-quality`, Recall@K, MRR, NDCG@K, decay impact, scalability, 34 tests.
**Objectif :** Suite de benchmarks reproductibles pour mesurer la qualité de recall.

MemPalace publie des résultats LongMemEval. MemOS devrait :
- Intégrer un benchmark interne (recall accuracy, latency, decay behavior)
- Script de génération de dataset synthétique
- CI : benchmarks tournent à chaque PR
- Publier les résultats dans le README

---

## [x] P12 — Memory Conflict Resolution (Multi-instance Sync) ✅ v0.31.0 (2026-04-08)
**Objectif** : Détecter et résoudre les conflits quand deux instances MemOS partagent des mémoires.

Cas d'usage : Agent A et Agent B ont chacun leur MemOS. Ils synchronisent. Si les deux ont modifié la même mémoire → conflit.

À implémenter dans `src/memos/conflict.py` :
- `ConflictDetector` classe
- `detect_conflicts(local: MemOS, remote_envelope: MemoryEnvelope)` → liste de conflits
- `Conflict` dataclass : `memory_id, local_version, remote_version, conflict_type`
- `ConflictType` enum : `CONTENT_CHANGED`, `TAGS_CHANGED`, `IMPORTANCE_CHANGED`, `DELETED_MODIFIED`
- `ResolutionStrategy` enum : `LOCAL_WINS`, `REMOTE_WINS`, `MERGE`, `MANUAL`
- `resolve(conflict, strategy)` → applique la résolution
- `merge_versions(local, remote)` → tente un merge intelligent (union des tags, contenu le plus récent)
- CLI : `memos sync-check <remote.json>`, `memos sync-apply <remote.json> --strategy merge`
- REST : `POST /api/v1/sync/check`, `POST /api/v1/sync/apply`
- MCP tools : `memory_sync_check`, `memory_sync_apply`

Validation :
```bash
# Export instance A
memos export --format json > /tmp/instance_a.json
# On instance B, check for conflicts
memos sync-check /tmp/instance_a.json
# Apply with merge strategy
memos sync-apply /tmp/instance_a.json --strategy merge
```

---

## [x] P15 — KG Path Queries (Multi-hop Graph Traversal)
Implemented v0.32.0 — KnowledgeGraph.find_paths/shortest_path/neighbors, CLI `memos kg-path/kg-neighbors`, REST `/api/v1/kg/paths` + `/api/v1/kg/neighbors`, 23 tests.
**Objectif** : Requêtes multi-sauts dans le Knowledge Graph — "comment X est-il connecté à Y ?"

Inspiré de Graphify : path queries (A → B), neighborhood expansion, shortest path.

À implémenter dans `src/memos/knowledge_graph.py` :
- `find_paths(entity_a, entity_b, max_hops=3, max_paths=10)` — BFS, retourne tous les chemins
- `shortest_path(entity_a, entity_b, max_hops=5)` — BFS chemin le plus court
- `neighbors(entity, depth=1, direction="both")` — expansion de voisinage multi-hop
- CLI : `memos kg-path <entity_a> <entity_b> --max-hops 3`, `memos kg-neighbors <entity> --depth 2`
- REST : `GET /api/v1/kg/paths?entity_a=X&entity_b=Y&max_hops=3`, `GET /api/v1/kg/neighbors?entity=X&depth=1`

Validation :
```bash
memos kg-path Alice Bob --max-hops 3
memos kg-neighbors Alice --depth 2
curl .../api/v1/kg/paths?entity_a=Alice&entity_b=Carol
```
