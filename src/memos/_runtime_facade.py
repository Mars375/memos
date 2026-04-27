"""Runtime identity, ACL, event, and analytics facade."""

from __future__ import annotations

from typing import Any

from .analytics import RecallAnalytics
from .events import EventBus
from .namespaces.acl import NamespaceACL


class RuntimeFacade:
    """Mixin providing runtime handles and event subscription helpers."""

    @property
    def namespace(self) -> str:
        return self._namespace

    @namespace.setter
    def namespace(self, value: str) -> None:
        self._namespace = value or ""

    @property
    def acl(self) -> NamespaceACL:
        """Access the namespace ACL for managing access control."""
        return self._acl

    def _check_acl(self, permission: str) -> None:
        """Check ACL permission for the current agent on the current namespace.

        Only enforces if agent_id is set via set_agent_id().
        Empty namespace bypasses ACL checks.
        """
        if not self._namespace or not hasattr(self, "_agent_id") or not self._agent_id:
            return
        self._acl.check(self._agent_id, self._namespace, permission)

    def set_agent_id(self, agent_id: str) -> None:
        """Set the agent identity for ACL checks.

        When set, all operations on namespaced memories will enforce
        the ACL permissions for this agent.

        Args:
            agent_id: Unique identifier for the agent.
        """
        self._agent_id: str = agent_id

    @property
    def events(self) -> EventBus:
        """Access the event bus for subscriptions."""
        return self._events

    @property
    def analytics(self) -> RecallAnalytics:
        """Access recall analytics."""
        return self._analytics

    def subscribe(
        self,
        callback,
        *,
        event_types: list[str] | None = None,
        namespaces: list[str] | None = None,
        tags: list[str] | None = None,
        label: str = "",
    ) -> str:
        """Subscribe to memory events with optional filters."""
        return self._events.subscribe_filtered(
            callback,
            event_types=event_types,
            namespaces=namespaces,
            tags=tags,
            label=label,
        )

    def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe from memory events by subscription ID."""
        return self._events.unsubscribe_subscription(subscription_id)

    def list_subscriptions(self) -> list[dict[str, Any]]:
        """List active event subscriptions."""
        return self._events.list_subscriptions()
