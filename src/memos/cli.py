"""MemOS CLI — command-line interface."""

from __future__ import annotations

import argparse
import os
import json
import sys
import time
from datetime import datetime, timezone
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
    """Export memories to JSON or Parquet file."""
    mem = _get_memos(ns)
    fmt = getattr(ns, "format", "json") or "json"

    if fmt == "parquet":
        out = ns.output
        if not out:
            print("Error: --output is required for parquet format", file=sys.stderr)
            sys.exit(1)
        result = mem.export_parquet(
            out,
            include_metadata=not ns.no_metadata,
            compression=getattr(ns, "compression", "zstd") or "zstd",
        )
        print(f"Exported {result['total']} memories to {out} "
              f"({result['size_bytes']} bytes, {result['compression']})")
        return

    # Default: JSON
    data = mem.export_json(include_metadata=not ns.no_metadata)
    out = ns.output or "-"
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if out == "-":
        print(text)
    else:
        Path(out).write_text(text, encoding="utf-8")
        print(f"Exported {data['total']} memories to {out}")


def cmd_import(ns: argparse.Namespace) -> None:
    """Import memories from JSON or Parquet file."""
    mem = _get_memos(ns)
    src = ns.input
    tags_prefix = ns.tags.split(",") if ns.tags else None

    # Auto-detect format from extension
    is_parquet = src.endswith(".parquet") if src != "-" else False

    if is_parquet:
        result = mem.import_parquet(
            src,
            merge=ns.merge,
            tags_prefix=tags_prefix,
            dry_run=ns.dry_run,
        )
    else:
        text = Path(src).read_text(encoding="utf-8") if src != "-" else sys.stdin.read()
        data = json.loads(text)
        result = mem.import_json(data, merge=ns.merge, tags_prefix=tags_prefix, dry_run=ns.dry_run)

    label = " (dry-run)" if ns.dry_run else ""
    fmt = "parquet" if is_parquet else "json"
    print(f"{label}[{fmt}] Imported: {result['imported']}, Skipped: {result['skipped']}, "
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
    exp = sub.add_parser("export", help="Export all memories to JSON or Parquet")
    exp.add_argument("--output", "-o", help="Output file (default: stdout)")
    exp.add_argument("--format", "-f", choices=["json", "parquet"], default="json", help="Export format (default: json)")
    exp.add_argument("--compression", choices=["zstd", "snappy", "gzip", "none"], default="zstd", help="Parquet compression (default: zstd)")
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


    # ── Versioning commands ─────────────────────────────────────

    # history
    hist = sub.add_parser("history", help="Show version history for a memory")
    hist.add_argument("item_id", help="Memory item ID")
    hist.add_argument("--json", action="store_true", help="JSON output")
    hist.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # diff
    diff_p = sub.add_parser("diff", help="Show diff between two versions")
    diff_p.add_argument("item_id", help="Memory item ID")
    diff_p.add_argument("--v1", type=int, help="First version number")
    diff_p.add_argument("--v2", type=int, help="Second version number")
    diff_p.add_argument("--latest", action="store_true", help="Diff last two versions")
    diff_p.add_argument("--json", action="store_true", help="JSON output")
    diff_p.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # rollback
    rb = sub.add_parser("rollback", help="Roll back a memory to a previous version")
    rb.add_argument("item_id", help="Memory item ID")
    rb.add_argument("--version", type=int, required=True, help="Target version number")
    rb.add_argument("--yes", action="store_true", help="Confirm rollback")
    rb.add_argument("--dry-run", action="store_true", help="Preview only")
    rb.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # snapshot-at
    snap = sub.add_parser("snapshot-at", help="Show all memories at a point in time")
    snap.add_argument("timestamp", help="Timestamp (epoch, ISO 8601, or relative like 1h, 2d)")
    snap.add_argument("--json", action="store_true", help="JSON output")
    snap.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # recall-at
    rcat = sub.add_parser("recall-at", help="Time-travel recall - query memories at a past time")
    rcat.add_argument("query", help="Search query")
    rcat.add_argument("--at", dest="timestamp", required=True, help="Timestamp (epoch, ISO 8601, or relative)")
    rcat.add_argument("--top", "-n", type=int, default=5)
    rcat.add_argument("--min-score", type=float, default=0.0)
    rcat.add_argument("--json", action="store_true", help="JSON output")
    rcat.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # version-stats
    vstats = sub.add_parser("version-stats", help="Show versioning statistics")
    vstats.add_argument("--json", action="store_true", help="JSON output")
    vstats.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # version-gc
    vgc = sub.add_parser("version-gc", help="Garbage collect old memory versions")
    vgc.add_argument("--max-age-days", type=float, default=90.0, help="Remove versions older than N days")
    vgc.add_argument("--keep-latest", type=int, default=3, help="Keep at least N latest versions per item")
    vgc.add_argument("--dry-run", action="store_true", help="Preview only")
    vgc.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # ── Namespace ACL commands ──────────────────────────────────

    # namespace grant
    ns_grant = sub.add_parser("ns-grant", help="Grant an agent access to a namespace")
    ns_grant.add_argument("namespace", help="Target namespace")
    ns_grant.add_argument("--agent", required=True, help="Agent ID")
    ns_grant.add_argument("--role", required=True, choices=["owner", "writer", "reader", "denied"], help="Access role")
    ns_grant.add_argument("--expires", type=float, default=None, help="Expires at (epoch timestamp)")
    ns_grant.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # namespace revoke
    ns_revoke = sub.add_parser("ns-revoke", help="Revoke an agent's namespace access")
    ns_revoke.add_argument("namespace", help="Target namespace")
    ns_revoke.add_argument("--agent", required=True, help="Agent ID")
    ns_revoke.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # namespace policies
    ns_list = sub.add_parser("ns-policies", help="List namespace ACL policies")
    ns_list.add_argument("--namespace", help="Filter by namespace")
    ns_list.add_argument("--json", action="store_true", help="JSON output")
    ns_list.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # namespace stats
    ns_stats = sub.add_parser("ns-stats", help="Show namespace ACL statistics")
    ns_stats.add_argument("--json", action="store_true", help="JSON output")
    ns_stats.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    return p




def _parse_timestamp(ts_str: str) -> float:
    """Parse timestamp: epoch, ISO 8601, or relative (1h, 30m, 2d, 1w)."""
    try:
        return float(ts_str)
    except ValueError:
        pass
    now = time.time()
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    if ts_str[-1] in units:
        try:
            return now - float(ts_str[:-1]) * units[ts_str[-1]]
        except (ValueError, IndexError):
            pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M",
                "%Y-%m-%dT%H:%M%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(ts_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse timestamp: {ts_str!r}")


