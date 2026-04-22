"""Structural regression tests for the NamespaceFacade mixin extraction.

Verifies that NamespaceFacade methods exist on MemOS via inheritance, have
correct signatures, and that delegation to the ACL engine works as expected.
"""

import inspect
from unittest.mock import MagicMock

from memos._namespace_facade import NamespaceFacade
from memos.core import MemOS
from memos.namespaces.acl import Role

NAMESPACE_METHODS = (
    "list_namespaces",
    "grant_namespace_access",
    "revoke_namespace_access",
    "list_namespace_policies",
    "namespace_acl_stats",
)


class TestNamespaceFacadeInheritance:
    def test_memos_inherits_namespace_facade(self):
        assert issubclass(MemOS, NamespaceFacade)

    def test_namespace_facade_is_mixin(self):
        assert "__init__" not in NamespaceFacade.__dict__, "NamespaceFacade should not define __init__"

    def test_memos_instance_has_all_namespace_methods(self):
        mem = MemOS(backend="memory", sanitize=False)
        for name in NAMESPACE_METHODS:
            assert hasattr(mem, name), f"MemOS instance missing method: {name}"
            assert callable(getattr(mem, name)), f"MemOS.{name} is not callable"


class TestMethodSignatures:
    def test_list_namespaces_signature(self):
        sig = inspect.signature(MemOS.list_namespaces)
        params = list(sig.parameters.keys())
        assert "self" in params

    def test_grant_namespace_access_signature(self):
        sig = inspect.signature(MemOS.grant_namespace_access)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "agent_id" in params
        assert "namespace" in params
        assert "role" in params
        assert "granted_by" in params
        assert "expires_at" in params

    def test_revoke_namespace_access_signature(self):
        sig = inspect.signature(MemOS.revoke_namespace_access)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "agent_id" in params
        assert "namespace" in params

    def test_list_namespace_policies_signature(self):
        sig = inspect.signature(MemOS.list_namespace_policies)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "namespace" in params

    def test_namespace_acl_stats_signature(self):
        sig = inspect.signature(MemOS.namespace_acl_stats)
        params = list(sig.parameters.keys())
        assert "self" in params


class TestNoDuplicationInCore:
    def test_methods_defined_on_facade(self):
        for name in NAMESPACE_METHODS:
            assert name in NamespaceFacade.__dict__, f"{name} should be defined on NamespaceFacade, not just inherited"


def _make_namespace_dummy():
    class _Dummy(NamespaceFacade):
        def __init__(self):
            self._store = MagicMock()
            self._acl = MagicMock()
            self._events = MagicMock()
            self._namespace = ""

    return _Dummy()


class TestListNamespacesDelegation:
    def test_delegates_to_store(self):
        mem = _make_namespace_dummy()
        mem._store.list_namespaces.return_value = ["agent-alice", "agent-bob"]

        result = mem.list_namespaces()

        mem._store.list_namespaces.assert_called_once_with()
        assert result == ["agent-alice", "agent-bob"]


class TestGrantNamespaceAccessDelegation:
    def test_grant_with_str_role(self):
        mem = _make_namespace_dummy()
        mock_policy = MagicMock()
        mock_policy.to_dict.return_value = {"agent_id": "a1", "role": "writer"}
        mem._acl.grant.return_value = mock_policy

        result = mem.grant_namespace_access("a1", "ns1", "writer")

        mem._acl.grant.assert_called_once_with("a1", "ns1", Role.WRITER, granted_by="", expires_at=None)
        mem._events.emit_sync.assert_called_once()
        assert result == {"agent_id": "a1", "role": "writer"}

    def test_grant_with_role_enum(self):
        mem = _make_namespace_dummy()
        mock_policy = MagicMock()
        mock_policy.to_dict.return_value = {"agent_id": "a1", "role": "owner"}
        mem._acl.grant.return_value = mock_policy

        result = mem.grant_namespace_access("a1", "ns1", Role.OWNER)

        mem._acl.grant.assert_called_once_with("a1", "ns1", Role.OWNER, granted_by="", expires_at=None)
        assert result["role"] == "owner"


class TestRevokeNamespaceAccessDelegation:
    def test_revoke_existing_policy_returns_true(self):
        mem = _make_namespace_dummy()
        mem._acl.revoke.return_value = True

        result = mem.revoke_namespace_access("a1", "ns1")

        mem._acl.revoke.assert_called_once_with("a1", "ns1")
        assert result is True
        mem._events.emit_sync.assert_called_once()

    def test_revoke_nonexistent_policy_returns_false(self):
        mem = _make_namespace_dummy()
        mem._acl.revoke.return_value = False

        result = mem.revoke_namespace_access("a1", "ns1")

        assert result is False
        mem._events.emit_sync.assert_not_called()


class TestListNamespacePoliciesDelegation:
    def test_delegates_to_acl(self):
        mem = _make_namespace_dummy()
        p1 = MagicMock()
        p1.to_dict.return_value = {"agent_id": "a1"}
        mem._acl.list_policies.return_value = [p1]

        result = mem.list_namespace_policies(namespace="ns1")

        mem._acl.list_policies.assert_called_once_with(namespace="ns1")
        assert len(result) == 1
        assert result[0] == {"agent_id": "a1"}


class TestNamespaceAclStatsDelegation:
    def test_delegates_to_acl(self):
        mem = _make_namespace_dummy()
        mem._acl.stats.return_value = {"total_policies": 3}

        result = mem.namespace_acl_stats()

        mem._acl.stats.assert_called_once_with()
        assert result == {"total_policies": 3}
