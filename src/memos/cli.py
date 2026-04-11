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
        print(f"Already initialized: {cfg}")
        return
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

    def _split_csv(value: str | None) -> list[str]:
        if not value:
            return []
        return [t.strip() for t in value.split(",") if t.strip()]

    memos = _get_memos(ns)
    filter_tags = _split_csv(getattr(ns, "tags", None))
    require_tags = _split_csv(getattr(ns, "require_tags", None))
    exclude_tags = _split_csv(getattr(ns, "exclude_tags", None))
    if (getattr(ns, "tag_mode", "any") or "any").lower() == "all" and filter_tags:
        require_tags.extend(filter_tags)
        filter_tags = []

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
    fmt = getattr(ns, "format", "text") or "text"
    if getattr(ns, "enriched", False):
        bridge = _get_kg_bridge(ns, memos=memos)
        try:
            payload = bridge.recall_enriched(
                ns.query,
                top=ns.top,
                filter_tags=filter_tags or require_tags,
                min_score=ns.min_score,
                filter_after=filter_after,
                filter_before=filter_before,
            )
        finally:
            bridge.close()
        if fmt == "json":
            print(json.dumps(payload, indent=2))
            return
        memories = payload["memories"]
        facts = payload["facts"]
        if not memories and not facts:
            print("No memories or KG facts found.")
            return
        if memories:
            print("Memories:")
            for r in memories:
                tags_str = f" [{', '.join(r['tags'])}]" if r['tags'] else ""
                print(f"  {r['score']:.3f} {r['content'][:120]}{tags_str}")
            print(f"\n{len(memories)} memory result(s)")
        if facts:
            print("\nKG facts:")
            for f in facts:
                print(f"  [{f['id']}] {f['subject']} -{f['predicate']}-> {f['object']}")
            print(f"\n{len(facts)} fact(s)")
        return
    retrieval_mode = getattr(ns, "retrieval_mode", "semantic") or "semantic"
    results = memos.recall(
        ns.query,
        top=ns.top,
        min_score=ns.min_score,
        filter_tags=filter_tags,
        filter_after=filter_after,
        filter_before=filter_before,
        retrieval_mode=retrieval_mode,
        tag_filter={"require": require_tags, "exclude": exclude_tags} if (require_tags or exclude_tags) else None,
        min_importance=getattr(ns, "min_importance", None),
        max_importance=getattr(ns, "max_importance", None),
    )
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


def cmd_analytics(ns: argparse.Namespace) -> None:
    """Show recall analytics."""
    memos = _get_memos(ns)
    action = getattr(ns, "analytics_action", None)
    if not action:
        print("Error: analytics subcommand required", file=sys.stderr)
        sys.exit(1)

    if action == "top":
        results = memos.analytics.top_recalled(n=ns.n)
        if ns.json:
            print(json.dumps({"results": results}, indent=2))
            return
        for row in results:
            print(f"  {row['count']:>3} {row['memory_id'][:8]}")
        print(f"\n{len(results)} result(s)")
        return

    if action == "patterns":
        results = memos.analytics.query_patterns(n=ns.n)
        if ns.json:
            print(json.dumps({"results": results}, indent=2))
            return
        for row in results:
            print(f"  {row['count']:>3} {row['query']}")
        print(f"\n{len(results)} result(s)")
        return

    if action == "latency":
        stats = memos.analytics.latency_stats()
        if ns.json:
            print(json.dumps(stats, indent=2))
            return
        print(f"  Count:   {stats['count']}")
        print(f"  Avg:     {stats['avg']:.2f} ms")
        print(f"  p50:     {stats['p50']:.2f} ms")
        print(f"  p95:     {stats['p95']:.2f} ms")
        print(f"  p99:     {stats['p99']:.2f} ms")
        return

    if action == "success-rate":
        stats = memos.analytics.recall_success_rate_stats(days=ns.days)
        if ns.json:
            print(json.dumps(stats, indent=2))
            return
        print(f"  Success rate: {stats['success_rate']:.1f}%")
        print(f"  Total recalls: {stats['total_recalls']}")
        print(f"  Successful:    {stats['successful_recalls']}")
        print(f"  Failed:        {stats['failed_recalls']}")
        return

    if action == "daily":
        results = memos.analytics.daily_activity(days=ns.days)
        if ns.json:
            print(json.dumps({"results": results}, indent=2))
            return
        for row in results:
            print(f"  {row['date']}  {row['count']}")
        print(f"\n{len(results)} day(s)")
        return

    if action == "zero":
        results = memos.analytics.zero_result_queries(n=ns.n)
        if ns.json:
            print(json.dumps({"results": results}, indent=2))
            return
        for row in results:
            print(f"  {row['count']:>3} {row['query']}")
        print(f"\n{len(results)} result(s)")
        return

    if action == "summary":
        summary = memos.analytics.summary(days=ns.days)
        if ns.json:
            print(json.dumps(summary, indent=2))
            return
        success = summary["success"]
        print(f"  Success rate: {success['success_rate']:.1f}% ({success['successful_recalls']}/{success['total_recalls']})")
        latency = summary["latency"]
        print(f"  Latency p95:  {latency['p95']:.2f} ms")
        print(f"  Top queries:  {len(summary['top_queries'])}")
        print(f"  Zero-result:   {len(summary['zero_result_queries'])}")
        print(f"  Daily points:  {len(summary['daily_activity'])}")
        return

    print(f"Error: unknown analytics action: {action}", file=sys.stderr)
    sys.exit(1)


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


