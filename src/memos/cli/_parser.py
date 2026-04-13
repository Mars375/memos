"""MemOS CLI — argument parser."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .. import __version__


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="memos",
        description="MemOS — Memory Operating System for LLM Agents",
    )
    p.add_argument("--version", action="version", version=f"memos {__version__}")
    sub = p.add_subparsers(dest="command")

    # init
    init = sub.add_parser("init", help="Initialize a MemOS data directory")
    init.add_argument("directory", nargs="?", default=".memos", help="Directory path")
    init.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])
    init.add_argument("--force", action="store_true", help="Overwrite existing config")

    # learn
    learn = sub.add_parser("learn", help="Store a new memory")
    learn.add_argument("content", nargs="?", help="Memory content")
    learn.add_argument("--file", "-f", help="Read content from file")
    learn.add_argument("--stdin", action="store_true", help="Read content from stdin (pipe support)")
    learn.add_argument("--tags", "-t", help="Comma-separated tags")
    learn.add_argument("--importance", "-i", type=float, default=0.5)
    learn.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])
    learn.add_argument("--no-sanitize", action="store_true")
    learn.add_argument("--ttl", help="Time-to-live (e.g., 30m, 2h, 7d, 3600)")

    # batch-learn
    batch_learn = sub.add_parser("batch-learn", help="Store multiple memories from JSON")
    batch_learn.add_argument("input", help="JSON file with items (use - for stdin)")
    batch_learn.add_argument("--strict", action="store_true", help="Stop on first error")
    batch_learn.add_argument("--dry-run", action="store_true", help="Preview only")
    batch_learn.add_argument("--verbose", "-v", action="store_true")
    batch_learn.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # recall
    recall = sub.add_parser("recall", help="Recall memories matching a query")
    recall.add_argument("query", help="Search query")
    recall.add_argument("--top", "-n", type=int, default=5)
    recall.add_argument("--min-score", type=float, default=0.0)
    recall.add_argument("--min-importance", type=float, help="Only return memories with importance >= this value")
    recall.add_argument("--max-importance", type=float, help="Only return memories with importance <= this value")
    recall.add_argument("--tags", help="Comma-separated tags to include")
    recall.add_argument("--tag-mode", choices=["any", "all"], default="any", help="How --tags are applied: any (default) or all")
    recall.add_argument("--require-tags", help="Comma-separated tags that must all be present")
    recall.add_argument("--exclude-tags", help="Comma-separated tags to exclude")
    recall.add_argument("--after", help="Only memories created after this date (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM)")
    recall.add_argument("--before", help="Only memories created before this date (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM)")
    recall.add_argument("--format", choices=["text", "json"], default="text", help="Output format (default: text)")
    recall.add_argument("--enriched", action="store_true", help="Augment recall with KG facts")
    recall.add_argument("--kg-db", dest="kg_db", default=None, help="Path to kg.db")
    recall.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])
    recall.add_argument("--mode", dest="retrieval_mode", default="semantic",
                        choices=["semantic", "keyword", "hybrid"],
                        help="Retrieval mode: semantic (default), keyword (BM25 only), hybrid (semantic+BM25)")
    recall.add_argument("--explain", action="store_true", help="Show detailed score breakdown for each result")

    # search
    search_p = sub.add_parser("search", help="Keyword-only search across memories (no embeddings)")
    search_p.add_argument("query", help="Search query (substring match on content + tags)")
    search_p.add_argument("--limit", "-n", type=int, default=20, help="Max results (default: 20)")
    search_p.add_argument("--format", choices=["text", "json"], default="text", help="Output format (default: text)")
    search_p.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # stats
    stats = sub.add_parser("stats", help="Show memory statistics")
    stats.add_argument("--json", action="store_true", help="JSON output")
    stats.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # analytics
    analytics = sub.add_parser("analytics", help="Show recall analytics")
    analytics_sub = analytics.add_subparsers(dest="analytics_action")
    analytics_top = analytics_sub.add_parser("top", help="Most recalled memories")
    analytics_top.add_argument("--n", type=int, default=20, help="Max memories (default: 20)")
    analytics_top.add_argument("--json", action="store_true", help="JSON output")
    analytics_top.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    analytics_patterns = analytics_sub.add_parser("patterns", help="Most frequent queries")
    analytics_patterns.add_argument("--n", type=int, default=20, help="Max queries (default: 20)")
    analytics_patterns.add_argument("--json", action="store_true", help="JSON output")
    analytics_patterns.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    analytics_latency = analytics_sub.add_parser("latency", help="Latency statistics")
    analytics_latency.add_argument("--json", action="store_true", help="JSON output")
    analytics_latency.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    analytics_success = analytics_sub.add_parser("success-rate", help="Recall success rate")
    analytics_success.add_argument("--days", type=int, default=7, help="Lookback window in days (default: 7)")
    analytics_success.add_argument("--json", action="store_true", help="JSON output")
    analytics_success.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    analytics_daily = analytics_sub.add_parser("daily", help="Daily recall activity")
    analytics_daily.add_argument("--days", type=int, default=30, help="Lookback window in days (default: 30)")
    analytics_daily.add_argument("--json", action="store_true", help="JSON output")
    analytics_daily.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    analytics_zero = analytics_sub.add_parser("zero", help="Queries with zero results")
    analytics_zero.add_argument("--n", type=int, default=20, help="Max queries (default: 20)")
    analytics_zero.add_argument("--json", action="store_true", help="JSON output")
    analytics_zero.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    analytics_summary = analytics_sub.add_parser("summary", help="Compact analytics summary")
    analytics_summary.add_argument("--days", type=int, default=7, help="Lookback window in days (default: 7)")
    analytics_summary.add_argument("--json", action="store_true", help="JSON output")
    analytics_summary.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # forget
    forget = sub.add_parser("forget", help="Delete a memory")
    forget.add_argument("target", nargs="?", help="Memory ID or content")
    forget.add_argument("--tag", help="Delete all memories with this tag")

    get_cmd = sub.add_parser("get", help="Show details of a single memory by ID")
    get_cmd.add_argument("item_id", help="Memory item ID")
    get_cmd.add_argument("--json", action="store_true", help="JSON output")
    get_cmd.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])
    forget.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # prune
    prune = sub.add_parser("prune", help="Remove decayed memories")
    prune.add_argument("--threshold", type=float, default=0.1)
    prune.add_argument("--max-age", type=float, default=90.0)
    prune.add_argument("--dry-run", action="store_true")
    prune.add_argument("--verbose", "-v", action="store_true")
    prune.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # consolidate
    cons = sub.add_parser("consolidate", help="Find and merge duplicate memories")
    cons.add_argument("--threshold", type=float, default=0.75, help="Similarity threshold (0-1)")
    cons.add_argument("--merge", action="store_true", help="Merge content from duplicates")
    cons.add_argument("--dry-run", action="store_true", help="Report only, don't modify")
    cons.add_argument("--verbose", "-v", action="store_true")
    cons.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # ingest
    ing = sub.add_parser("ingest", help="Import file(s) into memory")
    ing.add_argument("files", nargs="+", help="Files to ingest (md, json, txt)")
    ing.add_argument("--tags", "-t", help="Comma-separated tags to add")
    ing.add_argument("--importance", "-i", type=float, default=0.5)
    ing.add_argument("--dry-run", action="store_true", help="Parse only, don't store")
    ing.add_argument("--max-chunk", type=int, default=2000, help="Max chars per chunk")
    ing.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    ing_url = sub.add_parser("ingest-url", help="Import a URL into memory")
    ing_url.add_argument("url", help="HTTP(S) or file:// URL to ingest")
    ing_url.add_argument("--tags", "-t", help="Comma-separated tags to add")
    ing_url.add_argument("--importance", "-i", type=float, default=0.5)
    ing_url.add_argument("--dry-run", action="store_true", help="Fetch and parse only, don't store")
    ing_url.add_argument("--max-chunk", type=int, default=2000, help="Max chars per chunk")
    ing_url.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # export
    exp = sub.add_parser("export", help="Export all memories to JSON, Parquet, or Markdown")
    exp.add_argument("--output", "-o", help="Output file or directory (default: stdout for json)")
    exp.add_argument("--format", "-f", choices=["json", "parquet", "markdown", "obsidian"], default="json", help="Export format (default: json)")
    exp.add_argument("--compression", choices=["zstd", "snappy", "gzip", "none"], default="zstd", help="Parquet compression (default: zstd)")
    exp.add_argument("--no-metadata", action="store_true", help="Exclude metadata")
    exp.add_argument("--update", action="store_true", help="Markdown export: only rewrite changed pages when possible")
    exp.add_argument("--wiki-dir", default=None, help="Markdown export: living wiki root override")
    exp.add_argument("--db", dest="kg_db", default=None, help="Markdown export: path to kg.db")
    exp.add_argument("--persist-path", dest="persist_path", help="Path for json backend")
    exp.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "json", "chroma", "qdrant", "pinecone"])

    # import
    imp = sub.add_parser("import", help="Import memories from JSON")
    imp.add_argument("input", help="Input JSON file (use - for stdin)")
    imp.add_argument("--merge", default="skip", choices=["skip", "overwrite", "duplicate"])
    imp.add_argument("--tags", "-t", help="Extra tags to add to imported memories")
    imp.add_argument("--dry-run", action="store_true", help="Preview only")
    imp.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # migrate
    mig = sub.add_parser("migrate", help="Migrate memories to another backend")
    mig.add_argument("--dest", required=True, choices=["memory", "json", "chroma", "qdrant", "pinecone"])
    mig.add_argument("--namespaces", help="Comma-separated namespaces to migrate")
    mig.add_argument("--merge", default="skip", choices=["skip", "overwrite", "error"])
    mig.add_argument("--dry-run", action="store_true", help="Preview only")
    mig.add_argument("--json", action="store_true", help="JSON output")
    mig.add_argument("--batch-size", type=int, default=100, help="Progress callback interval")
    mig.add_argument("--dest-option", action="append", default=[], metavar="KEY=VALUE", help="Destination backend option (repeatable)")
    mig.add_argument("--persist-path", help="Source memory backend file path")
    mig.add_argument("--qdrant-host", default="localhost")
    mig.add_argument("--qdrant-port", type=int, default=6333)
    mig.add_argument("--qdrant-api-key")
    mig.add_argument("--qdrant-path")
    mig.add_argument("--pinecone-api-key")
    mig.add_argument("--pinecone-environment")
    mig.add_argument("--pinecone-index-name")
    mig.add_argument("--pinecone-cloud")
    mig.add_argument("--pinecone-region")
    mig.add_argument("--pinecone-serverless", action="store_true", default=None)
    mig.add_argument("--vector-size", type=int)
    mig.add_argument("--embed-host")
    mig.add_argument("--embed-model")
    mig.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # serve
    serve = sub.add_parser("serve", help="Start REST API server")
    serve.add_argument("--host", default=os.environ.get("MEMOS_HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=int(os.environ.get("MEMOS_PORT", "8000")))
    serve.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])
    serve.add_argument("--chroma-host", default="localhost")
    serve.add_argument("--chroma-port", type=int, default=8000)

    # mcp-serve (HTTP JSON-RPC 2.0)
    mcp_serve = sub.add_parser("mcp-serve", help="Start MCP server (HTTP JSON-RPC 2.0) for agent integration")
    mcp_serve.add_argument("--host", default="127.0.0.1")
    mcp_serve.add_argument("--port", type=int, default=8200)
    mcp_serve.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # mcp-stdio (stdin/stdout for Claude Code / Cursor direct integration)
    sub.add_parser("mcp-stdio", help="Start MCP server over stdio (for Claude Code / Cursor)")

    # watch / subscribe
    watch = sub.add_parser("watch", help="Watch live memory events from the SSE stream")
    watch.add_argument("--server", help="MemOS server URL (default: MEMOS_URL or http://127.0.0.1:8000)")
    watch.add_argument("--event-types", help="Comma-separated event types filter")
    watch.add_argument("--tags", help="Comma-separated tag filter")
    watch.add_argument("--namespace", help="Namespace filter")
    watch.add_argument("--json", action="store_true", help="Print raw JSON payloads")
    watch.add_argument("--max-events", type=int, default=0, help="Stop after N events (0 = infinite)")

    subscribe = sub.add_parser("subscribe", help="Alias for watch")
    subscribe.add_argument("--server", help="MemOS server URL (default: MEMOS_URL or http://127.0.0.1:8000)")
    subscribe.add_argument("--event-types", help="Comma-separated event types filter")
    subscribe.add_argument("--tags", help="Comma-separated tag filter")
    subscribe.add_argument("--namespace", help="Namespace filter")
    subscribe.add_argument("--json", action="store_true", help="Print raw JSON payloads")
    subscribe.add_argument("--max-events", type=int, default=0, help="Stop after N events (0 = infinite)")

    # config
    cfg_p = sub.add_parser("config", help="View or set CLI configuration")
    cfg_sub = cfg_p.add_subparsers(dest="config_action")
    cfg_show = cfg_sub.add_parser("show", help="Show current resolved config")
    cfg_show.add_argument("--json", action="store_true", help="JSON output")
    cfg_sub.add_parser("path", help="Show config file path")
    cfg_set = cfg_sub.add_parser("set", help="Set a config value")
    cfg_set.add_argument("key_value", nargs="+", help="key=value pairs")
    cfg_init = cfg_sub.add_parser("init", help="Create default config file")
    cfg_init.add_argument("--force", action="store_true", help="Overwrite existing")


    # ── Versioning commands ─────────────────────────────────────

    # history
    hist = sub.add_parser("history", help="Show version history for a memory")
    hist.add_argument("item_id", help="Memory item ID")
    hist.add_argument("--json", action="store_true", help="JSON output")
    hist.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # diff
    diff_p = sub.add_parser("diff", help="Show diff between two versions")
    diff_p.add_argument("item_id", help="Memory item ID")
    diff_p.add_argument("--v1", type=int, help="First version number")
    diff_p.add_argument("--v2", type=int, help="Second version number")
    diff_p.add_argument("--latest", action="store_true", help="Diff last two versions")
    diff_p.add_argument("--json", action="store_true", help="JSON output")
    diff_p.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # rollback
    rb = sub.add_parser("rollback", help="Roll back a memory to a previous version")
    rb.add_argument("item_id", help="Memory item ID")
    rb.add_argument("--version", type=int, required=True, help="Target version number")
    rb.add_argument("--yes", action="store_true", help="Confirm rollback")
    rb.add_argument("--dry-run", action="store_true", help="Preview only")
    rb.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # snapshot-at
    snap = sub.add_parser("snapshot-at", help="Show all memories at a point in time")
    snap.add_argument("timestamp", help="Timestamp (epoch, ISO 8601, or relative like 1h, 2d)")
    snap.add_argument("--json", action="store_true", help="JSON output")
    snap.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # recall-at
    rcat = sub.add_parser("recall-at", help="Time-travel recall - query memories at a past time")
    rcat.add_argument("query", help="Search query")
    rcat.add_argument("--at", dest="timestamp", required=True, help="Timestamp (epoch, ISO 8601, or relative)")
    rcat.add_argument("--top", "-n", type=int, default=5)
    rcat.add_argument("--min-score", type=float, default=0.0)
    rcat.add_argument("--json", action="store_true", help="JSON output")
    rcat.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # version-stats
    vstats = sub.add_parser("version-stats", help="Show versioning statistics")
    vstats.add_argument("--json", action="store_true", help="JSON output")
    vstats.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # version-gc
    vgc = sub.add_parser("version-gc", help="Garbage collect old memory versions")
    vgc.add_argument("--max-age-days", type=float, default=90.0, help="Remove versions older than N days")
    vgc.add_argument("--keep-latest", type=int, default=3, help="Keep at least N latest versions per item")
    vgc.add_argument("--dry-run", action="store_true", help="Preview only")
    vgc.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # ── Namespace ACL commands ──────────────────────────────────

    # namespace grant
    ns_grant = sub.add_parser("ns-grant", help="Grant an agent access to a namespace")
    ns_grant.add_argument("namespace", help="Target namespace")
    ns_grant.add_argument("--agent", required=True, help="Agent ID")
    ns_grant.add_argument("--role", required=True, choices=["owner", "writer", "reader", "denied"], help="Access role")
    ns_grant.add_argument("--expires", type=float, default=None, help="Expires at (epoch timestamp)")
    ns_grant.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # namespace revoke
    ns_revoke = sub.add_parser("ns-revoke", help="Revoke an agent's namespace access")
    ns_revoke.add_argument("namespace", help="Target namespace")
    ns_revoke.add_argument("--agent", required=True, help="Agent ID")
    ns_revoke.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # namespace policies
    ns_list = sub.add_parser("ns-policies", help="List namespace ACL policies")
    ns_list.add_argument("--namespace", help="Filter by namespace")
    ns_list.add_argument("--json", action="store_true", help="JSON output")
    ns_list.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # namespace stats
    ns_stats = sub.add_parser("ns-stats", help="Show namespace ACL statistics")
    ns_stats.add_argument("--json", action="store_true", help="JSON output")
    ns_stats.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # compact
    # prune-expired
    pe = sub.add_parser("prune-expired", help="Remove expired memories (past their TTL)")
    pe.add_argument("--dry-run", action="store_true", help="Preview only")
    pe.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])
    compact_p = sub.add_parser("compact", help="Run memory compaction (dedup + archive + merge)")
    compact_p.add_argument("--dry-run", action="store_true", help="Preview only, don't modify")
    compact_p.add_argument("--archive-age", type=float, default=90.0, help="Min age (days) for archival")
    compact_p.add_argument("--importance-floor", type=float, default=0.3, help="Never archive above this importance")
    compact_p.add_argument("--stale-threshold", type=float, default=0.25, help="Decay score threshold for stale")
    compact_p.add_argument("--max-per-run", type=int, default=200, help="Max modifications per run")
    compact_p.add_argument("--json", action="store_true", help="JSON output")
    compact_p.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # benchmark
    bench = sub.add_parser("benchmark", help="Run performance benchmarks")
    bench.add_argument("--size", type=int, default=1000, help="Number of memories to insert (default: 1000)")
    bench.add_argument("--recall-queries", type=int, default=100, help="Number of recall queries (default: 100)")
    bench.add_argument("--search-queries", type=int, default=100, help="Number of search queries (default: 100)")
    bench.add_argument("--warmup", type=int, default=50, help="Warmup operations (default: 50)")
    bench.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])
    bench.add_argument("--json", action="store_true", help="JSON output")

    # benchmark-quality
    bq = sub.add_parser("benchmark-quality", help="Run recall quality benchmarks (accuracy, MRR, NDCG)")
    bq.add_argument("--noise", type=int, default=50, help="Noise memories to add (default: 50)")
    bq.add_argument("--top", type=int, default=5, help="Top-K results per query (default: 5)")
    bq.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility (default: 42)")
    bq.add_argument("--no-decay", action="store_true", help="Skip decay behavior test")
    bq.add_argument("--scalability", action="store_true", help="Run scalability test")
    bq.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])
    bq.add_argument("--json", action="store_true", help="JSON output")

    # cache-stats
    cache_p = sub.add_parser("cache-stats", help="Show embedding cache statistics")
    cache_p.add_argument("--json", action="store_true", help="JSON output")
    cache_p.add_argument("--clear", action="store_true", help="Clear the cache")
    cache_p.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])



    # ── Tags commands ──────────────────────────────────────────
    tags_p = sub.add_parser("tags", help="List and manage memory tags")
    tags_sub = tags_p.add_subparsers(dest="tags_action")
    tags_list = tags_sub.add_parser("list", help="List all tags with counts")
    tags_list.add_argument("--sort", dest="tags_sort", default="count", choices=["count", "name"], help="Sort order")
    tags_list.add_argument("--limit", dest="tags_limit", type=int, default=0, help="Max tags (0=all)")
    tags_list.add_argument("--json", action="store_true", help="JSON output")
    tags_list.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    tags_rename = tags_sub.add_parser("rename", help="Rename a tag across all memories")
    tags_rename.add_argument("old_tag", help="Current tag name")
    tags_rename.add_argument("new_tag", help="New tag name")
    tags_rename.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    tags_delete = tags_sub.add_parser("delete", help="Delete a tag from all memories")
    tags_delete.add_argument("tag", help="Tag name to remove")
    tags_delete.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # ── Sharing commands ──────────────────────────────────────
    share_offer = sub.add_parser("share-offer", help="Offer to share memories with another agent")
    share_offer.add_argument("--target", required=True, help="Target agent ID")
    share_offer.add_argument("--scope", default="items", choices=["items", "tag", "namespace"], help="Share scope")
    share_offer.add_argument("--scope-key", default="", help="IDs (comma-sep), tag name, or namespace")
    share_offer.add_argument("--permission", default="read", choices=["read", "read_write", "admin"], help="Permission level")
    share_offer.add_argument("--expires", type=float, default=None, help="TTL in seconds from now")
    share_offer.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    share_accept = sub.add_parser("share-accept", help="Accept a pending share")
    share_accept.add_argument("share_id", help="Share request ID")
    share_accept.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    share_reject = sub.add_parser("share-reject", help="Reject a pending share")
    share_reject.add_argument("share_id", help="Share request ID")
    share_reject.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    share_revoke = sub.add_parser("share-revoke", help="Revoke a share you offered")
    share_revoke.add_argument("share_id", help="Share request ID")
    share_revoke.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    share_export = sub.add_parser("share-export", help="Export memories for an accepted share")
    share_export.add_argument("share_id", help="Share request ID")
    share_export.add_argument("--output", default=None, help="Output file path (default: stdout)")
    share_export.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    share_import = sub.add_parser("share-import", help="Import memories from an envelope file")
    share_import.add_argument("input_file", help="Envelope JSON file to import")
    share_import.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    share_list = sub.add_parser("share-list", help="List shares")
    share_list.add_argument("--agent", default=None, help="Filter by agent ID")
    share_list.add_argument("--status", default=None, choices=["pending", "accepted", "rejected", "revoked", "expired"], help="Filter by status")
    share_list.add_argument("--json", action="store_true", help="JSON output")
    share_list.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    share_stats = sub.add_parser("share-stats", help="Show sharing statistics")
    share_stats.add_argument("--json", action="store_true", help="JSON output")
    share_stats.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # sync-check (P12 — Conflict Resolution)
    sync_check = sub.add_parser("sync-check", help="Check for conflicts with a remote memory export")
    sync_check.add_argument("remote_file", help="Path to remote JSON envelope file")
    sync_check.add_argument("--json", action="store_true", help="JSON output")
    sync_check.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # sync-apply (P12 — Conflict Resolution)
    sync_apply = sub.add_parser("sync-apply", help="Apply remote memories with conflict resolution")
    sync_apply.add_argument("remote_file", help="Path to remote JSON envelope file")
    sync_apply.add_argument("--strategy", choices=["local_wins", "remote_wins", "merge", "manual"], default="merge", help="Conflict resolution strategy (default: merge)")
    sync_apply.add_argument("--dry-run", action="store_true", help="Show what would be applied without writing")
    sync_apply.add_argument("--json", action="store_true", help="JSON output")
    sync_apply.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])


    # feedback
    fb = sub.add_parser("feedback", help="Record relevance feedback for a memory")
    fb.add_argument("item_id", help="Memory item ID")
    fb.add_argument("rating", choices=["relevant", "not-relevant"], help="Feedback rating")
    fb.add_argument("--query", "-q", help="The query that triggered the recall")
    fb.add_argument("--score", type=float, default=0.0, help="Recall score at feedback time")
    fb.add_argument("--agent", help="Agent ID providing feedback")
    fb.add_argument("--json", action="store_true", help="JSON output")
    fb.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # feedback-list
    fb_list = sub.add_parser("feedback-list", help="List feedback entries")
    fb_list.add_argument("--item-id", dest="item_id", help="Filter by memory item ID")
    fb_list.add_argument("--limit", type=int, default=50, help="Max entries to show")
    fb_list.add_argument("--json", action="store_true", help="JSON output")
    fb_list.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # feedback-stats
    fb_stats = sub.add_parser("feedback-stats", help="Show feedback statistics")
    fb_stats.add_argument("--json", action="store_true", help="JSON output")
    fb_stats.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])

    # wiki-compile
    wiki_compile_p = sub.add_parser("wiki-compile", help="Compile memories into markdown pages per tag")
    wiki_compile_p.add_argument("--tags", nargs="*", help="Only compile these tags")
    wiki_compile_p.add_argument("--wiki-dir", dest="wiki_dir", help="Output directory (default: ~/.memos/wiki)")
    wiki_compile_p.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone", "json"])
    wiki_compile_p.add_argument("--persist-path", dest="persist_path", help="Path for json backend")

    # wiki-list
    wiki_list_p = sub.add_parser("wiki-list", help="List compiled wiki pages")
    wiki_list_p.add_argument("--wiki-dir", dest="wiki_dir", help="Wiki directory")
    wiki_list_p.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone", "json"])
    wiki_list_p.add_argument("--persist-path", dest="persist_path", help="Path for json backend")

    # wiki-read
    wiki_read_p = sub.add_parser("wiki-read", help="Read a compiled wiki page by tag")
    wiki_read_p.add_argument("tag", help="Tag name to read")
    wiki_read_p.add_argument("--wiki-dir", dest="wiki_dir", help="Wiki directory")
    wiki_read_p.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone", "json"])
    wiki_read_p.add_argument("--persist-path", dest="persist_path", help="Path for json backend")


    # wiki-living
    wl_sp = sub.add_parser("wiki-living", help="Living wiki: init/update/lint/index/log/read/search/list/stats")
    wl_sub = wl_sp.add_subparsers(dest="wl_action")
    wl_sub.add_parser("init", help="Initialize living wiki structure")
    wl_update = wl_sub.add_parser("update", help="Scan memories, extract entities, update pages")
    wl_update.add_argument("--force", action="store_true", help="Force full rebuild")
    wl_update.add_argument("--wiki-dir", dest="wiki_dir", help="Wiki directory")
    wl_update.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone", "json"])
    wl_update.add_argument("--persist-path", dest="persist_path", help="Path for json backend")
    wl_lint = wl_sub.add_parser("lint", help="Detect orphans, contradictions, empty pages")
    wl_lint.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone", "json"])
    wl_lint.add_argument("--persist-path", dest="persist_path", help="Path for json backend")
    wl_idx = wl_sub.add_parser("index", help="Regenerate index.md")
    wl_idx.add_argument("--wiki-dir", dest="wiki_dir", help="Wiki directory")
    wl_idx.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone", "json"])
    wl_idx.add_argument("--persist-path", dest="persist_path", help="Path for json backend")
    wl_log = wl_sub.add_parser("log", help="Show activity log")
    wl_log.add_argument("--limit", type=int, default=20, help="Max entries")
    wl_log.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone", "json"])
    wl_log.add_argument("--persist-path", dest="persist_path", help="Path for json backend")
    wl_read = wl_sub.add_parser("read", help="Read a living page")
    wl_read.add_argument("entity", help="Entity name")
    wl_read.add_argument("--wiki-dir", dest="wiki_dir", help="Wiki directory")
    wl_read.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone", "json"])
    wl_read.add_argument("--persist-path", dest="persist_path", help="Path for json backend")
    wl_search = wl_sub.add_parser("search", help="Search across living pages")
    wl_search.add_argument("query", help="Search query")
    wl_search.add_argument("--wiki-dir", dest="wiki_dir", help="Wiki directory")
    wl_search.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone", "json"])
    wl_search.add_argument("--persist-path", dest="persist_path", help="Path for json backend")
    wl_list = wl_sub.add_parser("list", help="List all living pages")
    wl_list.add_argument("--wiki-dir", dest="wiki_dir", help="Wiki directory")
    wl_list.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone", "json"])
    wl_list.add_argument("--persist-path", dest="persist_path", help="Path for json backend")
    wl_stats = wl_sub.add_parser("stats", help="Living wiki statistics")
    wl_stats.add_argument("--wiki-dir", dest="wiki_dir", help="Wiki directory")
    wl_stats.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone", "json"])
    wl_stats.add_argument("--persist-path", dest="persist_path", help="Path for json backend")

    # wiki-graph
    wg = sub.add_parser("wiki-graph", help="Generate or read graph community wiki pages from the knowledge graph")
    wg.add_argument("--output", dest="output", help="Output directory (default: alongside kg.db in wiki/graph)")
    wg.add_argument("--community", help="Read an existing community page by ID")
    wg.add_argument("--update", action="store_true", help="Incrementally update only changed pages")
    wg.add_argument("--db", dest="kg_db", default=None, help="Path to kg.db")

    # brain-search
    brain = sub.add_parser("brain-search", help="Unified search across memories, living wiki pages, and knowledge graph")
    brain.add_argument("query", help="Search query")
    brain.add_argument("--top", type=int, default=10, help="Max results per source")
    brain.add_argument("--tags", help="Comma-separated tag filter for memories")
    brain.add_argument("--wiki-dir", dest="wiki_dir", help="Wiki directory")
    brain.add_argument("--db", dest="kg_db", default=None, help="Path to kg.db")
    brain.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone", "json"])
    brain.add_argument("--persist-path", dest="persist_path", help="Path for json backend")

    # mine
    mine_p = sub.add_parser("mine", help="Smart mine — import files/conversations into memories")
    mine_p.add_argument("paths", nargs="+", help="Files or directories to mine")
    mine_p.add_argument("--format",
                        choices=["auto", "claude", "chatgpt", "slack", "discord", "telegram", "openclaw"],
                        default="auto", help="Force format (default: auto-detect)")
    mine_p.add_argument("--tags", nargs="*", help="Extra tags to apply to all chunks")
    mine_p.add_argument("--chunk-size", type=int, default=800, dest="chunk_size",
                        help="Max chars per chunk (default: 800)")
    mine_p.add_argument("--chunk-overlap", type=int, default=100, dest="chunk_overlap",
                        help="Overlap chars between chunks (default: 100)")
    mine_p.add_argument("--dry-run", action="store_true", help="Preview without storing")
    mine_p.add_argument("--verbose", "-v", action="store_true")
    mine_p.add_argument("--backend", default="json", choices=["memory", "json", "chroma", "qdrant"])
    mine_p.add_argument("--persist-path", dest="persist_path",
                        default=str(Path.home() / ".memos" / "store.json"))
    mine_p.add_argument("--update", action="store_true",
                        help="Re-mine files even if cached, replacing old memories")
    mine_p.add_argument("--diff", action="store_true",
                        help="Only mine chunks not previously seen for each file")
    mine_p.add_argument("--cache-db", dest="cache_db",
                        default=str(Path.home() / ".memos" / "mine-cache.db"),
                        help="Path to mine cache SQLite DB (default: ~/.memos/mine-cache.db)")
    mine_p.add_argument("--no-cache", dest="no_cache", action="store_true",
                        help="Disable incremental cache for this run")

    # mine-conversation
    mine_conv_p = sub.add_parser(
        "mine-conversation",
        help="Mine a speaker-attributed transcript file into MemOS",
    )
    mine_conv_p.add_argument("path", help="Path to transcript file")
    mine_conv_p.add_argument(
        "--per-speaker",
        dest="per_speaker",
        action="store_true",
        default=True,
        help="Store each speaker under a dedicated namespace (default: on)",
    )
    mine_conv_p.add_argument(
        "--no-per-speaker",
        dest="per_speaker",
        action="store_false",
        help="Store all turns in a single namespace",
    )
    mine_conv_p.add_argument(
        "--namespace-prefix",
        dest="namespace_prefix",
        default="conv",
        help="Prefix for per-speaker namespaces (default: conv)",
    )
    mine_conv_p.add_argument(
        "--tags",
        default="",
        help="Comma-separated extra tags",
    )
    mine_conv_p.add_argument(
        "--importance",
        type=float,
        default=0.6,
        help="Memory importance (default: 0.6)",
    )
    mine_conv_p.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=False,
        help="Preview without storing",
    )

    # mine-status
    mine_status_p = sub.add_parser("mine-status", help="Show incremental mine cache status")
    mine_status_p.add_argument("paths", nargs="*", help="Specific paths to inspect (default: all)")
    mine_status_p.add_argument("--cache-db", dest="cache_db",
                               default=str(Path.home() / ".memos" / "mine-cache.db"),
                               help="Path to mine cache SQLite DB")

    # mine-stale
    mine_stale_p = sub.add_parser("mine-stale", help="Report sources changed since last mine (staleness detection)")
    mine_stale_p.add_argument("--only-stale", dest="only_stale", action="store_true",
                              help="Only show changed/missing files (hide fresh)")
    mine_stale_p.add_argument("--cache-db", dest="cache_db",
                              default=str(Path.home() / ".memos" / "mine-cache.db"),
                              help="Path to mine cache SQLite DB")

    # skills-export
    skills_p = sub.add_parser("skills-export", help="Export MemOS workflows as agent skill files")
    skills_p.add_argument("--output", "-o", default=None,
                          help="Output directory (default: ~/.claude/commands/)")
    skills_p.add_argument("--format", "-f", choices=["claude-code", "generic"],
                          default="claude-code", help="Skill format (default: claude-code)")
    skills_p.add_argument("--skills", nargs="*", default=None,
                          help="Specific skills to export (default: all)")
    skills_p.add_argument("--overwrite", action="store_true",
                          help="Overwrite existing skill files")
    skills_p.add_argument("--list", dest="list_skills", action="store_true",
                          help="List available skill names without exporting")

    # kg-add
    kg_add = sub.add_parser("kg-add", help="Add a fact to the knowledge graph")
    kg_add.add_argument("subject", help="Subject entity")
    kg_add.add_argument("predicate", help="Relation type")
    kg_add.add_argument("object", help="Object entity or value")
    kg_add.add_argument("--from", dest="valid_from", default=None,
                        help="Valid from (epoch, ISO 8601, or relative e.g. 2d)")
    kg_add.add_argument("--to", dest="valid_to", default=None,
                        help="Valid to (epoch, ISO 8601, or relative)")
    kg_add.add_argument("--confidence", type=float, default=1.0,
                        help="Confidence 0.0-1.0 (default 1.0)")
    kg_add.add_argument("--source", default=None, help="Source label")
    kg_add.add_argument("--label", dest="confidence_label", default="EXTRACTED",
                        choices=["EXTRACTED", "INFERRED", "AMBIGUOUS"],
                        help="Confidence label (default: EXTRACTED)")
    kg_add.add_argument("--db", dest="kg_db", default=None, help="Path to kg.db")

    # kg-query
    kg_query = sub.add_parser("kg-query", help="Query facts about an entity")
    kg_query.add_argument("entity", help="Entity name")
    kg_query.add_argument("--at", dest="at_time", default=None,
                          help="Point in time (epoch, ISO 8601, or relative)")
    kg_query.add_argument("--direction", choices=["both", "subject", "object"], default="both")
    kg_query.add_argument("--db", dest="kg_db", default=None)

    # kg-timeline
    kg_tl = sub.add_parser("kg-timeline", help="Show chronological facts about an entity")
    kg_tl.add_argument("entity", help="Entity name")
    kg_tl.add_argument("--db", dest="kg_db", default=None)

    # kg-invalidate
    kg_inv = sub.add_parser("kg-invalidate", help="Invalidate (expire) a fact by ID")
    kg_inv.add_argument("fact_id", help="Fact ID to invalidate")
    kg_inv.add_argument("--db", dest="kg_db", default=None)

    # kg-stats
    kg_stats = sub.add_parser("kg-stats", help="Show knowledge graph statistics")
    kg_stats.add_argument("--db", dest="kg_db", default=None)

    # kg-path
    kg_path = sub.add_parser("kg-path", help="Find paths between two entities")
    kg_path.add_argument("entity_a", help="Start entity")
    kg_path.add_argument("entity_b", help="Target entity")
    kg_path.add_argument("--max-hops", type=int, default=3, help="Max hops (default: 3)")
    kg_path.add_argument("--max-paths", type=int, default=10, help="Max paths to return (default: 10)")
    kg_path.add_argument("--db", dest="kg_db", default=None)

    # kg-neighbors
    kg_nbrs = sub.add_parser("kg-neighbors", help="Show entity neighborhood")
    kg_nbrs.add_argument("entity", help="Entity name")
    kg_nbrs.add_argument("--depth", type=int, default=1, help="Neighborhood depth (default: 1)")
    kg_nbrs.add_argument("--direction", choices=["both", "subject", "object"], default="both")
    kg_nbrs.add_argument("--db", dest="kg_db", default=None)

    # kg-infer
    kg_infer = sub.add_parser("kg-infer", help="Infer transitive facts for a predicate")
    kg_infer.add_argument("predicate", help="Predicate to infer transitivity on (e.g. 'manages')")
    kg_infer.add_argument("--as", dest="inferred_predicate", default=None,
                          help="Name for inferred predicate (default: <predicate>_transitive)")
    kg_infer.add_argument("--max-depth", type=int, default=3, help="Max inference depth (default: 3)")
    kg_infer.add_argument("--db", dest="kg_db", default=None, help="Path to kg.db")

    # kg-labels
    kg_labels = sub.add_parser("kg-labels", help="Show facts by confidence label")
    kg_labels.add_argument("label", choices=["EXTRACTED", "INFERRED", "AMBIGUOUS"],
                           help="Confidence label to filter by")
    kg_labels.add_argument("--all", dest="show_all", action="store_true",
                           help="Include invalidated facts")
    kg_labels.add_argument("--db", dest="kg_db", default=None, help="Path to kg.db")

    # kg-lint
    kg_lint = sub.add_parser("kg-lint", help="Lint the KG — find contradictions, orphans, sparse entities")
    kg_lint.add_argument("--min-facts", dest="min_facts", type=int, default=2,
                         help="Minimum active facts per entity (default: 2)")
    kg_lint.add_argument("--db", dest="kg_db", default=None, help="Path to kg.db")

    # kg-backlinks
    kg_backlinks = sub.add_parser("kg-backlinks", help="Show incoming edges (backlinks) for an entity")
    kg_backlinks.add_argument("entity", help="Entity name to find backlinks for")
    kg_backlinks.add_argument("--predicate", default=None, help="Filter by predicate")
    kg_backlinks.add_argument("--all", dest="show_all", action="store_true",
                              help="Include invalidated facts")
    kg_backlinks.add_argument("--db", dest="kg_db", default=None, help="Path to kg.db")

    # ---- Palace (P6) ----
    palace_db_help = "Path to palace.db (default: ~/.memos/palace.db)"

    palace_init = sub.add_parser("palace-init", help="Initialise the Palace schema")
    palace_init.add_argument("--db", dest="palace_db", default=None, help=palace_db_help)

    palace_wing_create = sub.add_parser("palace-wing-create", help="Create a Wing")
    palace_wing_create.add_argument("name", help="Wing name")
    palace_wing_create.add_argument("--description", default="", help="Wing description")
    palace_wing_create.add_argument("--db", dest="palace_db", default=None, help=palace_db_help)

    palace_wing_list = sub.add_parser("palace-wing-list", help="List Wings")
    palace_wing_list.add_argument("--db", dest="palace_db", default=None, help=palace_db_help)

    palace_room_create = sub.add_parser("palace-room-create", help="Create a Room inside a Wing")
    palace_room_create.add_argument("wing", help="Wing name")
    palace_room_create.add_argument("room", help="Room name")
    palace_room_create.add_argument("--description", default="", help="Room description")
    palace_room_create.add_argument("--db", dest="palace_db", default=None, help=palace_db_help)

    palace_room_list = sub.add_parser("palace-room-list", help="List Rooms")
    palace_room_list.add_argument("--wing", default=None, help="Filter by wing name")
    palace_room_list.add_argument("--db", dest="palace_db", default=None, help=palace_db_help)

    palace_assign = sub.add_parser("palace-assign", help="Assign a memory to a Wing/Room")
    palace_assign.add_argument("memory_id", help="Memory ID")
    palace_assign.add_argument("--wing", required=True, help="Wing name")
    palace_assign.add_argument("--room", default=None, help="Room name (optional)")
    palace_assign.add_argument("--db", dest="palace_db", default=None, help=palace_db_help)

    palace_recall = sub.add_parser("palace-recall", help="Scoped recall using Palace")
    palace_recall.add_argument("query", help="Recall query")
    palace_recall.add_argument("--wing", default=None, help="Scope to wing")
    palace_recall.add_argument("--room", default=None, help="Scope to room (requires --wing)")
    palace_recall.add_argument("--top", type=int, default=10, help="Max results (default 10)")
    palace_recall.add_argument("--db", dest="palace_db", default=None, help=palace_db_help)

    palace_stats = sub.add_parser("palace-stats", help="Show Palace statistics")
    palace_stats.add_argument("--db", dest="palace_db", default=None, help=palace_db_help)

    # ---- Context Stack (P7) ----

    # wake-up
    wake_up_p = sub.add_parser("wake-up", help="Print L0+L1 context for session priming")
    wake_up_p.add_argument("--max-chars", dest="max_chars", type=int, default=2000,
                           help="Max characters in output (default: 2000)")
    wake_up_p.add_argument("--top", dest="l1_top", type=int, default=15,
                           help="Top-N memories by importance (default: 15)")
    wake_up_p.add_argument("--no-stats", dest="no_stats", action="store_true",
                           help="Omit the STATS section")
    wake_up_p.add_argument("--compact", dest="compact", action="store_true",
                           help="~200-token compressed output (no headers, top-5 snippets)")
    wake_up_p.add_argument("--backend", default="memory",
                           choices=["memory", "chroma", "qdrant", "pinecone"])

    # identity
    identity_p = sub.add_parser("identity", help="Manage agent identity (L0)")
    identity_sub = identity_p.add_subparsers(dest="identity_action")

    id_set = identity_sub.add_parser("set", help="Write identity (use - to read from stdin)")
    id_set.add_argument("text", nargs="?", default=None,
                        help="Identity text (omit to read from stdin)")

    identity_sub.add_parser("show", help="Show current identity")

    # context-for
    ctx_for_p = sub.add_parser("context-for", help="Retrieve optimised context for a query")
    ctx_for_p.add_argument("query", help="Query string")
    ctx_for_p.add_argument("--max-chars", dest="max_chars", type=int, default=1500,
                           help="Max characters in output (default: 1500)")
    ctx_for_p.add_argument("--top", type=int, default=10,
                           help="Number of semantic results to include (default: 10)")
    ctx_for_p.add_argument("--backend", default="memory",
                           choices=["memory", "chroma", "qdrant", "pinecone"])

    # --- Classify ---
    classify_p = sub.add_parser("classify", help="Classify text into memory type tags")
    classify_p.add_argument("text", help="Text to classify")
    classify_p.add_argument("--detailed", action="store_true", help="Show matched patterns")

    # --- Decay & Reinforce ---
    decay_p = sub.add_parser("decay", help="Apply importance decay to memories")
    decay_p.add_argument("--apply", action="store_true", help="Apply decay (default is dry-run)")
    decay_p.add_argument("--min-age-days", type=float, default=None, help="Min age in days to be eligible")
    decay_p.add_argument("--floor", type=float, default=None, help="Minimum importance after decay")
    decay_p.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "json", "chroma", "qdrant", "pinecone"])

    reinforce_p = sub.add_parser("reinforce", help="Boost a memory's importance")
    reinforce_p.add_argument("memory_id", help="Memory ID to reinforce")
    reinforce_p.add_argument("--strength", type=float, default=None, help="Boost amount (default: 0.05)")
    reinforce_p.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "json", "chroma", "qdrant", "pinecone"])

    compress_p = sub.add_parser("compress", help="Compress decayed memories into aggregate summaries")
    compress_p.add_argument("--threshold", type=float, default=0.1, help="Importance threshold (default: 0.1)")
    compress_p.add_argument("--dry-run", action="store_true", help="Preview without modifying memories")
    compress_p.add_argument("--verbose", "-v", action="store_true")
    compress_p.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "json", "chroma", "qdrant", "pinecone"])

    return p




