# MemOS v2.3 — 5 Features Implementation Plan

**Date:** 2026-04-16  
**Target:** Mars375/memos, branch `feat/5-features`  
**Method:** GSD via OpenCode, one subagent per task  

---

## Feature 1: Enriched KG Extraction

**Goal:** Expand `_FACT_PATTERNS` in `kg_bridge.py` from 4 regex → 15+ SVO patterns + add community detection + god nodes to the graph.

### Task 1.1: Expand SVO regex patterns in kg_bridge.py
**File:** `src/memos/kg_bridge.py`  
**What:** Add verb-based SVO patterns to `_FACT_PATTERNS`:
- `deployed`, `uses`, `runs`, `manages`, `owns`, `depends on`, `contains`, `supports`, `located in`, `part of`, `connected to`, `built with`, `hosts`
- General SVO fallback: `[CapitalizedEntity] [verb_ed] [something]` catching subject-verb-object triples
- Add unit tests in `tests/test_kg_bridge.py` (or extend `test_core.py`)

**Test:** `pytest tests/ -q -k "kg_bridge or extract"` must pass  
**Commit:** `feat: expand KG extraction with 15+ SVO patterns`

### Task 1.2: Add community detection (Leiden-like clustering)
**File:** `src/memos/knowledge_graph.py`  
**What:**
- Add `detect_communities()` method to `KnowledgeGraph` class
- Use simple label-propagation or connected-components on the KG adjacency list (no external deps)
- Return: `list[Community]` where Community = `{id, label, nodes: list[str], size: int}`
- Add API endpoint: `GET /api/v1/kg/communities`
- Add MCP tool: `kg_communities`

**Test:** `pytest tests/ -q` must pass  
**Commit:** `feat: add community detection to knowledge graph`

### Task 1.3: Add god nodes (top-degree hub entities)
**File:** `src/memos/knowledge_graph.py`  
**What:**
- Add `god_nodes(top_n=10)` method: returns entities sorted by degree (total facts as subject + object)
- Return: `list[{entity, degree, facts}]`
- Add API endpoint: `GET /api/v1/kg/god-nodes?top=10`
- Add MCP tool: `kg_god_nodes`

**Test:** `pytest tests/ -q` must pass  
**Commit:** `feat: add god nodes (top-degree entities) to KG`

---

## Feature 2: Hybrid Retrieval v2 (temporal + importance + rerank)

**Goal:** Upgrade from basic BM25 to MemPalace-inspired hybrid v4 with temporal proximity, importance boosting, and optional LLM rerank.

### Task 2.1: Add temporal proximity boosting
**File:** `src/memos/retrieval/engine.py`  
**What:**
- In the `search()` method, add temporal proximity scoring: boost memories created within the same session/time-window as the query
- Add `RECENCY_PROXIMITY_WEIGHT` constant to `_constants.py`
- Factor into final score: `final += temporal_proximity_bonus * weight`
- Log score breakdown in `ScoreBreakdown`

**Test:** `pytest tests/test_retrieval.py -q`  
**Commit:** `feat: add temporal proximity boosting to retrieval`

### Task 2.2: Add importance-weighted retrieval
**File:** `src/memos/retrieval/engine.py`  
**What:**
- Factor `memory.importance` into the final score: `final += importance * IMPORTANCE_BOOST_WEIGHT`
- Already partially there (`IMPORTANCE_BOOST_WEIGHT` exists in constants) — wire it properly
- Add preference pattern extraction: if user queries same topic repeatedly, boost related memories

**Test:** `pytest tests/test_retrieval.py -q`  
**Commit:** `feat: add importance-weighted scoring to retrieval`

### Task 2.3: Add LLM rerank endpoint
**File:** `src/memos/retrieval/hybrid.py`, new `src/memos/retrieval/rerank.py`  
**What:**
- Create `LLMReranker` class with `rerank(query: str, candidates: list[RecallResult], top_n: int) -> list[RecallResult]`
- Uses a simple prompt: "Given query Q, rank these N items by relevance. Return ordered IDs."
- Works with any LLM via the existing embedder pattern (Ollama local, or API)
- Add API endpoint: `POST /api/v1/recall/rerank` with `query` and optional `top_n`
- Falls back gracefully if no LLM available (returns original order)
- Make it optional — controlled by config flag `reranking.enabled`

