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
from .models import parse_ttl


def _get_memos(ns: argparse.Namespace) -> MemOS:
    cli_overrides = {
        "backend": getattr(ns, "backend", None),
        "chroma_host": getattr(ns, "chroma_host", None),
        "chroma_port": getattr(ns, "chroma_port", None),
        "persist_path": getattr(ns, "persist_path", None),
        "qdrant_host": getattr(ns, "qdrant_host", None),
        "qdrant_port": getattr(ns, "qdrant_port", None),
        "qdrant_api_key": getattr(ns, "qdrant_api_key", None),
        "qdrant_path": getattr(ns, "qdrant_path", None),
        "pinecone_api_key": getattr(ns, "pinecone_api_key", None),
        "pinecone_environment": getattr(ns, "pinecone_environment", None),
        "pinecone_index_name": getattr(ns, "pinecone_index_name", None),
        "pinecone_cloud": getattr(ns, "pinecone_cloud", None),
        "pinecone_region": getattr(ns, "pinecone_region", None),
        "pinecone_serverless": getattr(ns, "pinecone_serverless", None),
        "vector_size": getattr(ns, "vector_size", None),
        "embed_host": getattr(ns, "embed_host", None),
        "embed_model": getattr(ns, "embed_model", None),
        "sanitize": not getattr(ns, "no_sanitize", False) or None,
    }
    cfg = resolve({k: v for k, v in cli_overrides.items() if v is not None})
    kwargs: dict = {"backend": cfg["backend"]}
    if cfg["backend"] == "chroma":
        kwargs["chroma_host"] = cfg["chroma_host"]
        kwargs["chroma_port"] = cfg["chroma_port"]
    if cfg["backend"] == "qdrant":
        kwargs["qdrant_host"] = cfg["qdrant_host"]
        kwargs["qdrant_port"] = cfg["qdrant_port"]
        if cfg.get("qdrant_api_key"):
            kwargs["qdrant_api_key"] = cfg["qdrant_api_key"]
        if cfg.get("qdrant_path"):
            kwargs["qdrant_path"] = cfg["qdrant_path"]
        if cfg.get("vector_size"):
            kwargs["vector_size"] = cfg["vector_size"]
    if cfg["backend"] == "pinecone":
        if cfg.get("pinecone_api_key"):
            kwargs["pinecone_api_key"] = cfg["pinecone_api_key"]
        if cfg.get("pinecone_environment"):
            kwargs["pinecone_environment"] = cfg["pinecone_environment"]
        if cfg.get("pinecone_index_name"):
            kwargs["pinecone_index_name"] = cfg["pinecone_index_name"]
        if cfg.get("pinecone_cloud"):
            kwargs["pinecone_cloud"] = cfg["pinecone_cloud"]
        if cfg.get("pinecone_region"):
            kwargs["pinecone_region"] = cfg["pinecone_region"]
        if cfg.get("pinecone_serverless") is not None:
            kwargs["pinecone_serverless"] = cfg["pinecone_serverless"]
        if cfg.get("vector_size"):
            kwargs["vector_size"] = cfg["vector_size"]
    if cfg.get("embed_host"):
        kwargs["embed_host"] = cfg["embed_host"]
    if cfg.get("embed_model"):
        kwargs["embed_model"] = cfg["embed_model"]
    if cfg.get("persist_path"):
        kwargs["persist_path"] = cfg["persist_path"]
    if not cfg.get("sanitize", True):
        kwargs["sanitize"] = False
    # Default "memory" backend auto-persists to .memos/store.json
    if cfg["backend"] == "memory" and "persist_path" not in kwargs:
        kwargs["persist_path"] = str(Path(".memos") / "store.json")
    return MemOS(**kwargs)


