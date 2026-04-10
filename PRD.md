# MemOS — Product Requirements Document (PRD)

**Version:** v0.2  
**Status:** Draft  
**Product:** MemOS  
**Tagline:** The memory layer every LLM agent should use instead of brute-force context injection.

---

## 1. Vision

MemOS is a Memory Operating System for LLM agents. It captures, structures, relates, synthesizes, corrects and serves the right context at the right time, without having to reload massive chat logs or RAG chunks every turn.

Instead of treating memory as an afterthought (chat history + vector DB + a few ad-hoc summaries), MemOS is a dedicated memory layer that:

- mines raw conversations and events into structured memory units,
- compiles them into a living wiki and knowledge graph,
- maintains them over time (reinforcement, decay, correction, versioning),
- returns compact, task-specific context packs for agents.

MemOS draws inspiration from four main sources:

- **MemPalace** — spatial / navigable memory structures and mental “rooms”.
- **Karpathy’s LLM Knowledge Base / Wiki** — compiling raw text into a living knowledge base rather than re-running RAG over raw docs.
- **Obsidian & knowledge graphs** — backlinks, graph view, emergent structure, entity pages.
- **Nexus-style orchestration** — consistent handling of agents, tools, sessions, skills and memory spaces.

---

## 2. Problem

Today, most agents rely on a simple but expensive pattern:

- Store chat history.
- Sometimes add a vector store or RAG.
- Re-inject large chunks of logs or retrieved text every time.

This leads to:

- high token usage and latency,
- noisy context with mixed signal and irrelevant history,
- poor long-term continuity across sessions,
- weak personalization per user / project / agent,
- memory that is hard to inspect, correct or reason about.

At the same time:

- Agent builders increasingly want **persistent, structured, inspectable memory**, not just a vector DB.
- There is strong interest in “memory-native” agents that can reuse skills, facts and preferences across tasks, with clear benefits in token savings and performance.

MemOS aims to be the **standard memory layer** that solves this coherently.

---

## 3. Goals

### 3.1 Primary Goal

Provide a **local-first, framework-agnostic, inspectable memory OS** for LLM agents that:

- stores what matters (facts, preferences, decisions, tasks, skills, tools, episodes),
- forgets or de-prioritizes what becomes obsolete,
- retrieves only context that is relevant for the current task,
- explains and visualizes what the agent “knows”,
- composes memory across agents, users, projects and tools in a controlled way.

### 3.2 Secondary Goals

- Reduce tokens consumed by context injection versus naive chat-history replay.
- Improve continuity across sessions and tasks for a given user / agent / project.
- Make memory **auditable and correctable** (version history, diffs, rollbacks).
- Offer a self-hosted, local-first alternative with multiple backends (JSON, SQLite, vector DBs, etc.).

---

## 4. Target Users

### 4.1 Agent Builders

Developers / AI engineers who build agents using:

- Claude Code / MCP,
- OpenClaw,
- Cursor / dev environments,
- custom agent frameworks.

They want a plug-in memory layer with:

- **MCP support**,
- **HTTP API**,
- **Python SDK**,
- **CLI** for local workflows.

### 4.2 Advanced Self-Hosters

Users who run local LLM setups and want:

- persistent, structured, inspectable memory,
- no forced cloud dependency,
- Docker / local-first setup,
- manageable exports and backups.

### 4.3 Multi-Agent / Team Environments

Teams that run multiple agents and want:

- isolated memory per agent, user, project or environment,
- shared memory spaces when needed (e.g. team knowledge base),
- observability on what each agent knows and uses.

---

## 5. Value Proposition

**MemOS replaces “chat logs + generic RAG + hacks” with a dedicated memory OS.**

It offers:

- **Token savings:** smaller, more relevant context packs instead of replaying full logs.
- **Continuity:** persistent memory across sessions, tasks and tools.
- **Personalization:** stable preferences, decisions and skills per user / project / agent.
- **Observability:** knowledge graphs, living wiki, history, diffs and dashboards.
- **Composability:** namespaces / cubes that can be isolated or shared between agents.

---

## 6. Design Principles

