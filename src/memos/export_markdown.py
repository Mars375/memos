"""Portable markdown export for MemOS knowledge."""

from __future__ import annotations

import json
import tempfile
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .knowledge_graph import KnowledgeGraph
from .wiki_graph import GraphWikiEngine
from .wiki_living import LivingWikiEngine


@dataclass
class MarkdownExportResult:
    output_dir: str
    entities_written: int = 0
    entities_skipped: int = 0
    memory_pages_written: int = 0
    memory_pages_skipped: int = 0
    communities_written: int = 0
    communities_skipped: int = 0
    stale_removed: int = 0
    total_memories: int = 0
    total_entities: int = 0
    total_facts: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_dir": self.output_dir,
            "entities_written": self.entities_written,
            "entities_skipped": self.entities_skipped,
            "memory_pages_written": self.memory_pages_written,
            "memory_pages_skipped": self.memory_pages_skipped,
            "communities_written": self.communities_written,
            "communities_skipped": self.communities_skipped,
            "stale_removed": self.stale_removed,
            "total_memories": self.total_memories,
            "total_entities": self.total_entities,
            "total_facts": self.total_facts,
        }


class MarkdownExporter:
    """Export MemOS knowledge into portable markdown files."""

    def __init__(
        self,
        memos: Any,
        *,
        kg: KnowledgeGraph | None = None,
        wiki_dir: str | None = None,
    ) -> None:
        self._memos = memos
        self._kg = kg or getattr(memos, "_kg", None) or KnowledgeGraph()
        self._wiki = LivingWikiEngine(memos, wiki_dir=wiki_dir)

    def export(self, output_dir: str, update: bool = False) -> MarkdownExportResult:
        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)
        entities_dir = root / "entities"
        memories_dir = root / "memories"
        communities_dir = root / "communities"
        entities_dir.mkdir(parents=True, exist_ok=True)
        memories_dir.mkdir(parents=True, exist_ok=True)
        communities_dir.mkdir(parents=True, exist_ok=True)

        self._wiki.init()
        self._wiki.update(force=not update)

        result = MarkdownExportResult(output_dir=str(root))
        items = self._load_memories()
        pages = self._wiki.list_pages()
        kg_stats = self._kg.stats()
        graph_result = self._export_communities(root, update=update)

        result.total_memories = len(items)
        result.total_entities = len(pages)
        result.total_facts = int(kg_stats.get("active_facts", kg_stats.get("total_facts", 0)))
        result.communities_written = graph_result["written"]
        result.communities_skipped = graph_result["skipped"]
        result.stale_removed += graph_result["removed"]

        entity_paths: set[str] = set()
        for page in pages:
            entity_paths.add(f"{self._safe_slug(page.entity)}.md")
            content = self._render_entity_page(page.entity)
            changed = self._write_if_changed(entities_dir / f"{self._safe_slug(page.entity)}.md", content)
            if changed:
                result.entities_written += 1
            else:
                result.entities_skipped += 1
        result.stale_removed += self._remove_stale_markdown(entities_dir, entity_paths)

        memory_groups = self._group_memories(items)
        memory_paths: set[str] = set()
        for name, group in sorted(memory_groups.items()):
            slug = self._safe_slug(name)
            memory_paths.add(f"{slug}.md")
            content = self._render_memory_page(name, group)
            changed = self._write_if_changed(memories_dir / f"{slug}.md", content)
            if changed:
                result.memory_pages_written += 1
            else:
                result.memory_pages_skipped += 1
        result.stale_removed += self._remove_stale_markdown(memories_dir, memory_paths)

        index_content = self._render_index(items, pages, kg_stats, communities_dir)
        if self._write_if_changed(root / "INDEX.md", index_content):
            result.memory_pages_written += 1
        else:
            result.memory_pages_skipped += 1

        self._append_log(root / "LOG.md", result, update=update)
        return result

    def _load_memories(self) -> list[Any]:
        store = getattr(self._memos, "_store", None)
        namespace = getattr(self._memos, "_namespace", None)
        if store is not None and hasattr(store, "list_all"):
            return list(store.list_all(namespace=namespace))
        return []

    def _render_entity_page(self, entity: str) -> str:
        detail = None
        try:
            from .brain import BrainSearch

            detail = BrainSearch(self._memos, kg=self._kg, wiki_dir=str(self._wiki._wiki_dir.parent)).entity_detail(entity)
        except Exception:
            detail = None

        raw = self._wiki.read_page(entity) or f"# {entity}\n"
        metadata = {
            "entity": entity,
            "type": "entity",
            "community": detail.community if detail else None,
            "kg_facts_count": len(detail.kg_facts) if detail else 0,
            "backlinks": detail.backlinks if detail else [],
            "exported_at": self._iso_now(),
        }
        body = self._strip_frontmatter(raw)
        return "\n".join([
            self._frontmatter(metadata),
            "",
            body.strip(),
            "",
        ]).strip() + "\n"

    def _group_memories(self, items: list[Any]) -> dict[str, list[Any]]:
        grouped: dict[str, list[Any]] = defaultdict(list)
        for item in items:
            name = "untagged"
            if getattr(item, "tags", None):
                name = sorted(item.tags)[0]
            grouped[name].append(item)
        return grouped

    def _render_memory_page(self, name: str, items: list[Any]) -> str:
        ordered = sorted(items, key=lambda item: getattr(item, "created_at", 0.0), reverse=True)
        metadata = {
            "group": name,
            "type": "memory-group",
            "entries": len(ordered),
            "tags": [name],
            "exported_at": self._iso_now(),
        }
        lines = [self._frontmatter(metadata), "", f"# {name}", "", f"> {len(ordered)} memory item(s).", ""]
        for item in ordered:
            created = self._iso_ts(getattr(item, "created_at", time.time()))
            tags = ", ".join(getattr(item, "tags", []) or [])
            lines.extend(
                [
                    f"## Memory {getattr(item, 'id', '')}",
                    "",
                    f"- Created: {created}",
                    f"- Importance: {round(float(getattr(item, 'importance', 0.5)), 3)}",
                    f"- Tags: {tags or 'none'}",
                    "",
                    getattr(item, "content", "").strip(),
                    "",
                ]
            )
        return "\n".join(lines).strip() + "\n"

    def _export_communities(self, root: Path, update: bool) -> dict[str, int]:
        written = 0
        skipped = 0
        removed = 0
        with tempfile.TemporaryDirectory(prefix="memos-graph-export-") as tmp:
            graph = GraphWikiEngine(self._kg, output_dir=tmp)
            graph.build(update=update)
            src = Path(tmp) / "communities"
            dest = root / "communities"
            keep: set[str] = set()
            for page in sorted(src.glob("*.md")):
                keep.add(page.name)
                if self._write_if_changed(dest / page.name, page.read_text(encoding="utf-8")):
                    written += 1
                else:
                    skipped += 1
            removed += self._remove_stale_markdown(dest, keep)
        return {"written": written, "skipped": skipped, "removed": removed}

    def _render_index(self, items: list[Any], pages: list[Any], kg_stats: dict[str, Any], communities_dir: Path) -> str:
        community_pages = sorted(communities_dir.glob("*.md"))
        lines = [
            "# MemOS Knowledge Export",
            "",
            "> Portable markdown snapshot of memories, entities, and graph communities.",
            "",
            "## Stats",
            "",
            f"- Memories: {len(items)}",
            f"- Entities: {len(pages)}",
            f"- Active KG facts: {kg_stats.get('active_facts', kg_stats.get('total_facts', 0))}",
            f"- Communities: {len(community_pages)}",
            "",
            "## Sections",
            "",
            "- [Entities](entities/)",
            "- [Memories](memories/)",
            "- [Communities](communities/)",
            "- [Log](LOG.md)",
            "",
            "## Top entities",
            "",
        ]
        for page in pages[:20]:
            slug = self._safe_slug(page.entity)
            lines.append(f"- [{page.entity}](entities/{slug}.md)")
        if not pages:
            lines.append("- No entities exported yet.")
        lines.extend(["", "## Communities", ""])
        if community_pages:
            for community in community_pages[:20]:
                lines.append(f"- [{community.stem}](communities/{community.name})")
        else:
            lines.append("- No communities exported yet.")
        return "\n".join(lines).strip() + "\n"

    def _append_log(self, path: Path, result: MarkdownExportResult, update: bool) -> None:
        if not path.exists():
            path.write_text("# MemOS Export Log\n\n", encoding="utf-8")
        mode = "update" if update else "full"
        entry = (
            f"- {self._iso_now()} | {mode} | memories={result.total_memories} "
            f"entities={result.total_entities} facts={result.total_facts} "
            f"entities_written={result.entities_written} memory_pages_written={result.memory_pages_written} "
            f"communities_written={result.communities_written} stale_removed={result.stale_removed}\n"
        )
        with path.open("a", encoding="utf-8") as handle:
            handle.write(entry)

    def _remove_stale_markdown(self, directory: Path, keep: set[str]) -> int:
        removed = 0
        for path in directory.glob("*.md"):
            if path.name in keep:
                continue
            path.unlink()
            removed += 1
        return removed

    def _write_if_changed(self, path: Path, content: str) -> bool:
        if path.exists() and path.read_text(encoding="utf-8") == content:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return True

    def _strip_frontmatter(self, text: str) -> str:
        if not text.startswith("---\n"):
            return text
        marker = text.find("\n---\n", 4)
        if marker == -1:
            return text
        return text[marker + 5 :]

    def _frontmatter(self, payload: dict[str, Any]) -> str:
        lines = ["---"]
        for key, value in payload.items():
            if value is None:
                continue
            if isinstance(value, list):
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {json.dumps(item, ensure_ascii=False)}")
            elif isinstance(value, bool):
                lines.append(f"{key}: {'true' if value else 'false'}")
            elif isinstance(value, (int, float)):
                lines.append(f"{key}: {value}")
            else:
                lines.append(f"{key}: {json.dumps(str(value), ensure_ascii=False)}")
        lines.append("---")
        return "\n".join(lines)

    def _safe_slug(self, name: str) -> str:
        return self._wiki._safe_slug(name)

    def _iso_now(self) -> str:
        return self._iso_ts(time.time())

    def _iso_ts(self, value: float) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(value))