def _coerce_cli_value(value: str):
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _parse_kv_options(values: list[str] | None) -> dict[str, object]:
    parsed: dict[str, object] = {}
    for entry in values or []:
        if "=" not in entry:
            raise ValueError(f"Expected KEY=VALUE, got {entry!r}")
        key, raw = entry.split("=", 1)
        parsed[key] = _coerce_cli_value(raw)
    return parsed


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
    elif getattr(ns, 'stdin', False):
        content = sys.stdin.read().strip()
    if not content:
        print("Error: no content provided (use positional arg, --file, or --stdin)", file=sys.stderr)
        sys.exit(1)
    tags = ns.tags.split(",") if ns.tags else []
    ttl = None
    if hasattr(ns, 'ttl') and ns.ttl:
        ttl = parse_ttl(ns.ttl)
    item = memos.learn(content, tags=tags, importance=ns.importance, ttl=ttl)
    ttl_str = f", ttl={ns.ttl}" if ns.ttl else ""
    print(f"✓ Learned [{item.id[:8]}...] ({len(item.content)} chars, tags={item.tags}{ttl_str})")


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
    from datetime import datetime as _dt
    memos = _get_memos(ns)
    # Parse tag filter
    filter_tags = None
    if ns.tags:
        filter_tags = [t.strip() for t in ns.tags.split(",") if t.strip()]
    # Parse date filters
    filter_after = None
    filter_before = None
    if ns.after:
        try:
            filter_after = _dt.fromisoformat(ns.after).timestamp()
        except ValueError:
            print(f"Error: Invalid --after date format: {ns.after!r}. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM")
            return
    if ns.before:
        try:
            filter_before = _dt.fromisoformat(ns.before).timestamp()
        except ValueError:
            print(f"Error: Invalid --before date format: {ns.before!r}. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM")
            return
    results = memos.recall(
        ns.query, top=ns.top, min_score=ns.min_score,
        filter_tags=filter_tags, filter_after=filter_after, filter_before=filter_before,
    )
    fmt = getattr(ns, "format", "text") or "text"
    if not results:
        if fmt == "json":
            print(json.dumps({"results": [], "total": 0}))
        else:
            print("No memories found.")
        return
    if fmt == "json":
        print(json.dumps({
            "results": [
                {
                    "id": r.item.id,
                    "content": r.item.content,
                    "score": round(r.score, 4),
                    "tags": r.item.tags,
                    "match_reason": r.match_reason,
                    "importance": r.item.importance,
                    "created_at": r.item.created_at,
                }
                for r in results
            ],
            "total": len(results),
        }, indent=2))
        return
    for r in results:
        tags_str = f" [{', '.join(r.item.tags)}]" if r.item.tags else ""
        print(f"  {r.score:.3f} {r.item.content[:120]}{tags_str}")
    print(f"\n{len(results)} result(s)")



def cmd_search(ns: argparse.Namespace) -> None:
    """Keyword-only search across all memories (no embeddings required)."""
    memos = _get_memos(ns)
    items = memos.search(q=ns.query, limit=ns.limit)
    fmt = getattr(ns, "format", "text") or "text"
    if not items:
        if fmt == "json":
            print(json.dumps({"results": [], "total": 0}))
        else:
            print("No memories found.")
        return
    if fmt == "json":
        print(json.dumps({
            "results": [
                {
                    "id": item.id,
                    "content": item.content[:200],
                    "tags": item.tags,
                    "importance": item.importance,
                }
                for item in items
            ],
            "total": len(items),
        }, indent=2))
        return
    for item in items:
        tags_str = f" [{', '.join(item.tags)}]" if item.tags else ""
        print(f"  [{item.id[:8]}] {item.content[:120]}{tags_str}")
    print(f"\n{len(items)} result(s)")

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
    """Forget (delete) a memory by ID/content or by tag."""
    memos = _get_memos(ns)
    if ns.tag:
        removed = memos.forget_tag(ns.tag)
        print(f"✓ Forgotten {removed} memory(s) with tag '{ns.tag}'" if removed else "✗ Not found")
        return
    if not ns.target:
        print("Error: target or --tag required", file=sys.stderr)
        sys.exit(1)
    ok = memos.forget(ns.target)
    print("✓ Forgotten" if ok else "✗ Not found")


def cmd_get(ns: argparse.Namespace) -> None:
    """Retrieve and display a single memory by ID."""
    memos = _get_memos(ns)
    item = memos.get(ns.item_id)
    if item is None:
        print(f"✗ Memory not found: {ns.item_id}", file=sys.stderr)
        sys.exit(1)
    if getattr(ns, "json", False):
        out = {
            "id": item.id,
            "content": item.content,
            "tags": item.tags,
            "importance": item.importance,
            "created_at": item.created_at,
            "accessed_at": item.accessed_at,
            "access_count": item.access_count,
            "relevance_score": item.relevance_score,
        }
        if item.ttl is not None:
            out["ttl"] = item.ttl
            out["expires_at"] = item.expires_at
            out["is_expired"] = item.is_expired
        public_meta = {k: v for k, v in item.metadata.items() if not k.startswith("_")}
        if public_meta:
            out["metadata"] = public_meta
        print(json.dumps(out, indent=2))
        return
    # Human-readable output
    age_days = (time.time() - item.created_at) / 86400
    print(f"  ID:           {item.id}")
    print(f"  Content:      {item.content}")
    print(f"  Tags:         {', '.join(item.tags) if item.tags else '(none)'}")
    print(f"  Importance:   {item.importance:.2f}")
    print(f"  Relevance:    {item.relevance_score:.3f}")
    print(f"  Created:      {_fmt_ts(item.created_at)}  ({age_days:.1f} days ago)")
    print(f"  Last access:  {_fmt_ts(item.accessed_at)}")
    print(f"  Access count: {item.access_count}")
    if item.ttl is not None:
        print(f"  TTL:          {item.ttl:.0f}s")
        if item.expires_at:
            print(f"  Expires at:   {_fmt_ts(item.expires_at)}")
        print(f"  Expired:      {'Yes' if item.is_expired else 'No'}")
    public_meta = {k: v for k, v in item.metadata.items() if not k.startswith("_")}
    if public_meta:
        print(f"  Metadata:     {json.dumps(public_meta)}")


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


