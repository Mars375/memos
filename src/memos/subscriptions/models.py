"""Subscription models and filter matching helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional
from uuid import uuid4
import time


def _normalize(values: Optional[Iterable[str]]) -> tuple[str, ...]:
    if not values:
        return ()
    if isinstance(values, str):
        values = [v.strip() for v in values.split(",")]
    cleaned = {str(v).strip() for v in values if str(v).strip()}
    return tuple(sorted(cleaned))


@dataclass(frozen=True, slots=True)
class SubscriptionFilter:
    """Filter criteria for an event subscription."""

    event_types: tuple[str, ...] = ()
    namespaces: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    @classmethod
    def from_options(
        cls,
        *,
        event_types: Optional[Iterable[str]] = None,
        namespaces: Optional[Iterable[str]] = None,
        tags: Optional[Iterable[str]] = None,
    ) -> "SubscriptionFilter":
        return cls(
            event_types=_normalize(event_types),
            namespaces=_normalize(namespaces),
            tags=_normalize(tags),
        )

    def is_empty(self) -> bool:
        return not (self.event_types or self.namespaces or self.tags)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_types": list(self.event_types),
            "namespaces": list(self.namespaces),
            "tags": list(self.tags),
        }

    def matches(self, event: Any) -> bool:
        event_type = getattr(event, "type", None)
        namespace = getattr(event, "namespace", "") or ""
        data = getattr(event, "data", {}) or {}

        if self.event_types and "*" not in self.event_types and event_type not in self.event_types:
            return False
        if self.namespaces and namespace not in self.namespaces:
            return False
        if self.tags:
            event_tags = _extract_tags(data)
            if not event_tags:
                return False
            if not set(self.tags).intersection(event_tags):
                return False
        return True


@dataclass(slots=True)
class SubscriptionRecord:
    """A live subscription entry."""

    id: str = field(default_factory=lambda: str(uuid4()))
    kind: str = "callback"  # callback | queue
    filters: SubscriptionFilter = field(default_factory=SubscriptionFilter)
    created_at: float = field(default_factory=time.time)
    active: bool = True
    label: str = ""
    queue: Any = None
    handler: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "filters": self.filters.to_dict(),
            "created_at": self.created_at,
            "active": self.active,
            "label": self.label,
        }


def _extract_tags(data: dict[str, Any]) -> set[str]:
    raw = data.get("tags")
    tags: set[str] = set()
    if isinstance(raw, str):
        tags.add(raw)
    elif isinstance(raw, (list, tuple, set)):
        tags.update(str(tag).strip() for tag in raw if str(tag).strip())

    nested = data.get("memory")
    if isinstance(nested, dict):
        extra = nested.get("tags")
        if isinstance(extra, str):
            tags.add(extra)
        elif isinstance(extra, (list, tuple, set)):
            tags.update(str(tag).strip() for tag in extra if str(tag).strip())

    return tags
