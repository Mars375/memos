"""MemOS CLI — command-line interface."""

from __future__ import annotations

import argparse
import os
import json
import sys
from pathlib import Path

from . import __version__
from .config import config_path, load_config, resolve, write_config, DEFAULTS, ENV_MAP
from .core import MemOS


def _get_memos(ns: argparse.Namespace) -> MemOS:
    cli_overrides = {
        "backend": getattr(ns, "backend", None),
        "chroma_host": getattr(ns, "chroma_host", None),
        "chroma_port": getattr(ns, "chroma_port", None),
        "embed_host": getattr(ns, "embed_host", None),
        "sanitize": not getattr(ns, "no_sanitize", False) or None,
    }
    cfg = resolve({k: v for k, v in cli_overrides.items() if v is not None})
    kwargs: dict = {"backend": cfg["backend"]}
    if cfg["backend"] == "chroma":
        kwargs["chroma_host"] = cfg["chroma_host"]
        kwargs["chroma_port"] = cfg["chroma_port"]
    if cfg.get("embed_host"):
        kwargs["embed_host"] = cfg["embed_host"]
    if not cfg.get("sanitize", True):
        kwargs["sanitize"] = False
    return MemOS(**kwargs)


def cmd_init(ns: argparse.Namespace) -> None:
    """Initialize a MemOS data directory."""
    path = Path(ns.directory)
    path.mkdir(parents=True, exist_ok=True)
    cfg = path / "memos.json"
    if cfg.exists() and not ns.force:
        print(f"Already initialized: {cfg}", file=sys.stderr)
        sys.exit(1)
    config = {
        "backend": getattr(ns, "backend", "memory"),
        "version": __version__,
    }
    cfg.write_text(json.dumps(config, indent=2))
    print(f"✓ Initialized MemOS in {path}/")


def cmd_learn(ns: argparse.Namespace) -> None:
    """Learn (store) a new memory."""
    memos = _get_memos(ns)
    content = ns.content
    if ns.file:
        content = Path(ns.file).read_text().strip()
    if not content:
        print("Error: no content provided (use positional arg or --file)", file=sys.stderr)
        sys.exit(1)
    tags = ns.tags.split(",") if ns.tags else []
    item = memos.learn(content, tags=tags, importance=ns.importance)
    print(f"✓ Learned [{item.id[:8]}...] ({len(item.content)} chars, tags={item.tags})")


def cmd_batch_learn(ns: argparse.Namespace) -> None:
    """Batch learn — store multiple memories from a JSON file."""
    memos = _get_memos(ns)
    src = ns.input
    text = Path(src).read_text(encoding="utf-8") if src != "-" else sys.stdin.read()
    data = json.loads(text)
    items = data if isinstance(data, list) else data.get("items", [])
    if not items:
        print("No items found in input", file=sys.stderr)
        sys.exit(1)
    result = memos.batch_learn(
        items=items,
        continue_on_error=not ns.strict,
    )
    label = " (dry-run)" if ns.dry_run else ""
    print(f"{label}Batch learn: {result['learned']} learned, {result['skipped']} skipped, {len(result['errors'])} errors")
    if ns.verbose and result["items"]:
        for item in result["items"][:10]:
            print(f"  ✓ [{item['id'][:8]}] {item['content'][:80]}")
        if len(result["items"]) > 10:
            print(f"  ... and {len(result['items']) - 10} more")
    if result["errors"]:
        for err in result["errors"][:5]:
            print(f"  ⚠ {err.get('reason', err)}", file=sys.stderr)


def cmd_recall(ns: argparse.Namespace) -> None:
    """Recall memories matching a query."""
    memos = _get_memos(ns)
    results = memos.recall(ns.query, top=ns.top, min_score=ns.min_score)
    if not results:
        print("No memories found.")
        return
    for r in results:
        tags_str = f" [{', '.join(r.item.tags)}]" if r.item.tags else ""
        print(f"  {r.score:.3f} {r.item.content[:120]}{tags_str}")
    print(f"\n{len(results)} result(s)")