def cmd_prune_expired(ns: argparse.Namespace) -> None:
    """Remove expired memories."""
    memos = _get_memos(ns)
    expired = memos.prune_expired(dry_run=ns.dry_run)
    if not expired:
        print("No expired memories.")
        return
    label = " (dry-run)" if ns.dry_run else ""
    print(f"{'Would remove' if ns.dry_run else 'Removed'} {len(expired)} expired memories{label}:")
    for item in expired[:10]:
        print(f"  [{item.id[:8]}] {item.content[:80]}")
    if len(expired) > 10:
        print(f"  ... and {len(expired) - 10} more")


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


def cmd_watch(ns: argparse.Namespace) -> None:
    """Watch live memory events via the SSE stream."""
    import httpx

    server = getattr(ns, "server", None) or os.environ.get("MEMOS_URL", "http://127.0.0.1:8000")
    params: dict[str, str] = {}
    if ns.event_types:
        params["event_types"] = ns.event_types
    if ns.tags:
        params["tags"] = ns.tags
    if ns.namespace:
        params["namespace"] = ns.namespace

    url = f"{server.rstrip('/')}/api/v1/events/stream"

    def _emit(event_name: str, payload: str) -> None:
        if ns.json:
            print(payload)
            return
        try:
            data = json.loads(payload)
        except Exception:
            print(f"{event_name}: {payload}")
            return
        if isinstance(data, dict):
            content = data.get("data", {})
            tags = content.get("tags") or []
            tags_txt = f" [{', '.join(tags)}]" if tags else ""
            preview = content.get("content") or content.get("query") or content.get("message") or ""
            ns_txt = f" @{data.get('namespace')}" if data.get("namespace") else ""
            print(f"{event_name}{ns_txt}{tags_txt} {preview}".strip())
        else:
            print(f"{event_name}: {payload}")

    seen = 0
    with httpx.stream("GET", url, params=params, timeout=None) as resp:
        resp.raise_for_status()
        event_name = "message"
        data_lines: list[str] = []
        for line in resp.iter_lines():
            if line is None:
                continue
            line = line.decode() if isinstance(line, bytes) else line
            if line.startswith("event: "):
                event_name = line.split(": ", 1)[1]
            elif line.startswith("data: "):
                data_lines.append(line.split(": ", 1)[1])
            elif line == "":
                if data_lines:
                    _emit(event_name, "\n".join(data_lines))
                    seen += 1
                    data_lines = []
                    event_name = "message"
                    if ns.max_events and seen >= ns.max_events:
                        break


def cmd_subscribe(ns: argparse.Namespace) -> None:
    """Alias for watch, more explicit for subscription-style usage."""
    cmd_watch(ns)


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


def cmd_migrate(ns: argparse.Namespace) -> None:
    """Migrate memories to a different backend."""
    memos = _get_memos(ns)
    namespaces = ns.namespaces.split(",") if ns.namespaces else None
    try:
        dest_kwargs = _parse_kv_options(ns.dest_option)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    report = memos.migrate_to(
        ns.dest,
        namespaces=namespaces,
        merge=ns.merge,
        dry_run=ns.dry_run,
        batch_size=ns.batch_size,
        **dest_kwargs,
    )

    if getattr(ns, "json", False):
        print(json.dumps({
            "source_backend": report.source_backend,
            "dest_backend": report.dest_backend,
            "total_items": report.total_items,
            "migrated": report.migrated,
            "skipped": report.skipped,
            "errors": report.errors,
            "namespaces_migrated": report.namespaces_migrated,
            "duration_seconds": report.duration_seconds,
            "dry_run": report.dry_run,
        }, indent=2))
    else:
        print(report.summary())
        if report.errors:
            for err in report.errors[:10]:
                print(f"  ⚠ {err}", file=sys.stderr)

    if report.errors and not ns.dry_run:
        sys.exit(1)