def cmd_mcp_serve(ns: argparse.Namespace) -> None:
    """Start MCP HTTP server (JSON-RPC 2.0)."""
    try:
        import uvicorn
    except ImportError:
        print("Error: install memos[server] first", file=sys.stderr)
        sys.exit(1)
    from .mcp_server import create_mcp_app
    from .core import MemOS
    memos = MemOS(backend=getattr(ns, "backend", "memory"))
    app = create_mcp_app(memos)
    host = getattr(ns, "host", "127.0.0.1")
    port = getattr(ns, "port", 8200)
    print(f"MemOS MCP server running at http://{host}:{port}")
    print("Tools: memory_search, memory_save, memory_forget, memory_stats")
    uvicorn.run(app, host=host, port=port, log_level="warning")


def cmd_mcp_stdio(ns: argparse.Namespace) -> None:
    """Start MCP server over stdio (for Claude Code / Cursor)."""
    from .mcp_server import run_stdio
    from .core import MemOS
    memos = MemOS()
    run_stdio(memos)


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
    """Export memories to JSON, Parquet, or portable Markdown."""
    mem = _get_memos(ns)
    fmt = getattr(ns, "format", "json") or "json"

    if fmt == "markdown":
        out = ns.output
        if not out:
            print("Error: --output is required for markdown format", file=sys.stderr)
            sys.exit(1)
        from .export_markdown import MarkdownExporter
        from .knowledge_graph import KnowledgeGraph

        kg = KnowledgeGraph(db_path=getattr(ns, "kg_db", None))
        try:
            exporter = MarkdownExporter(mem, kg=kg, wiki_dir=getattr(ns, "wiki_dir", None))
            result = exporter.export(out, update=getattr(ns, "update", False))
        finally:
            kg.close()
        print(
            f"Exported markdown knowledge to {out} "
            f"(memories={result.total_memories}, entities={result.total_entities}, facts={result.total_facts})"
        )
        return

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


def cmd_ingest_url(ns: argparse.Namespace) -> None:
    """Fetch a URL and ingest its contents into memory."""
    memos = _get_memos(ns)
    tags = ns.tags.split(",") if ns.tags else None
    result = memos.ingest_url(
        ns.url,
        tags=tags,
        importance=ns.importance,
        max_chunk=ns.max_chunk,
        dry_run=ns.dry_run,
    )
    source_type = result.chunks[0].get("metadata", {}).get("source_type", "unknown") if result.chunks else "unknown"
    label = "DRY-RUN " if ns.dry_run else ""
    print(f"{label}{ns.url}: {result.total_chunks} chunks, {result.skipped} skipped ({source_type})")
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


def _get_kg(ns: argparse.Namespace):
    """Return a KnowledgeGraph instance from CLI namespace."""
    from .knowledge_graph import KnowledgeGraph
    db_path = getattr(ns, "kg_db", None)
    return KnowledgeGraph(db_path=db_path)


def _get_kg_bridge(ns: argparse.Namespace, memos: Any | None = None):
    """Return a KGBridge instance from CLI namespace."""
    from .kg_bridge import KGBridge
    from .knowledge_graph import KnowledgeGraph
    if memos is None:
        memos = _get_memos(ns)
    kg = KnowledgeGraph(db_path=getattr(ns, "kg_db", None))
    return KGBridge(memos, kg)


def cmd_kg_add(ns: argparse.Namespace) -> None:
    """Add a fact to the knowledge graph."""
    kg = _get_kg(ns)
    try:
        fact_id = kg.add_fact(
            subject=ns.subject,
            predicate=ns.predicate,
            object=ns.object,
            valid_from=ns.valid_from,
            valid_to=ns.valid_to,
            confidence=ns.confidence,
            confidence_label=getattr(ns, 'confidence_label', 'EXTRACTED'),
            source=ns.source,
        )
        _label = getattr(ns, 'confidence_label', 'EXTRACTED')
        print(f"✓ Fact added [{fact_id}]: {ns.subject} -{ns.predicate}-> {ns.object} [{_label}]")
    finally:
        kg.close()


def cmd_kg_query(ns: argparse.Namespace) -> None:
    """Query facts about an entity."""
    kg = _get_kg(ns)
    try:
        facts = kg.query(ns.entity, time=ns.at_time, direction=ns.direction)
        if not facts:
            print(f"No facts found for entity: {ns.entity}")
            return
        for f in facts:
            inv = " [INVALIDATED]" if f["invalidated_at"] else ""
            bounds = ""
            if f["valid_from"] or f["valid_to"]:
                vf = datetime.fromtimestamp(f["valid_from"]).strftime("%Y-%m-%d") if f["valid_from"] else "?"
                vt = datetime.fromtimestamp(f["valid_to"]).strftime("%Y-%m-%d") if f["valid_to"] else "?"
                bounds = f" [{vf} → {vt}]"
            label = f.get('confidence_label', 'EXTRACTED')
            print(f"  [{f['id']}] {f['subject']} -{f['predicate']}-> {f['object']}{bounds} (conf={f['confidence']:.2f}, label={label}){inv}")
        print(f"\n{len(facts)} fact(s)")
    finally:
        kg.close()