def cmd_stats(ns: argparse.Namespace) -> None:
    """Show memory store statistics."""
    memos = _get_memos(ns)
    s = memos.stats()
    if ns.json:
        print(json.dumps({
            "total_memories": s.total_memories,
            "total_tags": s.total_tags,
            "avg_relevance": round(s.avg_relevance, 3),
            "avg_importance": round(s.avg_importance, 3),
            "decay_candidates": s.decay_candidates,
            "top_tags": s.top_tags,
        }, indent=2))
        return
    print(f"  Total memories:  {s.total_memories}")
    print(f"  Total tags:      {s.total_tags}")
    print(f"  Avg relevance:   {s.avg_relevance:.3f}")
    print(f"  Avg importance:  {s.avg_importance:.3f}")
    print(f"  Decay candidates:{s.decay_candidates}")
    if s.top_tags:
        print(f"  Top tags:        {', '.join(s.top_tags[:5])}")


def cmd_forget(ns: argparse.Namespace) -> None:
    """Forget (delete) a memory by ID or content."""
    memos = _get_memos(ns)
    ok = memos.forget(ns.target)
    print("✓ Forgotten" if ok else "✗ Not found")


def cmd_prune(ns: argparse.Namespace) -> None:
    """Prune decayed memories."""
    memos = _get_memos(ns)
    candidates = memos.prune(
        threshold=ns.threshold,
        max_age_days=ns.max_age,
        dry_run=ns.dry_run,
    )
    label = "would be pruned" if ns.dry_run else "pruned"
    print(f"✓ {len(candidates)} memories {label}")
    if ns.verbose:
        for c in candidates[:10]:
            print(f"  - [{c.id[:8]}] {c.content[:80]}")


def cmd_consolidate(ns: argparse.Namespace) -> None:
    """Find and merge semantically similar memories."""
    memos = _get_memos(ns)
    result = memos.consolidate(
        similarity_threshold=ns.threshold,
        merge_content=ns.merge,
        dry_run=ns.dry_run,
    )
    label = "would be" if ns.dry_run else ""
    print(f"Groups found: {result.groups_found}")
    print(f"Memories {label} merged: {result.memories_merged}")
    if not ns.dry_run:
        print(f"Space freed: {result.space_freed} memories removed")
    if ns.verbose:
        for g in result.details[:10]:
            print(f"  [{g.reason}] sim={g.similarity:.2f} keep=[{g.keep.id[:8]}] {g.keep.content[:60]}")
            for d in g.duplicates:
                print(f"    dup=[{d.id[:8]}] {d.content[:60]}")


def cmd_serve(ns: argparse.Namespace) -> None:
    """Start the REST API server."""
    try:
        import uvicorn
    except ImportError:
        print("Error: install memos[server] first", file=sys.stderr)
        sys.exit(1)

    from .api import create_fastapi_app

    kwargs: dict = {}
    import os

    backend = os.environ.get("MEMOS_BACKEND", getattr(ns, "backend", "memory"))
    kwargs["backend"] = backend
    if backend == "chroma":
        # Support MEMOS_CHROMA_URL (docker-compose) or individual flags
        chroma_url = os.environ.get("MEMOS_CHROMA_URL", "")
        if chroma_url and "//" in chroma_url:
            from urllib.parse import urlparse
            parsed = urlparse(chroma_url)
            kwargs["chroma_host"] = parsed.hostname or "localhost"
            kwargs["chroma_port"] = parsed.port or 8000
        else:
            kwargs["chroma_host"] = getattr(ns, "chroma_host", "localhost")
            kwargs["chroma_port"] = getattr(ns, "chroma_port", 8000)

    app = create_fastapi_app(**kwargs)
    uvicorn.run(app, host=ns.host, port=ns.port)


def cmd_export(ns: argparse.Namespace) -> None:
    """Export memories to JSON file."""
    mem = _get_memos(ns)
    data = mem.export_json(include_metadata=not ns.no_metadata)
    out = ns.output or "-"
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if out == "-":
        print(text)
    else:
        Path(out).write_text(text, encoding="utf-8")
        print(f"Exported {data['total']} memories to {out}")