def _fmt_ts(epoch: float) -> str:
    """Format an epoch timestamp for display."""
    return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")




def cmd_history(ns: argparse.Namespace) -> None:
    """Show version history for a memory item."""
    memos = _get_memos(ns)
    versions = memos.history(ns.item_id)
    if not versions:
        print(f"No version history for item {ns.item_id[:12]}...")
        return
    if getattr(ns, "json", False):
        print(json.dumps([v.to_dict() for v in versions], indent=2))
        return
    print(f"Version history for {ns.item_id[:12]}...  ({len(versions)} versions)\n")
    for v in versions:
        preview = v.content[:80].replace("\n", " ")
        print(f"  v{v.version_number:>3d}  {_fmt_ts(v.created_at)}  [{v.source:12s}]  {preview}")
    print()


def cmd_diff(ns: argparse.Namespace) -> None:
    """Show diff between two versions of a memory."""
    memos = _get_memos(ns)
    item_id = ns.item_id
    if getattr(ns, "latest", False):
        result = memos.diff_latest(item_id)
        if result is None:
            print(f"Fewer than 2 versions for item {item_id[:12]}...")
            return
    else:
        v1, v2 = ns.v1, ns.v2
        if v1 is None or v2 is None:
            print("Error: provide --v1 and --v2, or --latest", file=sys.stderr)
            sys.exit(1)
        result = memos.diff(item_id, v1, v2)
        if result is None:
            print(f"Version(s) not found for item {item_id[:12]}...")
            return
    if getattr(ns, "json", False):
        print(json.dumps(result.to_dict(), indent=2))
        return
    d = result.to_dict()
    print(f"Diff: {item_id[:12]}...  v{d['from_version']} -> v{d['to_version']}  "
          f"(delta {d['delta_seconds']:.1f}s)\n")
    if not d["changes"]:
        print("  (no changes)")
    else:
        for field, change in d["changes"].items():
            print(f"  {field}:")
            if field == "tags":
                old = ", ".join(change.get("from", []))
                new = ", ".join(change.get("to", []))
                added = change.get("added", [])
                removed = change.get("removed", [])
                print(f"    - {old or '(none)'}")
                print(f"    + {new or '(none)'}")
                if added:
                    print(f"    added: {', '.join(added)}")
                if removed:
                    print(f"    removed: {', '.join(removed)}")
            elif field == "content":
                print(f"    - {change['from'][:200]}")
                print(f"    + {change['to'][:200]}")
            else:
                print(f"    {change.get('from', '?')} -> {change.get('to', '?')}")
    print()


