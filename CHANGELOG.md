# Changelog

## v1.0.0 (2026-04-10) — PyPI release prep and reference docs

- PyPI package renamed to `memos-agent`
- Packaging metadata completed for a `src/` layout release
- README rewritten as the reference entrypoint for install, MCP, backends, Docker, and API usage
- Added PyPI publish workflow for `v1.*` tags
- Consolidated release history from `v0.29.0` onward

## v0.47.0 (2026-04-10) — Advanced Recall Filters

- Added `MemoryQuery` and `QueryEngine`
- Enriched `POST /api/v1/recall` with tag logic, importance ranges, and date filters
- Added `GET /api/v1/memories`
- Extended CLI and MCP recall filters

## v0.46.0 (2026-04-10) — Namespace Management API

- Added persistent namespace registry and namespace stats/export/import
- Added namespace REST endpoints, CLI commands, and MCP helpers
- Fixed export/import to respect the active namespace

## v0.45.0 (2026-04-10) — Memory Deduplication

- Added `DedupEngine` for exact and near-duplicate detection
- Added duplicate checks in `MemOS.learn()` with opt-out support
- Added CLI and API dedup surfaces

## v0.44.0 (2026-04-10) — API Authentication

- Added bearer auth and namespace-scoped API keys
- Added `GET /api/v1/auth/whoami`
- Kept `X-API-Key` compatibility for existing clients

## v0.43.0 (2026-04-10) — Markdown knowledge export

- Added portable Markdown export with `INDEX.md`, `LOG.md`, entity pages, and communities
- Added API ZIP export and incremental update mode

## v0.42.0 (2026-04-10) — Entity detail and graph/wiki bridge

- Added entity detail APIs and entity-centric graph navigation
- Enriched wiki pages with graph neighbors, backlinks, and top memories
- Improved dashboard support for entity drill-downs

## v0.41.0 (2026-04-09) — Unified Brain Search

- Added `BrainSearch` orchestration across memories, wiki, and KG facts
- Added CLI `memos brain-search`, REST `POST /api/v1/brain/search`, and MCP `brain_search`

## v0.40.0 (2026-04-09) — Memory Compression

- Added `MemoryCompressor` for low-importance memory aggregation
- Added CLI `memos compress` and REST `POST /api/v1/compress`

## v0.39.0 (2026-04-09) — Auto KG extraction on write

- Added zero-LLM `KGExtractor`
- Wired KG extraction into `MemOS.learn()`
- Added CLI/API preview and `MEMOS_AUTO_KG`

## v0.38.0 (2026-04-09) — Speaker ownership

- Added conversation mining by speaker namespace
- Added transcript parsing for common chat formats
- Added CLI `memos mine-conversation` and REST ingestion route

## v0.37.0 (2026-04-09) — URL ingest

- Added URL ingest for webpages, PDFs, arXiv, and X/Twitter links
- Added `MemOS.ingest_url()`, CLI `memos ingest-url`, and REST API support

## v0.36.0 (2026-04-09) — Hybrid retrieval

- Added semantic + keyword hybrid retrieval
- Improved recall quality without changing client APIs

## v0.35.0 (2026-04-09) — Incremental miner

- Added SHA-256 cache for incremental mining
- Added update mode for reprocessing only changed inputs

## v0.34.0 (2026-04-08) — KG confidence labels

- Added `EXTRACTED`, `INFERRED`, and `AMBIGUOUS` confidence labels
- Added label stats and confidence-aware KG queries

## v0.33.0 (2026-04-08) — Memory type tags

- Added zero-LLM auto-tagging for memory types
- Added CLI and REST classification support

## v0.32.0 (2026-04-08) — Graph traversal

- Added multi-hop KG path queries and neighbor traversal
- Added related CLI and REST endpoints

## v0.31.2 (2026-04-08) — Living wiki and benchmark suite

- Added living wiki pages with index, log, search, backlinks, and linting
- Added benchmark suite for Recall@K, MRR, NDCG, decay impact, and scalability

## v0.31.1 (2026-04-08) — KG bridge

- Added KG bridge and enriched recall
- Added explicit memory-to-graph linking and extraction helpers

## v0.31.0 (2026-04-08) — Decay engine and sync conflict resolution

- Added decay/reinforcement engine and related APIs
- Added multi-instance sync conflict resolution

## v0.30.0 (2026-04-08) — Foundation release

- Added MCP server and stdio bridge
- Added wiki compile mode and markdown migration tool
- Added temporal knowledge graph and hierarchical palace model
- Added wake-up context stack and multi-format ingest/mining

## v0.29.0 (2026-04-07) — Second Brain dashboard

- Added graph dashboard with search, stats, and dark theme
- Established the initial browser-based navigation layer for MemOS