def cmd_import(ns: argparse.Namespace) -> None:
    """Import memories from JSON file."""
    mem = _get_memos(ns)
    src = ns.input
    text = Path(src).read_text(encoding="utf-8") if src != "-" else sys.stdin.read()
    data = json.loads(text)
    tags_prefix = ns.tags.split(",") if ns.tags else None
    result = mem.import_json(data, merge=ns.merge, tags_prefix=tags_prefix, dry_run=ns.dry_run)
    label = " (dry-run)" if ns.dry_run else ""
    print(f"{label}Imported: {result['imported']}, Skipped: {result['skipped']}, "
          f"Overwritten: {result['overwritten']}")
    if result["errors"]:
        for e in result["errors"]:
            print(f"  Error: {e}", file=sys.stderr)


def cmd_ingest(ns: argparse.Namespace) -> None:
    """Ingest files into memory."""
    memos = _get_memos(ns)
    tags = ns.tags.split(",") if ns.tags else None

    for fpath in ns.files:
        result = memos.ingest(
            fpath,
            tags=tags,
            importance=ns.importance,
            max_chunk=ns.max_chunk,
            dry_run=ns.dry_run,
        )
        label = "DRY-RUN " if ns.dry_run else ""
        print(f"{label}{fpath}: {result.total_chunks} chunks, {result.skipped} skipped")
        if result.errors:
            for err in result.errors:
                print(f"  ⚠ {err}", file=sys.stderr)


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
    init.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])
    init.add_argument("--force", action="store_true", help="Overwrite existing config")

    # learn
    learn = sub.add_parser("learn", help="Store a new memory")
    learn.add_argument("content", nargs="?", help="Memory content")
    learn.add_argument("--file", "-f", help="Read content from file")
    learn.add_argument("--tags", "-t", help="Comma-separated tags")
    learn.add_argument("--importance", "-i", type=float, default=0.5)
    learn.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])
    learn.add_argument("--no-sanitize", action="store_true")

    # batch-learn
    batch_learn = sub.add_parser("batch-learn", help="Store multiple memories from JSON")
    batch_learn.add_argument("input", help="JSON file with items (use - for stdin)")
    batch_learn.add_argument("--strict", action="store_true", help="Stop on first error")
    batch_learn.add_argument("--dry-run", action="store_true", help="Preview only")
    batch_learn.add_argument("--verbose", "-v", action="store_true")
    batch_learn.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # recall
    recall = sub.add_parser("recall", help="Recall memories matching a query")
    recall.add_argument("query", help="Search query")
    recall.add_argument("--top", "-n", type=int, default=5)
    recall.add_argument("--min-score", type=float, default=0.0)
    recall.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # stats
    stats = sub.add_parser("stats", help="Show memory statistics")
    stats.add_argument("--json", action="store_true", help="JSON output")
    stats.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # forget
    forget = sub.add_parser("forget", help="Delete a memory")
    forget.add_argument("target", help="Memory ID or content")
    forget.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # prune
    prune = sub.add_parser("prune", help="Remove decayed memories")
    prune.add_argument("--threshold", type=float, default=0.1)
    prune.add_argument("--max-age", type=float, default=90.0)
    prune.add_argument("--dry-run", action="store_true")
    prune.add_argument("--verbose", "-v", action="store_true")
    prune.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # consolidate
    cons = sub.add_parser("consolidate", help="Find and merge duplicate memories")
    cons.add_argument("--threshold", type=float, default=0.75, help="Similarity threshold (0-1)")
    cons.add_argument("--merge", action="store_true", help="Merge content from duplicates")
    cons.add_argument("--dry-run", action="store_true", help="Report only, don't modify")
    cons.add_argument("--verbose", "-v", action="store_true")
    cons.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # ingest
    ing = sub.add_parser("ingest", help="Import file(s) into memory")
    ing.add_argument("files", nargs="+", help="Files to ingest (md, json, txt)")
    ing.add_argument("--tags", "-t", help="Comma-separated tags to add")
    ing.add_argument("--importance", "-i", type=float, default=0.5)
    ing.add_argument("--dry-run", action="store_true", help="Parse only, don't store")
    ing.add_argument("--max-chunk", type=int, default=2000, help="Max chars per chunk")
    ing.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # export
    exp = sub.add_parser("export", help="Export all memories to JSON")
    exp.add_argument("--output", "-o", help="Output file (default: stdout)")
    exp.add_argument("--no-metadata", action="store_true", help="Exclude metadata")
    exp.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # import
    imp = sub.add_parser("import", help="Import memories from JSON")
    imp.add_argument("input", help="Input JSON file (use - for stdin)")
    imp.add_argument("--merge", default="skip", choices=["skip", "overwrite", "duplicate"])
    imp.add_argument("--tags", "-t", help="Extra tags to add to imported memories")
    imp.add_argument("--dry-run", action="store_true", help="Preview only")
    imp.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # serve
    serve = sub.add_parser("serve", help="Start REST API server")
    serve.add_argument("--host", default=os.environ.get("MEMOS_HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=int(os.environ.get("MEMOS_PORT", "8000")))
    serve.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])
    serve.add_argument("--chroma-host", default="localhost")
    serve.add_argument("--chroma-port", type=int, default=8000)

    # config
    cfg_p = sub.add_parser("config", help="View or set CLI configuration")
    cfg_sub = cfg_p.add_subparsers(dest="config_action")
    cfg_show = cfg_sub.add_parser("show", help="Show current resolved config")
    cfg_show.add_argument("--json", action="store_true", help="JSON output")
    cfg_path_cmd = cfg_sub.add_parser("path", help="Show config file path")
    cfg_set = cfg_sub.add_parser("set", help="Set a config value")
    cfg_set.add_argument("key_value", nargs="+", help="key=value pairs")
    cfg_init = cfg_sub.add_parser("init", help="Create default config file")
    cfg_init.add_argument("--force", action="store_true", help="Overwrite existing")

    return p


