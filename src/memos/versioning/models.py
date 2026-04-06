"""Data models for memory versioning."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from ..models import MemoryItem


@dataclass
class MemoryVersion:
    """Snapshot of a memory item at a specific point in time.

    Each time a memory is upserted, a new version is created preserving
    the full state of the item at that moment.
    """

    version_id: str          # "{item_id}#{version_number}"
    item_id: str             # The original memory item ID
    version_number: int      # Monotonically increasing (1, 2, 3, ...)
    content: str             # Content snapshot
    tags: list[str]          # Tags snapshot
    importance: float        # Importance snapshot
    metadata: dict[str, Any] # Metadata snapshot
    created_at: float        # When this version was recorded (= item modified time)
    source: str = "upsert"   # What caused this version: "upsert" | "learn" | "consolidate" | "import"

    def to_memory_item(self) -> MemoryItem:
        """Reconstruct a MemoryItem from this version snapshot."""
        return MemoryItem(
            id=self.item_id,
            content=self.content,
            tags=list(self.tags),
            importance=self.importance,
            created_at=self.created_at,
            accessed_at=self.created_at,
            access_count=0,
            metadata=dict(self.metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "version_id": self.version_id,
            "item_id": self.item_id,
            "version_number": self.version_number,
            "content": self.content,
            "tags": list(self.tags),
            "importance": self.importance,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryVersion:
        """Deserialize from a plain dict."""
        return cls(
            version_id=data["version_id"],
            item_id=data["item_id"],
            version_number=data["version_number"],
            content=data["content"],
            tags=data.get("tags", []),
            importance=data.get("importance", 0.5),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", time.time()),
            source=data.get("source", "upsert"),
        )

    @classmethod
    def from_item(
        cls,
        item: MemoryItem,
        version_number: int,
        source: str = "upsert",
    ) -> MemoryVersion:
        """Create a version snapshot from a MemoryItem."""
        return cls(
            version_id=f"{item.id}#{version_number}",
            item_id=item.id,
            version_number=version_number,
            content=item.content,
            tags=list(item.tags),
            importance=item.importance,
            metadata=dict(item.metadata),
            created_at=time.time(),
            source=source,
        )


@dataclass
class VersionDiff:
    """Difference between two versions of the same memory.

    Computed by comparing two MemoryVersion instances.
    """

    item_id: str
    from_version: int
    to_version: int
    changes: dict[str, Any]  # field -> {"from": old, "to": new}
    delta_seconds: float     # Time between versions

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "changes": self.changes,
            "delta_seconds": round(self.delta_seconds, 2),
        }

    @classmethod
    def between(cls, v_old: MemoryVersion, v_new: MemoryVersion) -> VersionDiff:
        """Compute diff between two versions of the same item."""
        if v_old.item_id != v_new.item_id:
            raise ValueError(
                f"Cannot diff versions of different items: "
                f"{v_old.item_id} vs {v_new.item_id}"
            )

        changes: dict[str, Any] = {}

        if v_old.content != v_new.content:
            changes["content"] = {"from": v_old.content, "to": v_new.content}

        if set(v_old.tags) != set(v_new.tags):
            changes["tags"] = {
                "from": list(v_old.tags),
                "to": list(v_new.tags),
                "added": list(set(v_new.tags) - set(v_old.tags)),
                "removed": list(set(v_old.tags) - set(v_new.tags)),
            }

        if v_old.importance != v_new.importance:
            changes["importance"] = {
                "from": v_old.importance,
                "to": v_new.importance,
            }

        old_meta = v_old.metadata or {}
        new_meta = v_new.metadata or {}
        if old_meta != new_meta:
            changes["metadata"] = {
                "from": old_meta,
                "to": new_meta,
                "added_keys": list(set(new_meta.keys()) - set(old_meta.keys())),
                "removed_keys": list(set(old_meta.keys()) - set(new_meta.keys())),
            }

        return cls(
            item_id=v_old.item_id,
            from_version=v_old.version_number,
            to_version=v_new.version_number,
            changes=changes,
            delta_seconds=abs(v_new.created_at - v_old.created_at),
        )
