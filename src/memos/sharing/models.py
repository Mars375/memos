"""Data models for multi-agent memory sharing.

Provides structured types for sharing memories between agents:
- ShareRequest: intent to share memories (tracks lifecycle)
- MemoryEnvelope: portable exchange format for transport
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ShareStatus(Enum):
    """Lifecycle states for a share."""

    PENDING = "pending"  # Offered but not yet accepted
    ACCEPTED = "accepted"  # Active share
    REJECTED = "rejected"  # Recipient declined
    REVOKED = "revoked"  # Owner revoked access
    EXPIRED = "expired"  # TTL expired


class SharePermission(Enum):
    """Permission level granted to the recipient."""

    READ = "read"  # Recipient can recall shared memories
    READ_WRITE = "read_write"  # Recipient can recall + append
    ADMIN = "admin"  # Recipient can re-share (transitive)


class ShareScope(Enum):
    """What is being shared."""

    ITEMS = "items"  # Specific memory IDs
    TAG = "tag"  # All memories with a given tag
    NAMESPACE = "namespace"  # Full namespace


def _generate_share_id(source: str, target: str) -> str:
    """Generate a deterministic share ID."""
    raw = f"{source}:{target}:{time.time()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class ShareRequest:
    """A request to share memories with another agent.

    Created by the sharing agent, must be accepted by the recipient
    before memories become accessible.
    """

    id: str = ""
    source_agent: str = ""
    target_agent: str = ""
    scope: ShareScope = ShareScope.ITEMS
    scope_key: str = ""  # IDs (comma-sep), tag name, or namespace name
    permission: SharePermission = SharePermission.READ
    status: ShareStatus = ShareStatus.PENDING
    created_at: float = field(default_factory=time.time)
    accepted_at: Optional[float] = None
    expires_at: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            self.id = _generate_share_id(self.source_agent, self.target_agent)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "scope": self.scope.value,
            "scope_key": self.scope_key,
            "permission": self.permission.value,
            "status": self.status.value,
            "created_at": self.created_at,
            "accepted_at": self.accepted_at,
            "expires_at": self.expires_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ShareRequest:
        return cls(
            id=data.get("id", ""),
            source_agent=data["source_agent"],
            target_agent=data["target_agent"],
            scope=ShareScope(data.get("scope", "items")),
            scope_key=data.get("scope_key", ""),
            permission=SharePermission(data.get("permission", "read")),
            status=ShareStatus(data.get("status", "pending")),
            created_at=data.get("created_at", time.time()),
            accepted_at=data.get("accepted_at"),
            expires_at=data.get("expires_at"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class MemoryEnvelope:
    """Portable memory exchange format for inter-agent transfer.

    Contains memories, provenance metadata, and checksum for integrity.
    Can be serialized to/from JSON for transport over any medium
    (HTTP, file, message queue, etc.).
    """

    source_agent: str
    target_agent: str
    memories: list[dict[str, Any]] = field(default_factory=list)
    share_id: str = ""
    scope: ShareScope = ShareScope.ITEMS
    exported_at: float = field(default_factory=time.time)
    checksum: str = ""
    format_version: str = "1.0"

    def compute_checksum(self) -> str:
        """Compute a SHA-256 checksum over the memories payload."""
        payload = str(sorted(self.memories, key=lambda m: m.get("id", "")))
        return hashlib.sha256(payload.encode()).hexdigest()[:32]

    def validate(self) -> bool:
        """Validate envelope integrity (checksum if present)."""
        if not self.checksum:
            return True  # No checksum = skip validation
        return self.compute_checksum() == self.checksum

    def to_dict(self) -> dict[str, Any]:
        out_checksum = self.compute_checksum()
        return {
            "format_version": self.format_version,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "memories": self.memories,
            "share_id": self.share_id,
            "scope": self.scope.value,
            "exported_at": self.exported_at,
            "checksum": out_checksum,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryEnvelope:
        return cls(
            source_agent=data["source_agent"],
            target_agent=data["target_agent"],
            memories=data.get("memories", []),
            share_id=data.get("share_id", ""),
            scope=ShareScope(data.get("scope", "items")),
            exported_at=data.get("exported_at", time.time()),
            format_version=data.get("format_version", "1.0"),
            checksum=data.get("checksum", ""),
        )

    @classmethod
    def from_items(
        cls,
        items: list[Any],
        *,
        source_agent: str,
        target_agent: str,
        share_id: str = "",
        scope: ShareScope = ShareScope.ITEMS,
    ) -> MemoryEnvelope:
        """Create an envelope from MemoryItem objects."""
        mem_dicts = []
        for item in items:
            if hasattr(item, "to_dict"):
                mem_dicts.append(item.to_dict())
            elif hasattr(item, "__dict__"):
                mem_dicts.append(vars(item))
            else:
                mem_dicts.append(item)
        env = cls(
            source_agent=source_agent,
            target_agent=target_agent,
            memories=mem_dicts,
            share_id=share_id,
            scope=scope,
        )
        env.checksum = env.compute_checksum()
        return env
