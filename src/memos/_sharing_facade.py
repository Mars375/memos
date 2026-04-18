"""Sharing facade for MemOS."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from ._constants import DEFAULT_IMPORTANCE
from .models import MemoryItem
from .sharing.engine import SharingEngine
from .sharing.models import MemoryEnvelope, SharePermission, ShareRequest, ShareScope, ShareStatus

if TYPE_CHECKING:
    from .sharing.engine import SharingEngine as SharingEngineType


class SharingFacade:
    """Mixin exposing sharing APIs on MemOS."""

    _sharing: "SharingEngineType"
    _store: Any
    _namespace: str

    def sharing(self) -> SharingEngine:
        """Access the sharing engine for multi-agent memory exchange."""
        return self._sharing

    def share_with(
        self,
        target_agent: str,
        *,
        scope: ShareScope = ShareScope.ITEMS,
        scope_key: str = "",
        permission: SharePermission = SharePermission.READ,
        expires_at: Optional[float] = None,
    ) -> ShareRequest:
        """Offer to share memories with another agent."""
        source = getattr(self, "_agent_id", "") or "default"
        return self._sharing.offer(
            source,
            target_agent,
            scope=scope,
            scope_key=scope_key,
            permission=permission,
            expires_at=expires_at,
        )

    def accept_share(self, share_id: str) -> ShareRequest:
        """Accept a pending share addressed to this agent."""
        agent = getattr(self, "_agent_id", "") or "default"
        return self._sharing.accept(share_id, agent)

    def reject_share(self, share_id: str) -> ShareRequest:
        """Reject a pending share addressed to this agent."""
        agent = getattr(self, "_agent_id", "") or "default"
        return self._sharing.reject(share_id, agent)

    def revoke_share(self, share_id: str) -> ShareRequest:
        """Revoke a share previously offered by this agent."""
        agent = getattr(self, "_agent_id", "") or "default"
        return self._sharing.revoke(share_id, agent)

    def export_shared(self, share_id: str) -> MemoryEnvelope:
        """Export memories for an accepted share as a portable envelope."""
        req = self._sharing.get(share_id)
        if req is None or req.status != ShareStatus.ACCEPTED:
            raise ValueError("Share not found or not accepted")
        items = self._resolve_share_scope(req)
        return self._sharing.export_envelope(share_id, items)

    def import_shared(self, envelope: MemoryEnvelope) -> list[MemoryItem]:
        """Import memories from a received envelope."""
        mem_dicts = SharingEngine.import_envelope(envelope)
        learned = []
        for md in mem_dicts:
            tags = md.get("tags", [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            importance = md.get("importance", DEFAULT_IMPORTANCE)
            item = self.learn(
                md.get("content", ""),
                tags=tags,
                importance=float(importance),
            )
            learned.append(item)
        return learned

    def list_shares(self, agent: Optional[str] = None, status: Optional[ShareStatus] = None) -> list[ShareRequest]:
        """List shares, optionally filtered by agent and status."""
        return self._sharing.list_shares(agent=agent, status=status)

    def sharing_stats(self) -> dict[str, Any]:
        """Get sharing statistics."""
        return self._sharing.stats()

    def _resolve_share_scope(self, req: ShareRequest) -> list[MemoryItem]:
        """Resolve memory items matching a share scope."""
        if req.scope == ShareScope.ITEMS:
            ids = [i.strip() for i in req.scope_key.split(",") if i.strip()]
            results = []
            for mid in ids:
                item = self._store.get(mid, namespace=self._namespace)
                if item is not None:
                    results.append(item)
            return results
        if req.scope == ShareScope.TAG:
            all_items = self._store.list_all(namespace=self._namespace)
            return [i for i in all_items if req.scope_key in i.tags]
        if req.scope == ShareScope.NAMESPACE:
            return self._store.list_all(namespace=self._namespace or req.scope_key)
        return []
