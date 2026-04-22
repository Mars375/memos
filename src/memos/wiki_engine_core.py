"""Core helpers for the living wiki engine."""

from __future__ import annotations

import datetime
import re
import sqlite3
import time


def get_db(engine) -> sqlite3.Connection:
    """Get SQLite connection, creating schema if needed."""
    engine._db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(engine._db_path))
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS entities (
            name TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL DEFAULT 'default',
            page_path TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS entity_memories (
            entity_name TEXT NOT NULL,
            memory_id TEXT NOT NULL,
            snippet TEXT DEFAULT '',
            added_at REAL NOT NULL,
            PRIMARY KEY (entity_name, memory_id),
            FOREIGN KEY (entity_name) REFERENCES entities(name)
        );
        CREATE TABLE IF NOT EXISTS backlinks (
            source_entity TEXT NOT NULL,
            target_entity TEXT NOT NULL,
            PRIMARY KEY (source_entity, target_entity)
        );
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            action TEXT NOT NULL,
            entity TEXT DEFAULT '',
            detail TEXT DEFAULT ''
        );
    """)
    return db


def frontmatter_for_page(page) -> str:
    """Generate Obsidian-compatible YAML frontmatter for a page-like object."""
    title = getattr(page, "title", None) or getattr(page, "entity", "Untitled")
    entity_type = getattr(page, "entity_type", "default")

    page_tags = getattr(page, "tags", None)
    if page_tags:
        tags = ", ".join(str(t) for t in page_tags)
    else:
        tags = "auto, entity"

    created_ts = getattr(page, "created", None) or getattr(page, "created_at", None)
    if created_ts:
        created = datetime.datetime.fromtimestamp(created_ts).strftime("%Y-%m-%d")
    else:
        created = datetime.datetime.now().strftime("%Y-%m-%d")

    updated = datetime.datetime.now().strftime("%Y-%m-%d")
    memory_ids = getattr(page, "memory_ids", None)
    sources = len(memory_ids) if memory_ids else 0

    return (
        "---\n"
        f'title: "{title}"\n'
        f"type: {entity_type}\n"
        f"tags: [{tags}]\n"
        f"created: {created}\n"
        f"updated: {updated}\n"
        f"sources: {sources}\n"
        "---\n"
    )


def get_page_summary(engine, entity_name: str) -> str:
    """Extract a one-line summary from a wiki page."""
    slug = engine._safe_slug(entity_name)
    page_path = engine._wiki_dir / "pages" / f"{slug}.md"
    if not page_path.exists():
        return ""
    content = page_path.read_text(encoding="utf-8")

    candidates: list[str] = []
    in_frontmatter = False
    in_code_fence = False

    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "---" and not in_code_fence:
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter:
            continue
        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence or not stripped:
            continue
        if stripped.startswith("#") or stripped.startswith("<!--") or stripped.startswith("-->"):
            continue
        if stripped.startswith(">") or stripped.startswith("---") or stripped.startswith("==="):
            continue
        if stripped.startswith("|") or (stripped.startswith("- ") and len(stripped) < 15):
            continue
        if "http://" in stripped or "https://" in stripped:
            continue
        if len(stripped) < 10:
            continue
        alpha_count = sum(1 for c in stripped if c.isalpha() or c.isalnum())
        if alpha_count < len(stripped) * 0.4:
            continue
        candidates.append(stripped)

    if not candidates:
        return ""

    def _score(value: str) -> int:
        score = 0
        if len(value) >= 20:
            score += 2
        if re.search(
            r"\b(is|are|was|were|has|have|had|do|does|did|will|can|could|should|would|deploy|build|create|make|use|run|show|provide|implement|support|enable|contain|include|represent|describe)\b",
            value,
            re.IGNORECASE,
        ):
            score += 3
        if any(value.endswith(p) for p in (".", "!", "?")):
            score += 1
        return score

    candidates.sort(key=_score, reverse=True)
    best = candidates[0]
    if len(best) > 100:
        cut = best[:100]
        for sep in (". ", "! ", "? "):
            idx = cut.rfind(sep)
            if idx > 20:
                cut = cut[: idx + 1]
                break
        else:
            idx = cut.rfind(" ")
            if idx > 20:
                cut = cut[:idx]
        best = cut.rstrip()
    return best


def log_action(db: sqlite3.Connection, action: str, entity: str = "", detail: str = "") -> None:
    """Log an action to the activity log."""
    db.execute(
        "INSERT INTO activity_log (ts, action, entity, detail) VALUES (?, ?, ?, ?)",
        (time.time(), action, entity, detail),
    )


def append_log(engine, action: str, detail: str = "") -> None:
    """Append chronological entry to log.md."""
    ts = time.strftime("%Y-%m-%d %H:%M")
    entry = f"\n## [{ts}] {action}"
    if detail:
        entry += f" | {detail}"
    entry += "\n"

    if not engine._log_path.exists():
        header = "# Wiki Activity Log\n"
        engine._log_path.parent.mkdir(parents=True, exist_ok=True)
        engine._log_path.write_text(header + entry, encoding="utf-8")
    else:
        current = engine._log_path.read_text(encoding="utf-8")
        engine._log_path.write_text(current + entry, encoding="utf-8")


def get_log_markdown(engine) -> str:
    """Read the log.md file content."""
    if engine._log_path.exists():
        return engine._log_path.read_text(encoding="utf-8")
    return "# Wiki Activity Log\n"
