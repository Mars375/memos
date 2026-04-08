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

---

## [x] P16 — MCP HTTP Universel (Streamable HTTP 2025-03-26)
Implemented — `add_mcp_routes()` dans `mcp_server.py`, intégré dans le FastAPI principal via `api/__init__.py`.
**Objectif :** Point d'entrée MCP accessible par tout agent (OpenClaw, Claude Code, Cursor, n'importe quel client HTTP/MCP).

Spec MCP 2025-03-26 :
- `POST /mcp` — JSON-RPC 2.0, réponse JSON ou SSE selon `Accept: text/event-stream`
- `GET /mcp` — SSE keepalive stream (canal server→client)
- `OPTIONS /mcp` — CORS preflight (wildcard origin)
- `GET /.well-known/mcp.json` — discovery document
- Header `Mcp-Session-Id` — tracking de session (auto-généré si absent)

Config OpenClaw (`~/.openclaw/openclaw.json`) :
```json
"mcp": { "servers": { "memos": { "type": "http", "url": "http://127.0.0.1:8100/mcp" } } }
```

Config Claude Code (`~/.claude.json`) :
```json
"mcpServers": { "memos": { "type": "http", "url": "http://127.0.0.1:8100/mcp" } }
```

---

## [ ] P17 — Memory Type Tags Zéro-LLM
**Objectif :** Classifier automatiquement chaque mémoire sans appel LLM, via patterns regex heuristiques.

Inspiré de mempalace : 96.6% accuracy sans extraction LLM. Catégories :
- `decision` — "j'ai décidé", "on a choisi", "we decided", "le choix est"
- `preference` — "j'aime", "je préfère", "I prefer", "my favorite"
- `milestone` — "terminé", "livré", "deployed", "shipped", "completed"
- `problem` — "bug", "erreur", "bloqué", "issue", "broken", "crash"
- `emotional` — "frustrant", "content", "excited", "proud", "annoyed"

À implémenter dans `src/memos/tagger.py` :
- `AutoTagger` class avec patterns compilés par type
- `tag(content: str) -> list[str]` — retourne les type-tags détectés
- Intégration dans `MemOS.learn()` — auto-append type tags si aucun tag de type présent
- CLI : `memos classify "<text>"` — affiche les tags auto-détectés
- REST : `GET /api/v1/classify?text=...` — retourne `{"tags": [...]}`
- Tests : 20+ cas pour chaque type, edge cases (multilingue, majuscules)

---

## [ ] P18 — Confidence Labels KG (EXTRACTED / INFERRED / AMBIGUOUS)
**Objectif :** Ajouter un champ `confidence_label` sur les triplets KG pour indiquer l'origine de la connaissance.

Inspiré de Graphify : distinguer ce qui est explicitement dit vs inféré vs ambigu.

Labels :
- `EXTRACTED` — fait explicitement déclaré dans le texte source
- `INFERRED` — déduit logiquement d'autres faits (transitivité, règles)
- `AMBIGUOUS` — mention implicite ou interprétation incertaine

À implémenter :
- Ajouter `confidence_label: str = "EXTRACTED"` au schéma SQLite KG (migration)
- `KnowledgeGraph.add_fact()` accepte `confidence_label` param
- `KGBridge` : règles d'inférence basiques (si A-emploie->B et B-emploie->C → A-emploie_indirect->C, label INFERRED)
- CLI : `memos kg-add-fact ... --label INFERRED`
- REST : `POST /api/v1/kg/facts` accepte `confidence_label`
- Dashboard : filtres par label

---

## [ ] P19 — Miner Incrémental (SHA-256 Cache + --update)
**Objectif :** `memos mine` ne re-minera pas les fichiers déjà minés — SHA-256 cache persistant.

Inspiré de mempalace verbatim storage : éviter les re-imports redondants.

À implémenter dans `src/memos/miner/` :
- `MinerCache` classe dans `src/memos/miner/cache.py` — SQLite `(path, sha256, mined_at, memory_ids)`
- `mine()` : skip si `sha256(file) == cache[path].sha256`
- `mine --update` : force re-mine même si déjà vu (remplace les mémoires existantes du fichier)
- `mine --diff` : ne mine que les nouveaux chunks vs le cache
- CLI : `memos mine-status <path>` — affiche quels fichiers sont dans le cache
- Intégration : le cache SQLite est stocké dans `~/.memos/mine-cache.db`

