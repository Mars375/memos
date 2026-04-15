"""Living Wiki — entity/concept-based incremental wiki (Karpathy-inspired).

Extends wiki-compile with living pages organized by entity/concept:
- Pages created by entity/concept (not by tag)
- index.md = auto-generated catalog
- log.md = activity journal (append-only)
- Each ingest/update: update existing pages + lint contradictions
- YAML frontmatter standardized per page type
- Auto-backlinks between pages

Commands:
    memos wiki-living init       — initialize living wiki structure
    memos wiki-living update     — scan memories, update/create pages
    memos wiki-living lint       — detect orphans, contradictions, empty pages
    memos wiki-living index      — regenerate index.md
    memos wiki-living log        — show activity log
    memos wiki-living read <entity> — read a living page
    memos wiki-living search <query> — search across all pages
"""

from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Entity extraction — simple heuristic (no LLM required)
# ---------------------------------------------------------------------------

# Common patterns for entity/concept extraction
_ENTITY_PATTERNS = [
    # Projects: "Project Phoenix"
    (r"\b(Project(?:\s+[A-Z][A-Za-z0-9_-]*)+)\b", "project"),
    # Full names: "Alice Smith"
    (r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", "person"),
    # Single proper names: "Alice", "Bob"
    (r"\b([A-Z][a-z]{2,})\b", "person"),
    # Known concept patterns: "X is Y", "X means Y"
    (r"\b([A-Z][a-z]+(?:\s+[a-z]+){0,2})\s+(?:is|are|means?|refers?\s+to)\b", "concept"),
    # Project/product names with quotes or backticks
    (r"[`\"']([A-Za-z][A-Za-z0-9_-]+)[`\"']", "project"),
    # URLs and domains
    (r"\b(?:https?://|www\.)([a-zA-Z0-9.-]+)", "resource"),
    # Hashtag entities
    (r"#([a-zA-Z][a-zA-Z0-9_-]+)", "topic"),
    # Email-like (local@domain)
    (r"\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b", "contact"),
]

# Stopwords to filter out false-positive entities
_STOPWORDS = {
    "The",
    "This",
    "That",
    "These",
    "Those",
    "There",
    "Then",
    "They",
    "When",
    "Where",
    "What",
    "Which",
    "While",
    "With",
    "From",
    "Into",
    "About",
    "After",
    "Before",
    "Between",
    "Through",
    "During",
    "Without",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
    "First",
    "Second",
    "Third",
    "Last",
    "Next",
    "Each",
    "Every",
    "NOTE",
    "TODO",
    "FIXME",
    "XXX",
    "Use",
    "Read",
    "Write",
    "Scan",
    "Search",
    "List",
    "Stats",
    "Update",
    "Index",
    "Log",
    "Wiki",
    "Project",
}


def extract_entities(text: str) -> List[Tuple[str, str]]:
    """Extract entities from text using heuristic patterns.

    Returns:
        List of (entity_name, entity_type) tuples, deduplicated.
    """
    seen: Set[str] = set()
    entities: List[Tuple[str, str]] = []

    for pattern, etype in _ENTITY_PATTERNS:
        for match in re.finditer(pattern, text):
            name = match.group(1).strip()
            # Filter short/generic names
            if len(name) < 2 or name in _STOPWORDS:
                continue
            key = name.lower()
            if key not in seen:
                seen.add(key)
                entities.append((name, etype))

    return entities


# ---------------------------------------------------------------------------
# Page templates
# ---------------------------------------------------------------------------


def _frontmatter(meta: Dict[str, Any]) -> str:
    """Generate YAML frontmatter block."""
    lines = ["---"]
    for k, v in meta.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            for item in v:
                lines.append(f'  - "{item}"')
        elif isinstance(v, str):
            lines.append(f'{k}: "{v}"')
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines)