1. **Selective retrieval over raw replay**
 Retrieve only what is needed for the current task, not all past text.

2. **Structured memory over flat logs**
 Memory is stored as typed units: facts, episodes, preferences, decisions, tasks, skills, tool traces, entity pages.

3. **Inspectable by design**
 Memory must be visualizable, explorable, correctable and versioned, not a black-box embedding store.

4. **Composable across agents**
 Memory spaces (namespaces / cubes) can be per-agent, per-user, per-project, per-org, with controlled sharing.

5. **Self-maintaining**
 Memory is not static: it decays, is reinforced, summarized, pruned, merged and corrected over time.

---

## 7. Product Scope

MemOS is structured as three main layers:

1. **Capture:** how raw reality becomes memory.
2. **Memory Engine:** how memory is stored, maintained and retrieved.
3. **Knowledge Surface:** how memory is exposed to humans and other systems.

### 7.1 Capture Layer

#### 7.1.1 Learn / Save

- Store new memory units from plain text or structured payloads.
- Attach metadata: type, tags, importance, namespace, source, timestamps, confidence.

#### 7.1.2 Batch Learn

- Ingest multiple memories in one call (backfill, migrations, bulk imports).

#### 7.1.3 Mine (Memory Mining)

- Ingest raw sources (chat exports, logs, agent traces, docs) and **mine** them into memory units:
 - chunking and deduplication,
 - entity / fact / preference / decision extraction,
 - tagging and scoring,
 - mapping into types (fact, episode, task, skill, etc.).

- Entry points: CLI (`memos mine ...`), API endpoints and SDK helpers.

#### 7.1.4 Imports

- Built-in importers for:
 - Claude chat / Claude Code exports,
 - OpenClaw / other agent orchestrators,
 - Slack / Discord / Telegram / other chat logs,
 - generic JSON/Markdown/HTML sources.

### 7.2 Memory Engine Layer

#### 7.2.1 Core Data Model

Every memory unit should support at least:

- `id`
- `content` (text / structured)
- `type` (fact, episode, preference, decision, task, skill, tool_trace, entity_page, etc.)
- `tags`
- `importance`
- `namespace` / `cube`
- `source` (agent, tool, user, system)
- `created_at`, `updated_at`
- `confidence`
- `valid_from`, `valid_to` (optional)
- `links` (references to other memories / entities)
- `version` info

#### 7.2.2 Semantic + Hybrid Recall

- **Recall:** semantic search over memories (vector-based).
- **Search:** keyword / hybrid (BM25 + vector) retrieval.
- Support filters:
 - by namespace / cube,
 - by type,
 - by tags,
 - by date range,
 - by importance threshold.

#### 7.2.3 Query-specific Context Compilation

- `memory_context_for(query, namespace)` returns a **compact context pack** for a given question or task:
 - ranked and filtered memories,
 - relevant facts from the knowledge graph,
 - short synthesized context paragraph(s) for direct injection.

- The model should think in terms of **compiling** a mini knowledge base for the current request, not just listing raw snippets.

#### 7.2.4 Wake-up Memory

- `memory_wake_up(agent_or_user)` returns a **boot packet** for a session:
 - identity / profile,
 - long-term preferences,
 - current goals,
 - last important events and decisions.

#### 7.2.5 Enriched Recall

- `memory_recall_enriched` enriches retrieved memories with:
 - related entities / facts from the graph,
 - relevant wiki pages,
 - a short summary.

#### 7.2.6 Memory Lifecycle

- **Reinforce:** increase importance / confidence of useful memories.
- **Decay:** gradually lower importance / confidence of unused or stale memories.
- **Prune:** automatically remove memories below certain thresholds or marked as noise.
- **Forget / Delete:** manual or API-driven deletion of memories (GDPR, privacy, cleanup).

#### 7.2.7 History, Diff, Rollback

- Every memory unit has a version history:
 - `history(id)` — timeline of changes,
 - `diff(id, v1, v2)` — compare versions,
 - `rollback(id, v)` — restore previous version.

- Supports auditability, debugging and “time-travel”.

#### 7.2.8 Recall-at / Snapshot-at

