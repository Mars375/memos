"""Obsidian-compatible markdown export for MemOS knowledge (P6).

Produces a vault-ready directory with:
- YAML frontmatter containing ``aliases``, ``tags``, and MemOS metadata
- ``[[wikilinks]]`` for entity cross-references in content
- One note per entity (in ``entities/``) and per memory group (in ``memories/``)
- An ``INDEX.md`` with ``[[wikilink]]`` navigation

Usage::

    from memos.export_obsidian import ObsidianExporter
    exporter = ObsidianExporter(memos, kg=kg)
    result = exporter.export("~/Documents/memos-vault/")
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .export_markdown import MarkdownExporter, MarkdownExportResult


@dataclass
class ObsidianExportResult(MarkdownExportResult):
    """Export result with Obsidian-specific stats."""
    wikilinks_added: int = 0


class ObsidianExporter:
    """Export MemOS knowledge as an Obsidian-compatible vault.

    Extends :class:`~memos.export_markdown.MarkdownExporter` with:

    * YAML frontmatter that includes ``aliases`` and ``tags`` arrays
      understood by Obsidian's metadata indexer.
    * ``[[EntityName]]`` wikilinks injected wherever an entity name
      appears verbatim in memory content or entity pages.
    * Navigation index (``INDEX.md``) written with ``[[wikilink]]``
      references instead of plain Markdown links.
    """

    def __init__(
        self,
        memos: Any,
        *,
        kg: Any | None = None,
        wiki_dir: str | None = None,
    ) -> None:
        self._memos = memos
        self._kg = kg
        self._wiki_dir = wiki_dir
        self._base = MarkdownExporter(memos, kg=kg, wiki_dir=wiki_dir)

    def export(self, output_dir: str, update: bool = False) -> ObsidianExportResult:
        """Export vault to *output_dir*.

        Parameters
        ----------
        output_dir:
            Destination directory.  Created if it does not exist.
        update:
            If True, only rewrite changed files (incremental).

        Returns
        -------
        ObsidianExportResult with counts of written/skipped pages and wikilinks.
        """
        base_result = self._base.export(output_dir, update=update)
        result = ObsidianExportResult(
            output_dir=base_result.output_dir,
            entities_written=base_result.entities_written,
            entities_skipped=base_result.entities_skipped,
            memory_pages_written=base_result.memory_pages_written,
            memory_pages_skipped=base_result.memory_pages_skipped,
            communities_written=base_result.communities_written,
            communities_skipped=base_result.communities_skipped,
            stale_removed=base_result.stale_removed,
            total_memories=base_result.total_memories,
            total_entities=base_result.total_entities,
            total_facts=base_result.total_facts,
        )

        root = Path(output_dir)
        # Collect all entity names for wikilink substitution
        entity_names = self._collect_entity_names(root / "entities")

        if not entity_names:
            return result

        # Post-process all markdown files to inject wikilinks and fix frontmatter
        total_links = 0
        for md_file in sorted(root.rglob("*.md")):
            if md_file.name in ("INDEX.md", "LOG.md"):
                continue
            original = md_file.read_text(encoding="utf-8")
            patched, n_links = self._inject_wikilinks(original, entity_names)
            patched = self._patch_frontmatter(patched, md_file, root)
            if patched != original:
                md_file.write_text(patched, encoding="utf-8")
            total_links += n_links

        # Rewrite INDEX.md with [[wikilinks]]
        index_path = root / "INDEX.md"
        if index_path.exists():
            idx_content = index_path.read_text(encoding="utf-8")
            idx_patched = self._plain_links_to_wikilinks(idx_content)
            if idx_patched != idx_content:
                index_path.write_text(idx_patched, encoding="utf-8")

        result.wikilinks_added = total_links
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _collect_entity_names(self, entities_dir: Path) -> list[str]:
        """Return all entity names derived from filenames in *entities_dir*."""
        if not entities_dir.is_dir():
            return []
        names: list[str] = []
        for md_path in entities_dir.glob("*.md"):
            # Try to read the 'entity' field from frontmatter
            content = md_path.read_text(encoding="utf-8")
            match = re.search(r'^entity:\s*(.+)$', content, re.MULTILINE)
            if match:
                names.append(match.group(1).strip())
            else:
                # Fall back to stem with underscores → spaces
                names.append(md_path.stem.replace("_", " "))
        # Longest first so longer names are replaced before substrings
        return sorted(names, key=len, reverse=True)

    def _inject_wikilinks(self, content: str, entity_names: list[str]) -> tuple[str, int]:
        """Replace entity name occurrences (outside frontmatter/existing links) with [[name]].

        Only substitutes in the body (after the closing ``---`` frontmatter fence).
        Skips text already inside ``[[...]]`` or Markdown links ``[text](url)``.
        """
        # Split frontmatter from body
        front, body = self._split_frontmatter(content)

        count = 0
        for name in entity_names:
            if not name or len(name) < 2:
                continue
            # Skip if it's just a generic word (< 4 chars) to avoid false positives
            if len(name) < 4:
                continue
            escaped = re.escape(name)
            # Match the name as a whole word, not already inside [[ ]]
            pattern = r'(?<!\[\[)(?<!\[)\b' + escaped + r'\b(?!\]\])(?!\])'
            new_body, n = re.subn(pattern, f"[[{name}]]", body)
            if n:
                body = new_body
                count += n

        return front + body, count

    def _split_frontmatter(self, content: str) -> tuple[str, str]:
        """Return (frontmatter_section, body) where frontmatter_section includes the closing ---."""
        if not content.startswith("---\n"):
            return "", content
        end = content.find("\n---\n", 4)
        if end == -1:
            return "", content
        split_at = end + 5  # after "\n---\n"
        return content[:split_at], content[split_at:]

    def _patch_frontmatter(self, content: str, md_file: Path, root: Path) -> str:
        """Ensure the frontmatter has Obsidian-compatible ``aliases`` and ``tags`` fields."""
        if not content.startswith("---\n"):
            return content
        end = content.find("\n---\n", 4)
        if end == -1:
            return content

        fm_block = content[4:end]  # the YAML body between the ---'s
        body_after = content[end + 5:]

        # Extract existing tags list if present
        tags_match = re.search(r'^tags:\s*\[([^\]]*)\]', fm_block, re.MULTILINE)
        existing_tags: list[str] = []
        if tags_match:
            existing_tags = [t.strip().strip('"\'') for t in tags_match.group(1).split(',') if t.strip()]

        # Extract entity name
        entity_match = re.search(r'^entity:\s*(.+)$', fm_block, re.MULTILINE)
        entity_name = entity_match.group(1).strip() if entity_match else md_file.stem

        # Add aliases if not present
        needs_aliases = "aliases:" not in fm_block
        needs_obsidian_tags = "obsidian_tags:" not in fm_block

        additions: list[str] = []
        if needs_aliases:
            additions.append(f'aliases: ["{entity_name}"]')
        if needs_obsidian_tags and existing_tags:
            tags_yaml = ", ".join(f'"{t}"' for t in existing_tags)
            additions.append(f"obsidian_tags: [{tags_yaml}]")

        if not additions:
            return content

        # Insert additions at the end of the frontmatter block
        new_fm = fm_block.rstrip() + "\n" + "\n".join(additions)
        return f"---\n{new_fm}\n---\n{body_after}"

    def _plain_links_to_wikilinks(self, content: str) -> str:
        """Convert ``[EntityName](entities/slug.md)`` links to ``[[EntityName]]`` wikilinks."""
        # Match: [Some Text](entities/some_slug.md) or [Some Text](communities/...)
        pattern = r'\[([^\]]+)\]\((?:entities|memories|communities)/[^)]+\.md\)'
        return re.sub(pattern, r'[[\1]]', content)
