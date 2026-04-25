from __future__ import annotations

from ._brain_models import KGFact, ScoredMemory, WikiHit
from ._constants import DEFAULT_SNIPPET_WINDOW


def build_context(
    *,
    query: str,
    entities: list[str],
    memories: list[ScoredMemory],
    wiki_pages: list[WikiHit],
    kg_facts: list[KGFact],
    max_chars: int,
) -> str:
    lines = [f"Query: {query}"]
    if entities:
        lines.append("Entities: " + ", ".join(entities[:8]))
    lines.append("")
    lines.append("Fused context:")

    buckets: dict[str, list[tuple[float, str]]] = {
        "memory": [(item.score, f"[memory {item.score:.2f}] {item.content}") for item in memories[:5]],
        "wiki": [(item.score, f"[wiki {item.entity}] {item.snippet}") for item in wiki_pages[:5]],
        "kg": [
            (
                item.score,
                f"[kg {item.confidence_label}] {item.subject} -{item.predicate}-> {item.object}",
            )
            for item in kg_facts[:5]
        ],
    }

    while any(buckets.values()):
        ordered_sources = sorted(
            (source for source, items in buckets.items() if items),
            key=lambda source: buckets[source][0][0],
            reverse=True,
        )
        for source in ordered_sources:
            _, text = buckets[source].pop(0)
            candidate = lines + [f"- {text}"]
            rendered = "\n".join(candidate)
            if len(rendered) > max_chars:
                return "\n".join(lines)
            lines.append(f"- {text}")
    return "\n".join(lines)


def snippet(content: str, query: str, window: int = DEFAULT_SNIPPET_WINDOW) -> str:
    lowered = content.lower()
    query_lower = query.lower()
    idx = lowered.find(query_lower)
    if idx == -1:
        return content[: window * 2].replace("\n", " ").strip()
    start = max(0, idx - window)
    end = min(len(content), idx + len(query) + window)
    return content[start:end].replace("\n", " ").strip()