def cmd_config(ns: argparse.Namespace) -> None:
    """Manage CLI configuration."""
    action = getattr(ns, "config_action", None)
    if not action:
        print(f"Config file: {config_path()}")
        print(f"Exists: {config_path().is_file()}")
        print("Use: memos config [show|path|set|init]")
        return

    if action == "path":
        print(str(config_path()))
    elif action == "show":
        cfg = resolve()
        if getattr(ns, "json", False):
            print(json.dumps(cfg, indent=2, default=str))
        else:
            p = config_path()
            print(f"# Resolved config (file={p}, exists={p.is_file()})")
            for k, v in cfg.items():
                src = "default"
                file_cfg = load_config()
                env_val = os.environ.get({v_: k_ for k_, v_ in ENV_MAP.items()}.get(k, ""))
                if k in file_cfg:
                    src = "file"
                if env_val is not None:
                    src = "env"
                print(f"  {k} = {v!r}  ({src})")
    elif action == "set":
        existing = load_config() if config_path().is_file() else {}
        for pair in ns.key_value:
            if "=" not in pair:
                print(f"Error: expected key=value, got '{pair}'", file=sys.stderr)
                sys.exit(1)
            key, val = pair.split("=", 1)
            if key not in DEFAULTS:
                print(f"Error: unknown key '{key}'. Valid: {', '.join(sorted(DEFAULTS))}", file=sys.stderr)
                sys.exit(1)
            # Type coercion
            if isinstance(DEFAULTS[key], bool):
                existing[key] = val.lower() in ("true", "1", "yes")
            elif isinstance(DEFAULTS[key], int):
                existing[key] = int(val)
            elif isinstance(DEFAULTS[key], float):
                existing[key] = float(val)
            else:
                existing[key] = val
        p = write_config(existing)
        print(f"✓ Config written to {p}")
    elif action == "init":
        p = config_path()
        if p.is_file() and not ns.force:
            print(f"Config exists: {p} (use --force to overwrite)", file=sys.stderr)
            sys.exit(1)
        write_config({}, p)
        print(f"✓ Default config created at {p}")


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    ns = parser.parse_args(argv)
    if not ns.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "init": cmd_init,
        "learn": cmd_learn,
        "batch-learn": cmd_batch_learn,
        "recall": cmd_recall,
        "stats": cmd_stats,
        "forget": cmd_forget,
        "prune": cmd_prune,
        "serve": cmd_serve,
        "consolidate": cmd_consolidate,
        "ingest": cmd_ingest,
        "export": cmd_export,
        "import": cmd_import,
        "config": cmd_config,
    }
    commands[ns.command](ns)


if __name__ == "__main__":
    main()
