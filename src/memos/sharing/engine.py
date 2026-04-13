"""Sharing engine — core logic for multi-agent memory sharing.

Manages the full lifecycle of memory shares:
  offer → accept/reject → active use → revoke/expire

Thread-safe, backed by an in-memory store with optional persistence
via the EventBus for real-time notification of share state changes.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

from .models import (
    MemoryEnvelope,
    SharePermission,
    ShareRequest,
    ShareScope,
    ShareStatus,
)


class SharingEngine:
    """Multi-agent memory sharing manager.

    Manages share requests, lifecycle transitions, and memory envelope
    creation for inter-agent exchange. Thread-safe.

    Usage::

        engine = SharingEngine()
        req = engine.offer("agent-a", "agent-b", scope=ShareScope.TAG, scope_key="research")
        engine.accept(req.id, "agent-b")
        envelope = engine.export("agent-a", "agent-b", memos_instance)
    """

    def __init__(self) -> None:
        self._shares: dict[str, ShareRequest] = {}
        self._lock = threading.RLock()

    # ── Offer / Accept / Reject / Revoke ────────────────────

    def offer(
        self,
        source_agent: str,
        target_agent: str,
        *,
        scope: ShareScope = ShareScope.ITEMS,
        scope_key: str = "",
        permission: SharePermission = SharePermission.READ,
        expires_at: Optional[float] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ShareRequest:
        """Create a new share offer (PENDING status).

        Returns the ShareRequest with generated ID.
        """
        with self._lock:
            req = ShareRequest(
                source_agent=source_agent,
                target_agent=target_agent,
                scope=scope,
                scope_key=scope_key,
                permission=permission,
                status=ShareStatus.PENDING,
                expires_at=expires_at,
                metadata=metadata or {},
            )
            self._shares[req.id] = req
            return req

    def accept(self, share_id: str, acceptor: str) -> ShareRequest:
        """Accept a pending share.

        Only the target_agent can accept. Raises ValueError if invalid.
        """
        with self._lock:
            req = self._get_valid(share_id)
            if req.target_agent != acceptor:
                raise ValueError(f"Only target agent '{req.target_agent}' can accept this share")
            if req.status != ShareStatus.PENDING:
                raise ValueError(f"Share is {req.status.value}, not pending")
            req.status = ShareStatus.ACCEPTED
            req.accepted_at = time.time()
            return req

    def reject(self, share_id: str, rejector: str) -> ShareRequest:
        """Reject a pending share.

        Only the target_agent can reject.
        """
        with self._lock:
            req = self._get_valid(share_id)
            if req.target_agent != rejector:
                raise ValueError(f"Only target agent '{req.target_agent}' can reject this share")
            if req.status != ShareStatus.PENDING:
                raise ValueError(f"Share is {req.status.value}, not pending")
            req.status = ShareStatus.REJECTED
            return req

    def revoke(self, share_id: str, revoker: str) -> ShareRequest:
        """Revoke an accepted or pending share.

        Only the source_agent can revoke.
        """
        with self._lock:
            req = self._get_valid(share_id)
            if req.source_agent != revoker:
                raise ValueError(f"Only source agent '{req.source_agent}' can revoke this share")
            if req.status not in (ShareStatus.PENDING, ShareStatus.ACCEPTED):
                raise ValueError(f"Cannot revoke share in {req.status.value} state")
            req.status = ShareStatus.REVOKED
            return req

    # ── Queries ─────────────────────────────────────────────

    def get(self, share_id: str) -> Optional[ShareRequest]:
        """Get a share by ID (checks expiry)."""
        with self._lock:
            req = self._shares.get(share_id)
            if req is None:
                return None
            self._check_expiry(req)
            return req

    def list_shares(
        self,
        agent: Optional[str] = None,
        status: Optional[ShareStatus] = None,
    ) -> list[ShareRequest]:
        """List shares, optionally filtered by agent and status."""
        with self._lock:
            self._gc_expired()
            results = list(self._shares.values())
            if agent:
                results = [s for s in results if s.source_agent == agent or s.target_agent == agent]
            if status:
                results = [s for s in results if s.status == status]
            return sorted(results, key=lambda s: s.created_at, reverse=True)

    def list_shared_with(self, agent: str) -> list[ShareRequest]:
        """List active shares where agent is the recipient."""
        with self._lock:
            self._gc_expired()
            return [s for s in self._shares.values() if s.target_agent == agent and s.status == ShareStatus.ACCEPTED]

    def list_shared_by(self, agent: str) -> list[ShareRequest]:
        """List active shares where agent is the source."""
        with self._lock:
            self._gc_expired()
            return [s for s in self._shares.values() if s.source_agent == agent and s.status == ShareStatus.ACCEPTED]

    def get_accepted_permissions(self, source_agent: str, target_agent: str) -> Optional[SharePermission]:
        """Get the permission level for an accepted share."""
        with self._lock:
            for req in self._shares.values():
                if (
                    req.source_agent == source_agent
                    and req.target_agent == target_agent
                    and req.status == ShareStatus.ACCEPTED
                ):
                    self._check_expiry(req)
                    if req.status == ShareStatus.ACCEPTED:
                        return req.permission
            return None

    def can_read(self, source_agent: str, target_agent: str) -> bool:
        """Check if target_agent has any read access to source_agent's memories."""
        perm = self.get_accepted_permissions(source_agent, target_agent)
        return perm is not None

    def can_write(self, source_agent: str, target_agent: str) -> bool:
        """Check if target_agent has write access."""
        perm = self.get_accepted_permissions(source_agent, target_agent)
        return perm in (SharePermission.READ_WRITE, SharePermission.ADMIN)

    # ── Export / Import ─────────────────────────────────────

    def export_envelope(
        self,
        share_id: str,
        items: list[Any],
    ) -> MemoryEnvelope:
        """Create a MemoryEnvelope for an accepted share."""
        with self._lock:
            req = self._get_valid(share_id)
            if req.status != ShareStatus.ACCEPTED:
                raise ValueError("Can only export accepted shares")
            return MemoryEnvelope.from_items(
                items,
                source_agent=req.source_agent,
                target_agent=req.target_agent,
                share_id=req.id,
                scope=req.scope,
            )

    @staticmethod
    def import_envelope(envelope: MemoryEnvelope) -> list[dict[str, Any]]:
        """Validate and extract memories from an envelope.

        Returns the list of memory dicts ready for storage.
        Raises ValueError if envelope fails validation.
        """
        if not envelope.validate():
            raise ValueError("Envelope checksum validation failed")
        if not envelope.memories:
            raise ValueError("Envelope contains no memories")
        return envelope.memories

    # ── Stats ───────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Get sharing statistics."""
        with self._lock:
            self._gc_expired()
            status_counts: dict[str, int] = {}
            agents = set()
            for req in self._shares.values():
                s = req.status.value
                status_counts[s] = status_counts.get(s, 0) + 1
                agents.add(req.source_agent)
                agents.add(req.target_agent)
            return {
                "total_shares": len(self._shares),
                "active_shares": status_counts.get("accepted", 0),
                "pending_shares": status_counts.get("pending", 0),
                "total_agents": len(agents),
                "status_distribution": status_counts,
            }

    # ── Maintenance ─────────────────────────────────────────

    def cleanup_expired(self) -> int:
        """Remove expired shares. Returns count removed."""
        with self._lock:
            return self._gc_expired()

    def clear(self) -> None:
        """Remove all shares."""
        with self._lock:
            self._shares.clear()

    # ── Internal ────────────────────────────────────────────

    def _get_valid(self, share_id: str) -> ShareRequest:
        """Get a share or raise ValueError."""
        req = self._shares.get(share_id)
        if req is None:
            raise ValueError(f"Share '{share_id}' not found")
        self._check_expiry(req)
        return req

    def _check_expiry(self, req: ShareRequest) -> None:
        """Mark a share as expired if its TTL has passed."""
        if req.expires_at is not None and req.status == ShareStatus.ACCEPTED:
            if time.time() > req.expires_at:
                req.status = ShareStatus.EXPIRED

    def _gc_expired(self) -> int:
        """Garbage-collect expired shares. Returns count cleaned."""
        now = time.time()
        expired_ids = []
        for sid, req in self._shares.items():
            if req.expires_at is not None and now > req.expires_at:
                if req.status in (ShareStatus.ACCEPTED, ShareStatus.PENDING):
                    req.status = ShareStatus.EXPIRED
                    expired_ids.append(sid)
        for sid in expired_ids:
            del self._shares[sid]
        return len(expired_ids)