_PAGE_TEMPLATES = {
    "person": lambda name, meta: "\n".join(
        [
            _frontmatter(meta),
            "",
            f"# {name}",
            "",
            "## Overview",
            "",
            f"<!-- Auto-generated page for {name}. Update as needed. -->",
            "",
            "## Key Facts",
            "",
            "<!-- Facts extracted from memories appear here. -->",
            "",
        ]
    ),
    "project": lambda name, meta: "\n".join(
        [
            _frontmatter(meta),
            "",
            f"# {name}",
            "",
            "## Overview",
            "",
            f"<!-- Auto-generated page for project: {name}. -->",
            "",
            "## Status",
            "",
            "<!-- Current status and progress. -->",
            "",
            "## Architecture",
            "",
            "<!-- Technical details and decisions. -->",
            "",
        ]
    ),
    "concept": lambda name, meta: "\n".join(
        [
            _frontmatter(meta),
            "",
            f"# {name}",
            "",
            "## Definition",
            "",
            f"<!-- Concept: {name}. -->",
            "",
            "## Related",
            "",
            "<!-- Links to related concepts. -->",
            "",
        ]
    ),
    "topic": lambda name, meta: "\n".join(
        [
            _frontmatter(meta),
            "",
            f"# {name}",
            "",
            "## Summary",
            "",
            f"<!-- Topic: {name}. -->",
            "",
            "## Notes",
            "",
            "<!-- Accumulated notes. -->",
            "",
        ]
    ),
    "resource": lambda name, meta: "\n".join(
        [
            _frontmatter(meta),
            "",
            f"# {name}",
            "",
            "## Details",
            "",
            f"<!-- Resource: {name}. -->",
            "",
        ]
    ),
    "contact": lambda name, meta: "\n".join(
        [
            _frontmatter(meta),
            "",
            f"# {name}",
            "",
            "## Contact Info",
            "",
            f"<!-- Contact: {name}. -->",
            "",
        ]
    ),
    "default": lambda name, meta: "\n".join(
        [
            _frontmatter(meta),
            "",
            f"# {name}",
            "",
            "## Notes",
            "",
            "<!-- Content accumulated from memories. -->",
            "",
        ]
    ),
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class LivingPage:
    """A single living wiki page."""

    entity: str
    entity_type: str
    path: Path
    memory_ids: List[str] = field(default_factory=list)
    backlinks: List[str] = field(default_factory=list)  # entity names
    created_at: float = 0.0
    updated_at: float = 0.0
    size_bytes: int = 0
    is_orphan: bool = False
    has_contradictions: bool = False


@dataclass
class LintReport:
    """Result of linting the living wiki."""

    orphan_pages: List[str] = field(default_factory=list)
    empty_pages: List[str] = field(default_factory=list)
    contradictions: List[Dict[str, Any]] = field(default_factory=list)
    stale_pages: List[str] = field(default_factory=list)  # no update in >30 days
    missing_backlinks: List[Tuple[str, str]] = field(default_factory=list)  # (from, to)


@dataclass
class UpdateResult:
    """Result of a living wiki update."""

    pages_created: int = 0
    pages_updated: int = 0
    entities_found: int = 0
    memories_indexed: int = 0
    backlinks_added: int = 0


# ---------------------------------------------------------------------------
# Living Wiki Engine
# ---------------------------------------------------------------------------


class LivingWikiEngine:
    """Entity/concept-based living wiki with incremental updates."""

    def __init__(self, memos: Any, wiki_dir: Optional[str] = None) -> None:
        self._memos = memos
        if wiki_dir:
            self._wiki_dir = Path(wiki_dir) / "living"
        else:
            persist = getattr(memos, "_persist_path", None)
            if persist:
                self._wiki_dir = Path(persist).parent / "wiki" / "living"
            else:
                self._wiki_dir = Path.home() / ".memos" / "wiki" / "living"

        self._db_path = self._wiki_dir / ".living.db"
        self._index_path = self._wiki_dir / "index.md"
        self._log_path = self._wiki_dir / "log.md"

    def _get_db(self) -> sqlite3.Connection:
        """Get SQLite connection, creating schema if needed."""
        db = sqlite3.connect(str(self._db_path))
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

    def _safe_slug(self, name: str) -> str:
        """Convert entity name to filesystem-safe slug."""
        slug = name.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[\s_]+", "-", slug)
        slug = slug.strip("-")
        return slug or "unnamed"

    def _log_action(self, db: sqlite3.Connection, action: str, entity: str = "", detail: str = "") -> None:
        """Log an action to the activity log."""
        db.execute(
            "INSERT INTO activity_log (ts, action, entity, detail) VALUES (?, ?, ?, ?)",
            (time.time(), action, entity, detail),
        )

    # -- Public API --

    def init(self) -> Dict[str, Any]:
        """Initialize the living wiki structure.

        Returns:
            Summary dict with paths created.
        """
        self._wiki_dir.mkdir(parents=True, exist_ok=True)
        pages_dir = self._wiki_dir / "pages"
        pages_dir.mkdir(exist_ok=True)

        # Init DB
        db = self._get_db()
        db.close()

        # Create index.md
        if not self._index_path.exists():
            self._index_path.write_text(
                "# Living Wiki Index\n\n> Auto-generated catalog of entities and concepts.\n\n<!-- Run: memos wiki-living update -->\n",
                encoding="utf-8",
            )

        # Create log.md
        if not self._log_path.exists():
            self._log_path.write_text(
                "# Living Wiki Activity Log\n\n> Append-only journal of wiki changes.\n\n",
                encoding="utf-8",
            )

        return {
            "initialized": True,
            "wiki_dir": str(self._wiki_dir),
            "pages_dir": str(pages_dir),
            "db": str(self._db_path),
        }

    def update(self, force: bool = False) -> UpdateResult:
        """Scan all memories, extract entities, update/create pages.

        Args:
            force: If True, re-process all memories. If False, only new ones.

        Returns:
            UpdateResult with counts.
        """
        self.init()

        db = self._get_db()
        result = UpdateResult()

        # Get all memories
        store = self._memos._store
        namespace = self._memos._namespace
        all_items = store.list_all(namespace=namespace)
        result.memories_indexed = len(all_items)

        # Track which memory IDs we've already indexed
        if not force:
            existing = set(row[0] for row in db.execute("SELECT memory_id FROM entity_memories").fetchall())
        else:
            existing = set()
            # Clear existing for full rebuild
            db.execute("DELETE FROM entity_memories")
            db.execute("DELETE FROM backlinks")

        # Entity → set of memory IDs (for backlink detection)
        entity_mems: Dict[str, Set[str]] = {}

        for item in all_items:
            if item.id in existing and not force:
                continue

            entities = extract_entities(item.content)

            # Also treat tags as entities
            for tag in item.tags or []:
                entities.append((tag, "topic"))

            for ename, etype in entities:
                entity_mems.setdefault(ename, set()).add(item.id)

                # Ensure entity exists
                row = db.execute("SELECT name FROM entities WHERE name = ?", (ename,)).fetchone()

                if row is None:
                    # Create page
                    slug = self._safe_slug(ename)
                    page_path = self._wiki_dir / "pages" / f"{slug}.md"
                    meta = {
                        "entity": ename,
                        "type": etype,
                        "created": time.strftime("%Y-%m-%d", time.localtime()),
                        "updated": time.strftime("%Y-%m-%d", time.localtime()),
                        "memory_count": 1,
                        "tags": [],
                    }
                    template_fn = _PAGE_TEMPLATES.get(etype, _PAGE_TEMPLATES["default"])
                    page_content = template_fn(ename, meta)
                    page_content += f"\n## Memory Snippet\n\n> {item.content[:200]}\n"
                    page_path.write_text(page_content, encoding="utf-8")

                    db.execute(
                        "INSERT INTO entities (name, entity_type, page_path, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                        (ename, etype, str(page_path), time.time(), time.time()),
                    )
                    self._log_action(db, "create", ename, f"New {etype} page")
                    result.pages_created += 1
                else:
                    # Update existing page — append memory snippet
                    slug = self._safe_slug(ename)
                    page_path = self._wiki_dir / "pages" / f"{slug}.md"
                    if page_path.exists():
                        existing_content = page_path.read_text(encoding="utf-8")
                        snippet = f"\n## Snippet ({time.strftime('%Y-%m-%d %H:%M')})\n\n> {item.content[:200]}\n"

                        # Update frontmatter count
                        existing_content = re.sub(
                            r"memory_count: \d+",
                            lambda m: f"memory_count: {int(m.group().split(': ')[1]) + 1}",
                            existing_content,
                        )
                        existing_content = re.sub(
                            r'updated: "[^"]*"',
                            f'updated: "{time.strftime("%Y-%m-%d")}"',
                            existing_content,
                        )
                        existing_content += snippet
                        page_path.write_text(existing_content, encoding="utf-8")
                    else:
                        # Page file missing, recreate
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

                    db.execute(
                        "UPDATE entities SET updated_at = ? WHERE name = ?",
                        (time.time(), ename),
                    )
                    result.pages_updated += 1

                # Link memory to entity
                db.execute(
                    "INSERT OR IGNORE INTO entity_memories (entity_name, memory_id, snippet, added_at) VALUES (?, ?, ?, ?)",
                    (ename, item.id, item.content[:100], time.time()),
                )

            result.entities_found += len(entities)

        # Build backlinks — if two entities share memories, they link to each other
        all_entities = [row["name"] for row in db.execute("SELECT name FROM entities").fetchall()]
        for i, e1 in enumerate(all_entities):
            for e2 in all_entities[i + 1 :]:
                # Check if they share any memories
                shared = db.execute(
                    "SELECT COUNT(*) FROM entity_memories em1 "
                    "JOIN entity_memories em2 ON em1.memory_id = em2.memory_id "
                    "WHERE em1.entity_name = ? AND em2.entity_name = ?",
                    (e1, e2),
                ).fetchone()[0]
                if shared > 0:
                    db.execute(
                        "INSERT OR IGNORE INTO backlinks (source_entity, target_entity) VALUES (?, ?)",
                        (e1, e2),
                    )
                    db.execute(
                        "INSERT OR IGNORE INTO backlinks (source_entity, target_entity) VALUES (?, ?)",
                        (e2, e1),
                    )
                    result.backlinks_added += 1

        # Update backlink sections in pages
        for ename in all_entities:
            links = [
                row["target_entity"]
                for row in db.execute(
                    "SELECT target_entity FROM backlinks WHERE source_entity = ?", (ename,)
                ).fetchall()
            ]
            if links:
                slug = self._safe_slug(ename)
                page_path = self._wiki_dir / "pages" / f"{slug}.md"
                if page_path.exists():
                    content = page_path.read_text(encoding="utf-8")
                    # Replace or append backlinks section
                    link_lines = (
                        "\n## Backlinks\n\n"
                        + "\n".join(f"- [[{self._safe_slug(line)}|{line}]]" for line in links)
                        + "\n"
                    )
                    if "## Backlinks" in content:
                        content = re.sub(
                            r"## Backlinks\n.*",
                            link_lines,
                            content,
                            flags=re.DOTALL,
                        )
                    else:
                        content += link_lines

                    kg = getattr(self._memos, "_kg", None)
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
                                    f"- [[{self._safe_slug(other)}|{other}]] ({', '.join(sorted(predicates))})"
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

        self._log_action(
            db,
            "update",
            "",
            f"Created {result.pages_created}, updated {result.pages_updated}, "
            f"indexed {result.memories_indexed} memories, {result.backlinks_added} backlinks",
        )

        # Regenerate index
        self._regenerate_index(db)
        # Append to log.md
        self._append_log(db, result)

        db.commit()
        db.close()

        return result

    def update_for_item(self, item: Any) -> UpdateResult:
        """Incrementally update wiki pages for a single newly-learned memory.

        Faster than a full :meth:`update` — only processes the one item.
        Creates or updates entity pages for every entity and tag found in
        *item*.  Skips the item if it was already indexed.

        Parameters
        ----------
        item:
            A :class:`~memos.models.MemoryItem` instance, as returned by
            :meth:`~memos.core.MemOS.learn`.

        Returns
        -------
        :class:`UpdateResult` with counts for this single item.
        """
        self.init()
        db = self._get_db()
        result = UpdateResult()
        result.memories_indexed = 1

        try:
            # Skip if already indexed
            already = db.execute("SELECT COUNT(*) FROM entity_memories WHERE memory_id = ?", (item.id,)).fetchone()[0]
            if already > 0:
                return result

            entities = extract_entities(item.content)
            for tag in item.tags or []:
                entities.append((tag, "topic"))

            for ename, etype in entities:
                row = db.execute("SELECT name FROM entities WHERE name = ?", (ename,)).fetchone()

                slug = self._safe_slug(ename)
                page_path = self._wiki_dir / "pages" / f"{slug}.md"

                if row is None:
                    meta = {
                        "entity": ename,
                        "type": etype,
                        "created": time.strftime("%Y-%m-%d", time.localtime()),
                        "updated": time.strftime("%Y-%m-%d", time.localtime()),
                        "memory_count": 1,
                        "tags": [],
                    }
                    template_fn = _PAGE_TEMPLATES.get(etype, _PAGE_TEMPLATES["default"])
                    page_content = template_fn(ename, meta)
                    page_content += f"\n## Memory Snippet\n\n> {item.content[:200]}\n"
                    page_path.parent.mkdir(parents=True, exist_ok=True)
                    page_path.write_text(page_content, encoding="utf-8")
                    db.execute(
                        "INSERT INTO entities (name, entity_type, page_path, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (ename, etype, str(page_path), time.time(), time.time()),
                    )
                    self._log_action(db, "create", ename, f"New {etype} page (compounding)")
                    result.pages_created += 1
                else:
                    if page_path.exists():
                        existing_content = page_path.read_text(encoding="utf-8")
                        snippet = f"\n## Snippet ({time.strftime('%Y-%m-%d %H:%M')})\n\n> {item.content[:200]}\n"
                        existing_content = re.sub(
                            r"memory_count: \d+",
                            lambda m: f"memory_count: {int(m.group().split(': ')[1]) + 1}",
                            existing_content,
                        )
                        existing_content = re.sub(
                            r'updated: "[^"]*"',
                            f'updated: "{time.strftime("%Y-%m-%d")}"',
                            existing_content,
                        )
                        existing_content += snippet
                        page_path.write_text(existing_content, encoding="utf-8")
                    db.execute(
                        "UPDATE entities SET updated_at = ? WHERE name = ?",
                        (time.time(), ename),
                    )
                    result.pages_updated += 1

                db.execute(
                    "INSERT OR IGNORE INTO entity_memories "
                    "(entity_name, memory_id, snippet, added_at) VALUES (?, ?, ?, ?)",
                    (ename, item.id, item.content[:100], time.time()),
                )

            result.entities_found += len(entities)
            db.commit()
        finally:
            db.close()

        return result

    def lint(self) -> LintReport:
        """Detect orphan pages, contradictions, empty pages, and stale content.

        Returns:
            LintReport with issues found.
        """
        self.init()
        db = self._get_db()
        report = LintReport()

        pages_dir = self._wiki_dir / "pages"
        if not pages_dir.exists():
            db.close()
            return report

        now = time.time()
        thirty_days = 30 * 86400

        all_entities = {
            row["name"]: dict(row)
            for row in db.execute("SELECT name, entity_type, page_path, updated_at FROM entities").fetchall()
        }

        # Get all memory IDs currently in store
        store = self._memos._store
        namespace = self._memos._namespace
        all_mem_ids = {item.id for item in store.list_all(namespace=namespace)}

        for ename, edata in all_entities.items():
            slug = self._safe_slug(ename)
            page_path = pages_dir / f"{slug}.md"

            # Orphan: entity with no memories in current store
            mem_ids = [
                row["memory_id"]
                for row in db.execute(
                    "SELECT memory_id FROM entity_memories WHERE entity_name = ?", (ename,)
                ).fetchall()
            ]
            active_mems = [m for m in mem_ids if m in all_mem_ids]
            if not active_mems:
                report.orphan_pages.append(ename)

            # Empty: page file is mostly template (very small)
            if page_path.exists():
                content = page_path.read_text(encoding="utf-8")
                # Count non-template lines (not comments, not frontmatter)
                real_lines = [
                    line
                    for line in content.splitlines()
                    if line.strip()
                    and not line.strip().startswith("<!--")
                    and not line.strip().startswith("---")
                    and not line.startswith("# ")
                    and not line.startswith("## ")
                ]
                if len(real_lines) < 3:
                    report.empty_pages.append(ename)
            else:
                report.empty_pages.append(ename)

            # Stale: not updated in 30 days
            if edata["updated_at"] and (now - edata["updated_at"]) > thirty_days:
                report.stale_pages.append(ename)

        # Simple contradiction detection: memories with opposing sentiment on same entity
        for ename in all_entities:
            mem_contents = []
            for row in db.execute(
                "SELECT em.snippet FROM entity_memories em WHERE em.entity_name = ?",
                (ename,),
            ).fetchall():
                mem_contents.append(row["snippet"])

            # Look for contradiction patterns (X is Y vs X is not Y)
            negated = set()
            affirmed = set()
            for snippet in mem_contents:
                # Simple: "not X" vs "X"
                neg_matches = re.findall(r"not\s+(\w+)", snippet.lower())
                negated.update(neg_matches)
                pos_matches = re.findall(r"\bis\s+(\w+)", snippet.lower())
                affirmed.update(pos_matches)

            conflicts = negated & affirmed
            if conflicts:
                report.contradictions.append(
                    {
                        "entity": ename,
                        "conflicting_terms": list(conflicts),
                    }
                )

        # Missing backlinks: if page A mentions entity B but no backlink exists
        for ename in all_entities:
            slug = self._safe_slug(ename)
            page_path = pages_dir / f"{slug}.md"
            if not page_path.exists():
                continue
            content = page_path.read_text(encoding="utf-8")

            # Find entities mentioned in content
            mentioned = extract_entities(content)
            for mentioned_name, _ in mentioned:
                if mentioned_name in all_entities and mentioned_name != ename:
                    # Check if backlink exists
                    has_link = db.execute(
                        "SELECT 1 FROM backlinks WHERE source_entity = ? AND target_entity = ?",
                        (ename, mentioned_name),
                    ).fetchone()
                    if not has_link:
                        report.missing_backlinks.append((ename, mentioned_name))

        db.close()
        return report

    def regenerate_index(self) -> str:
        """Regenerate the index.md catalog page."""
        self.init()
        db = self._get_db()
        content = self._regenerate_index(db)
        db.close()
        return content

    def _regenerate_index(self, db: sqlite3.Connection) -> str:
        """Internal: regenerate index.md from DB."""
        entities = db.execute("SELECT name, entity_type, updated_at FROM entities ORDER BY name").fetchall()

        lines = [
            "# Living Wiki Index\n",
            f"> {len(entities)} entities · Updated {time.strftime('%Y-%m-%d %H:%M')}\n",
            "",
        ]

        # Group by type
        by_type: Dict[str, List[Any]] = {}
        for row in entities:
            by_type.setdefault(row["entity_type"], []).append(row)

        for etype, items in sorted(by_type.items()):
            lines.append(f"## {etype.title()} ({len(items)})\n")
            for item in items:
                slug = self._safe_slug(item["name"])
                age = ""
                if item["updated_at"]:
                    delta = time.time() - item["updated_at"]
                    if delta < 86400:
                        age = " 🟢"
                    elif delta < 7 * 86400:
                        age = " 🟡"
                    else:
                        age = " 🔴"
                lines.append(f"- [[pages/{slug}|{item['name']}]]{age}")
            lines.append("")

        content = "\n".join(lines)
        self._index_path.write_text(content, encoding="utf-8")
        return content

    def _append_log(self, db: sqlite3.Connection, result: UpdateResult) -> None:
        """Append update summary to log.md."""
        ts = time.strftime("%Y-%m-%d %H:%M")
        entry = (
            f"\n## {ts} — Update\n\n"
            f"- Pages created: {result.pages_created}\n"
            f"- Pages updated: {result.pages_updated}\n"
            f"- Entities found: {result.entities_found}\n"
            f"- Memories indexed: {result.memories_indexed}\n"
            f"- Backlinks added: {result.backlinks_added}\n"
        )

        current = ""
        if self._log_path.exists():
            current = self._log_path.read_text(encoding="utf-8")
        current += entry
        self._log_path.write_text(current, encoding="utf-8")

    def read_page(self, entity: str) -> Optional[str]:
        """Read a living wiki page by entity name."""
        slug = self._safe_slug(entity)
        page_path = self._wiki_dir / "pages" / f"{slug}.md"
        if page_path.exists():
            return page_path.read_text(encoding="utf-8")

        # Fuzzy: check DB for matching entity
        db = self._get_db()
        row = db.execute(
            "SELECT page_path FROM entities WHERE name LIKE ?",
            (f"%{entity}%",),
        ).fetchone()
        db.close()

        if row:
            p = Path(row["page_path"])
            if p.exists():
                return p.read_text(encoding="utf-8")
        return None

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search across all living wiki pages.

        Returns:
            List of dicts with entity, type, matches, snippet.
        """
        self.init()
        db = self._get_db()
        results: List[Dict[str, Any]] = []
        query_lower = query.lower()

        pages_dir = self._wiki_dir / "pages"
        if not pages_dir.exists():
            db.close()
            return results

        for page_file in pages_dir.glob("*.md"):
            content = page_file.read_text(encoding="utf-8")
            # Count matches
            matches = content.lower().count(query_lower)
            if matches > 0:
                # Extract entity from frontmatter or filename
                entity = page_file.stem.replace("-", " ")
                etype = "default"
                fm_match = re.search(r'entity:\s*"([^"]+)"', content)
                if fm_match:
                    entity = fm_match.group(1)
                type_match = re.search(r'type:\s*"([^"]+)"', content)
                if type_match:
                    etype = type_match.group(1)

                # Extract snippet around first match
                idx = content.lower().find(query_lower)
                start = max(0, idx - 60)
                end = min(len(content), idx + len(query) + 60)
                snippet = content[start:end].replace("\n", " ")

                results.append(
                    {
                        "entity": entity,
                        "type": etype,
                        "matches": matches,
                        "snippet": snippet,
                    }
                )

        db.close()
        results.sort(key=lambda x: -x["matches"])
        return results

    def get_log(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Read activity log entries.

        Returns:
            List of log entries (newest first).
        """
        self.init()
        db = self._get_db()
        rows = db.execute(
            "SELECT ts, action, entity, detail FROM activity_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
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

    def list_pages(self) -> List[LivingPage]:
        """List all living wiki pages with metadata."""
        self.init()
        db = self._get_db()
        pages: List[LivingPage] = []

        for row in db.execute(
            "SELECT name, entity_type, page_path, created_at, updated_at FROM entities ORDER BY name"
        ).fetchall():
            slug = self._safe_slug(row["name"])
            page_path = self._wiki_dir / "pages" / f"{slug}.md"

            mem_ids = [
                r["memory_id"]
                for r in db.execute(
                    "SELECT memory_id FROM entity_memories WHERE entity_name = ?",
                    (row["name"],),
                ).fetchall()
            ]

            backlinks = [
                r["target_entity"]
                for r in db.execute(
                    "SELECT target_entity FROM backlinks WHERE source_entity = ?",
                    (row["name"],),
                ).fetchall()
            ]

            size = page_path.stat().st_size if page_path.exists() else 0

            pages.append(
                LivingPage(
                    entity=row["name"],
                    entity_type=row["entity_type"],
                    path=page_path,
                    memory_ids=mem_ids,
                    backlinks=backlinks,
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    size_bytes=size,
                )
            )

        db.close()
        return pages

    def stats(self) -> Dict[str, Any]:
        """Get living wiki statistics."""
        self.init()
        db = self._get_db()

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
            "wiki_dir": str(self._wiki_dir),
        }