def cmd_rollback(ns: argparse.Namespace) -> None:
    """Roll back a memory item to a specific version."""
    memos = _get_memos(ns)
    if getattr(ns, "dry_run", False):
        ver = memos.get_version(ns.item_id, ns.version)
        if ver is None:
            print(f"Version {ns.version} not found for item {ns.item_id[:12]}...", file=sys.stderr)
            sys.exit(1)
        print(f"Would roll back {ns.item_id[:12]}... to v{ns.version}:")
        print(f"  Content: {ver.content[:120]}")
        print(f"  Tags: {', '.join(ver.tags) or '(none)'}")
        print("(dry-run)")
        return
    if not getattr(ns, "yes", False):
        ver = memos.get_version(ns.item_id, ns.version)
        if ver is None:
            print(f"Version {ns.version} not found for item {ns.item_id[:12]}...", file=sys.stderr)
            sys.exit(1)
        print(f"Will roll back {ns.item_id[:12]}... to v{ns.version}:")
        print(f"  Content: {ver.content[:120]}")
        print(f"  Tags: {', '.join(ver.tags) or '(none)'}")
        print(f"  Importance: {ver.importance}")
        print("Use --yes to confirm.")
        return
    result = memos.rollback(ns.item_id, ns.version)
    if result is None:
        print(f"X Rollback failed - version {ns.version} not found", file=sys.stderr)
        sys.exit(1)
    print(f"OK Rolled back {ns.item_id[:12]}... to v{ns.version}")


def cmd_snapshot_at(ns: argparse.Namespace) -> None:
    """Show all memories as they were at a given point in time."""
    memos = _get_memos(ns)
    ts = _parse_timestamp(ns.timestamp)
    versions = memos.snapshot_at(ts)
    if getattr(ns, "json", False):
        print(json.dumps([v.to_dict() for v in versions], indent=2))
        return
    print(f"Snapshot at {_fmt_ts(ts)}  ({len(versions)} memories)\n")
    if not versions:
        print("  (no memories existed at that time)")
        return
    for v in versions[:50]:
        tags_str = f" [{', '.join(v.tags[:3])}]" if v.tags else ""
        vc = v.content[:100].replace("\n", " ")
        print(f"  [{v.item_id[:8]}] {vc}{tags_str}  (v{v.version_number})")
    if len(versions) > 50:
        print(f"\n  ... and {len(versions) - 50} more")
    print()


def cmd_recall_at(ns: argparse.Namespace) -> None:
    """Time-travel recall - query memories at a past time."""
    memos = _get_memos(ns)
    ts = _parse_timestamp(ns.timestamp)
    results = memos.recall_at(ns.query, ts, top=ns.top, min_score=ns.min_score)
    if getattr(ns, "json", False):
        print(json.dumps([{"id": r.item.id, "content": r.item.content,
                           "score": round(r.score, 4), "tags": r.item.tags,
                           "match_reason": r.match_reason} for r in results], indent=2))
        return
    if not results:
        print(f"No memories found at {_fmt_ts(ts)}.")
        return
    print(f"Recall at {_fmt_ts(ts)}  ({len(results)} results)\n")
    for r in results:
        tags_str = f" [{', '.join(r.item.tags)}]" if r.item.tags else ""
        print(f"  {r.score:.3f} {r.item.content[:120]}{tags_str}")
    print(f"\n{len(results)} result(s)")


