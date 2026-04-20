"""Page templates for living wiki."""

from __future__ import annotations

import time
from typing import Any, Dict


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