---

## [ ] P20 — Hybrid Retrieval (Semantic + Keyword BM25)
**Objectif :** Réduire de ~30% le bruit dans le recall en combinant recherche sémantique et keyword.

Inspiré de mempalace : semantic top-50 → BM25 rerank → top-K final.

À implémenter dans `src/memos/retrieval.py` :
- `HybridRetriever` class
- Phase 1 : semantic recall top-50 (via backend existant)
- Phase 2 : BM25 score sur les 50 résultats (rank_bm25 ou implémentation maison)
- Phase 3 : score final = `alpha * semantic + (1-alpha) * bm25` (alpha=0.7 par défaut)
- `MemOS.recall()` accepte `retrieval_mode: str = "hybrid"` ("semantic", "keyword", "hybrid")
- CLI : `memos recall "<query>" --mode hybrid`
- REST : `POST /api/v1/recall` accepte `retrieval_mode`
- Dépendance optionnelle : `rank-bm25` (ajout dans `pyproject.toml` extras)

---

## [ ] P21 — Community Wiki (Leiden Graph + Index Navigable)
**Objectif :** Wiki navigable organisé par communautés de concepts, inspiré du LLM wiki pattern de Karpathy.

Karpathy : 71x moins de tokens vs fichiers bruts, navigation communauté→page→backlinks.

À implémenter :
- Leiden community detection sur le KG (bibliothèque `leidenalg` ou algo maison BFS clusters)
- `memos wiki-graph` — génère un wiki structuré par communautés
  - `index.md` — catalogue auto-généré (une ligne par communauté + top entities)
  - `log.md` — journal d'activité append-only (chaque ingest ajoute une entrée)
  - `communities/<id>.md` — page par communauté avec entités, faits, backlinks
  - "god nodes" — entités présentes dans 3+ communautés, page dédiée
- Update incrémental : `memos wiki-graph --update` ne regénère que les pages touchées
- CLI : `memos wiki-graph --output ./wiki/`, `memos wiki-graph --community <id>`
- Dépendance optionnelle : `leidenalg` ou `python-igraph`

---

## [ ] P22 — URL Ingest (Tweet, arXiv, PDF, Webpage)
**Objectif :** `memos ingest-url <url>` — ingère n'importe quelle URL dans MemOS sans setup manuel.

Sources supportées :
- `https://arxiv.org/abs/...` → abstract + titre + auteurs → mémoires tagées `arxiv`, `paper`
- `https://twitter.com/...` ou `x.com` → texte du tweet → tag `tweet`, `author:<handle>`
- `*.pdf` → extraction texte (PyMuPDF ou pdfplumber) → chunking intelligent
- Toute URL HTML → extraction article (readability ou trafilatura) → chunking

À implémenter dans `src/memos/ingest/url.py` :
- `URLIngestor` classe avec routing par domaine
- `ingest(url: str, tags: list[str] = []) -> list[Memory]`
- Dépendances optionnelles : `httpx`, `trafilatura`, `PyMuPDF` (extras `[ingest]`)
- CLI : `memos ingest-url <url> [--tags tag1,tag2]`
- REST : `POST /api/v1/ingest/url` body `{"url": "...", "tags": [...]}`

---

## [ ] P23 — Speaker Ownership (Conversation Miner)
**Objectif :** Dans le conversation miner, attribuer chaque mémoire au bon speaker.

Actuellement : toutes les lignes d'un transcript vont dans le même namespace.

À implémenter dans `src/memos/miner/conversation.py` :
- Parsing des formats courants : `Speaker: message`, `[HH:MM] Speaker: message`, markdown bold `**Speaker:**`
- `mine_conversation(path, namespace_prefix="conv", per_speaker=True)`
  - Si `per_speaker=True` : namespace = `{namespace_prefix}:{speaker}` par speaker
  - Tags auto : `speaker:{name}`, `conversation`, `date:{YYYY-MM-DD}`
- CLI : `memos mine-conversation <path> --per-speaker`
- REST : `POST /api/v1/mine/conversation` accepte `per_speaker: bool`

