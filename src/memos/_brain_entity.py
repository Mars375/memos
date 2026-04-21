from __future__ import annotations

from typing import Any

from ._brain_models import EntityDetail, EntityNeighbor, EntitySubgraph


class _BrainEntityMixin:
    _memos: Any
    _kg: Any
    _wiki: Any

    def entity_detail(
        self,
        entity: str,
        *,
        top_memories: int = 5,
        neighbor_limit: int = 12,
    ) -> EntityDetail:
        canonical = self._canonical_entity_name(entity)
        self._ensure_wiki_page(canonical)

        wiki_page = self._wiki.read_page(canonical) or ""
        memories = self._entity_memories(canonical, top=top_memories)
        kg_facts = self._entity_kg_facts(canonical)
        kg_neighbors = self._entity_neighbors(canonical, limit=neighbor_limit)
        backlinks = self._entity_backlinks(canonical)

        if not wiki_page:
            wiki_page = self._render_fallback_wiki(canonical, memories, kg_facts, backlinks)

        return EntityDetail(
            entity=canonical,
            wiki_page=wiki_page,
            memories=memories,
            kg_facts=kg_facts,
            kg_neighbors=kg_neighbors,
            backlinks=backlinks,
            community=self._community_for_entity(canonical),
        )

    def entity_subgraph(self, entity: str, depth: int = 2) -> EntitySubgraph:
        canonical = self._canonical_entity_name(entity)
        neighborhood = self._kg.neighbors(canonical, depth=depth, direction="both")
        nodes = [{"id": name, "label": name, "is_center": name == canonical} for name in neighborhood["nodes"]]
        edges = [
            {
                "id": edge["id"],
                "source": edge["subject"],
                "target": edge["object"],
                "predicate": edge["predicate"],
                "confidence": edge["confidence"],
                "confidence_label": edge.get("confidence_label", "EXTRACTED"),
            }
            for edge in neighborhood["edges"]
        ]
        return EntitySubgraph(
            center=canonical,
            depth=depth,
            nodes=nodes,
            edges=edges,
            layers=neighborhood["layers"],
        )

    def _canonical_entity_name(self, entity: str) -> str:
        entity = " ".join(entity.split()).strip()
        if not entity:
            return entity
        matches = self._kg.search_entities(entity)
        for hit in matches:
            if hit["name"].lower() == entity.lower():
                return hit["name"]
        page = next((page for page in self._wiki.list_pages() if page.entity.lower() == entity.lower()), None)
        if page:
            return page.entity
        return matches[0]["name"] if matches else entity

    def _ensure_wiki_page(self, entity: str) -> None:
        if self._wiki.read_page(entity):
            return
        self._wiki.update(force=False)

    def _entity_memories(self, entity: str, top: int) -> list[dict[str, Any]]:
        ranked: list[dict[str, Any]] = []
        seen: set[str] = set()
        db = self._wiki._get_db()
        try:
            rows = db.execute(
                "SELECT memory_id, snippet, added_at FROM entity_memories WHERE LOWER(entity_name)=LOWER(?) ORDER BY added_at DESC",
                (entity,),
            ).fetchall()
        finally:
            db.close()

        memory_ids = [row["memory_id"] for row in rows]

        if memory_ids:
            all_items = {
                item.id: item
                for item in self._memos._store.list_all(namespace=self._memos._namespace)
                if item.id in set(memory_ids)
            }
            for mid in memory_ids:
                item = all_items.get(mid)
                if item is None or item.id in seen:
                    continue
                seen.add(item.id)
                ranked.append(
                    {
                        "id": item.id,
                        "content": item.content,
                        "tags": list(item.tags),
                        "importance": float(item.importance),
                        "created_at": float(item.created_at),
                        "access_count": int(getattr(item, "access_count", 0)),
                        "source": "wiki_link",
                    }
                )

        if len(ranked) < top:
            entity_lower = entity.lower()
            for item in self._memos._store.list_all(namespace=self._memos._namespace):
                haystacks = [item.content.lower(), *[str(tag).lower() for tag in item.tags]]
                if entity_lower not in " ".join(haystacks) or item.id in seen:
                    continue
                seen.add(item.id)
                ranked.append(
                    {
                        "id": item.id,
                        "content": item.content,
                        "tags": list(item.tags),
                        "importance": float(item.importance),
                        "created_at": float(item.created_at),
                        "access_count": int(getattr(item, "access_count", 0)),
                        "source": "content_match",
                    }
                )
                if len(seen) >= top * 3:
                    break

        ranked.sort(
            key=lambda item: (-item["importance"], -item["created_at"], -item["access_count"]),
        )
        return ranked[:top]

    def _entity_kg_facts(self, entity: str) -> list[dict[str, Any]]:
        facts = self._kg.query(entity)
        facts.sort(key=lambda fact: (fact.get("created_at") or 0.0, fact.get("confidence") or 0.0), reverse=True)
        return facts

    def _entity_neighbors(self, entity: str, limit: int) -> list[EntityNeighbor]:
        edges = self._kg.neighbors(entity, depth=1, direction="both")["edges"]
        neighbor_meta: dict[str, dict[str, Any]] = {}
        for edge in edges:
            other = edge["object"] if edge["subject"] == entity else edge["subject"]
            meta = neighbor_meta.setdefault(other, {"count": 0, "predicates": set()})
            meta["count"] += 1
            meta["predicates"].add(edge["predicate"])
        ranked = [
            EntityNeighbor(
                entity=name,
                relation_count=meta["count"],
                predicates=sorted(meta["predicates"]),
            )
            for name, meta in neighbor_meta.items()
        ]
        ranked.sort(key=lambda item: (-item.relation_count, item.entity.lower()))
        return ranked[:limit]

    def _entity_backlinks(self, entity: str) -> list[str]:
        db = self._wiki._get_db()
        try:
            rows = db.execute(
                "SELECT target_entity FROM backlinks WHERE LOWER(source_entity)=LOWER(?) ORDER BY target_entity COLLATE NOCASE",
                (entity,),
            ).fetchall()
        finally:
            db.close()
        return [row["target_entity"] for row in rows]

    def _community_for_entity(self, entity: str) -> str | None:
        communities = self._kg.detect_communities()
        for community in communities:
            if entity in community["nodes"]:
                return community.get("id") or community.get("label")
        return None

    def _render_fallback_wiki(
        self,
        entity: str,
        memories: list[dict[str, Any]],
        kg_facts: list[dict[str, Any]],
        backlinks: list[str],
    ) -> str:
        lines = [f"# {entity}", "", "## Overview", ""]
        if memories:
            lines.append(memories[0]["content"])
        else:
            lines.append("No living wiki page yet for this entity.")
        lines.extend(["", "## Key Facts", ""])
        if kg_facts:
            for fact in kg_facts[:8]:
                lines.append(f"- {fact['subject']} -{fact['predicate']}-> {fact['object']}")
        else:
            lines.append("- No graph facts yet.")
        lines.extend(["", "## Backlinks", ""])
        if backlinks:
            lines.extend(f"- {name}" for name in backlinks[:12])
        else:
            lines.append("- No backlinks yet.")
        return "\n".join(lines)
