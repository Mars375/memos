"""Update and cross-reference helpers for the living wiki engine."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Set

from .wiki_entities import extract_entities
from .wiki_models import UpdateResult
from .wiki_templates import _PAGE_TEMPLATES


def update(engine, force: bool = False) -> UpdateResult:
    """Scan memories and update/create wiki pages."""
    engine.init()
    db = engine._get_db()
    result = UpdateResult()

    store = engine._memos._store
    namespace = engine._memos._namespace
    all_items = store.list_all(namespace=namespace)
    result.memories_indexed = len(all_items)

    if not force:
        existing = {row[0] for row in db.execute("SELECT memory_id FROM entity_memories").fetchall()}
    else:
        existing = set()
        db.execute("DELETE FROM entity_memories")
        db.execute("DELETE FROM backlinks")

    for item in all_items:
        if item.id in existing and not force:
            continue

        entities = extract_entities(item.content)
        for tag in item.tags or []:
            entities.append((tag, "topic"))

        for ename, etype in entities:
            row = db.execute("SELECT name FROM entities WHERE name = ?", (ename,)).fetchone()
            if row is None:
                _create_entity_page(engine, db, ename, etype, item.content)
                result.pages_created += 1
            else:
                _append_entity_snippet(engine, db, ename, etype, item.content)
                result.pages_updated += 1

            db.execute(
                "INSERT OR IGNORE INTO entity_memories (entity_name, memory_id, snippet, added_at) VALUES (?, ?, ?, ?)",
                (ename, item.id, item.content[:100], time.time()),
            )

        result.entities_found += len(entities)

    all_entities = [row["name"] for row in db.execute("SELECT name FROM entities").fetchall()]
    cooc_rows = db.execute(
        "SELECT em1.entity_name AS e1, em2.entity_name AS e2 "
        "FROM entity_memories em1 "
        "JOIN entity_memories em2 ON em1.memory_id = em2.memory_id "
        "WHERE em1.entity_name < em2.entity_name "
        "GROUP BY em1.entity_name, em2.entity_name"
    ).fetchall()
    backlink_params: list[tuple[str, str]] = []
    for row in cooc_rows:
        backlink_params.append((row["e1"], row["e2"]))
        backlink_params.append((row["e2"], row["e1"]))
    if backlink_params:
        db.executemany(
            "INSERT OR IGNORE INTO backlinks (source_entity, target_entity) VALUES (?, ?)",
            backlink_params,
        )
    result.backlinks_added = len(cooc_rows)

    for ename in all_entities:
        _rewrite_page_links(engine, db, ename)

    engine._log_action(
        db,
        "update",
        "",
        f"Created {result.pages_created}, updated {result.pages_updated}, indexed {result.memories_indexed} memories, {result.backlinks_added} backlinks",
    )
    engine._regenerate_index(db)
    engine._append_log(
        "update",
        f"Created {result.pages_created}, updated {result.pages_updated}, indexed {result.memories_indexed} memories, {result.backlinks_added} backlinks",
    )
    db.commit()
    invalidate = getattr(engine, "_invalidate_list_pages_cache", None)
    if callable(invalidate):
        invalidate()
    db.close()
    return result


def update_for_item(engine, item: Any) -> UpdateResult:
    """Incrementally update wiki pages for a single memory."""
    engine.init()
    db = engine._get_db()
    result = UpdateResult()
    result.memories_indexed = 1

    try:
        already = db.execute("SELECT COUNT(*) FROM entity_memories WHERE memory_id = ?", (item.id,)).fetchone()[0]
        if already > 0:
            return result

        entities = extract_entities(item.content)
        for tag in item.tags or []:
            entities.append((tag, "topic"))

        entity_names: List[str] = []
        for ename, etype in entities:
            row = db.execute("SELECT name FROM entities WHERE name = ?", (ename,)).fetchone()
            if row is None:
                _create_entity_page(engine, db, ename, etype, item.content, compounding=True)
                result.pages_created += 1
            else:
                _append_entity_snippet(engine, db, ename, etype, item.content)
                result.pages_updated += 1
            db.execute(
                "INSERT OR IGNORE INTO entity_memories (entity_name, memory_id, snippet, added_at) VALUES (?, ?, ?, ?)",
                (ename, item.id, item.content[:100], time.time()),
            )
            entity_names.append(ename)

        result.entities_found += len(entities)
        for ename in entity_names:
            refresh_entity_page(engine, ename, trigger=item.id, db=db)
        update_cross_references(engine, entity_names, db=db)
        db.commit()
        engine._regenerate_index(db)
        engine._append_log(
            "update_for_item",
            f"Created {result.pages_created}, updated {result.pages_updated}, found {result.entities_found} entities",
        )
        invalidate = getattr(engine, "_invalidate_list_pages_cache", None)
        if callable(invalidate):
            invalidate()
    finally:
        db.close()

    return result


def refresh_entity_page(engine, entity: str, trigger: str | None = None, db=None) -> None:
    """Refresh a single entity page with current context."""
    slug = engine._safe_slug(entity)
    page_path = engine._wiki_dir / "pages" / f"{slug}.md"
    if not page_path.exists():
        return

    own_db = db is None
    if own_db:
        db = engine._get_db()

    try:
        row = db.execute("SELECT name FROM entities WHERE name = ?", (entity,)).fetchone()
        if row is None:
            return

        content = page_path.read_text(encoding="utf-8")
        content = re.sub(r"updated: \d{4}-\d{2}-\d{2}", f"updated: {time.strftime('%Y-%m-%d')}", content)

        if trigger and trigger not in content:
            content += f"\n## Related Context\n\n> Triggered by memory `{trigger}`\n"

        kg = getattr(engine._memos, "kg", None) or getattr(engine._memos, "_kg", None)
        if kg is not None:
            try:
                neighbor_edges = kg.neighbors(entity, depth=1, direction="both")["edges"]
            except Exception:
                neighbor_edges = []
            if neighbor_edges:
                seen_neighbors: Dict[str, Set[str]] = {}
                for edge in neighbor_edges:
                    other = edge["object"] if edge["subject"] == entity else edge["subject"]
                    seen_neighbors.setdefault(other, set()).add(edge["predicate"])
                neighbor_lines = (
                    "\n## Graph Neighbors\n\n"
                    + "\n".join(
                        f"- [[{engine._safe_slug(other)}|{other}]] ({', '.join(sorted(predicates))})"
                        for other, predicates in sorted(seen_neighbors.items())
                    )
                    + "\n"
                )
                if "## Graph Neighbors" in content:
                    content = re.sub(
                        r"## Graph Neighbors\n.*?(?=\n## |\Z)",
                        neighbor_lines.strip("\n"),
                        content,
                        flags=re.DOTALL,
                    )
                else:
                    content += neighbor_lines

        page_path.write_text(content, encoding="utf-8")
        db.execute("UPDATE entities SET updated_at = ? WHERE name = ?", (time.time(), entity))
        engine._log_action(
            db, "refresh", entity, f"Refreshed page (trigger: {trigger})" if trigger else "Refreshed page"
        )
        if own_db:
            db.commit()
        invalidate = getattr(engine, "_invalidate_list_pages_cache", None)
        if callable(invalidate):
            invalidate()
    finally:
        if own_db:
            db.close()


def update_cross_references(engine, entities: List[str], db=None) -> int:
    """Add bidirectional backlinks between related entity pages."""
    if len(entities) < 2:
        return 0

    own_db = db is None
    if own_db:
        db = engine._get_db()

    added = 0
    try:
        for i, e1 in enumerate(entities):
            for e2 in entities[i + 1 :]:
                for src, tgt in [(e1, e2), (e2, e1)]:
                    existing = db.execute(
                        "SELECT 1 FROM backlinks WHERE source_entity = ? AND target_entity = ?",
                        (src, tgt),
                    ).fetchone()
                    if existing is None:
                        db.execute(
                            "INSERT OR IGNORE INTO backlinks (source_entity, target_entity) VALUES (?, ?)",
                            (src, tgt),
                        )
                        added += 1
                        slug = engine._safe_slug(src)
                        page_path = engine._wiki_dir / "pages" / f"{slug}.md"
                        if page_path.exists():
                            content = page_path.read_text(encoding="utf-8")
                            link_line = f"- [[{engine._safe_slug(tgt)}|{tgt}]]"
                            if link_line not in content:
                                if "## Backlinks" in content:
                                    content = content.replace("## Backlinks\n", f"## Backlinks\n\n{link_line}\n", 1)
                                else:
                                    content += f"\n## Backlinks\n\n{link_line}\n"
                                page_path.write_text(content, encoding="utf-8")
        if own_db:
            db.commit()
        invalidate = getattr(engine, "_invalidate_list_pages_cache", None)
        if callable(invalidate):
            invalidate()
    finally:
        if own_db:
            db.close()
    return added


def _create_entity_page(engine, db, ename: str, etype: str, content: str, compounding: bool = False) -> None:
    slug = engine._safe_slug(ename)
    page_path = engine._wiki_dir / "pages" / f"{slug}.md"
    meta = {
        "entity": ename,
        "type": etype,
        "created": time.strftime("%Y-%m-%d", time.localtime()),
        "updated": time.strftime("%Y-%m-%d", time.localtime()),
        "memory_count": 1,
        "tags": [],
    }
    template_fn = _PAGE_TEMPLATES.get(etype, _PAGE_TEMPLATES["default"])
    page_content = template_fn(ename, meta) + f"\n## Memory Snippet\n\n> {content[:200]}\n"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(page_content, encoding="utf-8")
    db.execute(
        "INSERT INTO entities (name, entity_type, page_path, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (ename, etype, str(page_path), time.time(), time.time()),
    )
    detail = f"New {etype} page (compounding)" if compounding else f"New {etype} page"
    engine._log_action(db, "create", ename, detail)


def _append_entity_snippet(engine, db, ename: str, etype: str, content: str) -> None:
    slug = engine._safe_slug(ename)
    page_path = engine._wiki_dir / "pages" / f"{slug}.md"
    if page_path.exists():
        existing_content = page_path.read_text(encoding="utf-8")
        snippet = f"\n## Snippet ({time.strftime('%Y-%m-%d %H:%M')})\n\n> {content[:200]}\n"
        existing_content = re.sub(
            r"sources: \d+",
            lambda m: f"sources: {int(m.group().split(': ')[1]) + 1}",
            existing_content,
        )
        existing_content = re.sub(
            r"updated: \d{4}-\d{2}-\d{2}",
            f"updated: {time.strftime('%Y-%m-%d')}",
            existing_content,
        )
        page_path.write_text(existing_content + snippet, encoding="utf-8")
    else:
        meta = {
            "entity": ename,
            "type": etype,
            "created": time.strftime("%Y-%m-%d"),
            "updated": time.strftime("%Y-%m-%d"),
            "memory_count": 1,
        }
        template_fn = _PAGE_TEMPLATES.get(etype, _PAGE_TEMPLATES["default"])
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(template_fn(ename, meta), encoding="utf-8")
    db.execute("UPDATE entities SET updated_at = ? WHERE name = ?", (time.time(), ename))


def _rewrite_page_links(engine, db, ename: str) -> None:
    links = [
        row["target_entity"]
        for row in db.execute("SELECT target_entity FROM backlinks WHERE source_entity = ?", (ename,)).fetchall()
    ]
    slug = engine._safe_slug(ename)
    page_path = engine._wiki_dir / "pages" / f"{slug}.md"
    if not links or not page_path.exists():
        return

    content = page_path.read_text(encoding="utf-8")
    link_lines = "\n## Backlinks\n\n" + "\n".join(f"- [[{engine._safe_slug(line)}|{line}]]" for line in links) + "\n"
    if "## Backlinks" in content:
        content = re.sub(r"## Backlinks\n.*", link_lines, content, flags=re.DOTALL)
    else:
        content += link_lines

    kg = getattr(engine._memos, "kg", None) or getattr(engine._memos, "_kg", None)
    neighbor_lines = "\n## Graph Neighbors\n\n- No graph neighbors yet.\n"
    if kg is not None:
        try:
            neighbor_edges = kg.neighbors(ename, depth=1, direction="both")["edges"]
        except Exception:
            neighbor_edges = []
        if neighbor_edges:
            seen_neighbors: dict[str, set[str]] = {}
            for edge in neighbor_edges:
                other = edge["object"] if edge["subject"] == ename else edge["subject"]
                seen_neighbors.setdefault(other, set()).add(edge["predicate"])
            neighbor_lines = (
                "\n## Graph Neighbors\n\n"
                + "\n".join(
                    f"- [[{engine._safe_slug(other)}|{other}]] ({', '.join(sorted(predicates))})"
                    for other, predicates in sorted(seen_neighbors.items())
                )
                + "\n"
            )
    if "## Graph Neighbors" in content:
        content = re.sub(
            r"## Graph Neighbors\n.*?(?=\n## |\Z)",
            neighbor_lines.strip("\n"),
            content,
            flags=re.DOTALL,
        )
    else:
        content += neighbor_lines
    page_path.write_text(content, encoding="utf-8")