def cmd_feedback(ns: argparse.Namespace) -> None:
    """Record relevance feedback for a recalled memory."""
    memos = _get_memos(ns)
    try:
        entry = memos.record_feedback(
            item_id=ns.item_id,
            feedback=ns.rating,
            query=getattr(ns, 'query', '') or '',
            score_at_recall=getattr(ns, 'score', 0.0),
            agent_id=getattr(ns, 'agent', '') or '',
        )
        if getattr(ns, 'json', False):
            print(json.dumps(entry.to_dict(), indent=2))
        else:
            print(f"✓ Feedback recorded: {ns.item_id[:12]}... → {ns.rating}")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_feedback_list(ns: argparse.Namespace) -> None:
    """List feedback entries."""
    memos = _get_memos(ns)
    entries = memos.get_feedback(item_id=getattr(ns, 'item_id', None), limit=ns.limit)
    if getattr(ns, 'json', False):
        print(json.dumps([e.to_dict() for e in entries], indent=2))
        return
    if not entries:
        print("No feedback entries.")
        return
    for e in entries:
        ts = datetime.fromtimestamp(e.created_at).strftime("%Y-%m-%d %H:%M")
        print(f"  {ts}  [{e.item_id[:8]}]  {e.feedback}  q={e.query[:40]}  score={e.score_at_recall:.3f}")
    print(f"\n{len(entries)} entries")


