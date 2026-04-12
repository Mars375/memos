"""MemOS CLI — import/export/ingest/mine commands."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ._common import _get_memos


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