---

## [ ] P24 — Memory Compression (AAAK pour mémoires décayées)
**Objectif :** Compresser les mémoires très décayées (importance < 0.1) en résumés agrégés.

Inspiré de AAAK compression pattern : éviter accumulation de mémoires mortes qui polluent le recall.

À implémenter dans `src/memos/compression.py` :
- `MemoryCompressor` classe
- `compress(items: list[MemoryItem], threshold=0.1) -> CompressionResult`
  - Grouper les mémoires décayées par tags communs
  - Pour chaque groupe : créer une mémoire résumé (concaténation des contenus, importance = 0.15)
  - Supprimer les originaux
  - Retourner `CompressionResult(compressed_count, summary_count, freed_bytes)`
- Mode sans LLM : concaténation simple avec séparateur (`" | "`)
- Mode LLM optionnel : résumé via Ollama si disponible
- CLI : `memos compress [--dry-run] [--threshold 0.1]`
- REST : `POST /api/v1/compress` body `{"threshold": 0.1, "dry_run": true}`
- Cron : auto-compression hebdomadaire si mémoires décayées > 100

---
# ═══════════════════════════════════════════════════════
#  FUSION — Second Brain style Obsidian (mempalace + Karpathy + graphify)
#  Ces 3 priorités transforment les features séparées en un cerveau unifié.
# ═══════════════════════════════════════════════════════

## [ ] P25 — Unified Brain Search (Memories + Wiki + KG en une requête)
**Objectif :** Une seule requête cherche dans les 3 couches simultanément, résultats rankés par pertinence avec source label.

Actuellement : `recall` cherche dans les mémoires, `wiki-living search` cherche dans les pages wiki, le KG est interrogé séparément. Un agent doit faire 3 appels pour tout voir.

À implémenter dans `src/memos/brain.py` :
- `BrainSearch` classe
- `search(query: str, top_k=10) -> BrainSearchResult`
  ```python
  BrainSearchResult:
    memories: list[ScoredMemory]      # semantic recall
    wiki_pages: list[WikiHit]         # living wiki fulltext
    kg_facts: list[KGFact]            # facts liés aux entités détectées
    entities: list[str]               # entités extraites de la query
  ```
- Ranking fusionné : score normalisé par source, interleaving intelligent
- REST : `POST /api/v1/brain/search` body `{"query": "...", "top_k": 10}`
- MCP tool : `brain_search` — remplace les appels séparés `memory_search` + wiki + KG pour les agents
- CLI : `memos brain-search "<query>"` — output structuré (memories | wiki | kg sections)
- Dashboard : barre de recherche globale en haut du dashboard D3.js connectée à ce endpoint

Inspiré de :
- **graphify** : subgraph extraction par entité détectée
- **Karpathy** : index.md comme point d'entrée unique
- **mempalace** : hybrid retrieval (semantic + keyword)

---

## [ ] P26 — Graph ↔ Wiki Bridge (Dashboard cliquable → Wiki pages)
**Objectif :** Connecter le dashboard D3.js et le wiki vivant — cliquer un nœud ouvre sa page wiki ; les pages wiki montrent leurs voisins de graphe.

Actuellement : le dashboard D3.js affiche les nœuds/arêtes du KG mais ils sont "morts" (pas de lien). Les pages wiki existent mais sont inaccessibles depuis le graphe.

À implémenter :
**Côté API :**
- `GET /api/v1/brain/entity/{name}` — page complète d'une entité :
  ```json
  {
    "entity": "Alice",
    "wiki_page": "...",          // contenu markdown du wiki vivant
    "memories": [...],           // top-5 mémoires liées
    "kg_facts": [...],           // tous les faits KG actifs
    "kg_neighbors": [...],       // entités directement liées
    "backlinks": [...],          // pages wiki qui mentionnent cette entité
    "confidence_labels": {...}   // EXTRACTED/INFERRED/AMBIGUOUS counts
  }
  ```
- `GET /api/v1/brain/entity/{name}/graph` — sous-graphe JSON (ego network depth=2) pour D3.js

