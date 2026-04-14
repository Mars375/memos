"""Knowledge Graph ↔ Memory bridge."""

from __future__ import annotations

import re
from typing import Any

from ._constants import DEFAULT_IMPORTANCE, DEFAULT_INFERENCE_MAX_DEPTH
from .knowledge_graph import KnowledgeGraph

_ENTITY_PATTERN = re.compile(r"\b(?:[A-Z][\w.-]*(?:\s+[A-Z][\w.-]*)+|[A-Z]{2,})\b")

_FACT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "is",
        re.compile(
            r"(?P<subject>[A-Z][\w.-]*(?:\s+[A-Z][\w.-]*)*)\s+is\s+(?P<object>[A-Z][\w.-]*(?:\s+[A-Z][\w.-]*)*|[\w.-]+)",
            re.I,
        ),
    ),
    (
        "works_at",
        re.compile(
            r"(?P<subject>[A-Z][\w.-]*(?:\s+[A-Z][\w.-]*)*)\s+works\s+at\s+(?P<object>[A-Z][\w.&-]*(?:\s+[A-Z][\w.&-]*)*)",
            re.I,
        ),
    ),
    ("arrow", re.compile(r"(?P<subject>[^→\n]{1,80}?)\s*→\s*(?P<object>[^.\n;]{1,120})")),
    ("from_to", re.compile(r"from:\s*(?P<subject>[^\n;]{1,80}?)\s+to:\s*(?P<object>[^.\n;]{1,120})", re.I)),
]


class KGBridge:
    """Connect MemOS memories to the temporal knowledge graph."""

    def __init__(self, memos: Any, kg: KnowledgeGraph | None = None) -> None:
        self._memos = memos
        self._kg = kg or KnowledgeGraph()

    @property
    def kg(self) -> KnowledgeGraph:
        return self._kg

    def close(self) -> None:
        self._kg.close()

    def recall_enriched(
        self,
        query: str,
        top: int = 10,
        filter_tags: list[str] | None = None,
        min_score: float = 0.0,
        filter_after: float | None = None,
        filter_before: float | None = None,
    ) -> dict[str, Any]:
        """Recall memories and augment them with KG facts linked to detected entities."""
        results = list(
            self._memos.recall(
                query,
                top=top,
                filter_tags=filter_tags,
                min_score=min_score,
                filter_after=filter_after,
                filter_before=filter_before,
            )
        )
        entities = self._detect_entities(query, results)
        facts = self._collect_facts(entities)
        return {
            "query": query,
            "entities": entities,
            "memories": [self._serialize_recall_result(r) for r in results],
            "facts": facts,
            "memory_count": len(results),
            "fact_count": len(facts),
        }

    def learn_and_extract(
        self,
        content: str,
        tags: list[str] | None = None,
        importance: float = DEFAULT_IMPORTANCE,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Learn a memory and extract simple KG facts from the content."""
        item = self._memos.learn(
            content,
            tags=tags,
            importance=importance,
            metadata=metadata,
        )
        facts = []
        for subject, predicate, obj in self.extract_facts(content):
            fact_id = self._kg.add_fact(
                subject=subject,
                predicate=predicate,
                object=obj,
                confidence_label="AMBIGUOUS",
                source=f"memos:{item.id}",
            )
            facts.append(
                {
                    "id": fact_id,
                    "subject": subject,
                    "predicate": predicate,
                    "object": obj,
                    "confidence_label": "AMBIGUOUS",
                    "source": f"memos:{item.id}",
                }
            )
        return {
            "memory": self._serialize_memory(item),
            "facts": facts,
            "fact_count": len(facts),
        }

    def infer(
        self,
        predicate: str,
        inferred_predicate: str | None = None,
        max_depth: int = DEFAULT_INFERENCE_MAX_DEPTH,
    ) -> list[str]:
        """Run transitive inference on *predicate* and return new fact IDs.

        Example: if A-emploie->B and B-emploie->C, creates A-emploie_indirect->C
        with confidence_label='INFERRED'.
        """
        return self._kg.infer_transitive(
            predicate,
            inferred_predicate=inferred_predicate,
            max_depth=max_depth,
        )

    def link_fact_to_memory(self, fact_id: str, memory_id: str) -> str:
        """Create an explicit bridge fact linking a KG fact to a memory."""
        bridge_id = self._kg.add_fact(
            subject=f"fact:{fact_id}",
            predicate="linked_to_memory",
            object=f"memory:{memory_id}",
            source=f"memos:{memory_id}",
        )
        return bridge_id

    def _detect_entities(self, query: str, results: list[Any]) -> list[str]:
        candidates: list[str] = []
        seen: set[str] = set()

        def add(entity: str) -> None:
            entity = " ".join(entity.split()).strip(" ,.;:\t\n")
            if not entity:
                return
            key = entity.lower()
            if key not in seen:
                seen.add(key)
                candidates.append(entity)

        for hit in self._kg.search_entities(query):
            add(hit["name"])

        for source in [query, *[r.item.content for r in results]]:
            for match in _ENTITY_PATTERN.findall(source):
                add(match)

        refined: list[str] = []
        refined_seen: set[str] = set()
        for entity in candidates:
            for hit in self._kg.search_entities(entity):
                name = hit["name"]
                if name.lower() not in refined_seen:
                    refined_seen.add(name.lower())
                    refined.append(name)
            if entity.lower() not in refined_seen:
                refined_seen.add(entity.lower())
                refined.append(entity)
        return refined

    def _collect_facts(self, entities: list[str]) -> list[dict[str, Any]]:
        facts: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for entity in entities:
            for fact in self._kg.query(entity):
                if fact["id"] in seen_ids:
                    continue
                seen_ids.add(fact["id"])
                facts.append(fact)
        facts.sort(key=lambda f: (f.get("created_at") or 0, f.get("id") or ""), reverse=True)
        return facts

    @staticmethod
    def extract_facts(content: str) -> list[tuple[str, str, str]]:
        """Extract a small set of subject-predicate-object triples from text."""
        facts: list[tuple[str, str, str]] = []
        for line in re.split(r"[\n\r]+", content):
            line = line.strip()
            if not line:
                continue
            for predicate, pattern in _FACT_PATTERNS:
                match = pattern.search(line)
                if not match:
                    continue
                subject = " ".join(match.group("subject").split()).strip(" ,.;:")
                obj = " ".join(match.group("object").split()).strip(" ,.;:")
                if subject and obj:
                    facts.append((subject, predicate, obj))
                    break
        return facts

    @staticmethod
    def _serialize_memory(item: Any) -> dict[str, Any]:
        return {
            "id": item.id,
            "content": item.content,
            "tags": list(item.tags),
            "importance": item.importance,
            "created_at": item.created_at,
            "accessed_at": getattr(item, "accessed_at", None),
            "access_count": getattr(item, "access_count", 0),
            "metadata": dict(getattr(item, "metadata", {}) or {}),
        }

    @staticmethod
    def _serialize_recall_result(result: Any) -> dict[str, Any]:
        item = result.item
        return {
            "id": item.id,
            "content": item.content,
            "tags": list(item.tags),
            "importance": item.importance,
            "score": result.score,
            "match_reason": getattr(result, "match_reason", ""),
            "created_at": item.created_at,
        }
