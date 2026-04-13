"""Wiki compile mode — consolidate memories into markdown pages per tag.

Commands:
    memos wiki-compile   — group memories by tag, write data/wiki/<tag>.md
    memos wiki-list      — list compiled pages with metadata
    memos wiki-read <tag> — read a compiled page
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional


@dataclass
class WikiPage:
    tag: str
    path: Path
    memory_count: int
    compiled_at: float
    size_bytes: int

    def age_str(self) -> str:
        delta = time.time() - self.compiled_at
        if delta < 60:
            return f"{int(delta)}s ago"
        if delta < 3600:
            return f"{int(delta / 60)}m ago"
        if delta < 86400:
            return f"{int(delta / 3600)}h ago"
        return f"{int(delta / 86400)}d ago"


class WikiEngine:
    """Manages compiled wiki pages for a MemOS instance."""

    def __init__(self, memos: Any, wiki_dir: Optional[str] = None) -> None:
        self._memos = memos
        if wiki_dir:
            self._wiki_dir = Path(wiki_dir)
        else:
            # Default: data/wiki/ relative to persist_path if available, else ~/.memos/wiki
            persist = getattr(memos, "_persist_path", None)
            if persist:
                self._wiki_dir = Path(persist).parent / "wiki"
            else:
                self._wiki_dir = Path.home() / ".memos" / "wiki"
        self._wiki_dir.mkdir(parents=True, exist_ok=True)

    def _safe_filename(self, tag: str) -> str:
        return "".join(c if c.isalnum() or c in "-_." else "_" for c in tag)

    def compile(self, tags: Optional[List[str]] = None) -> List[WikiPage]:
        """Compile memories grouped by tag into markdown pages.

        Args:
            tags: If provided, only compile these tags. Otherwise compile all.

        Returns:
            List of WikiPage objects for pages that were written.
        """
        store = self._memos._store
        namespace = self._memos._namespace

        all_items = store.list_all(namespace=namespace)

        # Group by tag
        tag_map: dict[str, list] = {}
        for item in all_items:
            item_tags = item.tags if item.tags else ["_untagged"]
            for t in item_tags:
                if tags and t not in tags:
                    continue
                tag_map.setdefault(t, []).append(item)

        pages: List[WikiPage] = []
        for tag, items in tag_map.items():
            # Sort by importance desc, then by created_at desc
            items.sort(key=lambda i: (-i.importance, -(i.created_at or 0)))

            lines = [
                f"# {tag}",
                "",
                f"> Compiled from {len(items)} memories · {time.strftime('%Y-%m-%d %H:%M')}",
                "",
            ]
            for item in items:
                importance_bar = "★" * max(1, round(item.importance * 5))
                other_tags = [t for t in (item.tags or []) if t != tag]
                tag_str = f" · tags: {', '.join(other_tags)}" if other_tags else ""
                lines.append(f"## {importance_bar}{tag_str}")
                lines.append("")
                lines.append(item.content)
                lines.append("")

            content = "\n".join(lines)
            path = self._wiki_dir / f"{self._safe_filename(tag)}.md"
            path.write_text(content, encoding="utf-8")

            pages.append(WikiPage(
                tag=tag,
                path=path,
                memory_count=len(items),
                compiled_at=time.time(),
                size_bytes=len(content.encode()),
            ))

        return pages

    def list_pages(self) -> List[WikiPage]:
        """List all compiled wiki pages."""
        pages: List[WikiPage] = []
        for md_file in sorted(self._wiki_dir.glob("*.md")):
            stat = md_file.stat()
            # Count "## " headers as memory count
            text = md_file.read_text(encoding="utf-8")
            mem_count = text.count("\n## ")
            tag = md_file.stem.replace("_", " ")
            # Try to read exact tag from first H1
            for line in text.splitlines():
                if line.startswith("# "):
                    tag = line[2:].strip()
                    break
            pages.append(WikiPage(
                tag=tag,
                path=md_file,
                memory_count=mem_count,
                compiled_at=stat.st_mtime,
                size_bytes=stat.st_size,
            ))
        return pages

    def read(self, tag: str) -> Optional[str]:
        """Read a compiled wiki page by tag name. Returns None if not found."""
        filename = self._safe_filename(tag)
        path = self._wiki_dir / f"{filename}.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        # Fuzzy: look for any file whose H1 matches
        for md_file in self._wiki_dir.glob("*.md"):
            text = md_file.read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.startswith("# ") and line[2:].strip().lower() == tag.lower():
                    return text
        return None