**Test:** `pytest tests/test_retrieval.py -q`  
**Commit:** `feat: add LLM reranking pipeline`

---

## Feature 3: Wiki Auto-Compilation (Karpathy-inspired)

**Goal:** Make the Living Wiki proactive — auto-update on every ingest, generate index.md and log.md, cascade entity updates.

### Task 3.1: Auto-update wiki on learn/ingest
**File:** `src/memos/core.py`, `src/memos/wiki_living.py`  
**What:**
- In `MemOS.learn()`, after saving memory, call `LivingWikiEngine.update_on_ingest(memory_id, content, tags)`
- This method should:
  1. Extract entities from content
  2. Find/create matching wiki pages
  3. Append content reference to those pages
  4. Update cross-references between pages
  5. Log the ingest in log.md
- Make it async/optional via config `wiki.auto_update: true`

**Test:** `pytest tests/test_wiki.py -q`  
**Commit:** `feat: auto-update wiki pages on every learn/ingest`

### Task 3.2: Auto-generate index.md
**File:** `src/memos/wiki_living.py`  
**What:**
- Enhance existing `generate_index()` to produce a proper Karpathy-style index.md:
  - Categories: Entities, Concepts, Sources, Topics
  - Each page listed with link + one-line summary + metadata (date, source count)
  - Sorted by relevance/recency
- Add API endpoint: `POST /api/v1/wiki/regenerate-index`
- Add MCP tool: `wiki_regenerate_index`

**Test:** `pytest tests/test_wiki.py -q`  
**Commit:** `feat: auto-generate Karpathy-style wiki index.md`

### Task 3.3: Query answers filed as wiki pages
**File:** `src/memos/brain.py`, `src/memos/wiki_living.py`  
**What:**
- Add `file_as_page(question, answer, tags)` method to LivingWikiEngine
- Brain search `/api/v1/brain/search` gets optional param `file_to_wiki: bool`
- When true, the answer is saved as a new wiki page with type="query-answer"
- Includes: question as title, answer as content, source memories as references
- Logged in log.md as "query-answer" entry

**Test:** `pytest tests/test_brain_search.py tests/test_wiki.py -q`  
**Commit:** `feat: file brain search answers as wiki pages`

### Task 3.4: Wiki lint (health-check)
**File:** `src/memos/wiki_living.py`  
**What:**
- Enhance existing `lint()` to check:
  - Contradictions between pages (same entity, conflicting info)
  - Orphan pages (no inbound links)
  - Missing cross-references (entity mentioned in page but no link)
  - Stale claims (older than N days without update)
  - Data gaps (concepts referenced but no page exists)
- Return structured report: `{issues: [{type, severity, page, detail}], summary: {orphan_count, contradiction_count, ...}}`
- Add API endpoint: `GET /api/v1/wiki/lint`
- Add MCP tool: `wiki_lint`

**Test:** `pytest tests/test_wiki.py -q`  
**Commit:** `feat: comprehensive wiki lint/health-check`

---

## Feature 4: Agent Diaries

**Goal:** Each agent gets its own wing + diary journal in the Palace. Agents can discover each other.

### Task 4.1: Agent wing auto-provisioning
**File:** `src/memos/palace.py`, `src/memos/core.py`  
**What:**
- Add `ensure_agent_wing(agent_name: str, description: str = "") -> dict` to PalaceIndex
- Creates wing named `agent:<name>` if not exists
- Creates default rooms: `diary`, `context`, `learnings`
- Add API endpoint: `POST /api/v1/palace/agents` with `{name, description}`
- Auto-call on first `learn()` with `namespace=agent_name`

**Test:** `pytest tests/test_palace.py -q`  
**Commit:** `feat: auto-provision agent wings in palace`

### Task 4.2: Agent diary append + retrieval
**File:** `src/memos/palace.py`  
**What:**
- Add `append_diary(agent_name: str, entry: str, tags: list[str] = None) -> str` to PalaceIndex
  - Creates a memory with the entry, assigns to `agent:<name>/diary` room
  - Adds tag `agent-diary` automatically
- Add `read_diary(agent_name: str, limit: int = 20) -> list[dict]` 
  - Returns last N diary entries for the agent
- Add API endpoints: `POST /api/v1/palace/diary`, `GET /api/v1/palace/diary/{agent}`
- Add MCP tools: `palace_diary_append`, `palace_diary_read`

