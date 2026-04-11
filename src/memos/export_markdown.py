"""Portable markdown knowledge export for MemOS."""

from __future__ import annotations

import re
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .brain import BrainSearch
from .knowledge_graph import KnowledgeGraph
from .wiki_graph import GraphWikiEngine
TYPE_TAGS = ("decision", "preference", "milestone", "problem", "emotional")


@dataclass
class MarkdownExportResult:
    output_dir: str
    generated_at: float
    entity_count: int = 0
    memory_count: int = 0
    memory_group_count: int = 0
    community_count: int = 0
    pages_written: int = 0
    pages_skipped: int = 0
    pages_removed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_dir": self.output_dir,
            "generated_at": self.generated_at,
            "entity_count": self.entity_count,
            "memory_count": self.memory_count,
            "memory_group_count": self.memory_group_count,
            "community_count": self.community_count,
            "pages_written": self.pages_written,
            "pages_skipped": self.pages_skipped,
            "pages_removed": self.pages_removed,
        }


class MarkdownExporter:
    """Export MemOS knowledge as portable markdown."""

    def __init__(
        self,
        memos: Any,
        *,
        kg: KnowledgeGraph | None = None,
        output_dir: str | None = None,
        wiki_dir: str | None = None,
    ) -> None:
        self._memos = memos
        self._kg = kg or getattr(memos, "_kg", None) or KnowledgeGraph()
        self._brain = BrainSearch(memos, kg=self._kg, wiki_dir=wiki_dir)
        base = Path(output_dir).expanduser().resolve() if output_dir else (Path.home() / ".memos" / "knowledge")
        self._output_dir = base
        self._entities_dir = base / "entities"
        self._memories_dir = base / "memories"
        self._communities_dir = base / "communities"
        self._index_path = base / "INDEX.md"
        self._log_path = base / "LOG.md"

    def export(self, output_dir: str | None = None, update: bool = False) -> MarkdownExportResult:
        if output_dir:
            self.__init__(self._memos, kg=self._kg, output_dir=output_dir)
        self._prepare_dirs()
        self._brain._wiki.init()
        self._brain._wiki.update(force=not update)

        now = time.time()
        result = MarkdownExportResult(output_dir=str(self._output_dir), generated_at=now)

        pages = self._brain._wiki.list_pages()
        items = sorted(
            self._memos._store.list_all(namespace=self._memos._namespace),
            key=lambda item: (-float(item.importance), -float(item.created_at), item.id),
        )
        communities, god_nodes = self._collect_communities()

        result.entity_count = len(pages)
        result.memory_count = len(items)
        result.community_count = len(communities)

        expected_entity_files: set[str] = set()
        for page in pages:
            detail = self._brain.entity_detail(page.entity)
            filename = f"{self._slug(page.entity)}.md"
            expected_entity_files.add(filename)
            content = self._render_entity_page(detail)
            self._record_write(self._entities_dir / filename, content, result)

        expected_memory_files = self._write_memory_groups(items, result)
        expected_community_files = self._write_communities(communities, god_nodes, result)

        self._cleanup_dir(self._entities_dir, expected_entity_files, result)
        self._cleanup_dir(self._memories_dir, expected_memory_files, result)
        self._cleanup_dir(self._communities_dir, expected_community_files, result)

        self._record_write(self._index_path, self._render_index(pages, items, communities, god_nodes, now), result)
        self._append_log(result, update=update)
        result.pages_written += 1
        return result

    def _prepare_dirs(self) -> None:
        self._entities_dir.mkdir(parents=True, exist_ok=True)
        self._memories_dir.mkdir(parents=True, exist_ok=True)
        self._communities_dir.mkdir(parents=True, exist_ok=True)
        if not self._log_path.exists():
            self._log_path.write_text("# MemOS Export Log\n\n", encoding="utf-8")

    def _collect_communities(self) -> tuple[list[Any], dict[str, list[str]]]:
        engine = GraphWikiEngine(self._kg, output_dir=str(self._output_dir / ".graph-cache"))
        facts = engine._load_facts()
        adjacency: dict[str, set[str]] = defaultdict(set)
        nodes: set[str] = set()
        for fact in facts:
            subject = fact["subject"]
            obj = fact["object"]
            nodes.update({subject, obj})
            adjacency[subject].add(obj)
            adjacency[obj].add(subject)
        bridge_nodes = engine._find_bridge_nodes(nodes, adjacency)
        communities = engine._detect_communities(nodes, adjacency, bridge_nodes=bridge_nodes)
        entity_to_community = {
            entity: community.community_id
            for community in communities
            for entity in community.entities
        }
        god_nodes: dict[str, list[str]] = defaultdict(list)
        for node in sorted(bridge_nodes, key=str.lower):
            touched = sorted({entity_to_community.get(neighbor) for neighbor in adjacency.get(node, set()) if entity_to_community.get(neighbor)})
            if len(touched) >= 2:
                god_nodes[node] = touched
        return communities, god_nodes

    def _write_memory_groups(self, items: list[Any], result: MarkdownExportResult) -> set[str]:
        groups: dict[str, list[Any]] = defaultdict(list)
        for item in items:
            matched = [tag for tag in item.tags if tag in TYPE_TAGS]
            for tag in matched or ["general"]:
                groups[tag].append(item)
        result.memory_group_count = len(groups)
        expected_files: set[str] = set()
        for group_name, group_items in sorted(groups.items()):
            filename = f"{self._slug(group_name)}.md"
            expected_files.add(filename)
            content = self._render_memory_group(group_name, group_items)
            self._record_write(self._memories_dir / filename, content, result)
        return expected_files

    def _write_communities(self, communities: list[Any], god_nodes: dict[str, list[str]], result: MarkdownExportResult) -> set[str]:
        expected_files: set[str] = set()
        for community in communities:
            filename = f"{community.community_id}.md"
            expected_files.add(filename)
            content = self._render_community_page(community, god_nodes)
            self._record_write(self._communities_dir / filename, content, result)
        return expected_files

    def _render_entity_page(self, detail: Any) -> str:
        related_tags = sorted({tag for memory in detail.memories for tag in memory.get("tags", [])})
        metadata = {
            "entity": detail.entity,
            "community": detail.community or "",
            "tags": related_tags,
            "importance": round(max((float(memory.get("importance", 0.0)) for memory in detail.memories), default=0.0), 3),
            "backlinks": detail.backlinks,
            "created": self._iso(max((float(memory.get("created_at", 0.0)) for memory in detail.memories), default=0.0)),
            "kg_facts_count": len(detail.kg_facts),
        }
        body = self._strip_frontmatter(detail.wiki_page).strip() or f"# {detail.entity}\n"
        lines = [self._frontmatter(metadata), "", body, "", "## Related Memories", ""]
        if detail.memories:
            for memory in detail.memories:
                lines.extend([
                    f"### {memory['id']}",
                    f"- Importance: {float(memory.get('importance', 0.0)):.2f}",
                    f"- Tags: {', '.join(memory.get('tags', [])) or 'none'}",
                    "",
                    memory.get("content", "").strip(),
                    "",
                ])
        else:
            lines.append("- No linked memories yet.")
            lines.append("")

        lines.extend(["## Graph Facts", ""])
        if detail.kg_facts:
            for fact in detail.kg_facts:
                lines.append(
                    f"- `{fact['subject']}` -`{fact['predicate']}`-> `{fact['object']}` ({fact.get('confidence_label', 'EXTRACTED')})"
                )
        else:
            lines.append("- No graph facts yet.")

        lines.extend(["", "## Graph Neighbors", ""])
        if detail.kg_neighbors:
            for neighbor in detail.kg_neighbors:
                link = self._entity_link(neighbor.entity, relative=True)
                predicates = ", ".join(neighbor.predicates)
                lines.append(f"- {link} ({neighbor.relation_count} relations: {predicates})")
        else:
            lines.append("- No neighbors yet.")

        lines.extend(["", "## Backlinks", ""])
        if detail.backlinks:
            for backlink in detail.backlinks:
                lines.append(f"- {self._entity_link(backlink, relative=True)}")
        else:
            lines.append("- No backlinks yet.")

        return "\n".join(lines).strip() + "\n"

    def _render_memory_group(self, group_name: str, items: list[Any]) -> str:
        metadata = {
            "type": group_name,
            "memory_count": len(items),
            "created": self._iso(max((float(item.created_at) for item in items), default=0.0)),
        }
        lines = [self._frontmatter(metadata), "", f"# {group_name.title()} Memories", ""]
        for item in items:
            lines.extend([
                f"## {item.id}",
                f"- Importance: {float(item.importance):.2f}",
                f"- Tags: {', '.join(item.tags) or 'none'}",
                f"- Created: {self._iso(float(item.created_at))}",
                "",
                item.content.strip(),
                "",
            ])
        return "\n".join(lines).strip() + "\n"

    def _render_community_page(self, community: Any, god_nodes: dict[str, list[str]]) -> str:
        linked_god_nodes = [node for node, touched in god_nodes.items() if community.community_id in touched]
        metadata = {
            "community": community.community_id,
            "entity_count": len(community.entities),
        }
        lines = [self._frontmatter(metadata), "", f"# Community {community.community_id}", "", "## Entities", ""]
        if community.entities:
            for entity in community.entities:
                lines.append(f"- {self._entity_link(entity)}")
        else:
            lines.append("- No entities.")
        lines.extend(["", "## God Nodes", ""])
        if linked_god_nodes:
            for node in linked_god_nodes:
                lines.append(f"- {self._entity_link(node)}")
        else:
            lines.append("- None.")
        return "\n".join(lines).strip() + "\n"

    def _render_index(self, pages: list[Any], items: list[Any], communities: list[Any], god_nodes: dict[str, list[str]], now: float) -> str:
        lines = [
            "# MemOS Knowledge Export",
            "",
            f"- Generated: {self._iso(now)}",
            f"- Entities: {len(pages)}",
            f"- Memories: {len(items)}",
            f"- Communities: {len(communities)}",
            "",
            "## Communities",
            "",
        ]
        if communities:
            for community in communities:
                top_entities = ", ".join(community.entities[:5]) or "n/a"
                lines.append(f"- [{community.community_id}](communities/{community.community_id}.md) — {top_entities}")
        else:
            lines.append("- No communities yet.")

        lines.extend(["", "## God Nodes", ""])
        if god_nodes:
            for node, touched in sorted(god_nodes.items()):
                community_links = ", ".join(f"[{cid}](communities/{cid}.md)" for cid in touched)
                lines.append(f"- {self._entity_link(node)} — {community_links}")
        else:
            lines.append("- No god nodes yet.")

        lines.extend(["", "## Entities", ""])
        for page in sorted(pages, key=lambda page: page.entity.lower())[:100]:
            lines.append(f"- {self._entity_link(page.entity)}")
        return "\n".join(lines).strip() + "\n"

    def _append_log(self, result: MarkdownExportResult, *, update: bool) -> None:
        mode = "update" if update else "full"
        line = (
            f"- {self._iso(result.generated_at)} — {mode} entities={result.entity_count} "
            f"memories={result.memory_count} communities={result.community_count} "
            f"written={result.pages_written} skipped={result.pages_skipped} removed={result.pages_removed}\n"
        )
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(line)

    def _cleanup_dir(self, directory: Path, expected_files: set[str], result: MarkdownExportResult) -> None:
        for path in directory.glob("*.md"):
            if path.name not in expected_files:
                path.unlink()
                result.pages_removed += 1

    def _record_write(self, path: Path, content: str, result: MarkdownExportResult) -> None:
        if self._write_if_changed(path, content):
            result.pages_written += 1
        else:
            result.pages_skipped += 1

    @staticmethod
    def _write_if_changed(path: Path, content: str) -> bool:
        if path.exists() and path.read_text(encoding="utf-8") == content:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return True

    @staticmethod
    def _frontmatter(meta: dict[str, Any]) -> str:
        lines = ["---"]
        for key, value in meta.items():
            if isinstance(value, list):
                lines.append(f"{key}:")
                for item in value:
                    safe = str(item).replace('"', '\\"')
                    lines.append(f'  - "{safe}"')
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                lines.append(f"{key}: {value}")
            else:
                safe = str(value).replace('"', '\\"')
                lines.append(f'{key}: "{safe}"')
        lines.append("---")
        return "\n".join(lines)

    @staticmethod
    def _strip_frontmatter(content: str) -> str:
        if content.startswith("---\n"):
            parts = content.split("\n---\n", 1)
            if len(parts) == 2:
                return parts[1]
        return content

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
        return slug or "item"

    @staticmethod
    def _iso(ts: float) -> str:
        if not ts:
            return ""
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))

    def _entity_link(self, entity: str, relative: bool = False) -> str:
        href = f"{self._slug(entity)}.md" if relative else f"../entities/{self._slug(entity)}.md"
        return f"[{entity}]({href})"
