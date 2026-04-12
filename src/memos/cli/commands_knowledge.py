"""MemOS CLI — knowledge graph, wiki, brain commands."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from ._common import _get_memos, _get_kg, _get_kg_bridge, _ts


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


def cmd_kg_backlinks(ns: argparse.Namespace) -> None:
    """Show all incoming edges (backlinks) for an entity."""
    kg = _get_kg(ns)
    try:
        predicate = getattr(ns, "predicate", None) or None
        active_only = not getattr(ns, "show_all", False)
        facts = kg.backlinks(ns.entity, predicate=predicate, active_only=active_only)
        if not facts:
            print(f"No backlinks found for: {ns.entity!r}")
            return
        print(f"Backlinks for {ns.entity!r}:")
        for f in facts:
            inv = " [INVALIDATED]" if f["invalidated_at"] else ""
            label = f.get("confidence_label", "EXTRACTED")
            print(f"  [{f['id']}] {f['subject']} -[{f['predicate']}]-> {f['object']} "
                  f"(conf={f['confidence']:.2f}, label={label}){inv}")
        print(f"\n{len(facts)} backlink(s)")
    finally:
        kg.close()


def cmd_kg_lint(ns: argparse.Namespace) -> None:
    """Lint the knowledge graph — detect contradictions, orphans, sparse entities."""
    kg = _get_kg(ns)
    try:
        min_facts = getattr(ns, "min_facts", 2)
        report = kg.lint(min_facts=min_facts)
        s = report["summary"]
        issues = s["contradictions"] + s["orphans"] + s["sparse"]

        print(f"KG Lint Report  (entities={s['total_entities']}, active_facts={s['active_facts']})")
        print("-" * 60)

        if report["contradictions"]:
            print(f"\n[CONTRADICTION] {s['contradictions']} subject+predicate pair(s) with multiple objects:")
            for c in report["contradictions"]:
                objects = ", ".join(c["objects"])
                print(f"  {c['subject']} -{c['predicate']}-> [{objects}]")

        if report["orphans"]:
            print(f"\n[ORPHAN] {s['orphans']} entity/entities appear in exactly one triple:")
            for e in report["orphans"]:
                print(f"  {e}")

        if report["sparse"]:
            print(f"\n[SPARSE] {s['sparse']} entity/entities with fewer than {min_facts} fact(s):")
            for e in report["sparse"]:
                print(f"  {e}")

        if issues == 0:
            print("\n✓ No issues found.")
        else:
            print(f"\nTotal issues: {issues}")
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




def cmd_wiki_compile(ns: argparse.Namespace) -> None:
    """Compile memories into per-tag wiki pages."""
    from ..wiki import WikiEngine
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
    from ..wiki import WikiEngine
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
    from ..wiki import WikiEngine
    memos = _get_memos(ns)
    wiki = WikiEngine(memos, wiki_dir=getattr(ns, "wiki_dir", None))
    content = wiki.read(ns.tag)
    if content is None:
        print(f"No wiki page found for tag '{ns.tag}'. Run: memos wiki-compile", file=sys.stderr)
        sys.exit(1)
    print(content)





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
        wl_sp.print_help()


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