def cmd_feedback_stats(ns: argparse.Namespace) -> None:
    """Show feedback statistics."""
    memos = _get_memos(ns)
    stats = memos.feedback_stats()
    if getattr(ns, 'json', False):
        print(json.dumps(stats.to_dict(), indent=2))
        return
    print(f"  Total feedback:      {stats.total_feedback}")
    print(f"  Relevant:            {stats.relevant_count}")
    print(f"  Not relevant:        {stats.not_relevant_count}")
    print(f"  Items with feedback: {stats.items_with_feedback}")
    print(f"  Avg feedback score:  {stats.avg_feedback_score:.3f}")


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
    learn.add_argument("--stdin", action="store_true", help="Read content from stdin (pipe support)")
    learn.add_argument("--tags", "-t", help="Comma-separated tags")
    learn.add_argument("--importance", "-i", type=float, default=0.5)
    learn.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])
    learn.add_argument("--no-sanitize", action="store_true")
    learn.add_argument("--ttl", help="Time-to-live (e.g., 30m, 2h, 7d, 3600)")

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
    recall.add_argument("--tags", help="Comma-separated tags to filter by")
    recall.add_argument("--after", help="Only memories created after this date (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM)")
    recall.add_argument("--before", help="Only memories created before this date (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM)")
    recall.add_argument("--format", choices=["text", "json"], default="text", help="Output format (default: text)")
    recall.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # search
    search_p = sub.add_parser("search", help="Keyword-only search across memories (no embeddings)")
    search_p.add_argument("query", help="Search query (substring match on content + tags)")
    search_p.add_argument("--limit", "-n", type=int, default=20, help="Max results (default: 20)")
    search_p.add_argument("--format", choices=["text", "json"], default="text", help="Output format (default: text)")
    search_p.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # stats
    stats = sub.add_parser("stats", help="Show memory statistics")
    stats.add_argument("--json", action="store_true", help="JSON output")
    stats.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # forget
    forget = sub.add_parser("forget", help="Delete a memory")
    forget.add_argument("target", nargs="?", help="Memory ID or content")
    forget.add_argument("--tag", help="Delete all memories with this tag")

    get_cmd = sub.add_parser("get", help="Show details of a single memory by ID")
    get_cmd.add_argument("item_id", help="Memory item ID")
    get_cmd.add_argument("--json", action="store_true", help="JSON output")
    get_cmd.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])
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
    mig.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # serve
    serve = sub.add_parser("serve", help="Start REST API server")
    serve.add_argument("--host", default=os.environ.get("MEMOS_HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=int(os.environ.get("MEMOS_PORT", "8000")))
    serve.add_argument("--backend", default=os.environ.get("MEMOS_BACKEND", "memory"), choices=["memory", "chroma", "qdrant", "pinecone"])
    serve.add_argument("--chroma-host", default="localhost")
    serve.add_argument("--chroma-port", type=int, default=8000)

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

    # compact
    # prune-expired
    pe = sub.add_parser("prune-expired", help="Remove expired memories (past their TTL)")
    pe.add_argument("--dry-run", action="store_true", help="Preview only")
    pe.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])
    compact_p = sub.add_parser("compact", help="Run memory compaction (dedup + archive + merge)")
    compact_p.add_argument("--dry-run", action="store_true", help="Preview only, don't modify")
    compact_p.add_argument("--archive-age", type=float, default=90.0, help="Min age (days) for archival")
    compact_p.add_argument("--importance-floor", type=float, default=0.3, help="Never archive above this importance")
    compact_p.add_argument("--stale-threshold", type=float, default=0.25, help="Decay score threshold for stale")
    compact_p.add_argument("--max-per-run", type=int, default=200, help="Max modifications per run")
    compact_p.add_argument("--json", action="store_true", help="JSON output")
    compact_p.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # benchmark
    bench = sub.add_parser("benchmark", help="Run performance benchmarks")
    bench.add_argument("--size", type=int, default=1000, help="Number of memories to insert (default: 1000)")
    bench.add_argument("--recall-queries", type=int, default=100, help="Number of recall queries (default: 100)")
    bench.add_argument("--search-queries", type=int, default=100, help="Number of search queries (default: 100)")
    bench.add_argument("--warmup", type=int, default=50, help="Warmup operations (default: 50)")
    bench.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])
    bench.add_argument("--json", action="store_true", help="JSON output")

    # cache-stats
    cache_p = sub.add_parser("cache-stats", help="Show embedding cache statistics")
    cache_p.add_argument("--json", action="store_true", help="JSON output")
    cache_p.add_argument("--clear", action="store_true", help="Clear the cache")
    cache_p.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])



    # ── Tags commands ──────────────────────────────────────────
    tags_p = sub.add_parser("tags", help="List and manage memory tags")
    tags_sub = tags_p.add_subparsers(dest="tags_action")
    tags_list = tags_sub.add_parser("list", help="List all tags with counts")
    tags_list.add_argument("--sort", dest="tags_sort", default="count", choices=["count", "name"], help="Sort order")
    tags_list.add_argument("--limit", dest="tags_limit", type=int, default=0, help="Max tags (0=all)")
    tags_list.add_argument("--json", action="store_true", help="JSON output")
    tags_list.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    tags_rename = tags_sub.add_parser("rename", help="Rename a tag across all memories")
    tags_rename.add_argument("old_tag", help="Current tag name")
    tags_rename.add_argument("new_tag", help="New tag name")
    tags_rename.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    tags_delete = tags_sub.add_parser("delete", help="Delete a tag from all memories")
    tags_delete.add_argument("tag", help="Tag name to remove")
    tags_delete.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # ── Sharing commands ──────────────────────────────────────
    share_offer = sub.add_parser("share-offer", help="Offer to share memories with another agent")
    share_offer.add_argument("--target", required=True, help="Target agent ID")
    share_offer.add_argument("--scope", default="items", choices=["items", "tag", "namespace"], help="Share scope")
    share_offer.add_argument("--scope-key", default="", help="IDs (comma-sep), tag name, or namespace")
    share_offer.add_argument("--permission", default="read", choices=["read", "read_write", "admin"], help="Permission level")
    share_offer.add_argument("--expires", type=float, default=None, help="TTL in seconds from now")
    share_offer.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    share_accept = sub.add_parser("share-accept", help="Accept a pending share")
    share_accept.add_argument("share_id", help="Share request ID")
    share_accept.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    share_reject = sub.add_parser("share-reject", help="Reject a pending share")
    share_reject.add_argument("share_id", help="Share request ID")
    share_reject.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    share_revoke = sub.add_parser("share-revoke", help="Revoke a share you offered")
    share_revoke.add_argument("share_id", help="Share request ID")
    share_revoke.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    share_export = sub.add_parser("share-export", help="Export memories for an accepted share")
    share_export.add_argument("share_id", help="Share request ID")
    share_export.add_argument("--output", default=None, help="Output file path (default: stdout)")
    share_export.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    share_import = sub.add_parser("share-import", help="Import memories from an envelope file")
    share_import.add_argument("input_file", help="Envelope JSON file to import")
    share_import.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    share_list = sub.add_parser("share-list", help="List shares")
    share_list.add_argument("--agent", default=None, help="Filter by agent ID")
    share_list.add_argument("--status", default=None, choices=["pending", "accepted", "rejected", "revoked", "expired"], help="Filter by status")
    share_list.add_argument("--json", action="store_true", help="JSON output")
    share_list.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    share_stats = sub.add_parser("share-stats", help="Show sharing statistics")
    share_stats.add_argument("--json", action="store_true", help="JSON output")
    share_stats.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])


    # feedback
    fb = sub.add_parser("feedback", help="Record relevance feedback for a memory")
    fb.add_argument("item_id", help="Memory item ID")
    fb.add_argument("rating", choices=["relevant", "not-relevant"], help="Feedback rating")
    fb.add_argument("--query", "-q", help="The query that triggered the recall")
    fb.add_argument("--score", type=float, default=0.0, help="Recall score at feedback time")
    fb.add_argument("--agent", help="Agent ID providing feedback")
    fb.add_argument("--json", action="store_true", help="JSON output")
    fb.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # feedback-list
    fb_list = sub.add_parser("feedback-list", help="List feedback entries")
    fb_list.add_argument("--item-id", dest="item_id", help="Filter by memory item ID")
    fb_list.add_argument("--limit", type=int, default=50, help="Max entries to show")
    fb_list.add_argument("--json", action="store_true", help="JSON output")
    fb_list.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # feedback-stats
    fb_stats = sub.add_parser("feedback-stats", help="Show feedback statistics")
    fb_stats.add_argument("--json", action="store_true", help="JSON output")
    fb_stats.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone"])

    # mcp-serve
    mcp_serve_p = sub.add_parser("mcp-serve", help="Start MCP HTTP server (JSON-RPC 2.0)")
    mcp_serve_p.add_argument("--port", type=int, default=8200, help="Port to listen on (default: 8200)")
    mcp_serve_p.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    mcp_serve_p.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone", "json"])
    mcp_serve_p.add_argument("--persist-path", dest="persist_path", help="Path for json backend")

    # mcp-stdio
    mcp_stdio_p = sub.add_parser("mcp-stdio", help="Start MCP server over stdio (Claude Code / Cursor)")
    mcp_stdio_p.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone", "json"])
    mcp_stdio_p.add_argument("--persist-path", dest="persist_path", help="Path for json backend")

    # wiki-compile
    wiki_compile_p = sub.add_parser("wiki-compile", help="Compile memories into markdown pages per tag")
    wiki_compile_p.add_argument("--tags", nargs="*", help="Only compile these tags")
    wiki_compile_p.add_argument("--wiki-dir", dest="wiki_dir", help="Output directory (default: ~/.memos/wiki)")
    wiki_compile_p.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone", "json"])
    wiki_compile_p.add_argument("--persist-path", dest="persist_path", help="Path for json backend")

    # wiki-list
    wiki_list_p = sub.add_parser("wiki-list", help="List compiled wiki pages")
    wiki_list_p.add_argument("--wiki-dir", dest="wiki_dir", help="Wiki directory")
    wiki_list_p.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone", "json"])
    wiki_list_p.add_argument("--persist-path", dest="persist_path", help="Path for json backend")

    # wiki-read
    wiki_read_p = sub.add_parser("wiki-read", help="Read a compiled wiki page by tag")
    wiki_read_p.add_argument("tag", help="Tag name to read")
    wiki_read_p.add_argument("--wiki-dir", dest="wiki_dir", help="Wiki directory")
    wiki_read_p.add_argument("--backend", default="memory", choices=["memory", "chroma", "qdrant", "pinecone", "json"])
    wiki_read_p.add_argument("--persist-path", dest="persist_path", help="Path for json backend")

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