- `recall_at(time, query, namespace)` — what would recall have returned at time T.
- `snapshot_at(time, namespace)` — view of the memory graph / store at time T.

Provides tools for debugging, retrospective analysis and reproducibility.

#### 7.2.9 Feedback & Correction

- Allow agents or users to give feedback:
 - “this memory is wrong”,
 - “this is outdated”,
 - “this is incomplete”,
 - “this is more important than you think”.

- MemOS should:
 - either correct in-place with versioning,
 - or create a corrected memory unit linked to the original,
 - update the wiki / graph accordingly.

#### 7.2.10 Task Memory

- Capture structured **task memories** at the end of a run:
 - task id / description,
 - plan and steps,
 - tools used,
 - outcome,
 - issues,
 - lessons learned.

- Auto-generated via **task summarization** from logs / traces.

#### 7.2.11 Skill Memory

- Learn procedural skills from repeated successful flows:
 - how to perform a certain operation,
 - how to debug a common class of errors,
 - how to interact with a particular API / system.

- Skills are reusable “recipes” stored in memory and refinable over time.

#### 7.2.12 Tool Memory

- Store traces about tools:
 - which tool,
 - which inputs,
 - success / failure,
 - latency,
 - cost,
 - context in which it was effective.

- Used to improve future agent planning (which tool to call when).

#### 7.2.13 Multi-Agent Memory Spaces

- Namespaces / cubes for:
 - per-agent memory,
 - per-user memory,
 - per-project memory,
 - shared team memory.

- Configurable read/write policies:
 - agent A can read team and project spaces, but only write its own, etc.

#### 7.2.14 Multi-Modal Memory (Future)

- Design for future support of:
 - images,
 - documents,
 - charts,
 - other multimodal embeddings.

#### 7.2.15 Memory Scheduling

- Background jobs and scheduling for:
 - batch mining / ingestion,
 - consolidation / deduplication,
 - decay / pruning runs,
 - reindexing and refresh tasks,
 - conflict detection and resolution.

---

### 7.3 Knowledge Surface Layer

#### 7.3.1 Knowledge Graph

- Internal representation of entities, relations, temporal edges.
- APIs:
 - `kg_add_fact`,
 - `kg_query_entity`,
 - `kg_neighbors`,
 - `kg_path`,
 - `kg_timeline`.

- UI: graph view (D3.js or similar), focused on exploration and debugging of what the agent “knows”.

#### 7.3.2 Living Wiki

- Compile long-term memory into **entity / topic pages**:
 - aggregated facts,
 - relevant episodes,
 - decisions,
 - tasks,
 - links to other pages,
 - source references.

- Operations:
 - `wiki_living_update(entity/topic)` — recompute / refresh page,
 - `wiki_living_read` — read compiled page,
 - `wiki_living_search` — find pages by name / content,
 - `wiki_living_lint` — detect contradictions, orphans, low-confidence sections.

#### 7.3.3 Dashboard & Memory Viewer

- Web UI to:

 - explore memories by namespace / type / tags,
 - view recall logs (what was returned and why),
 - inspect graph and wiki pages,
 - see decay / prune candidates,
 - navigate version history and diffs,
 - monitor scheduler jobs and ingestion pipelines.

#### 7.3.4 Export, Backup, Portability

- Export / import capabilities:

 - export namespace / cube,
 - export by time range,
 - export specific entities / pages / graphs.

- Support portable formats (e.g. Parquet, JSON, Markdown wikis), to allow:

 - backup / restore,
 - migration between backends,
 - analysis in external tools.

---

## 8. Integrations

### 8.1 MCP (Model Context Protocol)

- First-class MCP server exposing MemOS as a memory tool:
 - learn / recall / context-for / wake-up / feedback,
 - multi-namespace handling,
 - configuration via MCP manifest.

### 8.2 HTTP API

- REST-style API exposing all core operations:
 - capture, recall, mining, graph, wiki, lifecycle, feedback, task/skill, exports.

### 8.3 Python SDK

