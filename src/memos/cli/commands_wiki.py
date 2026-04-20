"""MemOS CLI — wiki/brain search commands."""

from __future__ import annotations

import argparse
import sys
import sys as _sys


def _get_memos(ns):
    return _sys.modules["memos.cli.commands_memory"]._get_memos(ns)


def _get_kg(ns):
    return _sys.modules["memos.cli.commands_memory"]._get_kg(ns)


def cmd_wiki_living(ns: argparse.Namespace) -> None:
    """Living wiki commands."""
    from ..wiki_living import LivingWikiEngine

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
        print("No wiki-living action specified. Use: init, update, lint, index, log, read, search, list, stats")


def cmd_wiki_graph(ns: argparse.Namespace) -> None:
    """Generate or read graph-community wiki pages."""
    from ..wiki_graph import GraphWikiEngine

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
    from ..brain import BrainSearch

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