def cmd_compact(ns: argparse.Namespace) -> None:
    """Run memory compaction."""
    memos = _get_memos(ns)
    report = memos.compact(
        archive_age_days=ns.archive_age,
        archive_importance_floor=ns.importance_floor,
        stale_score_threshold=ns.stale_threshold,
        max_compact_per_run=ns.max_per_run,
        dry_run=ns.dry_run,
    )
    if getattr(ns, 'json', False):
        print(json.dumps(report, indent=2))
        return
    prefix = "[DRY RUN] " if ns.dry_run else ""
    print(f"{prefix}Compaction complete:")
    print(f"  Dedup groups:    {report['dedup_groups']} ({report['dedup_merged']} merged)")
    print(f"  Archived:        {report['archived']}")
    print(f"  Stale merged:    {report['stale_merged']} in {report['stale_groups']} groups")
    print(f"  Clusters:        {report['clusters_compacted']} compacted")
    print(f"  Net delta:       {report['net_delta']:+d} memories")
    print(f"  Duration:        {report['duration_seconds']:.3f}s")


def cmd_benchmark(ns: argparse.Namespace) -> None:
    """Run performance benchmarks."""
    from .benchmark import run_benchmark

    memos = _get_memos(ns)
    report = run_benchmark(
        memos=memos,
        memories=ns.size,
        recall_queries=ns.recall_queries,
        search_queries=ns.search_queries,
        warmup=ns.warmup,
    )
    if getattr(ns, 'json', False):
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.to_text())


def cmd_cache_stats(ns: argparse.Namespace) -> None:
    """Show embedding cache statistics."""
    memos = _get_memos(ns)
    if getattr(ns, 'clear', False):
        cleared = memos.cache_clear()
        if cleared < 0:
            print("Cache is not enabled")
        else:
            print(f"Cleared {cleared} entries")
        return
    stats = memos.cache_stats()
    if stats is None:
        print("Cache is not enabled. Use cache_enabled=True to enable.")
        return
    if getattr(ns, 'json', False):
        print(json.dumps(stats, indent=2))
        return
    print(f"  Cache entries:   {stats['size']}/{stats['max_size']}")
    print(f"  Hits:            {stats['hits']}")
    print(f"  Misses:          {stats['misses']}")
    print(f"  Hit rate:        {stats['hit_rate']:.1%}")
    print(f"  Evictions:       {stats['evictions']}")


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