def cmd_kg_timeline(ns: argparse.Namespace) -> None:
    """Show chronological timeline of facts about an entity."""
    kg = _get_kg(ns)
    try:
        facts = kg.timeline(ns.entity)
        if not facts:
            print(f"No facts found for entity: {ns.entity}")
            return
        print(f"Timeline for: {ns.entity}")
        print("-" * 60)
        for f in facts:
            ts = datetime.fromtimestamp(f["created_at"]).strftime("%Y-%m-%d %H:%M")
            inv = " [INVALIDATED]" if f["invalidated_at"] else ""
            label = f.get('confidence_label', 'EXTRACTED')
            print(f"  {ts}  [{f['id']}] {f['subject']} -{f['predicate']}-> {f['object']} [{label}]{inv}")
        print(f"\n{len(facts)} event(s)")
    finally:
        kg.close()


def cmd_kg_invalidate(ns: argparse.Namespace) -> None:
    """Invalidate a fact by ID."""
    kg = _get_kg(ns)
    try:
        ok = kg.invalidate(ns.fact_id)
        if ok:
            print(f"✓ Fact [{ns.fact_id}] invalidated")
        else:
            print(f"Fact [{ns.fact_id}] not found or already invalidated", file=sys.stderr)
            sys.exit(1)
    finally:
        kg.close()


def cmd_kg_stats(ns: argparse.Namespace) -> None:
    """Show knowledge graph statistics."""
    kg = _get_kg(ns)
    try:
        s = kg.stats()
        print(f"  Total facts:        {s['total_facts']}")
        print(f"  Active facts:       {s['active_facts']}")
        print(f"  Invalidated facts:  {s['invalidated_facts']}")
        print(f"  Total entities:     {s['total_entities']}")
        ls = kg.label_stats()
        parts = ", ".join(f"{k}={v}" for k, v in ls.items())
        print(f"  By label:           {parts}")
    finally:
        kg.close()


def cmd_kg_infer(ns: argparse.Namespace) -> None:
    """Infer transitive facts for a predicate."""
    kg = _get_kg(ns)
    try:
        new_ids = kg.infer_transitive(
            predicate=ns.predicate,
            inferred_predicate=ns.inferred_predicate,
            max_depth=ns.max_depth,
        )
        if new_ids:
            for fid in new_ids:
                print(f"  ✓ Inferred fact [{fid}]")
            print(f"\n{len(new_ids)} inferred fact(s)")
        else:
            print("No new facts inferred.")
    finally:
        kg.close()


def cmd_kg_labels(ns: argparse.Namespace) -> None:
    """Show facts filtered by confidence label."""
    kg = _get_kg(ns)
    try:
        facts = kg.query_by_label(ns.label, active_only=not ns.show_all)
        if not facts:
            print(f"No facts with label: {ns.label}")
            return
        for f in facts:
            inv = " [INVALIDATED]" if f.get("invalidated_at") else ""
            print(f"  [{f['id']}] {f['subject']} -{f['predicate']}-> {f['object']} (conf={f['confidence']:.2f}){inv}")
        print(f"\n{len(facts)} fact(s) with label {ns.label}")
    finally:
        kg.close()


def cmd_kg_path(ns: argparse.Namespace) -> None:
    """Find paths between two entities in the knowledge graph."""
    kg = _get_kg(ns)
    try:
        paths = kg.find_paths(
            ns.entity_a, ns.entity_b,
            max_hops=getattr(ns, "max_hops", 3),
            max_paths=getattr(ns, "max_paths", 10),
        )
        if not paths:
            print(f"No path found between {ns.entity_a!r} and {ns.entity_b!r}")
            return
        print(f"Found {len(paths)} path(s):")
        for i, path in enumerate(paths, 1):
            hops = len(path)
            print(f"\n  Path {i} ({hops} hop{'s' if hops != 1 else ''}):")
            for triple in path:
                vf = f" (from {_ts(triple['valid_from'])})" if triple.get('valid_from') else ""
                print(f"    {triple['subject']} -[{triple['predicate']}]-> {triple['object']}{vf}")
    finally:
        kg.close()


def cmd_kg_neighbors(ns: argparse.Namespace) -> None:
    """Show entity neighborhood in the knowledge graph."""
    kg = _get_kg(ns)
    try:
        result = kg.neighbors(
            ns.entity,
            depth=getattr(ns, "depth", 1),
            direction=getattr(ns, "direction", "both"),
        )
        print(f"Neighborhood of {ns.entity!r} (depth={result['depth']}):")
        print(f"  Nodes discovered: {len(result['nodes'])}")
        print(f"  Edges discovered: {len(result['edges'])}")
        if result["layers"]:
            for hop, entities in result["layers"].items():
                if entities:
                    print(f"  Hop {hop}: {', '.join(entities)}")
        if result["edges"]:
            print(f"\n  Edges:")
            for triple in result["edges"]:
                print(f"    {triple['subject']} -[{triple['predicate']}]-> {triple['object']}")
    finally:
        kg.close()


