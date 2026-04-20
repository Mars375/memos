"""Tag facade — tag listing, renaming, and deletion."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class TagFacade:
    """Mixin providing tag management operations for the MemOS nucleus."""

    def list_tags(self, sort: str = "count", limit: int = 0) -> list[tuple[str, int]]:
        """List all tags with their memory counts.

        Args:
            sort: "count" (descending) or "name" (alphabetical).
            limit: Max tags to return. 0 = all.

        Returns:
            List of (tag, count) tuples.
        """
        self._check_acl("read")
        items = self._store.list_all(namespace=self._namespace)
        tag_counts: dict[str, int] = {}
        for item in items:
            for tag in item.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        if sort == "name":
            result = sorted(tag_counts.items(), key=lambda x: x[0])
        else:
            result = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)

        if limit > 0:
            result = result[:limit]
        return result

    def rename_tag(self, old_tag: str, new_tag: str) -> int:
        """Rename a tag across all memories.

        Args:
            old_tag: Tag name to replace.
            new_tag: New tag name.

        Returns:
            Number of memories updated.
        """
        self._check_acl("write")
        updated = 0
        old_lower = old_tag.lower()
        for item in self._store.list_all(namespace=self._namespace):
            tags_lower = [t.lower() for t in item.tags]
            if old_lower not in tags_lower:
                continue
            new_tags = [new_tag if t.lower() == old_lower else t for t in item.tags]
            item.tags = new_tags
            item.accessed_at = time.time()
            self._store.upsert(item, namespace=self._namespace)
            self._versioning.record_version(item, source="rename_tag")
            self._events.emit_sync(
                "tag_renamed",
                {
                    "id": item.id,
                    "old_tag": old_tag,
                    "new_tag": new_tag,
                },
                namespace=self._namespace,
            )
            updated += 1
        return updated

    def delete_tag(self, tag: str) -> int:
        """Delete a tag from all memories without removing the memories.

        Args:
            tag: Tag name to remove.

        Returns:
            Number of memories updated.
        """
        self._check_acl("write")
        updated = 0
        tag_lower = tag.lower()
        for item in self._store.list_all(namespace=self._namespace):
            tags_lower = [t.lower() for t in item.tags]
            if tag_lower not in tags_lower:
                continue
            new_tags = [t for t in item.tags if t.lower() != tag_lower]
            item.tags = new_tags
            item.accessed_at = time.time()
            self._store.upsert(item, namespace=self._namespace)
            self._versioning.record_version(item, source="delete_tag")
            self._events.emit_sync(
                "tag_deleted",
                {
                    "id": item.id,
                    "tag": tag,
                },
                namespace=self._namespace,
            )
            updated += 1
        return updated
