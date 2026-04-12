# MemOS Roadmap

## v1.0.0 — Shipped (April 2026)

- [x] Core memory store (learn, recall, forget, prune, reinforce, decay)
- [x] 6 backends: memory, JSON, ChromaDB, Qdrant, Pinecone, local (sentence-transformers)
- [x] Hybrid retrieval (BM25 + semantic) with advanced filters
- [x] Recall explainability (score breakdown per component)
- [x] Deduplication enabled by default (SHA-256 exact + Jaccard near-duplicate)
- [x] Versioning & time-travel (history, diff, rollback, recall-at, snapshot-at)
- [x] Memory compression + compaction engine
- [x] TTL, ACL (RBAC), multi-agent sharing, conflict resolution
- [x] Temporal knowledge graph + auto KG extraction
- [x] Living wiki (update/read/search/lint) + graph-wiki bridge
- [x] Unified brain search (memories + wiki + KG)
- [x] Mine from 7 chat formats + URL ingest + speaker ownership
- [x] Portable markdown export + Parquet export/import
- [x] MCP server (HTTP + stdio, 12 tools)
- [x] REST API (20+ endpoints, SSE streaming, auth, rate limiting)
- [x] CLI (30+ commands) + Python SDK
- [x] Second brain dashboard (D3.js graph view)
- [x] Docker + CI (tests + PyPI publish workflow)
- [x] Package: `pip install memos-agent` — 1434 tests

---

## v1.1 — Polish & Observability (Q2 2026)

- [ ] Align README and docs with PRD (Capture / Engine / Knowledge Surface)
- [ ] Document the golden path: `learn → recall → context_for → wake_up → reinforce/decay`
- [ ] Clarify when to use `recall`, `search`, `memory_context_for`, `memory_recall_enriched`
- [ ] Provide example integrations:
  - [ ] Claude Code / MCP minimal example
  - [ ] OpenClaw / orchestrator example
- [ ] Harden existing importers & mining flows

---

## v2.0.0 — Agent-Native Memory (April 2026) ✅ SHIPPED

Inspired by MemPalace, Karpathy Wiki, Obsidian, Graphify, GitNexus.

### Knowledge Quality
- [x] **P1: Confidence labels** on all KG edges (EXTRACTED/INFERRED/AMBIGUOUS)
- [x] **P2: Lint command** — detect contradictions, orphan entities, coverage gaps
- [x] **P7: Backlinks** as first-class KG queries
- [x] **P8: Compounding ingest** — auto-update wiki pages when memories are added
- [x] **P9: Token compression reporting** — quantify token savings in `memos stats`

### Agent Integration
- [x] **P3: Wake-up compact mode** — ~200 token compressed identity injection
- [x] **P4: Pre/Post MCP hooks** — auto-capture and context injection
- [x] **P5: Staleness detection** — warn when sources need re-mining (`memos mine-stale`)
- [x] **P10: Skills-as-markdown** — packaged workflows for Claude Code / Cursor (`memos skills-export`)

### Export & Interop
- [x] **P6: Obsidian-compatible export** — markdown with `[[wikilinks]]` + YAML frontmatter

### Dashboard
- [x] Obsidian-style layout: ribbon + namespace/tag file tree + graph
- [x] KG edges (dashed) overlaid on memory edges (solid)
- [x] Wiki view — browse living wiki pages with rendered markdown + wikilinks
- [x] Memory Palace view — wing/room hierarchy with memory highlighting
- [x] Time-travel slider — filter graph to any past date
- [x] Right slide-in entity/detail panel

### Stats
- 1534 tests passing
- Package: `pip install memos-agent`

---

## v3.0.0 — Memory OS Orchestration (Q4 2026)

Inspired by GitNexus blast radius, MemPalace temporal validity, Graphify multimodal,
Karpathy compilation philosophy.

### Phase A — Temporal Intelligence

