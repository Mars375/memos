"""Index generation helpers for the living wiki engine."""

from __future__ import annotations

import time
from typing import Any, Dict, List


def regenerate_index(engine, db) -> str:
    """Regenerate index.md from DB."""
    now = time.time()
    now_fmt = time.strftime("%Y-%m-%d %H:%M", time.localtime(now))

    entities = db.execute("SELECT name, entity_type, page_path, created_at, updated_at FROM entities").fetchall()
    backlink_counts: Dict[str, int] = {
        row["target_entity"]: row["cnt"]
        for row in db.execute("SELECT target_entity, COUNT(*) as cnt FROM backlinks GROUP BY target_entity").fetchall()
    }
    source_counts: Dict[str, int] = {
        row["entity_name"]: row["cnt"]
        for row in db.execute(
            "SELECT entity_name, COUNT(*) as cnt FROM entity_memories GROUP BY entity_name"
        ).fetchall()
    }
    total_backlinks = db.execute("SELECT COUNT(*) FROM backlinks").fetchone()[0]
    total_memory_links = db.execute("SELECT COUNT(*) FROM entity_memories").fetchone()[0]

    category_map = {
        "person": "Entities",
        "contact": "Entities",
        "project": "Entities",
        "concept": "Concepts",
        "topic": "Topics",
        "resource": "Sources",
        "default": "Concepts",
    }

    sorted_entities = sorted(
        entities, key=lambda row: (-backlink_counts.get(row["name"], 0), -(row["updated_at"] or 0))
    )
    categories: Dict[str, List[Any]] = {"Entities": [], "Concepts": [], "Sources": [], "Topics": []}
    uncategorized: List[Any] = []
    for row in sorted_entities:
        category = category_map.get(row["entity_type"])
        if category and category in categories:
            categories[category].append(row)
        else:
            uncategorized.append(row)
    if uncategorized:
        categories["Concepts"].extend(uncategorized)

    lines: List[str] = []
    lines.append("# 📚 Living Wiki Index\n")
    lines.append("> Auto-generated Karpathy-style catalog of entities and concepts.\n")
    lines.extend(
        [
            "",
            "## 📊 Statistics\n",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total Pages | {len(entities)} |",
            f"| Total Memory Links | {total_memory_links} |",
            f"| Total Wiki Links | {total_backlinks} |",
            f"| Last Updated | {now_fmt} |",
            "",
        ]
    )

    recent = db.execute("SELECT ts, action, entity, detail FROM activity_log ORDER BY id DESC LIMIT 10").fetchall()
    if recent:
        lines.extend(["## 🕐 Recent Changes\n", ""])
        for entry in recent:
            ts_fmt = time.strftime("%Y-%m-%d %H:%M", time.localtime(entry["ts"]))
            entity = entry["entity"]
            entity_link = f"[[{engine._safe_slug(entity)}|{entity}]]" if entity else ""
            lines.append(f"- `{ts_fmt}` **{entry['action']}** {entity_link} — {entry['detail']}")
        lines.append("")

    for category_name, items in categories.items():
        if not items:
            continue
        lines.extend([f"## {category_name} ({len(items)})\n", ""])
        for item in items:
            slug = engine._safe_slug(item["name"])
            summary = engine._get_page_summary(item["name"])
            created_date = (
                time.strftime("%Y-%m-%d", time.localtime(item["created_at"])) if item["created_at"] else "N/A"
            )
            src_count = source_counts.get(item["name"], 0)
            updated_date = (
                time.strftime("%Y-%m-%d", time.localtime(item["updated_at"])) if item["updated_at"] else "N/A"
            )

            age = ""
            if item["updated_at"]:
                delta = now - item["updated_at"]
                if delta < 86400:
                    age = " 🟢"
                elif delta < 7 * 86400:
                    age = " 🟡"
                else:
                    age = " 🔴"

            link = f"[[{slug}|{item['name']}]]"
            suffix = f" — {summary}" if summary else ""
            meta = f" *(created: {created_date}, sources: {src_count}, updated: {updated_date})*"
            lines.append(f"- {link}{age}{suffix}")
            lines.append(f"  {meta}")
        lines.append("")

    content = "\n".join(lines)
    engine._index_path.write_text(content, encoding="utf-8")
    return content
