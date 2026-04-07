"""Namespace Access Control List — RBAC for memory namespaces.

Provides role-based access control for memory namespaces, enabling
multi-agent systems to share a MemOS instance while maintaining
strict isolation and permission boundaries.

Roles:
    owner   — Full control: read, write, delete, manage access, delete namespace
    writer  — Can learn (write) and recall (read) memories
    reader  — Can only recall (read) memories
    denied  — Explicitly denied access (overrides other grants)

Usage::

    from memos.namespaces import NamespaceACL, Role

    acl = NamespaceACL()

    # Grant roles
    acl.grant("agent-alpha", "production", Role.OWNER)
    acl.grant("agent-beta", "production", Role.WRITER)
    acl.grant("agent-gamma", "production", Role.READER)

    # Check permissions
    acl.check("agent-beta", "production", "write")   # OK
    acl.check("agent-gamma", "production", "write")  # raises PermissionError

    # Query namespace membership
    acl.namespaces_for("agent-beta")  # ["production"]
    acl.agents_in("production")       # [("agent-alpha", "owner"), ...]
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Role(Enum):
    """Namespace access role."""

    OWNER = "owner"
    WRITER = "writer"
    READER = "reader"
    DENIED = "denied"


# Permission hierarchy: higher index = more permissions
_ROLE_ORDER = [Role.DENIED, Role.READER, Role.WRITER, Role.OWNER]
_ROLE_PERMISSIONS: dict[Role, set[str]] = {
    Role.OWNER: {"read", "write", "delete", "manage", "destroy"},
    Role.WRITER: {"read", "write", "delete"},
    Role.READER: {"read"},
    Role.DENIED: set(),
}


def _role_rank(role: Role) -> int:
    """Get the numeric rank of a role (higher = more permissions)."""
    return _ROLE_ORDER.index(role)


@dataclass
class NamespacePolicy:
    """Access policy for a single (agent, namespace) pair."""

    agent_id: str
    namespace: str
    role: Role
    granted_by: str = ""
    granted_at: float = 0.0
    expires_at: Optional[float] = None  # None = never expires

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "namespace": self.namespace,
            "role": self.role.value,
            "granted_by": self.granted_by,
            "granted_at": self.granted_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> NamespacePolicy:
        return cls(
            agent_id=data["agent_id"],
            namespace=data["namespace"],
            role=Role(data["role"]),
            granted_by=data.get("granted_by", ""),
            granted_at=data.get("granted_at", 0.0),
            expires_at=data.get("expires_at"),
        )


class NamespaceACL:
    """Thread-safe namespace access control manager.

    Manages role-based access control for memory namespaces.
    Supports granting, revoking, checking permissions, and
    querying namespace membership.

    All operations are thread-safe.
    """

    def __init__(self) -> None:
        self._policies: dict[tuple[str, str], NamespacePolicy] = {}  # (agent_id, namespace) -> policy
        self._lock = threading.RLock()

    # ── Grant / Revoke ──────────────────────────────────────

    def grant(
        self,
        agent_id: str,
        namespace: str,
        role: Role,
        *,
        granted_by: str = "",
        expires_at: Optional[float] = None,
    ) -> NamespacePolicy:
        """Grant a role to an agent on a namespace.

        If the agent already has a role on this namespace, it is updated.
        Returns the new policy.
        """
        import time as _time

        with self._lock:
            policy = NamespacePolicy(
                agent_id=agent_id,
                namespace=namespace,
                role=role,
                granted_by=granted_by,
                granted_at=_time.time(),
                expires_at=expires_at,
            )
            self._policies[(agent_id, namespace)] = policy
            return policy

    def revoke(self, agent_id: str, namespace: str) -> Optional[NamespacePolicy]:
        """Revoke an agent's access to a namespace.

        Returns the removed policy, or None if no policy existed.
        """
        with self._lock:
            return self._policies.pop((agent_id, namespace), None)

    def deny(self, agent_id: str, namespace: str) -> NamespacePolicy:
        """Explicitly deny access to a namespace.

        This sets the DENIED role, which overrides any other grants.
        """
        return self.grant(agent_id, namespace, Role.DENIED)

    # ── Permission Checks ───────────────────────────────────

    def get_role(self, agent_id: str, namespace: str) -> Optional[Role]:
        """Get the role of an agent on a namespace.

        Returns None if no policy exists (no explicit access).
        """
        with self._lock:
            policy = self._policies.get((agent_id, namespace))
            if policy is None:
                return None
            # Check expiration
            if policy.expires_at is not None:
                import time as _time
                if _time.time() > policy.expires_at:
                    # Auto-cleanup expired policy
                    self._policies.pop((agent_id, namespace), None)
                    return None
            return policy.role

    def has_permission(self, agent_id: str, namespace: str, permission: str) -> bool:
        """Check if an agent has a specific permission on a namespace.

        Returns False if no policy exists or if the role doesn't include the permission.
        """
        role = self.get_role(agent_id, namespace)
        if role is None:
            return False
        return permission in _ROLE_PERMISSIONS.get(role, set())

    def check(self, agent_id: str, namespace: str, permission: str) -> None:
        """Check permission and raise if denied.

        Raises:
            PermissionError: If the agent doesn't have the required permission.
        """
        role = self.get_role(agent_id, namespace)
        if role is None:
            raise PermissionError(
                f"Agent '{agent_id}' has no access to namespace '{namespace}'"
            )
        if role == Role.DENIED:
            raise PermissionError(
                f"Agent '{agent_id}' is explicitly denied access to namespace '{namespace}'"
            )
        if permission not in _ROLE_PERMISSIONS.get(role, set()):
            raise PermissionError(
                f"Agent '{agent_id}' (role={role.value}) lacks '{permission}' "
                f"permission on namespace '{namespace}'"
            )

    # ── Queries ─────────────────────────────────────────────

    def namespaces_for(self, agent_id: str) -> list[str]:
        """List all namespaces an agent has access to (excluding DENIED)."""
        with self._lock:
            result = []
            for (aid, ns), policy in self._policies.items():
                if aid == agent_id and policy.role != Role.DENIED:
                    if policy.expires_at is not None:
                        import time as _time
                        if _time.time() > policy.expires_at:
                            continue
                    result.append(ns)
            return sorted(result)

    def agents_in(self, namespace: str) -> list[tuple[str, str]]:
        """List all agents with access to a namespace.

        Returns list of (agent_id, role) tuples, excluding DENIED.
        """
        with self._lock:
            result = []
            for (aid, ns), policy in self._policies.items():
                if ns == namespace and policy.role != Role.DENIED:
                    if policy.expires_at is not None:
                        import time as _time
                        if _time.time() > policy.expires_at:
                            continue
                    result.append((aid, policy.role.value))
            return sorted(result, key=lambda x: x[0])

    def get_policy(self, agent_id: str, namespace: str) -> Optional[NamespacePolicy]:
        """Get the full policy for an (agent, namespace) pair."""
        with self._lock:
            policy = self._policies.get((agent_id, namespace))
            if policy and policy.expires_at is not None:
                import time as _time
                if _time.time() > policy.expires_at:
                    return None
            return policy

    def list_policies(self, namespace: Optional[str] = None) -> list[NamespacePolicy]:
        """List all policies, optionally filtered by namespace."""
        with self._lock:
            policies = list(self._policies.values())
            if namespace:
                policies = [p for p in policies if p.namespace == namespace]
            return policies

    # ── Stats ───────────────────────────────────────────────

    def stats(self) -> dict:
        """Get ACL statistics."""
        with self._lock:
            agents = set(aid for aid, _ in self._policies)
            namespaces = set(ns for _, ns in self._policies)
            role_counts: dict[str, int] = {}
            for policy in self._policies.values():
                r = policy.role.value
                role_counts[r] = role_counts.get(r, 0) + 1
            return {
                "total_policies": len(self._policies),
                "total_agents": len(agents),
                "total_namespaces": len(namespaces),
                "role_distribution": role_counts,
            }

    # ── Maintenance ─────────────────────────────────────────

    def cleanup_expired(self) -> int:
        """Remove all expired policies. Returns count removed."""
        import time as _time

        with self._lock:
            now = _time.time()
            expired = [
                key for key, policy in self._policies.items()
                if policy.expires_at is not None and now > policy.expires_at
            ]
            for key in expired:
                del self._policies[key]
            return len(expired)

    def clear(self) -> None:
        """Remove all policies."""
        with self._lock:
            self._policies.clear()
