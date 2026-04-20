"""Read/search/page-management helpers for the living wiki engine."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .wiki_models import LivingPage
from .wiki_templates import _PAGE_TEMPLATES


def read_page(engine, entity: str) -> Optional[str]:
    slug = engine._safe_slug(entity)
    page_path = engine._wiki_dir / "pages" / f"{slug}.md"
    if page_path.exists():
        return page_path.read_text(encoding="utf-8")

    db = engine._get_db()
    row = db.execute("SELECT page_path FROM entities WHERE name LIKE ?", (f"%{entity}%",)).fetchone()
    db.close()
    if row:
        path = Path(row["page_path"])
        if path.exists():
            return path.read_text(encoding="utf-8")
    return None


def search(engine, query: str) -> List[Dict[str, Any]]:
    engine.init()
    db = engine._get_db()
    results: List[Dict[str, Any]] = []
    query_lower = query.lower()

    pages_dir = engine._wiki_dir / "pages"
    if not pages_dir.exists():
        db.close()
        return results

    for page_file in pages_dir.glob("*.md"):
        content = page_file.read_text(encoding="utf-8")
        matches = content.lower().count(query_lower)
        if matches > 0:
            entity = page_file.stem.replace("-", " ")
            entity_type = "default"
            fm_match = re.search(r'title:\s*"([^"]+)"', content)
            if fm_match:
                entity = fm_match.group(1)
            type_match = re.search(r"type:\s*(\w+)", content)
            if type_match:
                entity_type = type_match.group(1)
            idx = content.lower().find(query_lower)
            snippet = content[max(0, idx - 60) : min(len(content), idx + len(query) + 60)].replace("\n", " ")
            results.append({"entity": entity, "type": entity_type, "matches": matches, "snippet": snippet})

    db.close()
    results.sort(key=lambda item: -item["matches"])
    return results


def get_log(engine, limit: int = 20) -> List[Dict[str, Any]]:
    engine.init()
    db = engine._get_db()
    rows = db.execute("SELECT ts, action, entity, detail FROM activity_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    db.close()
    return [
        {
            "timestamp": row["ts"],
            "time": time.strftime("%Y-%m-%d %H:%M", time.localtime(row["ts"])),
            "action": row["action"],
            "entity": row["entity"],
            "detail": row["detail"],
        }
        for row in rows
    ]


def create_page(engine, entity: str, entity_type: str = "default", content: str = "") -> Dict[str, Any]:
    import time as _time

    engine.init()
    db = engine._get_db()
    slug = engine._safe_slug(entity)
    page_path = engine._wiki_dir / "pages" / f"{slug}.md"

    existing = db.execute("SELECT name FROM entities WHERE name = ?", (entity,)).fetchone()
    if existing is not None:
        db.close()
        return {"status": "already_exists", "slug": slug, "entity": entity, "path": str(page_path)}

    meta = {
        "entity": entity,
        "type": entity_type,
        "created": _time.strftime("%Y-%m-%d", _time.localtime()),
        "updated": _time.strftime("%Y-%m-%d", _time.localtime()),
        "memory_count": 0,
        "tags": [],
    }
    template_fn = _PAGE_TEMPLATES.get(entity_type, _PAGE_TEMPLATES["default"])
    page_content = template_fn(entity, meta)
    if content:
        page_content += f"\n{content}\n"

    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(page_content, encoding="utf-8")

    now = _time.time()
    db.execute(
        "INSERT INTO entities (name, entity_type, page_path, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (entity, entity_type, str(page_path), now, now),
    )
    engine._log_action(db, "create", entity, f"Manually created {entity_type} page")
    engine._append_log("create_page", f"Manually created {entity_type} page: {entity}")
    db.commit()
    db.close()
    return {"status": "created", "slug": slug, "entity": entity, "path": str(page_path)}


def list_pages(engine) -> List[LivingPage]:
    engine.init()
    db = engine._get_db()
    pages: List[LivingPage] = []
    for row in db.execute("SELECT name, entity_type, page_path, created_at, updated_at FROM entities ORDER BY name").fetchall():
        slug = engine._safe_slug(row["name"])
        page_path = engine._wiki_dir / "pages" / f"{slug}.md"
        memory_ids = [
            result["memory_id"]
            for result in db.execute("SELECT memory_id FROM entity_memories WHERE entity_name = ?", (row["name"],)).fetchall()
        ]
        backlinks = [
            result["target_entity"]
            for result in db.execute("SELECT target_entity FROM backlinks WHERE source_entity = ?", (row["name"],)).fetchall()
        ]
        pages.append(
            LivingPage(
                entity=row["name"],
                entity_type=row["entity_type"],
                path=page_path,
                memory_ids=memory_ids,
                backlinks=backlinks,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                size_bytes=page_path.stat().st_size if page_path.exists() else 0,
            )
        )
    db.close()
    return pages


def stats(engine) -> Dict[str, Any]:
    engine.init()
    db = engine._get_db()
    entity_count = db.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    mem_links = db.execute("SELECT COUNT(*) FROM entity_memories").fetchone()[0]
    link_count = db.execute("SELECT COUNT(*) FROM backlinks").fetchone()[0]
    type_dist = dict(db.execute("SELECT entity_type, COUNT(*) FROM entities GROUP BY entity_type").fetchall())
    db.close()
    return {
        "total_entities": entity_count,
        "total_memory_links": mem_links,
        "total_backlinks": link_count,
        "type_distribution": type_dist,
        "wiki_dir": str(engine._wiki_dir),
    }
