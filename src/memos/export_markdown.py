"""Portable Markdown export for MemOS knowledge."""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


TYPE_TAGS = {
    "decision",
    "preference",
    "milestone",
    "problem",
    "emotional",
    "fact",
    "action",
    "question",
}


@dataclass
class MarkdownExportResult:
    output_dir: str
    memories_total: int = 0
    entities_total: int = 0
    communities_total: int = 0
    pages_written: int = 0
    pages_skipped: int = 0
    pages_removed: int = 0
    generated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_dir": self.output_dir,
            "memories_total": self.memories_total,
            "entities_total": self.entities_total,
            "communities_total": self.communities_total,
            "pages_written": self.pages_written,
            "pages_skipped": self.pages_skipped,
            "pages_removed": self.pages_removed,
            "generated_at": self.generated_at,
        }


class MarkdownExporter:
    """Export MemOS knowledge into a portable Markdown knowledge bundle."""

    def __init__(self, memos: Any, output_dir: str | None = None) -> None:
        self._memos = memos
        if output_dir:
            self._output_dir = Path(output_dir)
        else:
            persist = getattr(memos, "_persist_path", None)
            if persist:
                self._output_dir = Path(persist).expanduser().resolve().parent / "knowledge"
            else:
                self._output_dir = Path.home() / ".memos" / "knowledge"

    def export(self, output_dir: str | None = None, *, update: bool = False) -> MarkdownExportResult:
        root = Path(output_dir) if output_dir else self._output_dir
        entities_dir = root / "entities"
        memories_dir = root / "memories"
        communities_dir = root / "communities"
        for directory in (root, entities_dir, memories_dir, communities_dir):
            directory.mkdir(parents=True, exist_ok=True)

        result = MarkdownExportResult(output_dir=str(root))
        items = sorted(
            self._memos._store.list_all(namespace=self._memos._namespace),
            key=lambda item: (-item.importance, -(item.created_at or 0), item.id),
        )
        result.memories_total = len(items)

        from .brain import BrainSearch

        brain = BrainSearch(self._memos)
        wiki = brain._get_wiki()
        if wiki is not None:
            try:
                wiki.update(force=False)
            except Exception:
                pass

        analysis = brain._get_graph_analysis()
        entities = self._collect_entities(analysis, wiki)
        result.entities_total = len(entities)
        result.communities_total = len(analysis.get("communities", []))

        kept_entity_pages: set[str] = set()
        for entity in entities:
            detail = brain.entity_detail(entity)
            path = entities_dir / f"{self._safe_name(detail.entity)}.md"
            kept_entity_pages.add(path.name)
            content = self._render_entity_page(detail)
            self._record_write(path, content, result)
        result.pages_removed += self._remove_stale(entities_dir, kept_entity_pages)

        memory_groups = self._group_memories(items)
        kept_memory_pages: set[str] = set()
        for group_name, grouped_items in sorted(memory_groups.items()):
            filename = self._memory_page_name(group_name)
            path = memories_dir / filename
            kept_memory_pages.add(filename)
            content = self._render_memory_page(group_name, grouped_items, entities)
            self._record_write(path, content, result)
        result.pages_removed += self._remove_stale(memories_dir, kept_memory_pages)

        kept_community_pages: set[str] = set()
        for community in analysis.get("communities", []):
            path = communities_dir / f"{community.community_id}.md"
            kept_community_pages.add(path.name)
            content = self._render_community_page(community, analysis)
            self._record_write(path, content, result)
        result.pages_removed += self._remove_stale(communities_dir, kept_community_pages)

        self._record_write(root / "INDEX.md", self._render_index(items, analysis, entities), result)
        self._append_log(root / "LOG.md", result, update=update)
        result.pages_written += 1

        return result

    def _collect_entities(self, analysis: dict[str, Any], wiki: Any | None) -> list[str]:
        entities = {
            fact["subject"]
            for fact in analysis.get("facts", [])
        } | {
            fact["object"]
            for fact in analysis.get("facts", [])
        }
        if wiki is not None:
            try:
                entities.update(page.entity for page in wiki.list_pages())
            except Exception:
                pass
        return sorted(entities, key=lambda name: name.lower())

    def _group_memories(self, items: list[Any]) -> dict[str, list[Any]]:
        groups: dict[str, list[Any]] = defaultdict(list)
        for item in items:
            matched = [tag for tag in item.tags if tag in TYPE_TAGS]
            if not matched:
                matched = ["untagged"]
            for tag in matched:
                groups[tag].append(item)
        return groups

    def _render_entity_page(self, detail: Any) -> str:
        tags = [detail.community] if detail.community else []
        avg_importance = (
            sum(memory.importance for memory in detail.memories) / len(detail.memories)
            if detail.memories else 0.0
        )
        confidences = [fact.confidence for fact in detail.kg_facts if getattr(fact, "confidence", None) is not None]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 1.0
        created_at = None
        frontmatter = self._frontmatter({
            "entity": detail.entity,
            "tags": tags,
            "importance": round(avg_importance, 3),
            "community": detail.community or "",
            "confidence": round(avg_confidence, 3),
            "created": self._iso(created_at if created_at is not None else None),
            "backlinks": sorted(detail.backlinks),
        })

        lines = [
            frontmatter,
            f"# {detail.entity}",
            "",
            f"- Community: {detail.community or 'none'}",
            f"- God node: {'yes' if detail.is_god_node else 'no'}",
            f"- Backlinks: {len(detail.backlinks)}",
            "",
        ]

        if detail.wiki_page:
            lines.extend([
                "## Wiki",
                "",
                detail.wiki_page.strip(),
                "",
            ])

        if detail.kg_facts:
            lines.append("## Knowledge Graph Facts")
            lines.append("")
            for fact in detail.kg_facts:
                target = fact.object if fact.subject == detail.entity else fact.subject
                lines.append(
                    f"- `{fact.predicate}` → {self._entity_link(target)} "
                    f"(confidence: {round(fact.confidence, 3)}, label: {fact.confidence_label})"
                )
            lines.append("")

        if detail.kg_neighbors:
            lines.append("## Graph Neighbors")
            lines.append("")
            for neighbor in detail.kg_neighbors:
                extra = []
                if neighbor.predicates:
                    extra.append(f"via {', '.join(f'`{predicate}`' for predicate in neighbor.predicates[:3])}")
                if neighbor.community:
                    extra.append(f"community: {neighbor.community}")
                if neighbor.is_god_node:
                    extra.append("god-node")
                suffix = f" ({', '.join(extra)})" if extra else ""
                lines.append(f"- {self._entity_link(neighbor.entity)}{suffix}")
            lines.append("")

        if detail.memories:
            lines.append("## Top Memories")
            lines.append("")
            for memory in sorted(detail.memories, key=lambda item: (-item.importance, item.id)):
                lines.append(f"- `{memory.id}` · importance {round(memory.importance, 3)}")
                lines.append(f"  - {memory.content}")
            lines.append("")

        if detail.backlinks:
            lines.append("## Backlinks")
            lines.append("")
            for backlink in detail.backlinks:
                lines.append(f"- {self._entity_link(backlink)}")
            lines.append("")

        return self._normalize_markdown("\n".join(lines).rstrip() + "\n")

    def _render_memory_page(self, group_name: str, items: list[Any], entities: list[str]) -> str:
        frontmatter = self._frontmatter({
            "tag": group_name,
            "tags": [group_name],
            "importance": round(sum(item.importance for item in items) / max(1, len(items)), 3),
            "community": "",
            "confidence": 1.0,
            "created": self._iso(min((item.created_at for item in items), default=None)),
            "backlinks": [],
        })
        title = group_name.replace("_", " ").title()
        lines = [
            frontmatter,
            f"# {title}",
            "",
            f"> {len(items)} memories grouped by type tag `{group_name}`.",
            "",
        ]
        entity_lookup = {entity.lower(): entity for entity in entities}
        for item in items:
            mentions = self._extract_mentions(item.content, entity_lookup)
            lines.append(f"## {item.id}")
            lines.append("")
            lines.append(f"- Created: {self._iso(item.created_at)}")
            lines.append(f"- Importance: {round(item.importance, 3)}")
            lines.append(f"- Tags: {', '.join(item.tags) if item.tags else 'none'}")
            if mentions:
                lines.append(f"- Mentions: {', '.join(self._entity_link(name) for name in mentions)}")
            metadata = item.metadata or {}
            if metadata:
                lines.append(f"- Metadata: `{json.dumps(metadata, ensure_ascii=False, sort_keys=True)}`")
            lines.append("")
            lines.append(item.content)
            lines.append("")
        return self._normalize_markdown("\n".join(lines).rstrip() + "\n")

    def _render_community_page(self, community: Any, analysis: dict[str, Any]) -> str:
        confidences = [fact.get("confidence", 1.0) for fact in community.facts]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 1.0
        frontmatter = self._frontmatter({
            "community": community.community_id,
            "tags": ["community"],
            "importance": round(min(1.0, len(community.entities) / 10), 3),
            "confidence": round(avg_confidence, 3),
            "created": self._iso(min((fact.get("created_at") for fact in community.facts if fact.get("created_at") is not None), default=None)),
            "backlinks": sorted(community.backlinks),
        })

        lines = [
            frontmatter,
            f"# Community {community.community_id}",
            "",
            f"- Entities: {len(community.entities)}",
            f"- Internal facts: {len(community.facts)}",
            f"- Cross-community facts: {len(community.cross_facts)}",
            "",
            "## Top Entities",
            "",
        ]
        for entity in community.top_entities or community.entities[:5]:
            degree = analysis.get("degrees", {}).get(entity, 0)
            lines.append(f"- {self._entity_link(entity)} (degree: {degree})")
        lines.append("")

        lines.extend(["## Members", ""])
        for entity in community.entities:
            lines.append(f"- {self._entity_link(entity)}")
        lines.append("")

        if community.facts:
            lines.extend(["## Internal Facts", ""])
            for fact in community.facts[:50]:
                lines.append(
                    f"- {self._entity_link(fact['subject'])} `{fact['predicate']}` {self._entity_link(fact['object'])}"
                )
            lines.append("")

        if community.cross_facts:
            lines.extend(["## Cross-community Links", ""])
            for fact in community.cross_facts[:30]:
                lines.append(
                    f"- {self._entity_link(fact['subject'])} `{fact['predicate']}` {self._entity_link(fact['object'])}"
                )
            lines.append("")

        if community.backlinks:
            lines.extend(["## Backlinks", ""])
            for backlink in community.backlinks:
                lines.append(f"- [Community {backlink}](./{backlink}.md)")
            lines.append("")

        if community.god_nodes:
            lines.extend(["## God Nodes", ""])
            for node in community.god_nodes:
                lines.append(f"- {self._entity_link(node)}")
            lines.append("")

        return self._normalize_markdown("\n".join(lines).rstrip() + "\n")

    def _render_index(self, items: list[Any], analysis: dict[str, Any], entities: list[str]) -> str:
        communities = analysis.get("communities", [])
        god_nodes = analysis.get("god_nodes", {})
        lines = [
            "# MemOS Knowledge Export",
            "",
            f"> Portable bundle with {len(items)} memories · {len(entities)} entities · {len(communities)} communities",
            "",
            "## Stats",
            "",
            f"- Memories: {len(items)}",
            f"- Entities: {len(entities)}",
            f"- Communities: {len(communities)}",
            f"- God nodes: {len(god_nodes)}",
            "",
            "## Communities",
            "",
        ]
        for community in communities:
            lines.append(
                f"- [Community {community.community_id}](./communities/{community.community_id}.md) "
                f"({len(community.entities)} entities)"
            )
        if not communities:
            lines.append("- None")
        lines.append("")

        lines.extend(["## Top Entities", ""])
        degrees = analysis.get("degrees", {})
        for entity in sorted(entities, key=lambda name: (-degrees.get(name, 0), name.lower()))[:25]:
            lines.append(f"- [{entity}](./entities/{self._safe_name(entity)}.md)")
        if not entities:
            lines.append("- None")
        lines.append("")

        grouped = self._group_memories(items)
        lines.extend(["## Memory Collections", ""])
        for group_name, grouped_items in sorted(grouped.items()):
            lines.append(
                f"- [{group_name}](./memories/{self._memory_page_name(group_name)}) ({len(grouped_items)})"
            )
        if not grouped:
            lines.append("- None")
        lines.append("")

        if god_nodes:
            lines.extend(["## God Nodes", ""])
            for node, touched in sorted(god_nodes.items()):
                lines.append(
                    f"- {self._entity_link(node, prefix='./entities/')} "
                    f"({len(touched)} communities)"
                )
            lines.append("")

        lines.extend([
            "## Files",
            "",
            "- [LOG.md](./LOG.md)",
            "- [entities/](./entities/)",
            "- [memories/](./memories/)",
            "- [communities/](./communities/)",
            "",
        ])
        return self._normalize_markdown("\n".join(lines).rstrip() + "\n")

    def _append_log(self, path: Path, result: MarkdownExportResult, *, update: bool) -> None:
        entry = (
            f"\n## {self._iso_now()} — {'Update' if update else 'Export'}\n\n"
            f"- Memories: {result.memories_total}\n"
            f"- Entities: {result.entities_total}\n"
            f"- Communities: {result.communities_total}\n"
            f"- Pages written: {result.pages_written}\n"
            f"- Pages skipped: {result.pages_skipped}\n"
            f"- Pages removed: {result.pages_removed}\n"
        )
        current = path.read_text(encoding="utf-8") if path.exists() else "# MemOS Export Log\n\n> Append-only journal of Markdown exports.\n"
        path.write_text(current + entry, encoding="utf-8")

    def _frontmatter(self, data: dict[str, Any]) -> str:
        lines = ["---"]
        for key, value in data.items():
            if isinstance(value, list):
                lines.append(f"{key}:")
                if value:
                    for item in value:
                        lines.append(f"  - {self._yaml_scalar(item)}")
                else:
                    lines[-1] += " []"
            else:
                lines.append(f"{key}: {self._yaml_scalar(value)}")
        lines.append("---")
        return "\n".join(lines)

    def _yaml_scalar(self, value: Any) -> str:
        if value is None:
            return '""'
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        text = str(value).replace('"', '\\"')
        return f'"{text}"'

    def _normalize_markdown(self, text: str) -> str:
        while "\n\n\n" in text:
            text = text.replace("\n\n\n", "\n\n")
        return text

    def _record_write(self, path: Path, content: str, result: MarkdownExportResult) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_text(encoding="utf-8") == content:
            result.pages_skipped += 1
            return
        path.write_text(content, encoding="utf-8")
        result.pages_written += 1

    def _remove_stale(self, directory: Path, keep: set[str]) -> int:
        removed = 0
        for path in directory.glob("*.md"):
            if path.name not in keep:
                path.unlink()
                removed += 1
        return removed

    def _extract_mentions(self, content: str, entity_lookup: dict[str, str]) -> list[str]:
        content_lower = content.lower()
        matches = [entity for lowered, entity in entity_lookup.items() if lowered in content_lower]
        return sorted(set(matches), key=lambda name: name.lower())[:12]

    def _entity_link(self, entity: str, prefix: str = "../entities/") -> str:
        return f"[{entity}]({prefix}{self._safe_name(entity)}.md)"

    def _memory_page_name(self, group_name: str) -> str:
        if group_name == "untagged":
            return "untagged.md"
        if group_name.endswith("y"):
            base = f"{group_name[:-1]}ies"
        elif group_name.endswith("s"):
            base = group_name
        else:
            base = f"{group_name}s"
        return f"{self._safe_name(base)}.md"

    def _safe_name(self, value: str) -> str:
        safe = "".join(char if char.isalnum() or char in "-_" else "-" for char in value.strip())
        while "--" in safe:
            safe = safe.replace("--", "-")
        return safe.strip("-") or "untitled"

    def _iso(self, value: float | None) -> str:
        if value is None:
            return ""
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(value))

    def _iso_now(self) -> str:
        return self._iso(time.time())
