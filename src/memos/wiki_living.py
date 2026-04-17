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
STOP_WORDS: Set[str] = {
    # --- Common English stop words (Title-case variants) ---
    "The", "This", "That", "These", "Those", "There", "Then", "They",
    "When", "Where", "What", "Which", "While", "With", "From", "Into",
    "About", "After", "Before", "Between", "Through", "During", "Without",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
    "Saturday", "Sunday",
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
    "First", "Second", "Third", "Last", "Next", "Each", "Every",
    # --- Common English stop words (lowercase) ---
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "of", "in", "on", "at", "to", "for", "and", "or", "but", "not",
    "with", "by", "from", "as", "into", "through", "during", "before",
    "after", "above", "below", "between", "under", "over", "again",
    "further", "then", "once", "here", "there", "when", "where", "why",
    "how", "all", "each", "every", "both", "few", "more", "most",
    "other", "some", "such", "no", "nor", "only", "own", "same", "so",
    "than", "too", "very", "can", "will", "just", "should", "now",
    "also", "any", "its", "it", "he", "she", "we", "they", "you",
    "me", "my", "your", "his", "her", "our", "their", "them",
    "what", "which", "who", "whom", "this", "that", "these", "those",
    "if", "else", "about", "up", "out", "off", "down",
    # --- Programming keywords / Python builtins ---
    "str", "dict", "type", "int", "float", "bool", "list", "set", "tuple",
    "None", "True", "False", "class", "def", "return", "import", "from",
    "object", "bytes", "bytearray", "frozenset", "complex", "memoryview",
    "range", "enumerate", "zip", "map", "filter", "sorted", "reversed",
    "iter", "next", "len", "max", "min", "sum", "abs", "round", "pow",
    "hash", "id", "isinstance", "issubclass", "callable", "hasattr",
    "getattr", "setattr", "delattr", "property", "staticmethod",
    "classmethod", "super", "self", "cls", "lambda", "yield", "async",
    "await", "try", "except", "finally", "raise", "assert", "with",
    "pass", "break", "continue", "global", "nonlocal", "del", "and",
    "or", "not", "in", "is", "while", "for",
    "True", "False", "None",
    "Exception", "ValueError", "TypeError", "KeyError", "IndexError",
    "AttributeError", "RuntimeError", "StopIteration",
    "Value", "Key", "Index", "Error",
    # --- HTTP / URL fragments ---
    "http", "https", "www", "com", "org", "io", "net", "dev", "app",
    "url", "uri", "api", "endpoint",
    # --- API doc noise ---
    "parameter", "parameters", "returns", "raises", "example", "note",
    "see", "also", "description", "arguments", "args", "kwargs",
    "param", "return", "raise", "throw", "throws", "exception",
    "deprecated", "version", "since", "todo", "fixme", "warning",
    "WARNING", "NOTE", "TODO", "FIXME", "XXX",
    "Parameter", "Parameters", "Returns", "Raises", "Example", "Note",
    "See", "Also", "Description", "Arguments",
    # --- Generic noise words (from API docs / READMEs) ---
    "Best", "General", "Same", "Augmenting", "Answers", "Any",
    "Discovery", "Function", "Method", "Module", "Package",
    "Class", "Instance", "Variable", "Constant", "Attribute",
    "Property", "Field", "Element", "Item", "Value", "Result",
    "Output", "Input", "Source", "Target", "Default", "Custom",
    "New", "Old", "Current", "Local", "Global", "Static",
    "Public", "Private", "Internal", "External",
    "Use", "Read", "Write", "Scan", "Search", "List",
    "Stats", "Update", "Index", "Log", "Wiki", "Project",
    "Add", "Remove", "Delete", "Create", "Get", "Set",
    "Name", "Type", "Data", "Info", "Config", "Option",
    "True", "False",
    # --- MCP / server noise ---
    "mcp", "servers", "server", "client", "handler", "middleware",
    "MCP", "Servers", "Server", "Client",
    # --- Short generic words that are noise ---
    "get", "set", "put", "post", "delete", "patch", "head",
    "run", "run", "try", "let", "var", "const",
}

# Python builtins for additional filtering
_PYTHON_BUILTINS = frozenset(dir(__builtins__)) if isinstance(__builtins__, dict) else frozenset(dir(__builtins__))

