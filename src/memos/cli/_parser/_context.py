"""Context and analytics commands: wake-up, identity, context-for, brain-search, analytics, stats."""

from __future__ import annotations

from ._common import _add_backend_arg


def build(sub) -> None:
    # stats
    stats = sub.add_parser("stats", help="Show memory statistics")
    stats.add_argument("--json", action="store_true", help="JSON output")
    _add_backend_arg(stats)

    # analytics
    analytics = sub.add_parser("analytics", help="Show recall analytics")
    analytics_sub = analytics.add_subparsers(dest="analytics_action")

    analytics_top = analytics_sub.add_parser("top", help="Most recalled memories")
    analytics_top.add_argument("--n", type=int, default=20, help="Max memories (default: 20)")
    analytics_top.add_argument("--json", action="store_true", help="JSON output")
    _add_backend_arg(analytics_top)

    analytics_patterns = analytics_sub.add_parser("patterns", help="Most frequent queries")
    analytics_patterns.add_argument("--n", type=int, default=20, help="Max queries (default: 20)")
    analytics_patterns.add_argument("--json", action="store_true", help="JSON output")
    _add_backend_arg(analytics_patterns)

    analytics_latency = analytics_sub.add_parser("latency", help="Latency statistics")
    analytics_latency.add_argument("--json", action="store_true", help="JSON output")
    _add_backend_arg(analytics_latency)

    analytics_success = analytics_sub.add_parser("success-rate", help="Recall success rate")
    analytics_success.add_argument("--days", type=int, default=7, help="Lookback window in days (default: 7)")
    analytics_success.add_argument("--json", action="store_true", help="JSON output")
    _add_backend_arg(analytics_success)

    analytics_daily = analytics_sub.add_parser("daily", help="Daily recall activity")
    analytics_daily.add_argument("--days", type=int, default=30, help="Lookback window in days (default: 30)")
    analytics_daily.add_argument("--json", action="store_true", help="JSON output")
    _add_backend_arg(analytics_daily)

    analytics_zero = analytics_sub.add_parser("zero", help="Queries with zero results")
    analytics_zero.add_argument("--n", type=int, default=20, help="Max queries (default: 20)")
    analytics_zero.add_argument("--json", action="store_true", help="JSON output")
    _add_backend_arg(analytics_zero)

    analytics_summary = analytics_sub.add_parser("summary", help="Compact analytics summary")
    analytics_summary.add_argument("--days", type=int, default=7, help="Lookback window in days (default: 7)")
    analytics_summary.add_argument("--json", action="store_true", help="JSON output")
    _add_backend_arg(analytics_summary)

    # brain-search
    brain = sub.add_parser(
        "brain-search", help="Unified search across memories, living wiki pages, and knowledge graph"
    )
    brain.add_argument("query", help="Search query")
    brain.add_argument("--top", type=int, default=10, help="Max results per source")
    brain.add_argument("--tags", help="Comma-separated tag filter for memories")
    brain.add_argument("--wiki-dir", dest="wiki_dir", help="Wiki directory")
    brain.add_argument("--db", dest="kg_db", default=None, help="Path to kg.db")
    _add_backend_arg(brain, choices=["memory", "chroma", "qdrant", "pinecone", "json"])
    brain.add_argument("--persist-path", dest="persist_path", help="Path for json backend")

    # wake-up
    wake_up_p = sub.add_parser("wake-up", help="Print L0+L1 context for session priming")
    wake_up_p.add_argument(
        "--max-chars", dest="max_chars", type=int, default=2000, help="Max characters in output (default: 2000)"
    )
    wake_up_p.add_argument(
        "--top", dest="l1_top", type=int, default=15, help="Top-N memories by importance (default: 15)"
    )
    wake_up_p.add_argument("--no-stats", dest="no_stats", action="store_true", help="Omit the STATS section")
    wake_up_p.add_argument(
        "--compact",
        dest="compact",
        action="store_true",
        help="~200-token compressed output (no headers, top-5 snippets)",
    )
    wake_up_p.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # identity
    identity_p = sub.add_parser("identity", help="Manage agent identity (L0)")
    identity_sub = identity_p.add_subparsers(dest="identity_action")
    id_set = identity_sub.add_parser("set", help="Write identity (use - to read from stdin)")
    id_set.add_argument("text", nargs="?", default=None, help="Identity text (omit to read from stdin)")
    identity_sub.add_parser("show", help="Show current identity")

    # context-for
    ctx_for_p = sub.add_parser("context-for", help="Retrieve optimised context for a query")
    ctx_for_p.add_argument("query", help="Query string")
    ctx_for_p.add_argument(
        "--max-chars", dest="max_chars", type=int, default=1500, help="Max characters in output (default: 1500)"
    )
    ctx_for_p.add_argument("--top", type=int, default=10, help="Number of semantic results to include (default: 10)")
    ctx_for_p.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])
