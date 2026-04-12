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

## NOW — v1.1 Polish & Observability (Q2 2026)

- [ ] Align README and docs with PRD (Capture / Engine / Knowledge Surface)
- [ ] Document the golden path: `learn → recall → context_for → wake_up → reinforce/decay`
- [ ] Clarify when to use `recall`, `search`, `memory_context_for`, `memory_recall_enriched`
- [ ] Improve dashboard UX (recall logs, freshness indicators, namespace nav)
- [ ] Provide example integrations (MCP + SDK):
  - [ ] Claude Code / MCP minimal example
  - [ ] OpenClaw / orchestrator example
- [ ] Harden existing importers & mining flows

---

## DONE — v2.0 Agent-Native Memory (April 2026)

Inspired by MemPalace, Karpathy Wiki, Obsidian, Graphify, GitNexus:

### Knowledge Quality
- [x] **P1: Confidence labels** on all KG edges (EXTRACTED/INFERRED/AMBIGUOUS)
- [x] **P2: Lint command** — detect contradictions, orphan entities, coverage gaps
- [x] **P7: Backlinks** as first-class KG queries
- [x] **P8: Compounding ingest** — auto-update wiki pages when memories are added
- [x] **P9: Token compression reporting** — quantify token savings in `memos stats`

### Agent Integration
- [ ] **P3: Wake-up context optimization** — ~200 token compressed identity injection
- [ ] **P4: Pre/Post MCP hooks** — auto-capture and context injection
- [ ] **P5: Staleness detection** — warn when sources need re-mining
- [ ] **P10: Skills-as-markdown** — packaged workflows for Claude Code / Cursor

### Export & Interop
- [ ] **P6: Obsidian-compatible export** — markdown with `[[wikilinks]]` + YAML frontmatter

### Memory Types
- [ ] Task memory (schema, auto-summarization from logs)
- [ ] Tool memory (traces, success/failure, planning hints)
- [ ] Skill memory (detect patterns, promote to reusable skills)
- [ ] Feedback & correction workflows

---

## LATER — v3.0 Memory OS Orchestration (Q4 2026+)

- [ ] Policy model for namespaces/cubes (read/write rules, sharing policies)
- [ ] Memory scheduler (background mining, consolidation, decay, reindexing)
- [ ] Multi-modal memory (images, documents, charts)
- [ ] Evaluation benchmarks (token savings, continuity, task quality)
- [ ] Integration templates for popular agent frameworks