def cmd_version_stats(ns: argparse.Namespace) -> None:
    """Show versioning statistics."""
    memos = _get_memos(ns)
    s = memos.versioning_stats()
    if getattr(ns, "json", False):
        print(json.dumps(s, indent=2))
        return
    print("Versioning Statistics\n")
    print(f"  Total versions:        {s.get('total_versions', 0)}")
    print(f"  Tracked items:         {s.get('total_items', 0)}")
    print(f"  Avg versions/item:     {s.get('avg_versions_per_item', 0):.1f}")
    print(f"  Max versions/item:     {s.get('max_versions_per_item', 0)}")
    oldest = s.get('oldest_version')
    print(f"  Oldest version:        {_fmt_ts(oldest) if oldest else 'N/A'}")
    print(f"  Estimated memory (KB): {s.get('estimated_size_kb', 0):.1f}")


def cmd_version_gc(ns: argparse.Namespace) -> None:
    """Garbage collect old memory versions."""
    memos = _get_memos(ns)
    if getattr(ns, "dry_run", False):
        sb = memos.versioning_stats()
        print(f"Current: {sb.get('total_versions', 0)} versions")
        print(f"Would remove versions older than {ns.max_age_days} days "
              f"(keeping latest {ns.keep_latest}/item)")
        return
    removed = memos.versioning_gc(max_age_days=ns.max_age_days, keep_latest=ns.keep_latest)
    print(f"OK Garbage collected {removed} old versions")


def cmd_ns_grant(ns: argparse.Namespace) -> None:
    """Grant an agent access to a namespace."""
    memos = _get_memos(ns)
    policy = memos.grant_namespace_access(
        agent_id=ns.agent,
        namespace=ns.namespace,
        role=ns.role,
        expires_at=ns.expires,
    )
    print(f"✓ Granted {ns.role} access to '{ns.namespace}' for agent '{ns.agent}'")
    if ns.json if hasattr(ns, 'json') else False:
        print(json.dumps(policy, indent=2))


def cmd_ns_revoke(ns: argparse.Namespace) -> None:
    """Revoke an agent's namespace access."""
    memos = _get_memos(ns)
    success = memos.revoke_namespace_access(
        agent_id=ns.agent,
        namespace=ns.namespace,
    )
    print(f"✓ Revoked access to '{ns.namespace}' for agent '{ns.agent}'" if success else "✗ No policy found")


def cmd_ns_policies(ns: argparse.Namespace) -> None:
    """List namespace ACL policies."""
    memos = _get_memos(ns)
    policies = memos.list_namespace_policies(namespace=getattr(ns, 'namespace', None))
    if getattr(ns, 'json', False):
        print(json.dumps(policies, indent=2))
        return
    if not policies:
        print("No policies found")
        return
    for p in policies:
        expires = f" (expires: {p['expires_at']})" if p.get('expires_at') else ""
        print(f"  {p['agent_id']}  {p['namespace']}  {p['role']}{expires}")
    print(f"\n{len(policies)} policy(ies)")


def cmd_ns_stats(ns: argparse.Namespace) -> None:
    """Show namespace ACL statistics."""
    memos = _get_memos(ns)
    stats = memos.namespace_acl_stats()
    if getattr(ns, 'json', False):
        print(json.dumps(stats, indent=2))
        return
    print(f"  Total policies:  {stats['total_policies']}")
    print(f"  Total agents:    {stats['total_agents']}")
    print(f"  Total namespaces:{stats['total_namespaces']}")
    if stats.get('role_distribution'):
        for role, count in stats['role_distribution'].items():
            print(f"    {role}: {count}")

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
        "history": cmd_history,
        "diff": cmd_diff,
        "rollback": cmd_rollback,
        "snapshot-at": cmd_snapshot_at,
        "recall-at": cmd_recall_at,
        "version-stats": cmd_version_stats,
        "version-gc": cmd_version_gc,
        "ns-grant": cmd_ns_grant,
        "ns-revoke": cmd_ns_revoke,
        "ns-policies": cmd_ns_policies,
        "ns-stats": cmd_ns_stats,
    }
    commands[ns.command](ns)


if __name__ == "__main__":
    main()