- Python client with high-level methods:
 - `learn()`, `mine()`, `recall()`, `context_for()`, `wake_up()`,
 - `add_fact()`, `query_entity()`, `timeline()`,
 - `update_wiki()`, `get_wiki()`,
 - `reinforce()`, `decay()`, `rollback()`, etc.

### 8.4 CLI

- Dev-friendly CLI:
 - `memos learn`, `memos mine`, `memos recall`,
 - `memos graph`, `memos wiki-living`,
 - `memos history`, `memos diff`, `memos rollback`,
 - `memos serve` to run the server + dashboard.

---

## 9. User Stories

- As an agent builder, I want to plug MemOS via MCP so my agent automatically reads/writes memory without heavy refactor.
- As a user, I want the agent to remember my preferences and recent context automatically in new sessions.
- As an operator, I want to see what memories were used to answer a request and be able to correct them.
- As a self-hoster, I want to pick the backend (local files, SQLite, vector DB) without changing application code.
- As a team, I want multiple agents with their own spaces, plus a shared knowledge base for the org.
- As a dev, I want to mine existing transcripts into structured memory without manually rewriting them.

---

## 10. MVP Definition

### 10.1 MVP Scope

**Capture**

- Learn / batch learn.
- Mine from at least one chat format (e.g. Claude / OpenClaw / ChatGPT).
- Basic imports from local files.

**Memory Engine**

- Semantic recall + simple filters.
- Query-specific `context_for`.
- `wake_up` bootstrap.
- Importance; basic decay + prune.
- Forget / delete.
- Namespaces for per-agent / per-user / per-project.

**Knowledge Surface**

- Minimal graph endpoint (API + basic UI).
- Minimal dashboard to inspect memories and recall logs.

**Integrations**

- MCP, HTTP, Python SDK, CLI.

### 10.2 Post-MVP

- Full living wiki (update/search/lint).
- Feedback & correction workflows.
- Task memories and automatic task summarization.
- Tool memory and basic planning hints.
- Skill extraction / evolution.
- Advanced scheduler (async, priorities, isolation).
- Multi-cube composition and sharing policies.
- Multi-modal memory support.

---

## 11. KPIs

- Average token reduction per task/session vs naive “full history” injection.
- Percentage of agent calls that use `wake_up` at session start.
- Percentage of tasks using `context_for` before LLM generation.
- Recall usefulness score (explicit or implicit).
- Number of active memories per namespace (healthy range vs bloat).
- Rate of corrections / contradictions detected and resolved.
- Time to integrate MemOS via MCP into a new agent.
- Percentage of sessions that end with a task memory summary.

---

## 12. Acceptance Criteria

- Agents can integrate MemOS via MCP / HTTP / SDK without major refactors.
- A conversation export can be mined into structured memories and graph entities.
- For a given query, MemOS can produce a compact context pack without replaying full logs.
- Users / operators can inspect which memories were used to answer a query.
- Memory units can be reinforced, decayed, pruned, corrected, versioned and rolled back.
- At least one benchmark (internal) demonstrates real token savings and stable or improved task quality.

---

## 13. Risks

### 13.1 Naming / Positioning

- “MemOS” and “memos” are already used by other projects in the memory/note-taking space, which may cause confusion.
- MemOS must clearly position itself as **agent memory OS**, not just “yet another notes app” or “just a vector DB”.

### 13.2 Scope Creep

- The vision covers many advanced capabilities (graph, wiki, task/skill memory, scheduling, multimodal).
- The MVP must stay laser-focused on:
 - capture (learn + mine),
 - core memory engine (recall + context_for + lifecycle),
 - minimal knowledge surface (graph + basic dashboard).

### 13.3 Memory Quality

- The real differentiator is not storage, but **quality of recall**:
 - low noise,
 - high relevance,
 - correct temporal behavior,
 - good packaging for LLM consumption.

- Poor ranking / packaging would negate token savings and hurt UX.

---

## 14. Recommended README Pitch

> MemOS is a local-first Memory Operating System for LLM agents. 
> It mines raw conversations and events into structured memory, compiles them into a living wiki and knowledge graph, and returns only the context an agent actually needs — instead of replaying entire chat histories.