def _ts(val) -> str:
    """Format a timestamp for display."""
    if val is None:
        return ""
    from datetime import datetime, timezone
    try:
        return datetime.fromtimestamp(val, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return str(val)


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
    exp.add_argument("--format", "-f", choices=["json", "parquet", "markdown"], default="json", help="Export format (default: json)")
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



def cmd_benchmark_quality(ns: argparse.Namespace) -> None:
    """Run recall quality benchmarks."""
    from .benchmark_quality import run_quality_benchmark

    report = run_quality_benchmark(
        memories_per_category=10,
        extra_noise=ns.noise,
        top_k=ns.top,
        seed=ns.seed,
        run_decay=not ns.no_decay,
        run_scalability=ns.scalability,
        scalability_sizes=[50, 200, 500, 1000] if ns.scalability else None,
        backend=ns.backend,
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



def cmd_sync_check(ns: argparse.Namespace) -> None:
    """Check for conflicts between local store and a remote export file."""
    from .conflict import ConflictDetector
    from .sharing.models import MemoryEnvelope

    memos = _get_memos(ns)
    path = ns.remote_file
    with open(path) as f:
        data = json.load(f)

    envelope = MemoryEnvelope.from_dict(data)
    if not envelope.validate():
        print(f"✗ Envelope checksum validation failed — data may be corrupted")
        return

    detector = ConflictDetector()
    report = detector.detect(memos, envelope)

    if getattr(ns, 'json', False):
        print(json.dumps(report.to_dict(), indent=2))
        return

    print(f"Sync check: {report.total_remote} remote memories")
    print(f"  New (no conflict):  {report.new_memories}")
    print(f"  Unchanged:          {report.unchanged}")
    print(f"  Conflicts:          {len(report.conflicts)}")
    if report.errors:
        print(f"  Errors:             {len(report.errors)}")
        for e in report.errors[:5]:
            print(f"    - {e}")

    if report.conflicts:
        print()
        for c in report.conflicts:
            types = ", ".join(t.value for t in c.conflict_types)
            print(f"  ⚠ {c.memory_id[:12]}… [{types}]")
            if c.local_content != c.remote_content:
                print(f"    local:  {c.local_content[:80]}")
                print(f"    remote: {c.remote_content[:80]}")
            if c.local_tags != c.remote_tags:
                print(f"    tags: {c.local_tags} → {c.remote_tags}")
            if abs(c.local_importance - c.remote_importance) > 0.01:
                print(f"    importance: {c.local_importance:.2f} → {c.remote_importance:.2f}")


def cmd_sync_apply(ns: argparse.Namespace) -> None:
    """Apply remote memories with conflict resolution."""
    from .conflict import ConflictDetector, ResolutionStrategy
    from .sharing.models import MemoryEnvelope

    memos = _get_memos(ns)
    path = ns.remote_file
    strategy = ResolutionStrategy(ns.strategy)

    with open(path) as f:
        data = json.load(f)

    envelope = MemoryEnvelope.from_dict(data)
    if not envelope.validate():
        print(f"✗ Envelope checksum validation failed — aborting")
        return

    detector = ConflictDetector()
    report = detector.detect(memos, envelope)

    if getattr(ns, 'dry_run', False):
        detector.resolve(report.conflicts, strategy)
        if getattr(ns, 'json', False):
            out = report.to_dict()
            out["dry_run"] = True
            print(json.dumps(out, indent=2))
            return
        print(f"Dry run — strategy: {strategy.value}")
        print(f"  Conflicts to resolve: {len(report.conflicts)}")
        print(f"  New memories to add:  {report.new_memories}")
        for c in report.conflicts:
            types = ", ".join(t.value for t in c.conflict_types)
            res = c.resolution.value if c.resolution else "none"
            print(f"  {c.memory_id[:12]}… [{types}] → {res}")
        return

    report = detector.apply(memos, report, strategy)

    if getattr(ns, 'json', False):
        print(json.dumps(report.to_dict(), indent=2))
        return

    print(f"✓ Sync applied — strategy: {strategy.value}")
    print(f"  Remote memories:  {report.total_remote}")
    print(f"  Applied:          {report.applied}")
    print(f"  Skipped:          {report.skipped}")
    print(f"  Conflicts:        {len(report.conflicts)}")
    if report.errors:
        print(f"  Errors:           {len(report.errors)}")
        for e in report.errors[:5]:
            print(f"    - {e}")


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



def cmd_mine(ns: argparse.Namespace) -> None:
    """Mine files or directories into memories (smart chunker + multi-format)."""
    from .ingest.miner import Miner
    memos = _get_memos(ns)
    fmt = getattr(ns, "format", "auto")
    dry_run = getattr(ns, "dry_run", False)
    tags = getattr(ns, "tags") or []
    chunk_size = getattr(ns, "chunk_size", 800)
    chunk_overlap = getattr(ns, "chunk_overlap", 100)
    verbose = getattr(ns, "verbose", False)
    use_update = getattr(ns, "update", False)
    use_diff = getattr(ns, "diff", False)
    no_cache = getattr(ns, "no_cache", False)
    cache_db = getattr(ns, "cache_db", str(Path.home() / ".memos" / "mine-cache.db"))

    cache = None
    if not no_cache and not dry_run:
        from .ingest.cache import MinerCache
        cache = MinerCache(cache_db)

    miner = Miner(
        memos,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        dry_run=dry_run,
        extra_tags=tags,
        cache=cache,
        update=use_update,
    )

    from pathlib import Path as _Path
    total = __import__("memos.ingest.miner", fromlist=["MineResult"]).MineResult()

    for path_str in ns.paths:
        path = _Path(path_str).expanduser()
        if verbose:
            print(f"Mining: {path}")

        if fmt == "claude":
            r = miner.mine_claude_export(path, tags=tags)
        elif fmt == "chatgpt":
            r = miner.mine_chatgpt_export(path, tags=tags)
        elif fmt == "slack":
            r = miner.mine_slack_export(path, tags=tags)
        elif fmt == "discord":
            r = miner.mine_discord_export(path, tags=tags)
        elif fmt == "telegram":
            r = miner.mine_telegram_export(path, tags=tags)
        elif fmt == "openclaw":
            r = miner.mine_openclaw(path, tags=tags)
        elif path.is_dir():
            r = miner.mine_directory(path, tags=tags, diff=use_diff)
        else:
            r = miner.mine_file(path, tags=tags, diff=use_diff)

        if r.errors and verbose:
            for e in r.errors:
                print(f"  [error] {e}", file=sys.stderr)

        total.merge(r)

    if cache:
        cache.close()

    status = "would import" if dry_run else "imported"
    cached_msg = f", {total.skipped_cached} cached" if total.skipped_cached else ""
    print(f"\n✓ {total.imported} chunks {status}, {total.skipped_duplicates} duplicates skipped{cached_msg}, {len(total.errors)} errors")
    if dry_run and total.chunks:
        print("\nSample chunks:")
        for c in total.chunks[:5]:
            print(f"  [{', '.join(c['tags'])}] {c['content']}")


def cmd_mine_conversation(ns: argparse.Namespace) -> None:
    """Mine a speaker-attributed transcript into MemOS."""
    from .ingest.conversation import ConversationMiner

    memos = _get_memos(ns)
    extra_tags = [t.strip() for t in (ns.tags or "").split(",") if t.strip()]

    miner = ConversationMiner(
        memos,
        dry_run=ns.dry_run,
    )
    result = miner.mine_conversation(
        ns.path,
        namespace_prefix=ns.namespace_prefix,
        per_speaker=ns.per_speaker,
        tags=extra_tags or None,
        importance=ns.importance,
    )

    if result.errors:
        for err in result.errors:
            print(f"Error: {err}", file=__import__("sys").stderr)

    mode = "per-speaker" if ns.per_speaker else "combined"
    print(
        f"Speakers: {', '.join(result.speakers) if result.speakers else 'none'}\n"
        f"Mode: {mode}\n"
        f"Imported: {result.imported}  |  "
        f"Duplicates: {result.skipped_duplicates}  |  "
        f"Skipped (short): {result.skipped_empty}"
    )
    if ns.dry_run:
        print("[dry-run: nothing stored]")


def cmd_mine_status(ns: argparse.Namespace) -> None:
    """Show the incremental mine cache."""
    from .ingest.cache import MinerCache
    import datetime as _dt

    cache_db = getattr(ns, "cache_db", str(Path.home() / ".memos" / "mine-cache.db"))
    with MinerCache(cache_db) as cache:
        paths = getattr(ns, "paths", [])
        if paths:
            entries = [e for p in paths for e in [cache.get(str(Path(p).expanduser().resolve()))] if e]
        else:
            entries = cache.list_all()
            stats = cache.stats()
            print(f"Cache: {cache_db}")
            print(f"Files: {stats['cached_files']}  |  Memories: {stats['total_memories']}\n")

        if not entries:
            print("No cached files.")
            return

        for e in entries:
            mined = _dt.datetime.fromtimestamp(e["mined_at"]).strftime("%Y-%m-%d %H:%M")
            mem_count = len(e["memory_ids"])
            chunk_count = len(e["chunk_hashes"])
            print(f"  {e['path']}")
            print(f"    sha256={e['sha256'][:12]}…  mined={mined}  memories={mem_count}  chunks={chunk_count}")


def _get_palace(ns: argparse.Namespace):
    """Return a PalaceIndex using the --db flag or the default path."""
    from .palace import PalaceIndex
    db = getattr(ns, "palace_db", None) or None
    if db:
        return PalaceIndex(db_path=db)
    return PalaceIndex()


def cmd_palace_init(ns: argparse.Namespace) -> None:
    """Initialise the Palace schema (creates tables if absent)."""
    palace = _get_palace(ns)
    palace.close()
    print("Palace schema initialised.")


def cmd_palace_wing_create(ns: argparse.Namespace) -> None:
    """Create a Wing in the Palace."""
    palace = _get_palace(ns)
    try:
        wing_id = palace.create_wing(ns.name, description=ns.description)
        print(f"Wing created: {ns.name} [{wing_id}]")
    finally:
        palace.close()


def cmd_palace_wing_list(ns: argparse.Namespace) -> None:
    """List all Wings."""
    palace = _get_palace(ns)
    try:
        wings = palace.list_wings()
        if not wings:
            print("No wings found.")
            return
        print(f"{'NAME':<24} {'ROOMS':>6} {'MEMORIES':>9}  DESCRIPTION")
        print("-" * 65)
        for w in wings:
            print(f"{w['name']:<24} {w['room_count']:>6} {w['memory_count']:>9}  {w['description']}")
    finally:
        palace.close()


def cmd_palace_room_create(ns: argparse.Namespace) -> None:
    """Create a Room inside a Wing."""
    palace = _get_palace(ns)
    try:
        room_id = palace.create_room(ns.wing, ns.room, description=ns.description)
        print(f"Room created: {ns.wing}/{ns.room} [{room_id}]")
    except KeyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        palace.close()


def cmd_palace_room_list(ns: argparse.Namespace) -> None:
    """List Rooms, optionally filtered by wing."""
    palace = _get_palace(ns)
    try:
        rooms = palace.list_rooms(wing_name=ns.wing)
        if not rooms:
            print("No rooms found.")
            return
        print(f"{'WING':<20} {'ROOM':<20} {'MEMORIES':>9}  DESCRIPTION")
        print("-" * 65)
        for r in rooms:
            print(f"{r['wing_name']:<20} {r['name']:<20} {r['memory_count']:>9}  {r['description']}")
    except KeyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        palace.close()


def cmd_palace_assign(ns: argparse.Namespace) -> None:
    """Assign a memory to a Wing (and optionally a Room)."""
    palace = _get_palace(ns)
    try:
        palace.assign(ns.memory_id, ns.wing, room_name=ns.room)
        room_str = f"/{ns.room}" if ns.room else ""
        print(f"Assigned [{ns.memory_id}] -> {ns.wing}{room_str}")
    except KeyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        palace.close()


def cmd_palace_recall(ns: argparse.Namespace) -> None:
    """Scoped recall using Palace wing/room filter."""
    from .palace import PalaceRecall
    palace = _get_palace(ns)
    memos = _get_memos(ns)
    try:
        pr = PalaceRecall(palace)
        results = pr.palace_recall(
            memos, ns.query,
            wing_name=ns.wing,
            room_name=ns.room,
            top=ns.top,
        )
        if not results:
            print("No memories found.")
            return
        for r in results:
            tags_str = f" [{', '.join(r.item.tags)}]" if r.item.tags else ""
            print(f"  {r.score:.3f} {r.item.content[:120]}{tags_str}")
        print(f"\n{len(results)} result(s)")
    finally:
        palace.close()


def cmd_palace_stats(ns: argparse.Namespace) -> None:
    """Show Palace statistics."""
    palace = _get_palace(ns)
    try:
        s = palace.stats()
        print(f"  Total wings:       {s['total_wings']}")
        print(f"  Total rooms:       {s['total_rooms']}")
        print(f"  Assigned memories: {s['assigned_memories']}")
    finally:
        palace.close()


def cmd_wake_up(ns: argparse.Namespace) -> None:
    """Print L0 (identity) + L1 (top memories) context for session priming."""
    from .context import ContextStack
    memos = _get_memos(ns)
    cs = ContextStack(memos)
    output = cs.wake_up(
        max_chars=ns.max_chars,
        l1_top=ns.l1_top,
        include_stats=not ns.no_stats,
    )
    print(output)


def cmd_identity(ns: argparse.Namespace) -> None:
    """Manage agent identity (L0 context)."""
    from .context import ContextStack
    action = getattr(ns, "identity_action", None) or "show"
    # identity uses its own path, not a memos backend
    # We instantiate ContextStack with a dummy memos only if needed
    # For show/set we only need the file path

    class _Stub:
        """Minimal stub so ContextStack can be constructed without a full backend."""
        namespace = ""
        def _store(self):  # pragma: no cover
            pass

    cs = ContextStack(_Stub())  # type: ignore[arg-type]

    if action == "set":
        text = ns.text
        if text is None or text == "-":
            text = sys.stdin.read()
        cs.set_identity(text)
        print(f"Identity written to {cs._identity_path}")
    else:
        content = cs.get_identity()
        if content:
            print(content)
        else:
            print(f"(no identity file at {cs._identity_path})")


def cmd_context_for(ns: argparse.Namespace) -> None:
    """Print context optimised for a specific query (L0 + L3)."""
    from .context import ContextStack
    memos = _get_memos(ns)
    cs = ContextStack(memos)
    output = cs.context_for(
        query=ns.query,
        max_chars=ns.max_chars,
        top=ns.top,
    )
    print(output)


def cmd_classify(ns: argparse.Namespace) -> None:
    """Classify text into memory type tags."""
    from .tagger import AutoTagger
    tagger = AutoTagger()
    text = ns.text

    if ns.detailed:
        result = tagger.tag_detailed(text)
        if not result:
            print("No type tags detected.")
            return
        for tag, matches in result.items():
            print(f"  {tag}: {', '.join(matches)}")
    else:
        tags = tagger.tag(text)
        if not tags:
            print("No type tags detected.")
        else:
            print(f"Tags: {', '.join(tags)}")


def cmd_decay(ns: argparse.Namespace) -> None:
    """Apply importance decay to memories."""
    from .core import MemOS
    m = _get_memos(ns)
    items = m._store.list_all(namespace=m._namespace)
    report = m._decay.run_decay(
        items,
        min_age_days=ns.min_age_days,
        floor=ns.floor,
        dry_run=not ns.apply,
    )
    # Persist changes if not dry-run
    if ns.apply:
        for item in items:
            m._store.upsert(item, namespace=m._namespace)
    mode = "APPLIED" if ns.apply else "DRY RUN"
    print(f"Decay report ({mode}):")
    print(f"  Total memories:    {report.total}")
    print(f"  Decayed:           {report.decayed}")
    print(f"  Avg importance:    {report.avg_importance_before:.3f} → {report.avg_importance_after:.3f}")
    if report.details:
        print("")
        print("Top decayed:")
        for d in report.details[:10]:
            print(f"  [{d['id'][:8]}] {d['importance_before']:.3f} → {d['importance_after']:.3f} (age {d['age_days']}d)")


def cmd_reinforce(ns: argparse.Namespace) -> None:
    """Boost a memory's importance."""
    from .core import MemOS
    m = _get_memos(ns)
    item = m._store.get(ns.memory_id, namespace=m._namespace)
    if item is None:
        print(f"Memory not found: {ns.memory_id}", file=sys.stderr)
        sys.exit(1)
    old_imp = item.importance
    new_imp = m._decay.reinforce(item, strength=ns.strength)
    m._store.upsert(item, namespace=m._namespace)
    print(f"✓ Reinforced [{item.id[:8]}] importance: {old_imp:.3f} → {new_imp:.3f}")


def cmd_compress(ns: argparse.Namespace) -> None:
    """Compress very low-importance memories into aggregate summaries."""
    m = _get_memos(ns)
    result = m.compress(threshold=ns.threshold, dry_run=ns.dry_run)
    prefix = "DRY RUN " if ns.dry_run else ""
    print(f"{prefix}Compression complete:")
    print(f"  Compressed memories: {result.compressed_count}")
    print(f"  Summary memories:    {result.summary_count}")
    print(f"  Freed bytes:         {result.freed_bytes}")
    if getattr(ns, "verbose", False) and result.details:
        for detail in result.details[:10]:
            tags = ", ".join(detail["tags"])
            print(
                f"  - [{tags}] {detail['source_count']} → {detail['summary_id'][:8]} "
                f"({detail['freed_bytes']} bytes)"
            )

def cmd_wiki_living(ns: argparse.Namespace) -> None:
    """Living wiki commands."""
    from .wiki_living import LivingWikiEngine
    memos = _get_memos(ns)
    wiki_dir = getattr(ns, "wiki_dir", None)
    engine = LivingWikiEngine(memos, wiki_dir=wiki_dir)

    action = getattr(ns, "wl_action", None)
    if action == "init":
        result = engine.init()
        print(f"Living wiki initialized: {result['wiki_dir']}")
        print(f"  Pages dir: {result['pages_dir']}")
        print(f"  DB: {result['db']}")

    elif action == "update":
        result = engine.update(force=getattr(ns, "force", False))
        print("Living wiki updated:")
        print(f"  Pages created: {result.pages_created}")
        print(f"  Pages updated: {result.pages_updated}")
        print(f"  Entities found: {result.entities_found}")
        print(f"  Memories indexed: {result.memories_indexed}")
        print(f"  Backlinks added: {result.backlinks_added}")

    elif action == "lint":
        report = engine.lint()
        issues = 0
        if report.orphan_pages:
            print(f"🟡 Orphan pages ({len(report.orphan_pages)}):")
            for p in report.orphan_pages:
                print(f"  - {p}")
            issues += len(report.orphan_pages)
        if report.empty_pages:
            print(f"🔵 Empty pages ({len(report.empty_pages)}):")
            for p in report.empty_pages:
                print(f"  - {p}")
            issues += len(report.empty_pages)
        if report.contradictions:
            print(f"🔴 Contradictions ({len(report.contradictions)}):")
            for c in report.contradictions:
                print(f"  - {c['entity']}: {c['conflicting_terms']}")
            issues += len(report.contradictions)
        if report.stale_pages:
            print(f"🟠 Stale pages ({len(report.stale_pages)}):")
            for p in report.stale_pages:
                print(f"  - {p}")
            issues += len(report.stale_pages)
        if report.missing_backlinks:
            print(f"⚪ Missing backlinks ({len(report.missing_backlinks)}):")
            for src, tgt in report.missing_backlinks:
                print(f"  - {src} → {tgt}")
            issues += len(report.missing_backlinks)
        if issues == 0:
            print("✅ Living wiki is clean — no issues found.")
        else:
            print(f"\nTotal issues: {issues}")

    elif action == "index":
        content = engine.regenerate_index()
        print(content)

    elif action == "log":
        entries = engine.get_log(limit=getattr(ns, "limit", 20))
        if not entries:
            print("No activity log entries.")
        for e in entries:
            print(f"  {e['time']} [{e['action']}] {e['entity']} — {e['detail']}")

    elif action == "read":
        content = engine.read_page(ns.entity)
        if content is None:
            print(f"No living page found for '{ns.entity}'.", file=sys.stderr)
            sys.exit(1)
        print(content)

    elif action == "search":
        results = engine.search(ns.query)
        if not results:
            print(f"No matches for '{ns.query}'.")
        for r in results:
            print(f"  [{r['type']}] {r['entity']} ({r['matches']} matches)")
            print(f"    ...{r['snippet']}...")

    elif action == "list":
        pages = engine.list_pages()
        if not pages:
            print("No living pages. Run: memos wiki-living update")
        for p in pages:
            bl = f" ←{len(p.backlinks)}" if p.backlinks else ""
            mc = len(p.memory_ids)
            print(f"  [{p.entity_type}] {p.entity} ({mc} mems{bl})")

    elif action == "stats":
        s = engine.stats()
        print("Living Wiki Stats:")
        print(f"  Entities: {s['total_entities']}")
        print(f"  Memory links: {s['total_memory_links']}")
        print(f"  Backlinks: {s['total_backlinks']}")
        print(f"  Types: {s['type_distribution']}")

    else:
        wl_sp.print_help()


def cmd_wiki_graph(ns: argparse.Namespace) -> None:
    """Generate or read graph-community wiki pages."""
    from .wiki_graph import GraphWikiEngine

    kg = _get_kg(ns)
    try:
        engine = GraphWikiEngine(kg, output_dir=getattr(ns, "output", None))
        community_id = getattr(ns, "community", None)
        if community_id:
            content = engine.read_community(community_id)
            if content is None:
                print(f"No graph community found for '{community_id}'.", file=sys.stderr)
                sys.exit(1)
            print(content)
            return

        result = engine.build(update=getattr(ns, "update", False))
        print("Graph wiki built:")
        print(f"  Communities: {result.community_count}")
        print(f"  Facts indexed: {result.facts_indexed}")
        print(f"  Pages written: {result.pages_written}")
        print(f"  Pages skipped: {result.pages_skipped}")
        print(f"  Pages removed: {result.pages_removed}")
        print(f"  God nodes: {result.god_nodes}")
        print(f"  Output: {result.output_dir}")
    finally:
        kg.close()


def cmd_brain_search(ns: argparse.Namespace) -> None:
    """Run unified search across memories, living wiki pages, and the knowledge graph."""
    from .brain import BrainSearch

    memos = _get_memos(ns)
    kg = _get_kg(ns)
    try:
        searcher = BrainSearch(memos, kg=kg, wiki_dir=getattr(ns, "wiki_dir", None))
        tags = ns.tags.split(",") if getattr(ns, "tags", None) else None
        result = searcher.search(ns.query, top_k=ns.top, filter_tags=tags)
        print(f"Brain search: {ns.query}")
        if result.entities:
            print("Entities:", ", ".join(result.entities))
        print(f"Memories: {len(result.memories)}")
        for item in result.memories:
            print(f"  [{item.score:.2f}] {item.content}")
        print(f"Wiki pages: {len(result.wiki_pages)}")
        for item in result.wiki_pages:
            print(f"  [{item.score:.2f}] {item.entity}: {item.snippet}")
        print(f"KG facts: {len(result.kg_facts)}")
        for item in result.kg_facts:
            print(f"  [{item.confidence_label}] {item.subject} -{item.predicate}-> {item.object}")
        print("Context:")
        print(result.context)
    finally:
        kg.close()


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
        "analytics": cmd_analytics,
        "forget": cmd_forget,
        "get": cmd_get,
        "prune-expired": cmd_prune_expired,
        "prune": cmd_prune,
        "mcp-serve": cmd_mcp_serve,
        "mcp-stdio": cmd_mcp_stdio,
        "serve": cmd_serve,
        "watch": cmd_watch,
        "subscribe": cmd_subscribe,
        "consolidate": cmd_consolidate,
        "ingest": cmd_ingest,
        "ingest-url": cmd_ingest_url,
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
        "benchmark-quality": cmd_benchmark_quality,
        "tags": cmd_tags,
        "share-offer": cmd_share_offer,
        "share-accept": cmd_share_accept,
        "share-reject": cmd_share_reject,
        "share-revoke": cmd_share_revoke,
        "share-export": cmd_share_export,
        "share-import": cmd_share_import,
        "share-list": cmd_share_list,
        "share-stats": cmd_share_stats,
        "sync-check": cmd_sync_check,
        "sync-apply": cmd_sync_apply,
        "feedback": cmd_feedback,
        "feedback-list": cmd_feedback_list,
        "feedback-stats": cmd_feedback_stats,
        "wiki-compile": cmd_wiki_compile,
        "wiki-list": cmd_wiki_list,
        "wiki-read": cmd_wiki_read,
        "wiki-living": cmd_wiki_living,
        "wiki-graph": cmd_wiki_graph,
        "brain-search": cmd_brain_search,
        "mine": cmd_mine,
        "mine-conversation": cmd_mine_conversation,
        "mine-status": cmd_mine_status,
        "kg-add": cmd_kg_add,
        "kg-query": cmd_kg_query,
        "kg-timeline": cmd_kg_timeline,
        "kg-invalidate": cmd_kg_invalidate,
        "kg-stats": cmd_kg_stats,
        "kg-path": cmd_kg_path,
        "kg-neighbors": cmd_kg_neighbors,
        "kg-infer": cmd_kg_infer,
        "kg-labels": cmd_kg_labels,
        "palace-init": cmd_palace_init,
        "palace-wing-create": cmd_palace_wing_create,
        "palace-wing-list": cmd_palace_wing_list,
        "palace-room-create": cmd_palace_room_create,
        "palace-room-list": cmd_palace_room_list,
        "palace-assign": cmd_palace_assign,
        "palace-recall": cmd_palace_recall,
        "palace-stats": cmd_palace_stats,
        "wake-up": cmd_wake_up,
        "identity": cmd_identity,
        "context-for": cmd_context_for,
        "classify": cmd_classify,
        "decay": cmd_decay,
        "reinforce": cmd_reinforce,
        "compress": cmd_compress,
    }
    commands[ns.command](ns)


if __name__ == "__main__":
    main()
