"""Namespace facade — namespace listing and ACL management."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from .namespaces.acl import Role

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class NamespaceFacade:
    """Mixin providing namespace management operations for the MemOS nucleus."""

    def list_namespaces(self) -> list[str]:
        """List all non-default namespaces."""
        return self._store.list_namespaces()

    # ── Namespace ACL Management ───────────────────────────

    def grant_namespace_access(
        self,
        agent_id: str,
        namespace: str,
        role: str | Role,
        *,
        granted_by: str = "",
        expires_at: Optional[float] = None,
    ) -> dict[str, Any]:
        """Grant an agent access to a namespace.

        Args:
            agent_id: Unique identifier for the agent.
            namespace: Target namespace.
            role: Access role ("owner", "writer", "reader", "denied").
            granted_by: ID of the agent performing the grant.
            expires_at: Optional Unix timestamp when access expires.

        Returns:
            The created policy as a dict.
        """
        if isinstance(role, str):
            role = Role(role)
        policy = self._acl.grant(
            agent_id,
            namespace,
            role,
            granted_by=granted_by,
            expires_at=expires_at,
        )
        self._events.emit_sync(
            "acl_granted",
            {
                "agent_id": agent_id,
                "namespace": namespace,
                "role": role.value,
            },
            namespace=namespace,
        )
        return policy.to_dict()

    def revoke_namespace_access(
        self,
        agent_id: str,
        namespace: str,
    ) -> bool:
        """Revoke an agent's access to a namespace.

        Returns True if a policy was revoked, False if none existed.
        """
        removed = self._acl.revoke(agent_id, namespace)
        if removed:
            self._events.emit_sync(
                "acl_revoked",
                {
                    "agent_id": agent_id,
                    "namespace": namespace,
                },
                namespace=namespace,
            )
            return True
        return False

    def list_namespace_policies(
        self,
        namespace: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """List ACL policies, optionally filtered by namespace."""
        return [p.to_dict() for p in self._acl.list_policies(namespace=namespace)]

    def namespace_acl_stats(self) -> dict[str, Any]:
        """Get namespace ACL statistics."""
        return self._acl.stats()