**Côté Dashboard (JS inline dans `api/__init__.py`) :**
- Clic sur un nœud D3.js → appel `GET /api/v1/brain/entity/{name}` → slide-in panel latéral
- Panel affiche : wiki page (rendu markdown) + top mémoires + bouton "open full page"
- Backlinks : liste des autres entités qui référencent cette entité → clic = navigation

**Wiki pages :**
- Ajouter section `## Graph Neighbors` auto-générée dans chaque page wiki vivant
- Ajouter frontmatter `kg_facts_count` et `backlinks_count`

Inspiré de :
- **graphify** : entity detail view avec faits + neighbours
- **Karpathy** : god nodes + backlinks navigation
- **Obsidian** : graph view cliquable → page

---

## [ ] P27 — Obsidian Vault Export (`[[wikilinks]]` + graph.json)
**Objectif :** Exporter tout le Second Brain MemOS comme un vault Obsidian standard — ouvrable directement dans Obsidian, Logseq, Foam, etc.

À implémenter dans `src/memos/export_obsidian.py` :
- `ObsidianExporter` classe
- `export(output_dir: str)` — génère la structure :
  ```
  vault/
  ├── _index.md          # catalogue (liens vers toutes les pages)
  ├── _log.md            # journal d'activité
  ├── _graph.json        # format Obsidian graph data
  ├── entities/
  │   ├── Alice.md       # page entité avec [[backlinks]]
  │   └── Project-X.md
  ├── memories/
  │   ├── decisions.md   # mémoires groupées par type-tag
  │   └── milestones.md
  └── kg/
      └── facts.md       # tous les faits KG en table markdown
  ```
- Format `[[wikilinks]]` dans chaque page — liens inter-pages auto-générés depuis les entités détectées
- Frontmatter YAML standard Obsidian : `tags`, `aliases`, `created`, `modified`
- `graph.json` : format compatible Obsidian graph plugin (nodes + edges avec weights)
- CLI : `memos export --format obsidian --output ./vault/`
- REST : `GET /api/v1/export/obsidian` → ZIP download du vault complet

Inspiré de :
- **graphify** : subgraph export, entity confidence labels dans le frontmatter
- **Karpathy** : structure index.md + community pages + god nodes
- **mempalace** : verbatim storage → contenu fidèle, pas de réécriture LLM

---
# ═══════════════════════════════════════════════════════
#  V1 RELEASE CHECKLIST — les 5 bloquants avant de taguer v1.0.0
# ═══════════════════════════════════════════════════════

## [ ] P28 — API Authentication (Bearer Token + Namespace Keys)
**Priorité : CRITIQUE — bloquant v1**
**Objectif :** Sécuriser l'API REST et isoler les namespaces par agent.

Sans auth, n'importe quel process sur le réseau peut lire/écrire toutes les mémoires de tous les agents.