def cmd_tags(ns: argparse.Namespace) -> None:
    """Tag management commands."""
    action = getattr(ns, 'tags_action', 'list') or 'list'
    memos = _get_memos(ns)

    if action == 'delete':
        count = memos.delete_tag(ns.tag)
        print(f"✓ Deleted tag '{ns.tag}' ({count} memory(s) updated)")
        return

    if action == 'rename':
        count = memos.rename_tag(ns.old_tag, ns.new_tag)
        print(f"✓ Renamed tag '{ns.old_tag}' → '{ns.new_tag}' ({count} memory(s) updated)")
        return

    # Default: list
    sort_by = getattr(ns, 'tags_sort', 'count') or 'count'
    limit = getattr(ns, 'tags_limit', 0) or 0
    tags = memos.list_tags(sort=sort_by, limit=limit)

    if getattr(ns, 'json', False):
        out = [{'tag': t, 'count': c} for t, c in tags]
        print(json.dumps(out, ensure_ascii=False))
    else:
        if not tags:
            print('No tags found.')
            return
        max_tag_len = max(len(t) for t, _ in tags)
        for tag, count in tags:
            print(f'  {tag:<{max_tag_len}}  {count}')

def cmd_share_offer(ns: argparse.Namespace) -> None:
    """Offer to share memories with another agent."""
    from .sharing.models import ShareScope, SharePermission
    memos = _get_memos(ns)
    import time as _time
    expires = ns.expires
    if expires is not None:
        expires = _time.time() + expires
    req = memos.share_with(
        ns.target,
        scope=ShareScope(ns.scope),
        scope_key=ns.scope_key,
        permission=SharePermission(ns.permission),
        expires_at=expires,
    )
    print(f"Share offer created: {req.id}")
    print(f"  Source:  {req.source_agent}")
    print(f"  Target:  {req.target_agent}")
    print(f"  Scope:   {req.scope.value} ({req.scope_key})")
    print(f"  Perm:    {req.permission.value}")
    print(f"  Status:  {req.status.value}")


def cmd_share_accept(ns: argparse.Namespace) -> None:
    """Accept a pending share."""
    memos = _get_memos(ns)
    req = memos.accept_share(ns.share_id)
    print(f"Share accepted: {req.id}")
    print(f"  {req.source_agent} → {req.target_agent} ({req.scope.value})")


def cmd_share_reject(ns: argparse.Namespace) -> None:
    """Reject a pending share."""
    memos = _get_memos(ns)
    req = memos.reject_share(ns.share_id)
    print(f"Share rejected: {req.id}")


def cmd_share_revoke(ns: argparse.Namespace) -> None:
    """Revoke a share."""
    memos = _get_memos(ns)
    req = memos.revoke_share(ns.share_id)
    print(f"Share revoked: {req.id}")


def cmd_share_export(ns: argparse.Namespace) -> None:
    """Export memories for a share."""
    memos = _get_memos(ns)
    envelope = memos.export_shared(ns.share_id)
    data = envelope.to_dict()
    output = json.dumps(data, indent=2, default=str)
    if ns.output:
        with open(ns.output, "w") as f:
            f.write(output)
        print(f"Exported {len(envelope.memories)} memories to {ns.output}")
    else:
        print(output)


def cmd_share_import(ns: argparse.Namespace) -> None:
    """Import memories from an envelope file."""
    from .sharing.models import MemoryEnvelope
    with open(ns.input_file, "r") as f:
        data = json.load(f)
    envelope = MemoryEnvelope.from_dict(data)
    memos = _get_memos(ns)
    learned = memos.import_shared(envelope)
    print(f"Imported {len(learned)} memories from {envelope.source_agent}")
    for item in learned[:10]:
        print(f"  {item.id}: {item.content[:60]}...")
    if len(learned) > 10:
        print(f"  ... and {len(learned) - 10} more")


def cmd_share_list(ns: argparse.Namespace) -> None:
    """List shares."""
    from .sharing.models import ShareStatus
    memos = _get_memos(ns)
    status = ShareStatus(ns.status) if ns.status else None
    shares = memos.list_shares(agent=ns.agent, status=status)
    if getattr(ns, 'json', False):
        print(json.dumps([s.to_dict() for s in shares], indent=2, default=str))
        return
    if not shares:
        print("No shares found")
        return
    print(f"Shares ({len(shares)}):")
    for s in shares:
        print(f"  {s.id}  {s.source_agent} → {s.target_agent}  [{s.status.value}]  scope={s.scope.value}({s.scope_key})")