- [ ] **Temporal validity windows** on KG edges (`valid_from`, `valid_to`)
  — Facts have expiry; retroactive queries: `kg_query_as_of(entity, ts)`
- [ ] **Contradiction detection** — semantic overlap scan across memories and KG;
  flag conflicting facts for review
- [ ] **Blast radius / impact analysis** — pre-compute downstream effects when a fact changes;
  `memory_impact(id, direction="downstream")`
- [ ] **God nodes detection** — rank entities by degree centrality;
  surface "what everything connects through" in dashboard + MCP tool

### Phase B — Specialist Agent Architecture

- [ ] **Per-agent namespaces with identity** — `--agent reviewer` persona;
  agents accumulate focused expertise across sessions
- [ ] **Agent diaries** — structured session log per agent (what was decided, why);
  AAAK-style compression (lossy abbreviation for identity injection)
- [ ] **Rationale extraction pipeline** — detect "because", "in order to", "the reason is"
  in memories; store as explicit `rationale_for` KG triples
- [ ] **`memos compile`** — weekly full wiki recompilation from raw memories + KG;
  produces synthesis articles with cross-references (not just per-item updates)

### Phase C — Enriched MCP Tools

- [ ] **`memory_compare(A, B)`** — structured tradeoff analysis between two concepts/approaches
- [ ] **`memory_timeline(topic)`** — chronological evolution of a topic across memories
- [ ] **`memory_detect_contradictions()`** — returns conflicting fact pairs with confidence
- [ ] **`memory_suggest_next()`** — gap analysis: what's mentioned but never expanded?
- [ ] **`memory_impact(id)`** — blast radius: which downstream memories/decisions depend on this?
- [ ] Extend MCP server from 12 → 20+ tools

### Phase D — Multimodal Memory

- [ ] **Image ingestion** — `memos ingest image.png` via vision API;
  extract entities, describe, link to KG
- [ ] **Audio/video ingestion** — `memos ingest talk.mp4` via local Whisper;
  transcribe, chunk, mine into memories
- [ ] **Code AST ingestion** — `memos ingest src/` via Tree-sitter (14 languages);
  extract classes, functions, call graph, rationale comments
- [ ] **EXTRACTED/INFERRED/AMBIGUOUS** tagging on all multimodal extractions
- [ ] **Surprising connections** — cross-domain edge scoring (code ↔ doc ↔ conversation)

### Phase E — Memory Scheduler & Policies

- [ ] **Memory scheduler** — background jobs: mining, consolidation, decay, reindexing
- [ ] **Policy model** — per-namespace read/write rules; agent A can read team space, only write own
- [ ] **Evaluation benchmarks** — internal: token savings vs naive replay, LongMemEval R@5 score
- [ ] **Integration templates** — agent framework connectors (LangChain, AutoGen, CrewAI, Pydantic AI)

### Phase F — Advanced Dashboard

- [ ] **Graph cluster view** — Leiden community detection; nodes colored by community
- [ ] **Surprising connections widget** — "Top 5 unexpected cross-domain links this week"
- [ ] **Time-travel comparison** — diff two graph snapshots side-by-side
- [ ] **Wiki graph** — interactive graph where nodes are wiki pages, edges are `[[wikilinks]]`
- [ ] **Palace map** — spatial visualization of wings → rooms → memories
- [ ] **Recall logs** — inspect exactly which memories were used to answer recent queries
- [ ] **Scheduler dashboard** — monitor background jobs, ingestion pipelines, freshness indicators

---

## v4.0.0 — (2027+, research)

- [ ] Federated memory sharing between agents across machines
- [ ] Memory as a service — hosted MemOS for teams
- [ ] Evaluation suite: automated memory quality benchmarks (continuity, relevance, token savings)
- [ ] Fine-tuned embedding model specialized for memory retrieval
- [ ] Native mobile / desktop client (Obsidian-style vault browser)
