"""Import/export and mining commands: export, import, migrate, ingest, ingest-url, mine, mine-conversation, mine-status, mine-stale, skills-export."""

from __future__ import annotations

from pathlib import Path

from ._common import _add_backend_arg


def build(sub) -> None:
    # ingest
    ing = sub.add_parser("ingest", help="Import file(s) into memory")
    ing.add_argument("files", nargs="+", help="Files to ingest (md, json, txt)")
    ing.add_argument("--tags", "-t", help="Comma-separated tags to add")
    ing.add_argument("--importance", "-i", type=float, default=0.5)
    ing.add_argument("--dry-run", action="store_true", help="Parse only, don't store")
    ing.add_argument("--max-chunk", type=int, default=2000, help="Max chars per chunk")
    _add_backend_arg(ing)

    # ingest-url
    ing_url = sub.add_parser("ingest-url", help="Import a URL into memory")
    ing_url.add_argument("url", help="HTTP(S) or file:// URL to ingest")
    ing_url.add_argument("--tags", "-t", help="Comma-separated tags to add")
    ing_url.add_argument("--importance", "-i", type=float, default=0.5)
    ing_url.add_argument("--dry-run", action="store_true", help="Fetch and parse only, don't store")
    ing_url.add_argument("--max-chunk", type=int, default=2000, help="Max chars per chunk")
    _add_backend_arg(ing_url)

    # export
    exp = sub.add_parser("export", help="Export all memories to JSON, Parquet, or Markdown")
    exp.add_argument("--output", "-o", help="Output file or directory (default: stdout for json)")
    exp.add_argument(
        "--format",
        "-f",
        choices=["json", "parquet", "markdown", "obsidian"],
        default="json",
        help="Export format (default: json)",
    )
    exp.add_argument(
        "--compression",
        choices=["zstd", "snappy", "gzip", "none"],
        default="zstd",
        help="Parquet compression (default: zstd)",
    )
    exp.add_argument("--no-metadata", action="store_true", help="Exclude metadata")
    exp.add_argument("--update", action="store_true", help="Markdown export: only rewrite changed pages when possible")
    exp.add_argument("--wiki-dir", default=None, help="Markdown export: living wiki root override")
    exp.add_argument("--db", dest="kg_db", default=None, help="Markdown export: path to kg.db")
    exp.add_argument("--persist-path", dest="persist_path", help="Path for json backend")
    _add_backend_arg(exp, choices=["memory", "json", "chroma", "qdrant", "pinecone"])

    # import
    imp = sub.add_parser("import", help="Import memories from JSON")
    imp.add_argument("input", help="Input JSON file (use - for stdin)")
    imp.add_argument("--merge", default="skip", choices=["skip", "overwrite", "duplicate"])
    imp.add_argument("--tags", "-t", help="Extra tags to add to imported memories")
    imp.add_argument("--dry-run", action="store_true", help="Preview only")
    _add_backend_arg(imp)

    # migrate
    mig = sub.add_parser("migrate", help="Migrate memories to another backend")
    mig.add_argument("--dest", required=True, choices=["memory", "json", "chroma", "qdrant", "pinecone"])
    mig.add_argument("--namespaces", help="Comma-separated namespaces to migrate")
    mig.add_argument("--merge", default="skip", choices=["skip", "overwrite", "error"])
    mig.add_argument("--dry-run", action="store_true", help="Preview only")
    mig.add_argument("--json", action="store_true", help="JSON output")
    mig.add_argument("--batch-size", type=int, default=100, help="Progress callback interval")
    mig.add_argument(
        "--dest-option",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Destination backend option (repeatable)",
    )
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
    _add_backend_arg(mig)

    # mine
    mine_p = sub.add_parser("mine", help="Smart mine — import files/conversations into memories")
    mine_p.add_argument("paths", nargs="+", help="Files or directories to mine")
    mine_p.add_argument(
        "--format",
        choices=["auto", "claude", "chatgpt", "slack", "discord", "telegram", "openclaw"],
        default="auto",
        help="Force format (default: auto-detect)",
    )
    mine_p.add_argument("--tags", nargs="*", help="Extra tags to apply to all chunks")
    mine_p.add_argument(
        "--chunk-size", type=int, default=800, dest="chunk_size", help="Max chars per chunk (default: 800)"
    )
    mine_p.add_argument(
        "--chunk-overlap",
        type=int,
        default=100,
        dest="chunk_overlap",
        help="Overlap chars between chunks (default: 100)",
    )
    mine_p.add_argument("--dry-run", action="store_true", help="Preview without storing")
    mine_p.add_argument("--verbose", "-v", action="store_true")
    mine_p.add_argument("--backend", default="json", choices=["memory", "json", "chroma", "qdrant"])
    mine_p.add_argument("--persist-path", dest="persist_path", default=str(Path.home() / ".memos" / "store.json"))
    mine_p.add_argument("--update", action="store_true", help="Re-mine files even if cached, replacing old memories")
    mine_p.add_argument("--diff", action="store_true", help="Only mine chunks not previously seen for each file")
    mine_p.add_argument(
        "--cache-db",
        dest="cache_db",
        default=str(Path.home() / ".memos" / "mine-cache.db"),
        help="Path to mine cache SQLite DB (default: ~/.memos/mine-cache.db)",
    )
    mine_p.add_argument(
        "--no-cache", dest="no_cache", action="store_true", help="Disable incremental cache for this run"
    )

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
    mine_status_p.add_argument(
        "--cache-db",
        dest="cache_db",
        default=str(Path.home() / ".memos" / "mine-cache.db"),
        help="Path to mine cache SQLite DB",
    )

    # mine-stale
    mine_stale_p = sub.add_parser("mine-stale", help="Report sources changed since last mine (staleness detection)")
    mine_stale_p.add_argument(
        "--only-stale", dest="only_stale", action="store_true", help="Only show changed/missing files (hide fresh)"
    )
    mine_stale_p.add_argument(
        "--cache-db",
        dest="cache_db",
        default=str(Path.home() / ".memos" / "mine-cache.db"),
        help="Path to mine cache SQLite DB",
    )

    # skills-export
    skills_p = sub.add_parser("skills-export", help="Export MemOS workflows as agent skill files")
    skills_p.add_argument("--output", "-o", default=None, help="Output directory (default: ~/.claude/commands/)")
    skills_p.add_argument(
        "--format",
        "-f",
        choices=["claude-code", "generic"],
        default="claude-code",
        help="Skill format (default: claude-code)",
    )
    skills_p.add_argument("--skills", nargs="*", default=None, help="Specific skills to export (default: all)")
    skills_p.add_argument("--overwrite", action="store_true", help="Overwrite existing skill files")
    skills_p.add_argument(
        "--list", dest="list_skills", action="store_true", help="List available skill names without exporting"
    )