def cmd_share_stats(ns: argparse.Namespace) -> None:
    """Show sharing statistics."""
    memos = _get_memos(ns)
    stats = memos.sharing_stats()
    if getattr(ns, 'json', False):
        print(json.dumps(stats, indent=2))
        return
    print(f"  Total shares:     {stats['total_shares']}")
    print(f"  Active shares:    {stats['active_shares']}")
    print(f"  Pending shares:   {stats['pending_shares']}")
    print(f"  Total agents:     {stats['total_agents']}")
    for status, count in stats.get('status_distribution', {}).items():
        print(f"    {status}: {count}")


def cmd_mcp_serve(ns: argparse.Namespace) -> None:
    """Start MCP HTTP server."""
    from .mcp_server import create_mcp_app
    try:
        import uvicorn
    except ImportError:
        print("Error: uvicorn is required. Install with: pip install memos[server]", file=sys.stderr)
        sys.exit(1)
    memos = _get_memos(ns)
    app = create_mcp_app(memos)
    host = getattr(ns, "host", "0.0.0.0")
    port = getattr(ns, "port", 8200)
    print(f"MemOS MCP server listening on http://{host}:{port}/mcp")
    uvicorn.run(app, host=host, port=port, log_level="info")


def cmd_mcp_stdio(ns: argparse.Namespace) -> None:
    """Start MCP server over stdio."""
    from .mcp_server import run_stdio
    memos = _get_memos(ns)
    run_stdio(memos)


def cmd_wiki_compile(ns: argparse.Namespace) -> None:
    """Compile memories into per-tag wiki pages."""
    from .wiki import WikiEngine
    memos = _get_memos(ns)
    wiki = WikiEngine(memos, wiki_dir=getattr(ns, "wiki_dir", None))
    tags = getattr(ns, "tags", None) or None
    pages = wiki.compile(tags=tags)
    if not pages:
        print("No memories found to compile.")
        return
    print(f"Compiled {len(pages)} wiki page(s):")
    for p in sorted(pages, key=lambda x: x.tag):
        print(f"  [{p.memory_count:3d} memories] {p.tag:30s} → {p.path}")


def cmd_wiki_list(ns: argparse.Namespace) -> None:
    """List compiled wiki pages."""
    from .wiki import WikiEngine
    memos = _get_memos(ns)
    wiki = WikiEngine(memos, wiki_dir=getattr(ns, "wiki_dir", None))
    pages = wiki.list_pages()
    if not pages:
        print("No wiki pages found. Run: memos wiki-compile")
        return
    print(f"{'TAG':<30} {'MEMORIES':>8} {'SIZE':>8}  COMPILED")
    print("-" * 65)
    for p in pages:
        size_str = f"{p.size_bytes // 1024}K" if p.size_bytes >= 1024 else f"{p.size_bytes}B"
        print(f"{p.tag:<30} {p.memory_count:>8} {size_str:>8}  {p.age_str()}")


def cmd_wiki_read(ns: argparse.Namespace) -> None:
    """Read a compiled wiki page by tag."""
    from .wiki import WikiEngine
    memos = _get_memos(ns)
    wiki = WikiEngine(memos, wiki_dir=getattr(ns, "wiki_dir", None))
    content = wiki.read(ns.tag)
    if content is None:
        print(f"No wiki page found for tag '{ns.tag}'. Run: memos wiki-compile", file=sys.stderr)
        sys.exit(1)
    print(content)


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
        "search": cmd_search,
        "stats": cmd_stats,
        "forget": cmd_forget,
        "get": cmd_get,
        "prune-expired": cmd_prune_expired,
        "prune": cmd_prune,
        "serve": cmd_serve,
        "watch": cmd_watch,
        "subscribe": cmd_subscribe,
        "consolidate": cmd_consolidate,
        "ingest": cmd_ingest,
        "export": cmd_export,
        "import": cmd_import,
        "migrate": cmd_migrate,
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
        "compact": cmd_compact,
        "cache-stats": cmd_cache_stats,
        "benchmark": cmd_benchmark,
        "tags": cmd_tags,
        "share-offer": cmd_share_offer,
        "share-accept": cmd_share_accept,
        "share-reject": cmd_share_reject,
        "share-revoke": cmd_share_revoke,
        "share-export": cmd_share_export,
        "share-import": cmd_share_import,
        "share-list": cmd_share_list,
        "share-stats": cmd_share_stats,
        "feedback": cmd_feedback,
        "feedback-list": cmd_feedback_list,
        "feedback-stats": cmd_feedback_stats,
        "mcp-serve": cmd_mcp_serve,
        "mcp-stdio": cmd_mcp_stdio,
        "wiki-compile": cmd_wiki_compile,
        "wiki-list": cmd_wiki_list,
        "wiki-read": cmd_wiki_read,
    }
    commands[ns.command](ns)


if __name__ == "__main__":
    main()