# Backwards-compatible alias
_STOPWORDS = STOP_WORDS


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

            # --- Minimum quality rules ---
            # Must be at least 2 characters
            if len(name) < 2:
                continue

            # Must contain at least one letter
            if not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", name):
                continue

            # Reject single-character entities
            if len(name) == 1:
                continue

            key = name.lower()

            # Reject all-lowercase entities shorter than 4 characters
            # (short lowercase words are almost always noise from code/docs)
            if name.islower() and len(name) < 4:
                continue

            # Check stop-words (case-insensitive)
            if key in _STOPWORDS or name in _STOPWORDS:
                continue

            # Reject Python builtin names (case-insensitive)
            if key in _PYTHON_BUILTINS:
                continue

            if key not in seen:
                seen.add(key)
                entities.append((name, etype))

    return entities


# ---------------------------------------------------------------------------
# Page templates
# ---------------------------------------------------------------------------


def _frontmatter(meta: Dict[str, Any]) -> str:
    """Generate Obsidian-compatible YAML frontmatter block.

    Maps internal meta keys to Obsidian-compatible field names:
      entity → title, type → type, tags → tags,
      created → created, updated → updated, memory_count → sources
    """
    title = meta.get("entity", meta.get("title", "Untitled"))
    page_type = meta.get("type", "default")
    tags_list = meta.get("tags", [])
    if isinstance(tags_list, list) and tags_list:
        tags_str = ", ".join(str(t) for t in tags_list)
    else:
        tags_str = "auto, entity"
    created = meta.get("created", time.strftime("%Y-%m-%d"))
    updated = meta.get("updated", time.strftime("%Y-%m-%d"))
    sources = meta.get("memory_count", meta.get("sources", 0))

    lines = [
        "---",
        f'title: "{title}"',
        f"type: {page_type}",
        f"tags: [{tags_str}]",
        f"created: {created}",
        f"updated: {updated}",
        f"sources: {sources}",
        "---",
    ]
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
    _slug_cache: Optional[str] = field(default=None, repr=False)

    @property
    def slug(self) -> str:
        """Filesystem-safe slug for this page (derived from entity name)."""
        if self._slug_cache is not None:
            return self._slug_cache
        import re as _re

        slug = self.entity.lower().strip()
        slug = _re.sub(r"[^\w\s-]", "", slug)
        slug = _re.sub(r"[\s_]+", "-", slug)
        slug = slug.strip("-")
        self._slug_cache = slug or "unnamed"
        return self._slug_cache

    @property
    def memory_count(self) -> int:
        """Number of memories linked to this page."""
        return len(self.memory_ids)


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
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
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

    def _get_page_summary(self, entity_name: str) -> str:
        """Extract a one-line summary from a wiki page.

        Scans the page content for the best non-junk line: skips frontmatter,
        headings, blockquotes, code fences, URLs, short/punctuation-only lines,
        and prefers natural-language sentences.  Returns up to 100 chars,
        truncated at a sentence boundary.
        """
        slug = self._safe_slug(entity_name)
        page_path = self._wiki_dir / "pages" / f"{slug}.md"
        if not page_path.exists():
            return ""
        content = page_path.read_text(encoding="utf-8")

        # Collect candidate lines — we prefer longer / sentence-like ones.
        candidates: list[str] = []
        in_frontmatter = False
        in_code_fence = False

        for line in content.splitlines():
            stripped = line.strip()

            # --- frontmatter toggle ---
            if stripped == "---" and not in_code_fence:
                in_frontmatter = not in_frontmatter
                continue
            if in_frontmatter:
                continue

            # --- code fence toggle ---
            if stripped.startswith("```"):
                in_code_fence = not in_code_fence
                continue
            if in_code_fence:
                continue

            # --- skip structural / noise lines ---
            if not stripped:
                continue
            if stripped.startswith("#"):
                continue
            if stripped.startswith("<!--") or stripped.startswith("-->"):
                continue
            if stripped.startswith(">"):
                continue
            if stripped.startswith("---") or stripped.startswith("==="):
                continue
            if stripped.startswith("|") or (stripped.startswith("- ") and len(stripped) < 15):
                continue
            if "http://" in stripped or "https://" in stripped:
                continue

            # --- quality filters ---
            # Skip very short lines (< 10 chars)
            if len(stripped) < 10:
                continue
            # Skip lines that are mostly punctuation / symbols
            alpha_count = sum(1 for c in stripped if c.isalpha() or c.isalnum())
            if alpha_count < len(stripped) * 0.4:
                continue

            candidates.append(stripped)

        if not candidates:
            return ""

        # Pick the best candidate: prefer lines with sentence-ending
        # punctuation and >= 20 chars (more likely natural language).
        def _score(s: str) -> int:
            sc = 0
            if len(s) >= 20:
                sc += 2
            if re.search(r"\b(is|are|was|were|has|have|had|do|does|did|will|can|could|should|would|deploy|build|create|make|use|run|show|provide|implement|support|enable|contain|include|represent|describe)\b", s, re.IGNORECASE):
                sc += 3
            if any(s.endswith(p) for p in (".", "!", "?")):
                sc += 1
            return sc

        candidates.sort(key=_score, reverse=True)
        best = candidates[0]

        # Trim to 100 chars, breaking at sentence boundary
        if len(best) > 100:
            # Try to cut at last sentence-ending punctuation before 100
            cut = best[:100]
            for sep in (". ", "! ", "? "):
                idx = cut.rfind(sep)
                if idx > 20:
                    cut = cut[: idx + 1]
                    break
            else:
                # Fall back to last space
                idx = cut.rfind(" ")
                if idx > 20:
                    cut = cut[:idx]
            best = cut.rstrip()

        return best

    def _frontmatter(self, page) -> str:
        """Generate Obsidian-compatible YAML frontmatter for a page object.

        Works with ``LivingPage`` instances or any object exposing
        ``entity``/``title``, ``entity_type``, ``tags``, ``created_at``/``created``,
        and ``memory_ids`` attributes.
        """
        import datetime

        # Title: prefer .title, fall back to .entity
        title = getattr(page, "title", None) or getattr(page, "entity", "Untitled")

        # Entity type
        entity_type = getattr(page, "entity_type", "default")

        # Tags
        page_tags = getattr(page, "tags", None)
        if page_tags:
            tags = ", ".join(str(t) for t in page_tags)
        else:
            tags = "auto, entity"

        # Created date
        created_ts = getattr(page, "created", None) or getattr(page, "created_at", None)
        if created_ts:
            created = datetime.datetime.fromtimestamp(created_ts).strftime("%Y-%m-%d")
        else:
            created = datetime.datetime.now().strftime("%Y-%m-%d")

        updated = datetime.datetime.now().strftime("%Y-%m-%d")

        # Source count
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
                "# Wiki Activity Log\n\n> Append-only journal of wiki changes.\n\n",
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

                        # Update frontmatter sources count
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
        self._append_log(
            "update",
            f"Created {result.pages_created}, updated {result.pages_updated}, "
            f"indexed {result.memories_indexed} memories, {result.backlinks_added} backlinks",
        )

        db.commit()
        db.close()

        return result

    def update_for_item(self, item: Any) -> UpdateResult:
        """Incrementally update wiki pages for a single newly-learned memory.

        Faster than a full :meth:`update` — only processes the one item.
        Creates or updates entity pages for every entity and tag found in
        *item*.  Skips the item if it was already indexed.

        After creating/updating the main entity pages, cascades updates to
        all mentioned entities via :meth:`_refresh_entity_page` and builds
        bidirectional cross-references via :meth:`_update_cross_references`.

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

            entity_names: List[str] = []

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
                            r"sources: \d+",
                            lambda m: f"sources: {int(m.group().split(': ')[1]) + 1}",
                            existing_content,
                        )
                        existing_content = re.sub(
                            r"updated: \d{4}-\d{2}-\d{2}",
                            f"updated: {time.strftime('%Y-%m-%d')}",
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
                entity_names.append(ename)

            result.entities_found += len(entities)

            # ── Cascading updates ─────────────────────────────────
            # Refresh every secondary entity page with the new context
            for ename in entity_names:
                self._refresh_entity_page(ename, trigger=item.id, db=db)

            # Add bidirectional cross-references between co-mentioned entities
            self._update_cross_references(entity_names, db=db)

            db.commit()
            # Regenerate index after single-item update
            self._regenerate_index(db)
            self._append_log(
                "update_for_item",
                f"Created {result.pages_created}, updated {result.pages_updated}, "
                f"found {result.entities_found} entities",
            )
        finally:
            db.close()

        return result

    def _refresh_entity_page(
        self, entity: str, trigger: str | None = None, db: sqlite3.Connection | None = None
    ) -> None:
        """Refresh a single entity's wiki page with current context.

        Updates the page with any new graph neighbor information and
        records the refresh in the activity log.

        Parameters
        ----------
        entity:
            The entity name whose page should be refreshed.
        trigger:
            Optional memory ID that triggered this refresh, used for
            logging and provenance tracking.
        db:
            Optional existing DB connection (avoids lock contention).
        """
        slug = self._safe_slug(entity)
        page_path = self._wiki_dir / "pages" / f"{slug}.md"
        if not page_path.exists():
            return

        own_db = db is None
        if own_db:
            db = self._get_db()

        try:
            # Verify the entity exists in the DB
            row = db.execute("SELECT name FROM entities WHERE name = ?", (entity,)).fetchone()
            if row is None:
                return

            content = page_path.read_text(encoding="utf-8")

            # Update the frontmatter updated timestamp
            content = re.sub(
                r"updated: \d{4}-\d{2}-\d{2}",
                f"updated: {time.strftime('%Y-%m-%d')}",
                content,
            )

            # Append a "Related Context" section noting the trigger
            if trigger:
                trigger_note = f"\n## Related Context\n\n> Triggered by memory `{trigger}`\n"
                # Only add if not already present for this trigger
                if trigger not in content:
                    content += trigger_note

            # Update graph neighbors section
            kg = getattr(self._memos, "_kg", None)
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
            db.execute("UPDATE entities SET updated_at = ? WHERE name = ?", (time.time(), entity))

            detail = f"Refreshed page (trigger: {trigger})" if trigger else "Refreshed page"
            self._log_action(db, "refresh", entity, detail)
            if own_db:
                db.commit()
        finally:
            if own_db:
                db.close()

    def _update_cross_references(
        self,
        entities: List[str],
        db: sqlite3.Connection | None = None,
    ) -> int:
        """Add bidirectional backlinks between related entity pages.

        For every pair of entities in the list, creates backlinks in both
        directions if they don't already exist, and appends ``[[wikilinks]]``
        to the page content.

        Parameters
        ----------
        entities:
            List of entity names to cross-reference.
        db:
            Optional existing DB connection (avoids re-opening).

        Returns
        -------
        Number of new backlinks added.
        """
        if len(entities) < 2:
            return 0

        own_db = db is None
        if own_db:
            db = self._get_db()

        added = 0
        try:
            for i, e1 in enumerate(entities):
                for e2 in entities[i + 1 :]:
                    # Bidirectional backlinks
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

                            # Append wikilink to source page
                            slug = self._safe_slug(src)
                            page_path = self._wiki_dir / "pages" / f"{slug}.md"
                            if page_path.exists():
                                content = page_path.read_text(encoding="utf-8")
                                link_line = f"- [[{self._safe_slug(tgt)}|{tgt}]]"
                                # Check if already present in content
                                if link_line not in content:
                                    if "## Backlinks" in content:
                                        # Append to existing backlinks section
                                        content = content.replace(
                                            "## Backlinks\n",
                                            f"## Backlinks\n\n{link_line}\n",
                                            1,
                                        )
                                    else:
                                        content += f"\n## Backlinks\n\n{link_line}\n"
                                    page_path.write_text(content, encoding="utf-8")
            if own_db:
                db.commit()
        finally:
            if own_db:
                db.close()

        return added

    def lint(self) -> LintReport:
        """Detect orphan pages, contradictions, empty pages, and stale content.

        Returns:
            LintReport with issues found.
        """
        structured = self.lint_report()
        report = LintReport()
        for issue in structured["issues"]:
            t = issue["type"]
            if t == "orphan":
                report.orphan_pages.append(issue["page"])
            elif t == "empty":
                report.empty_pages.append(issue["page"])
            elif t == "contradiction":
                report.contradictions.append(
                    {"entity": issue["page"], "conflicting_terms": issue.get("conflicting_terms", [])}
                )
            elif t == "stale":
                report.stale_pages.append(issue["page"])
            elif t == "missing_ref":
                report.missing_backlinks.append((issue["page"], issue.get("target", "")))
        return report

    def lint_report(self) -> Dict[str, Any]:
        """Comprehensive wiki health-check (Karpathy-inspired lint).

        Checks for:
        - **Orphan pages**: pages with no inbound links from other pages
        - **Missing cross-references**: entity mentioned in a page but no [[link]]
        - **Stale pages**: pages not updated in >30 days
        - **Empty pages**: pages with no content (just a title)
        - **Contradictions**: same entity has conflicting info on different pages

        Returns:
            Structured report dict with ``issues`` list and ``summary`` counts.
        """
        self.init()
        db = self._get_db()

        issues: List[Dict[str, Any]] = []

        pages_dir = self._wiki_dir / "pages"
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

        # ── Build inbound-link map ────────────────────────────────
        inbound: Dict[str, Set[str]] = {name: set() for name in all_entities}
        for row in db.execute("SELECT source_entity, target_entity FROM backlinks").fetchall():
            tgt = row["target_entity"]
            if tgt in inbound:
                inbound[tgt].add(row["source_entity"])

        # all memory IDs available for cross-reference checks

        # ── Per-page checks ───────────────────────────────────────
        for ename, edata in all_entities.items():
            slug = self._safe_slug(ename)
            page_path = pages_dir / f"{slug}.md"

            # -- Orphan: no inbound links from other pages --
            if not inbound.get(ename):
                issues.append({"type": "orphan", "severity": "warning", "page": ename, "detail": "No inbound links"})

            # -- Empty: page file is mostly template --
            if page_path.exists():
                content = page_path.read_text(encoding="utf-8")
                # Count non-template lines, skipping frontmatter
                in_fm = False
                real_lines: List[str] = []
                for line in content.splitlines():
                    stripped = line.strip()
                    if stripped == "---":
                        in_fm = not in_fm
                        continue
                    if in_fm:
                        continue
                    if (
                        stripped
                        and not stripped.startswith("<!--")
                        and not stripped.startswith("# ")
                        and not stripped.startswith("## ")
                    ):
                        real_lines.append(stripped)
                if len(real_lines) < 3:
                    issues.append(
                        {"type": "empty", "severity": "warning", "page": ename, "detail": "Page has no real content"}
                    )
            else:
                issues.append({"type": "empty", "severity": "warning", "page": ename, "detail": "Page file missing"})

            # -- Stale: not updated in 30 days --
            if edata["updated_at"] and (now - edata["updated_at"]) > thirty_days:
                days_stale = int((now - edata["updated_at"]) / 86400)
                issues.append(
                    {
                        "type": "stale",
                        "severity": "info",
                        "page": ename,
                        "detail": f"Not updated in {days_stale} days",
                    }
                )

        # ── Contradiction detection ───────────────────────────────
        for ename in all_entities:
            mem_contents: List[str] = []
            for row in db.execute(
                "SELECT em.snippet FROM entity_memories em WHERE em.entity_name = ?",
                (ename,),
            ).fetchall():
                mem_contents.append(row["snippet"])

            # Look for contradiction patterns (X is Y vs X is not Y)
            negated: Set[str] = set()
            affirmed: Set[str] = set()
            for snippet in mem_contents:
                neg_matches = re.findall(r"not\s+(\w+)", snippet.lower())
                negated.update(neg_matches)
                pos_matches = re.findall(r"\bis\s+(\w+)", snippet.lower())
                affirmed.update(pos_matches)

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

        # ── Missing cross-references ──────────────────────────────
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
                    # Check if [[link]] exists in the page content
                    link_patterns = [
                        f"[[{self._safe_slug(mentioned_name)}",
                        f"[[{mentioned_name}",
                    ]
                    has_link = any(pat in content for pat in link_patterns)
                    if not has_link:
                        issues.append(
                            {
                                "type": "missing_ref",
                                "severity": "info",
                                "page": ename,
                                "detail": f"Mentions '{mentioned_name}' but no link",
                                "target": mentioned_name,
                            }
                        )

        # ── Build summary ─────────────────────────────────────────
        orphan_count = sum(1 for i in issues if i["type"] == "orphan")
        missing_ref_count = sum(1 for i in issues if i["type"] == "missing_ref")
        stale_count = sum(1 for i in issues if i["type"] == "stale")
        empty_count = sum(1 for i in issues if i["type"] == "empty")
        contradiction_count = sum(1 for i in issues if i["type"] == "contradiction")

        self._append_log(
            "lint",
            f"Orphans: {orphan_count}, Empty: {empty_count}, "
            f"Contradictions: {contradiction_count}, "
            f"Missing refs: {missing_ref_count}, Stale: {stale_count}",
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

    def generate_index(self) -> str:
        """Generate index.md — all wiki pages grouped by entity_type.

        Lists every wiki page with ``[[wikilinks]]`` and one-line summaries,
        grouped by entity_type (mapped to Karpathy-style categories).
        Writes the result to ``wiki_dir / index.md`` and returns the markdown
        content.
        """
        self.init()
        db = self._get_db()
        content = self._regenerate_index(db)
        db.close()
        return content

    # Alias for backward compatibility
    regenerate_index = generate_index

    def _regenerate_index(self, db: sqlite3.Connection) -> str:
        """Internal: regenerate index.md from DB (Karpathy-style).

        Produces a rich index with:
        - Statistics section at top
        - Recent Changes section
        - Pages grouped by category (Entities, Concepts, Sources, Topics)
        - Each page with [[wiki-link]], one-line summary, and metadata
        - Sorted by relevance (most linked first, then by recency)
        """
        now = time.time()
        now_fmt = time.strftime("%Y-%m-%d %H:%M", time.localtime(now))

        # ── Gather data ──────────────────────────────────────────
        entities = db.execute("SELECT name, entity_type, page_path, created_at, updated_at FROM entities").fetchall()

        # Count backlinks per entity (incoming links = relevance signal)
        backlink_counts: Dict[str, int] = {}
        for row in db.execute("SELECT target_entity, COUNT(*) as cnt FROM backlinks GROUP BY target_entity").fetchall():
            backlink_counts[row["target_entity"]] = row["cnt"]

        # Count memory sources per entity
        source_counts: Dict[str, int] = {}
        for row in db.execute(
            "SELECT entity_name, COUNT(*) as cnt FROM entity_memories GROUP BY entity_name"
        ).fetchall():
            source_counts[row["entity_name"]] = row["cnt"]

        # Count total backlinks
        total_backlinks = db.execute("SELECT COUNT(*) FROM backlinks").fetchone()[0]
        total_memory_links = db.execute("SELECT COUNT(*) FROM entity_memories").fetchone()[0]

        # ── Map entity_type → Karpathy category ──────────────────
        _CATEGORY_MAP = {
            "person": "Entities",
            "contact": "Entities",
            "project": "Entities",
            "concept": "Concepts",
            "topic": "Topics",
            "resource": "Sources",
            "default": "Concepts",
        }

        # ── Sort by relevance (most linked → most recent) ────────
        def _sort_key(row):
            bl = backlink_counts.get(row["name"], 0)
            updated = row["updated_at"] or 0
            return (-bl, -updated)

        sorted_entities = sorted(entities, key=_sort_key)

        # ── Group by category ────────────────────────────────────
        categories: Dict[str, List[Any]] = {
            "Entities": [],
            "Concepts": [],
            "Sources": [],
            "Topics": [],
        }
        uncategorized: List[Any] = []

        for row in sorted_entities:
            cat = _CATEGORY_MAP.get(row["entity_type"])
            if cat and cat in categories:
                categories[cat].append(row)
            else:
                uncategorized.append(row)

        # If there are uncategorized entities, put them under Concepts
        if uncategorized:
            categories["Concepts"].extend(uncategorized)

        # ── Build index content ───────────────────────────────────
        lines: List[str] = []
        lines.append("# 📚 Living Wiki Index\n")
        lines.append("> Auto-generated Karpathy-style catalog of entities and concepts.\n")

        # ── Statistics Section ────────────────────────────────────
        lines.append("")
        lines.append("## 📊 Statistics\n")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total Pages | {len(entities)} |")
        lines.append(f"| Total Memory Links | {total_memory_links} |")
        lines.append(f"| Total Wiki Links | {total_backlinks} |")
        lines.append(f"| Last Updated | {now_fmt} |")
        lines.append("")

        # ── Recent Changes Section ────────────────────────────────
        recent = db.execute("SELECT ts, action, entity, detail FROM activity_log ORDER BY id DESC LIMIT 10").fetchall()
        if recent:
            lines.append("## 🕐 Recent Changes\n")
            lines.append("")
            for entry in recent:
                ts_fmt = time.strftime("%Y-%m-%d %H:%M", time.localtime(entry["ts"]))
                action = entry["action"]
                entity = entry["entity"]
                detail = entry["detail"]
                entity_slug = self._safe_slug(entity) if entity else ""
                entity_link = f"[[{entity_slug}|{entity}]]" if entity else ""
                lines.append(f"- `{ts_fmt}` **{action}** {entity_link} — {detail}")
            lines.append("")

        # ── Category Sections ─────────────────────────────────────
        for cat_name, items in categories.items():
            if not items:
                continue
            lines.append(f"## {cat_name} ({len(items)})\n")
            lines.append("")
            for item in items:
                slug = self._safe_slug(item["name"])
                summary = self._get_page_summary(item["name"])
                created_date = (
                    time.strftime("%Y-%m-%d", time.localtime(item["created_at"])) if item["created_at"] else "N/A"
                )
                src_count = source_counts.get(item["name"], 0)
                updated_date = (
                    time.strftime("%Y-%m-%d", time.localtime(item["updated_at"])) if item["updated_at"] else "N/A"
                )

                # Freshness indicator
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
        self._index_path.write_text(content, encoding="utf-8")
        return content

    def _append_log(self, action: str, detail: str = "") -> None:
        """Append chronological entry to log.md.

        Format: ``## [YYYY-MM-DD HH:MM] action | detail``
        Creates log.md with header ``# Wiki Activity Log`` if it does not exist.
        """
        ts = time.strftime("%Y-%m-%d %H:%M")
        entry = f"\n## [{ts}] {action}"
        if detail:
            entry += f" | {detail}"
        entry += "\n"

        if not self._log_path.exists():
            header = "# Wiki Activity Log\n"
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log_path.write_text(header + entry, encoding="utf-8")
        else:
            current = self._log_path.read_text(encoding="utf-8")
            current += entry
            self._log_path.write_text(current, encoding="utf-8")

    def get_log_markdown(self) -> str:
        """Read the log.md file content.

        Returns the header ``# Wiki Activity Log`` if the file does not exist.
        """
        if self._log_path.exists():
            return self._log_path.read_text(encoding="utf-8")
        return "# Wiki Activity Log\n"

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
                fm_match = re.search(r'title:\s*"([^"]+)"', content)
                if fm_match:
                    entity = fm_match.group(1)
                type_match = re.search(r"type:\s*(\w+)", content)
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

    def create_page(
        self,
        entity: str,
        entity_type: str = "default",
        content: str = "",
    ) -> Dict[str, Any]:
        """Create a new living wiki page manually.

        Parameters
        ----------
        entity:
            The entity / page name.
        entity_type:
            Page template type (person, project, concept, topic, resource, contact, default).
        content:
            Optional initial body content (appended after the template).

        Returns
        -------
        Dict with status, slug, and path.
        """
        import time as _time

        self.init()
        db = self._get_db()

        slug = self._safe_slug(entity)
        page_path = self._wiki_dir / "pages" / f"{slug}.md"

        # Check if page already exists
        existing = db.execute("SELECT name FROM entities WHERE name = ?", (entity,)).fetchone()
        if existing is not None:
            db.close()
            return {"status": "already_exists", "slug": slug, "entity": entity, "path": str(page_path)}

        # Generate from template
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
        self._log_action(db, "create", entity, f"Manually created {entity_type} page")
        self._append_log("create_page", f"Manually created {entity_type} page: {entity}")
        db.commit()
        db.close()

        return {"status": "created", "slug": slug, "entity": entity, "path": str(page_path)}

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