À implémenter dans `src/memos/api/auth.py` :
- `API_KEY` env var → master key (accès total)
- `MEMOS_NAMESPACE_KEYS` env var → JSON map `{"orion": "key1", "specter": "key2"}` (clé par namespace)
- FastAPI dependency `require_auth(request)` — vérifie `Authorization: Bearer <key>`
- Si clé de namespace → force `namespace` dans la requête (pas d'accès cross-namespace)
- Si master key → accès total (utile pour le dashboard, l'admin)
- `GET /api/v1/auth/whoami` — retourne namespace autorisé + permissions
- Middleware : log les tentatives d'accès non autorisées
- Si `API_KEY` non configuré → mode open (backward compat, log warning au démarrage)

Config docker-compose :
```yaml
- API_KEY=<master-key>
- MEMOS_NAMESPACE_KEYS={"orion":"<key>","specter":"<key>","tachikoma":"<key>"}
```

---

## [ ] P29 — Memory Deduplication (Near-duplicate Detection)
**Priorité : CRITIQUE — bloquant v1**
**Objectif :** Empêcher l'accumulation de mémoires dupliquées lors des re-imports.

Sans dédup, miner le même fichier deux fois double les mémoires → recall bruité, stats faussées.

À implémenter dans `src/memos/dedup.py` :
- `DedupEngine` classe
- `is_duplicate(content: str, existing: list[MemoryItem], threshold=0.95) -> MemoryItem | None`
  - Exact match : SHA-256 sur le contenu normalisé (trim + lowercase) → O(1)
  - Near-dup : Jaccard sur trigrams si aucun exact match → retourne le plus proche si ≥ threshold
- `MemOS.learn()` appelle `DedupEngine.is_duplicate()` avant d'insérer
  - Si doublon exact → skip silencieux, retourne l'original
  - Si near-dup → skip avec warning log, retourne l'original
  - `learn(..., allow_duplicate=True)` → bypass pour les cas légitimes
- CLI : `memos dedup-check "<text>"` — vérifie si une mémoire similaire existe déjà
- REST : `POST /api/v1/dedup/check` body `{"content": "..."}` → `{"is_duplicate": bool, "match": {...}}`
- Batch dedup : `memos dedup-scan [--fix]` — scanne toutes les mémoires, liste/supprime les doublons

---

## [ ] P30 — Namespace Management API
**Priorité : HAUTE — bloquant v1 multi-agent**
**Objectif :** API REST complète pour gérer les namespaces — indispensable pour 5 agents OpenClaw.

Actuellement : les namespaces existent en CLI mais invisible depuis l'API → aucun outil agent ne peut gérer ses propres espaces.

À implémenter dans `src/memos/api/__init__.py` :
- `GET /api/v1/namespaces` — liste tous les namespaces (nom, nb mémoires, taille, dernière activité)
- `POST /api/v1/namespaces` body `{"name": "orion", "description": "SRE agent"}` — crée un namespace
- `GET /api/v1/namespaces/{name}` — stats détaillées (nb mémoires, top tags, dernière écriture)
- `DELETE /api/v1/namespaces/{name}` — supprime namespace + toutes ses mémoires (confirmation required)
- `POST /api/v1/namespaces/{name}/export` — export JSON du namespace
- `POST /api/v1/namespaces/{name}/import` — import JSON dans le namespace
- MCP tool : `namespace_list`, `namespace_stats`
- CLI : `memos namespaces list`, `memos namespaces delete <name>`

---

## [ ] P31 — Advanced Recall Filters (Date, Importance, Tag Logic)
**Priorité : HAUTE — qualité v1**
**Objectif :** Recall structuré pour les requêtes agent complexes — pas juste query+tags+top_k.

À implémenter :
- `POST /api/v1/recall` body enrichi :
  ```json
  {
    "query": "...",
    "tags": {"include": ["project-x"], "exclude": ["archived"], "mode": "AND"},
    "importance": {"min": 0.3, "max": 1.0},
    "created_after": "2026-01-01",
    "created_before": "2026-04-01",
    "top_k": 10,
    "retrieval_mode": "hybrid"
  }
  ```
- `GET /api/v1/memories` query params : `tag=x&tag=y&min_importance=0.3&after=2026-01-01&sort=importance`
- `src/memos/query.py` : `MemoryQuery` dataclass + `QueryEngine.execute(query, store)`
- Tag logic : `include` (must have ANY), `require` (must have ALL), `exclude` (must not have)
- MCP tool `memory_search` enrichi avec les nouveaux paramètres
- CLI : `memos recall "<query>" --min-importance 0.5 --after 2026-01-01 --tags project-x`

---

## [ ] P32 — PyPI Release + README v1
**Priorité : HAUTE — condition nécessaire pour v1.0.0**
**Objectif :** `pip install memos-agent` fonctionne. Le README est la documentation de référence.

À faire :
- Renommer le package PyPI en `memos-agent` (éviter conflit avec `memos` existant)
- `pyproject.toml` : bump version → `1.0.0`, description complète, classifiers, keywords
- GitHub Actions workflow `publish.yml` : build + push PyPI sur tag `v1.*`
- README complet :
  - Quick start (3 commandes)
  - MCP config : OpenClaw, Claude Code, Cursor (exemples copy-paste)
  - Backends : memory/json/chroma/qdrant — quand utiliser lequel
  - Docker one-liner avec variables d'env
  - API reference (lien vers `/docs` Swagger auto-généré)
  - Badge PyPI, Docker, coverage
- `CHANGELOG.md` : entrées depuis v0.29.0 jusqu'à v1.0.0
- GitHub Release `v1.0.0` avec notes de release
