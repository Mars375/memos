"""Memory CRUD commands: init, learn, batch-learn, recall, search, forget, get."""

from __future__ import annotations

from ._common import _add_backend_arg


def build(sub) -> None:
    # init
    init = sub.add_parser("init", help="Initialize a MemOS data directory")
    init.add_argument("directory", nargs="?", default=".memos", help="Directory path")
    _add_backend_arg(init)
    init.add_argument("--force", action="store_true", help="Overwrite existing config")

    # learn
    learn = sub.add_parser("learn", help="Store a new memory")
    learn.add_argument("content", nargs="?", help="Memory content")
    learn.add_argument("--file", "-f", help="Read content from file")
    learn.add_argument("--stdin", action="store_true", help="Read content from stdin (pipe support)")
    learn.add_argument("--tags", "-t", help="Comma-separated tags")
    learn.add_argument("--importance", "-i", type=float, default=0.5)
    _add_backend_arg(learn)
    learn.add_argument("--no-sanitize", action="store_true")
    learn.add_argument("--ttl", help="Time-to-live (e.g., 30m, 2h, 7d, 3600)")

    # batch-learn
    batch_learn = sub.add_parser("batch-learn", help="Store multiple memories from JSON")
    batch_learn.add_argument("input", help="JSON file with items (use - for stdin)")
    batch_learn.add_argument("--strict", action="store_true", help="Stop on first error")
    batch_learn.add_argument("--dry-run", action="store_true", help="Preview only")
    batch_learn.add_argument("--verbose", "-v", action="store_true")
    _add_backend_arg(batch_learn)

    # recall
    recall = sub.add_parser("recall", help="Recall memories matching a query")
    recall.add_argument("query", help="Search query")
    recall.add_argument("--top", "-n", type=int, default=5)
    recall.add_argument("--min-score", type=float, default=0.0)
    recall.add_argument("--min-importance", type=float, help="Only return memories with importance >= this value")
    recall.add_argument("--max-importance", type=float, help="Only return memories with importance <= this value")
    recall.add_argument("--tags", help="Comma-separated tags to include")
    recall.add_argument(
        "--tag-mode", choices=["any", "all"], default="any", help="How --tags are applied: any (default) or all"
    )
    recall.add_argument("--require-tags", help="Comma-separated tags that must all be present")
    recall.add_argument("--exclude-tags", help="Comma-separated tags to exclude")
    recall.add_argument(
        "--after", help="Only memories created after this date (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM)"
    )
    recall.add_argument(
        "--before", help="Only memories created before this date (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM)"
    )
    recall.add_argument("--format", choices=["text", "json"], default="text", help="Output format (default: text)")
    recall.add_argument("--enriched", action="store_true", help="Augment recall with KG facts")
    recall.add_argument("--kg-db", dest="kg_db", default=None, help="Path to kg.db")
    _add_backend_arg(recall)
    recall.add_argument(
        "--mode",
        dest="retrieval_mode",
        default="semantic",
        choices=["semantic", "keyword", "hybrid"],
        help="Retrieval mode: semantic (default), keyword (BM25 only), hybrid (semantic+BM25)",
    )
    recall.add_argument("--explain", action="store_true", help="Show detailed score breakdown for each result")

    # search
    search_p = sub.add_parser("search", help="Keyword-only search across memories (no embeddings)")
    search_p.add_argument("query", help="Search query (substring match on content + tags)")
    search_p.add_argument("--limit", "-n", type=int, default=20, help="Max results (default: 20)")
    search_p.add_argument("--format", choices=["text", "json"], default="text", help="Output format (default: text)")
    _add_backend_arg(search_p)

    # forget
    forget = sub.add_parser("forget", help="Delete a memory")
    forget.add_argument("target", nargs="?", help="Memory ID or content")
    forget.add_argument("--tag", help="Delete all memories with this tag")
    _add_backend_arg(forget)

    # get
    get_cmd = sub.add_parser("get", help="Show details of a single memory by ID")
    get_cmd.add_argument("item_id", help="Memory item ID")
    get_cmd.add_argument("--json", action="store_true", help="JSON output")
    _add_backend_arg(get_cmd)
