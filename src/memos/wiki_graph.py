"""Graph community wiki generated from the knowledge graph.

P21 — Community Wiki (Leiden Graph + Index Navigable)

This module keeps the implementation dependency-light:
- community detection uses deterministic label propagation
- wiki output is plain markdown
- incremental updates rewrite only changed pages
"""

from __future__ import annotations

import hashlib
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set


@dataclass
class CommunitySummary:
    """A detected graph community and its rendered metadata."""

    community_id: str
    entities: List[str]
    facts: List[dict] = field(default_factory=list)
    cross_facts: List[dict] = field(default_factory=list)
    backlinks: List[str] = field(default_factory=list)
    top_entities: List[str] = field(default_factory=list)
    god_nodes: List[str] = field(default_factory=list)


@dataclass
class GraphWikiResult:
    """Build result for the graph wiki."""

    community_count: int = 0
    facts_indexed: int = 0
    pages_written: int = 0
    pages_skipped: int = 0
    pages_removed: int = 0
    god_nodes: int = 0
    output_dir: str = ""


class GraphWikiEngine:
    """Generate a navigable wiki organized by graph communities."""

    def __init__(self, kg, output_dir: Optional[str] = None) -> None:
        self._kg = kg
        if output_dir:
            self._output_dir = Path(output_dir)
        else:
            db_path = getattr(kg, "_db_path", None)
            if db_path and db_path != ":memory:":
                self._output_dir = Path(db_path).expanduser().resolve().parent / "wiki" / "graph"
            else:
                self._output_dir = Path.home() / ".memos" / "wiki" / "graph"
        self._communities_dir = self._output_dir / "communities"
        self._index_path = self._output_dir / "index.md"
        self._log_path = self._output_dir / "log.md"
        self._god_nodes_path = self._output_dir / "god-nodes.md"

    def init(self) -> dict:
        """Create the output structure if missing."""
        self._communities_dir.mkdir(parents=True, exist_ok=True)
        if not self._index_path.exists():
            self._index_path.write_text(
                "# Graph Wiki Index\n\n> Auto-generated catalog of graph communities.\n",
                encoding="utf-8",
            )
        if not self._log_path.exists():
            self._log_path.write_text(
                "# Graph Wiki Log\n\n> Append-only journal of graph wiki updates.\n\n",
                encoding="utf-8",
            )
        if not self._god_nodes_path.exists():
            self._god_nodes_path.write_text(
                "# God Nodes\n\n> Entities spanning three or more communities.\n",
                encoding="utf-8",
            )
        return {
            "output_dir": str(self._output_dir),
            "communities_dir": str(self._communities_dir),
            "index": str(self._index_path),
            "log": str(self._log_path),
            "god_nodes": str(self._god_nodes_path),
        }

    def build(self, update: bool = False) -> GraphWikiResult:
        """Build or incrementally update the graph wiki."""
        self.init()
        result = GraphWikiResult(output_dir=str(self._output_dir))

        analysis = self.analyze()
        facts = analysis["facts"]
        communities = analysis["communities"]
        degrees = analysis["degrees"]
        facts_by_community = analysis["facts_by_community"]
        cross_facts_by_community = analysis["cross_facts_by_community"]
        backlinks = analysis["backlinks"]
        god_nodes = analysis["god_nodes"]

        result.facts_indexed = len(facts)
        result.god_nodes = len(god_nodes)

        for community in communities:
            community.facts = facts_by_community.get(community.community_id, [])
            community.cross_facts = cross_facts_by_community.get(community.community_id, [])
            community.backlinks = sorted(backlinks.get(community.community_id, set()))
            community.top_entities = sorted(
                community.entities,
                key=lambda entity: (-degrees.get(entity, 0), entity.lower()),
            )[:5]
            community.god_nodes = sorted(
                entity for entity, touched in god_nodes.items()
                if community.community_id in touched
            )

        current_pages = {path.name for path in self._communities_dir.glob("*.md")}
        next_pages: set[str] = set()

        for community in communities:
            page_name = f"{community.community_id}.md"
            next_pages.add(page_name)
            page_path = self._communities_dir / page_name
            content = self._render_community_page(community)
            if self._write_if_changed(page_path, content):
                result.pages_written += 1
            else:
                result.pages_skipped += 1

        for stale_name in sorted(current_pages - next_pages):
            stale_path = self._communities_dir / stale_name
            if stale_path.exists():
                stale_path.unlink()
                result.pages_removed += 1

        index_content = self._render_index(communities, god_nodes)
        if self._write_if_changed(self._index_path, index_content):
            result.pages_written += 1
        else:
            result.pages_skipped += 1

        god_nodes_content = self._render_god_nodes(god_nodes)
        if self._write_if_changed(self._god_nodes_path, god_nodes_content):
            result.pages_written += 1
        else:
            result.pages_skipped += 1

        self._append_log(result, update=update)
        result.pages_written += 1  # append-only log always changes
        result.community_count = len(communities)
        return result

    def analyze(self) -> dict:
        """Return graph-community analysis without writing wiki files."""
        facts = self._load_facts()

        adjacency: dict[str, set[str]] = defaultdict(set)
        nodes: set[str] = set()
        for fact in facts:
            subject = fact["subject"]
            obj = fact["object"]
            nodes.add(subject)
            nodes.add(obj)
            if subject != obj:
                adjacency[subject].add(obj)
                adjacency[obj].add(subject)
            else:
                adjacency.setdefault(subject, set())

        bridge_nodes = self._find_bridge_nodes(nodes, adjacency)
        communities = self._detect_communities(nodes, adjacency, bridge_nodes=bridge_nodes)
        entity_to_community = {
            entity: community.community_id
            for community in communities
            for entity in community.entities
        }
        degrees = {node: len(adjacency.get(node, set())) for node in nodes}

        facts_by_community: dict[str, list[dict]] = defaultdict(list)
        cross_facts_by_community: dict[str, list[dict]] = defaultdict(list)
        backlinks: dict[str, set[str]] = defaultdict(set)

        for fact in facts:
            src = entity_to_community.get(fact["subject"])
            dst = entity_to_community.get(fact["object"])
            if not src or not dst:
                continue
            if src == dst:
                facts_by_community[src].append(fact)
            else:
                cross_facts_by_community[src].append(fact)
                cross_facts_by_community[dst].append(fact)
                backlinks[src].add(dst)
                backlinks[dst].add(src)

        god_nodes = self._detect_god_nodes(adjacency, entity_to_community, bridge_nodes)

        return {
            "facts": facts,
            "adjacency": {node: sorted(neighbors) for node, neighbors in adjacency.items()},
            "bridge_nodes": sorted(bridge_nodes),
            "communities": communities,
            "entity_to_community": entity_to_community,
            "degrees": degrees,
            "facts_by_community": facts_by_community,
            "cross_facts_by_community": cross_facts_by_community,
            "backlinks": backlinks,
            "god_nodes": god_nodes,
        }

    def read_community(self, community_id: str) -> Optional[str]:
        """Read a generated community page by its identifier."""
        name = community_id if community_id.endswith(".md") else f"{community_id}.md"
        path = self._communities_dir / name
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def _load_facts(self) -> List[dict]:
        """Load active facts from the underlying KG connection."""
        cur = self._kg._conn.execute(
            "SELECT * FROM triples WHERE invalidated_at IS NULL ORDER BY created_at ASC"
        )
        return [{key: row[key] for key in row.keys()} for row in cur.fetchall()]

    def _detect_communities(
        self,
        nodes: Set[str],
        adjacency: Dict[str, Set[str]],
        bridge_nodes: Set[str] | None = None,
    ) -> List[CommunitySummary]:
        if not nodes:
            return []

        bridge_nodes = bridge_nodes or set()
        core_nodes = sorted(node for node in nodes if node not in bridge_nodes)
        labels = {node: node for node in core_nodes}
        ordered_nodes = sorted(core_nodes, key=lambda node: (-len(adjacency.get(node, set())), node.lower()))

        for _ in range(25):
            changed = False
            label_weights = Counter(labels.values())
            for node in ordered_nodes:
                neighbors = {neighbor for neighbor in adjacency.get(node, set()) if neighbor in labels}
                if not neighbors:
                    continue
                counts = Counter(labels[neighbor] for neighbor in neighbors)
                if not counts:
                    continue
                best_count = max(counts.values())
                candidates = [label for label, count in counts.items() if count == best_count]
                current = labels[node]
                if current in candidates:
                    best = current
                else:
                    best = min(
                        candidates,
                        key=lambda label: (-label_weights[label], label.lower()),
                    )
                if best != current:
                    labels[node] = best
                    changed = True
            if not changed:
                break

        grouped: dict[str, list[str]] = defaultdict(list)
        for node, label in labels.items():
            grouped[label].append(node)
        for node in sorted(bridge_nodes, key=str.lower):
            grouped[f"bridge::{node}"] = [node]

        communities: list[CommunitySummary] = []
        for entities in grouped.values():
            sorted_entities = sorted(entities, key=str.lower)
            cid = f"community-{self._community_hash(sorted_entities)}"
            communities.append(CommunitySummary(community_id=cid, entities=sorted_entities))

        communities.sort(key=lambda community: (-len(community.entities), community.community_id))
        return communities

    def _find_bridge_nodes(
        self,
        nodes: Set[str],
        adjacency: Dict[str, Set[str]],
    ) -> Set[str]:
        bridge_nodes: set[str] = set()
        for candidate in nodes:
            neighbors = adjacency.get(candidate, set())
            if len(neighbors) < 3:
                continue
            remaining = set(neighbors)
            components = 0
            while remaining:
                start = remaining.pop()
                stack = [start]
                seen = {start}
                while stack:
                    node = stack.pop()
                    for neighbor in adjacency.get(node, set()):
                        if neighbor == candidate or neighbor in seen or neighbor not in neighbors:
                            continue
                        seen.add(neighbor)
                        stack.append(neighbor)
                remaining -= seen
                components += 1
            if components >= 3:
                bridge_nodes.add(candidate)
        return bridge_nodes

    def _detect_god_nodes(
        self,
        adjacency: Dict[str, Set[str]],
        entity_to_community: Dict[str, str],
        bridge_nodes: Set[str],
    ) -> Dict[str, List[str]]:
        god_nodes: dict[str, list[str]] = {}
        for entity in bridge_nodes:
            neighbors = adjacency.get(entity, set())
            touched = {
                entity_to_community.get(neighbor)
                for neighbor in neighbors
                if entity_to_community.get(neighbor)
            }
            touched.discard(entity_to_community.get(entity))
            if len(touched) >= 3:
                god_nodes[entity] = sorted(touched)
        return god_nodes

    def _render_index(
        self,
        communities: List[CommunitySummary],
        god_nodes: Dict[str, List[str]],
    ) -> str:
        lines = [
            "# Graph Wiki Index",
            "",
            "> Auto-generated catalog of graph communities.",
            "",
        ]
        if not communities:
            lines.extend([
                "No graph communities yet.",
                "",
                "Add graph facts with `memos kg-add`, then run `memos wiki-graph`.",
            ])
            return "\n".join(lines) + "\n"

        for community in communities:
            tops = ", ".join(community.top_entities) if community.top_entities else "n/a"
            lines.append(
                f"- [[communities/{community.community_id}.md|{community.community_id}]] "
                f"— {len(community.entities)} entities, {len(community.facts)} facts, top: {tops}"
            )

        lines.extend([
            "",
            "## Navigation",
            "",
            f"- [[god-nodes.md|God Nodes]] — {len(god_nodes)} entities spanning 3+ communities",
            f"- [[log.md|Activity Log]] — build history",
        ])
        return "\n".join(lines) + "\n"

    def _render_community_page(self, community: CommunitySummary) -> str:
        top_entities = ", ".join(community.top_entities) if community.top_entities else "n/a"
        lines = [
            "---",
            f'community_id: "{community.community_id}"',
            f"entity_count: {len(community.entities)}",
            f"fact_count: {len(community.facts)}",
            "top_entities:",
        ]
        for entity in community.top_entities:
            lines.append(f'  - "{entity}"')
        lines.extend([
            "backlinks:",
        ])
        for backlink in community.backlinks:
            lines.append(f'  - "{backlink}"')
        lines.extend([
            "god_nodes:",
        ])
        for node in community.god_nodes:
            lines.append(f'  - "{node}"')
        lines.extend([
            f'generated_at: "{time.strftime("%Y-%m-%d %H:%M:%S")}"',
            "---",
            "",
            f"# Community {community.community_id}",
            "",
            "## Overview",
            "",
            f"- Entities: {len(community.entities)}",
            f"- Facts: {len(community.facts)}",
            f"- Top entities: {top_entities}",
            "",
            "## Entities",
            "",
        ])
        for entity in community.entities:
            lines.append(f"- {entity}")

        lines.extend(["", "## Facts", ""])
        if community.facts:
            for fact in community.facts:
                lines.append(self._format_fact(fact))
        else:
            lines.append("- No intra-community facts yet.")

        lines.extend(["", "## Backlinks", ""])
        if community.backlinks:
            for backlink in community.backlinks:
                lines.append(f"- [[{backlink}]]")
        else:
            lines.append("- No cross-community backlinks.")

        lines.extend(["", "## Boundary Facts", ""])
        if community.cross_facts:
            for fact in community.cross_facts[:20]:
                lines.append(self._format_fact(fact))
        else:
            lines.append("- No boundary facts.")

        if community.god_nodes:
            lines.extend(["", "## God Nodes", ""])
            for node in community.god_nodes:
                lines.append(f"- [[god-nodes.md|{node}]]")

        return "\n".join(lines) + "\n"

    def _render_god_nodes(self, god_nodes: Dict[str, List[str]]) -> str:
        lines = [
            "# God Nodes",
            "",
            "> Entities touching three or more graph communities.",
            "",
        ]
        if not god_nodes:
            lines.append("No god nodes detected.")
            return "\n".join(lines) + "\n"

        for entity, communities in sorted(god_nodes.items()):
            links = ", ".join(f"[[communities/{community}.md|{community}]]" for community in communities)
            lines.append(f"- **{entity}** → {links}")
        return "\n".join(lines) + "\n"

    def _append_log(self, result: GraphWikiResult, update: bool) -> None:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        mode = "update" if update else "build"
        entry = (
            f"- {timestamp} — {mode} communities={result.community_count} facts={result.facts_indexed} "
            f"written={result.pages_written} skipped={result.pages_skipped} removed={result.pages_removed} "
            f"god_nodes={result.god_nodes}\n"
        )
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(entry)

    def _write_if_changed(self, path: Path, content: str) -> bool:
        if path.exists() and path.read_text(encoding="utf-8") == content:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return True

    def _community_hash(self, entities: List[str]) -> str:
        digest = hashlib.sha1("\n".join(sorted(entities, key=str.lower)).encode("utf-8")).hexdigest()
        return digest[:8]

    def _format_fact(self, fact: dict) -> str:
        return f"- {fact['subject']} --{fact['predicate']}--> {fact['object']}"
