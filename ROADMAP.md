# MemOS Roadmap

## Status Overview

- Core memory store: **Shipped**
- Developer interfaces (CLI, SDK, REST, MCP): **Shipped**
- Local-first / self-hosting (pip, Docker, multiple backends): **Shipped**
- Memory mining & imports: **Shipped (first wave)**
- Knowledge graph: **Shipped (base)**
- Living wiki: **Shipped (base)**
- Memory lifecycle (decay, prune, reinforce, versioning): **Shipped (base)**
- Inspectability (dashboard, graph, stats): **Partial**
- Team / policy memory: **Partial (namespaces only)**
- Task / skill / tool memory: **Planned**
- Evaluation & token savings benchmarks: **Planned**

---

## NOW — Stabilize and Clarify Core (Q2 2026)

- [ ] Align README and docs with the PRD (Capture / Engine / Knowledge Surface).
- [ ] Document the golden path: `learn → recall → context_for → wake_up → reinforce/decay`.
- [ ] Clarify when to use `recall`, `search`, `memory_context_for`, `memory_recall_enriched`.
- [ ] Improve dashboard UX around:
  - [ ] Inspecting which memories were used for an answer.
  - [ ] Showing freshness / importance / decay state.
  - [ ] Navigating namespaces and backends.
- [ ] Provide example integrations for agent loops (MCP + SDK):
  - [ ] Minimal Claude Code / MCP example.
  - [ ] Minimal OpenClaw / orchestrator example.
- [ ] Harden existing importers & mining flows (Claude / ChatGPT / Slack / Discord / Telegram / OpenClaw).

---

## NEXT — Make MemOS Agent-Native (Q3 2026)

- Task Memory
  - [ ] Define a `task` memory type (schema, metadata).
  - [ ] Add API/CLI to create task memories at end of runs.
  - [ ] Implement automatic task summarization from logs/traces.

- Tool Memory
  - [ ] Define a `tool_trace` memory type.
  - [ ] Capture tool calls (tool, inputs, success/failure, latency, cost).
  - [ ] Expose simple planning hints based on past tool performance.

- Skill Memory
  - [ ] Define a `skill` memory type.
  - [ ] Detect repeated successful patterns and promote them to skills.
  - [ ] Add APIs to list, apply and refine skills.

- Feedback & Correction
  - [ ] Add API to flag memories as wrong / outdated / incomplete.
  - [ ] Implement correction flow (update, link or supersede + version history).
  - [ ] Surface corrections in the wiki and graph.

- Retrieval & Context Packaging
  - [ ] Improve ranking (semantic + tags + recency + importance + graph signals).
  - [ ] Stabilize `memory_context_for` as the main way to build task-specific context packs.
  - [ ] Add metrics/logging for recall usefulness.

---

## LATER — Memory OS Orchestration (Q4 2026+)

- Policies & Shared Memory
  - [ ] Design a simple policy model for namespaces/cubes (read/write rules).
  - [ ] Implement per-agent / per-user / per-project / team spaces.
  - [ ] Add policy-aware inspection in the UI.

- Memory Scheduler
  - [ ] Add a scheduler for background jobs (mining, consolidation, decay, reindexing).
  - [ ] Dashboard for job status, queue health, failures.

- Multi-Modal Memory
  - [ ] Design schema for multimodal memories (docs, images, artefacts).
  - [ ] Provide at least one reference integration.

- Evaluation & Benchmarks
  - [ ] Define evaluation protocols (token savings, continuity, task quality).
  - [ ] Build internal benchmarks comparing MemOS vs naive history / RAG.
  - [ ] Publish results and guidance.

- Integration Templates
  - [ ] Ready-made templates for popular agent frameworks (Claude Code, OpenClaw, Cursor, etc.).

---

## Already Shipped (High-Level)

- [x] Python package (`pip install`).
- [x] CLI (`memos learn/recall/forget/prune/serve/...`).
- [x] Python SDK.
- [x] REST API + docs + SSE recall.
- [x] MCP server (HTTP + stdio).
- [x] Web dashboard.
- [x] Multiple backends (JSON, Chroma, Qdrant, Pinecone, etc.).
- [x] Import/mine from multiple sources.
- [x] Knowledge graph APIs and visualization.
- [x] Living wiki (update/read/search/lint).
- [x] Memory lifecycle (decay, prune, reinforce).
- [x] Versioning & time-travel (history, diff, rollback, recall-at, snapshot-at).
- [x] Multi-namespace support.
- [x] Memory deduplication (exact + near-duplicate detection at write time).