**Test:** `pytest tests/test_palace.py -q`  
**Commit:** `feat: agent diary append and retrieval`

### Task 4.3: Agent discovery
**File:** `src/memos/palace.py`, `src/memos/mcp_server.py`  
**What:**
- Add `list_agents() -> list[{name, wing_id, diary_count, last_activity}]` to PalaceIndex
  - Lists all wings with prefix `agent:`
  - Returns metadata: diary entry count, last diary timestamp
- Add MCP tool: `palace_list_agents` (like MemPalace's `mempalace_list_agents`)
- This lets agents discover each other at runtime without bloating system prompt

**Test:** `pytest tests/test_palace.py -q`  
**Commit:** `feat: agent discovery via palace wings`

---

## Feature 5: Dashboard Intelligence

**Goal:** Make the dashboard proactive — show surprising connections, suggested questions, and community clusters.

### Task 5.1: Surprising connections API
**File:** `src/memos/brain.py`, `src/memos/api/routes/knowledge.py`  
**What:**
- Add `surprising_connections(top_n=5) -> list[{subject, object, predicate, score, reason}]` to BrainSearch
  - Cross-domain edges: entities from different communities/wings connected by a fact
  - Score: `composite = cross_community_bonus * fact_confidence * edge_rarity`
  - Include plain-English `reason` string
- Add API endpoint: `GET /api/v1/brain/connections?top=5`

**Test:** `pytest tests/test_brain_search.py -q`  
**Commit:** `feat: surprising connections API`

### Task 5.2: Suggested questions API
**File:** `src/memos/brain.py`, `src/memos/api/routes/knowledge.py`  
**What:**
- Add `suggest_questions(n=5) -> list[str]` to BrainSearch
  - Based on: god nodes with low exploration, orphan pages, data gaps from lint, recent facts without follow-up
  - Returns 4-5 natural language questions the knowledge base can uniquely answer
- Add API endpoint: `GET /api/v1/brain/suggestions?n=5`

**Test:** `pytest tests/test_brain_search.py -q`  
**Commit:** `feat: suggested questions API`

### Task 5.3: Dashboard JS — connections + suggestions panels
**File:** `src/memos/web/js/api.js`, `src/memos/web/js/panels.js`  
**What:**
- Add "🧠 Insights" panel to the dashboard ribbon (new button)
- Shows:
  - Top 5 surprising connections as clickable cards
  - Top 5 suggested questions as buttons
  - Community cluster cards (from Task 1.2)
  - God nodes (from Task 1.3) as highlighted graph nodes
- Wire up to the new API endpoints from 5.1 and 5.2
- Auto-refresh on dashboard load

**Commit:** `feat: dashboard insights panel with connections and suggestions`

---

## Execution Order

Tasks are ordered by dependency:
1. **Task 1.1** (KG regex) → unblocks 1.2, 1.3, 3.1
2. **Task 1.2** (communities) → unblocks 5.1, 5.3
3. **Task 1.3** (god nodes) → unblocks 5.1, 5.3
4. **Task 2.1** (temporal boost) → independent
5. **Task 2.2** (importance boost) → independent
6. **Task 2.3** (LLM rerank) → depends on 2.1, 2.2
7. **Task 3.1** (auto-update wiki) → depends on 1.1
8. **Task 3.2** (index.md) → independent
9. **Task 3.3** (query→wiki) → depends on 3.1
10. **Task 3.4** (wiki lint) → depends on 3.1
11. **Task 4.1** (agent wings) → independent
12. **Task 4.2** (diary) → depends on 4.1
13. **Task 4.3** (discovery) → depends on 4.1
14. **Task 5.1** (connections API) → depends on 1.2, 1.3
15. **Task 5.2** (suggestions API) → independent
16. **Task 5.3** (dashboard JS) → depends on 5.1, 5.2, 1.2, 1.3

**Parallelizable groups:**
- Group A: 1.1, 2.1, 3.2, 4.1, 5.2 (all independent)
- Group B: 1.2, 1.3, 2.2 (after 1.1)
- Group C: 2.3, 3.1, 4.2, 4.3 (after their deps)
- Group D: 3.3, 3.4, 5.1 (after their deps)
- Group E: 5.3 (last)
