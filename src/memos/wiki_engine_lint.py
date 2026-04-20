"""Lint helpers for the living wiki engine."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Set


def lint_report(engine) -> Dict[str, Any]:
    """Run a comprehensive living wiki health check."""
    engine.init()
    db = engine._get_db()
    issues: List[Dict[str, Any]] = []

    pages_dir = engine._wiki_dir / "pages"
    if not pages_dir.exists():
        db.close()
        return {
            "issues": [],
            "summary": {
                "total_pages": 0,
                "orphan_count": 0,
                "missing_ref_count": 0,
                "stale_count": 0,
                "empty_count": 0,
                "contradiction_count": 0,
            },
        }

    now = time.time()
    thirty_days = 30 * 86400
    all_entities = {
        row["name"]: dict(row)
        for row in db.execute("SELECT name, entity_type, page_path, updated_at FROM entities").fetchall()
    }
    total_pages = len(all_entities)

    inbound: Dict[str, Set[str]] = {name: set() for name in all_entities}
    for row in db.execute("SELECT source_entity, target_entity FROM backlinks").fetchall():
        tgt = row["target_entity"]
        if tgt in inbound:
            inbound[tgt].add(row["source_entity"])

    for ename, edata in all_entities.items():
        slug = engine._safe_slug(ename)
        page_path = pages_dir / f"{slug}.md"

        if not inbound.get(ename):
            issues.append({"type": "orphan", "severity": "warning", "page": ename, "detail": "No inbound links"})

        if page_path.exists():
            content = page_path.read_text(encoding="utf-8")
            in_fm = False
            real_lines: List[str] = []
            for line in content.splitlines():
                stripped = line.strip()
                if stripped == "---":
                    in_fm = not in_fm
                    continue
                if in_fm:
                    continue
                if stripped and not stripped.startswith("<!--") and not stripped.startswith("# ") and not stripped.startswith("## "):
                    real_lines.append(stripped)
            if len(real_lines) < 3:
                issues.append({"type": "empty", "severity": "warning", "page": ename, "detail": "Page has no real content"})
        else:
            issues.append({"type": "empty", "severity": "warning", "page": ename, "detail": "Page file missing"})

        if edata["updated_at"] and (now - edata["updated_at"]) > thirty_days:
            days_stale = int((now - edata["updated_at"]) / 86400)
            issues.append({"type": "stale", "severity": "info", "page": ename, "detail": f"Not updated in {days_stale} days"})

    for ename in all_entities:
        mem_contents: List[str] = [
            row["snippet"]
            for row in db.execute("SELECT em.snippet FROM entity_memories em WHERE em.entity_name = ?", (ename,)).fetchall()
        ]
        negated: Set[str] = set()
        affirmed: Set[str] = set()
        for snippet in mem_contents:
            negated.update(re.findall(r"not\s+(\w+)", snippet.lower()))
            affirmed.update(re.findall(r"\bis\s+(\w+)", snippet.lower()))
        conflicts = negated & affirmed
        if conflicts:
            issues.append(
                {
                    "type": "contradiction",
                    "severity": "error",
                    "page": ename,
                    "detail": f"Conflicting terms: {', '.join(sorted(conflicts))}",
                    "conflicting_terms": sorted(conflicts),
                }
            )

    for ename in all_entities:
        slug = engine._safe_slug(ename)
        page_path = pages_dir / f"{slug}.md"
        if not page_path.exists():
            continue
        content = page_path.read_text(encoding="utf-8")
        mentioned = engine._extract_entities(content)
        for mentioned_name, _ in mentioned:
            if mentioned_name in all_entities and mentioned_name != ename:
                link_patterns = [f"[[{engine._safe_slug(mentioned_name)}", f"[[{mentioned_name}"]
                if not any(pattern in content for pattern in link_patterns):
                    issues.append(
                        {
                            "type": "missing_ref",
                            "severity": "info",
                            "page": ename,
                            "detail": f"Mentions '{mentioned_name}' but no link",
                            "target": mentioned_name,
                        }
                    )

    orphan_count = sum(1 for issue in issues if issue["type"] == "orphan")
    missing_ref_count = sum(1 for issue in issues if issue["type"] == "missing_ref")
    stale_count = sum(1 for issue in issues if issue["type"] == "stale")
    empty_count = sum(1 for issue in issues if issue["type"] == "empty")
    contradiction_count = sum(1 for issue in issues if issue["type"] == "contradiction")

    engine._append_log(
        "lint",
        f"Orphans: {orphan_count}, Empty: {empty_count}, Contradictions: {contradiction_count}, Missing refs: {missing_ref_count}, Stale: {stale_count}",
    )
    db.close()
    return {
        "issues": issues,
        "summary": {
            "total_pages": total_pages,
            "orphan_count": orphan_count,
            "missing_ref_count": missing_ref_count,
            "stale_count": stale_count,
            "empty_count": empty_count,
            "contradiction_count": contradiction_count,
        },
    }
