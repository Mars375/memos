"""Structural regression tests for the extracted sharing facade."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.memos.models import MemoryItem
from src.memos.sharing.models import MemoryEnvelope, SharePermission, ShareRequest, ShareScope, ShareStatus


def test_sharing_facade_delegates_engine_methods():
    from src.memos._sharing_facade import SharingFacade

    class _DummyMemOS(SharingFacade):
        def __init__(self):
            self._sharing = MagicMock()
            self._store = MagicMock()
            self._namespace = ""
            self._agent_id = "agent-a"

        def learn(self, *args, **kwargs):
            return MemoryItem(
                id="learned", content=args[0], tags=kwargs.get("tags", []), importance=kwargs.get("importance", 0.5)
            )

    mem = _DummyMemOS()
    req = ShareRequest(source_agent="agent-a", target_agent="agent-b", status=ShareStatus.ACCEPTED)
    mem._sharing.get.return_value = req
    mem._sharing.export_envelope.return_value = MemoryEnvelope(source_agent="agent-a", target_agent="agent-b")

    mem.share_with("agent-b", scope=ShareScope.TAG, scope_key="research", permission=SharePermission.READ_WRITE)
    mem.accept_share("share-1")
    mem.reject_share("share-2")
    mem.revoke_share("share-3")
    mem.list_shares()
    mem.sharing_stats()

    mem._sharing.offer.assert_called_once()
    mem._sharing.accept.assert_called_once_with("share-1", "agent-a")
    mem._sharing.reject.assert_called_once_with("share-2", "agent-a")
    mem._sharing.revoke.assert_called_once_with("share-3", "agent-a")
    mem._sharing.list_shares.assert_called_once_with(agent=None, status=None)
    mem._sharing.stats.assert_called_once_with()


def test_sharing_facade_import_shared_uses_learn():
    from src.memos._sharing_facade import SharingFacade

    class _DummyMemOS(SharingFacade):
        def __init__(self):
            self._sharing = MagicMock()
            self._store = MagicMock()
            self._namespace = ""

        def learn(self, *args, **kwargs):
            return MemoryItem(
                id=f"learned-{args[0]}",
                content=args[0],
                tags=kwargs.get("tags", []),
                importance=kwargs.get("importance", 0.5),
            )

    mem = _DummyMemOS()
    envelope = MemoryEnvelope(source_agent="a", target_agent="b")

    with patch(
        "src.memos._sharing_facade.SharingEngine.import_envelope",
        return_value=[{"content": "hello", "tags": ["x"], "importance": 0.7}],
    ):
        learned = mem.import_shared(envelope)

    assert len(learned) == 1
    assert learned[0].content == "hello"


def test_sharing_facade_resolves_tag_scope_from_store():
    from src.memos._sharing_facade import SharingFacade

    class _DummyMemOS(SharingFacade):
        def __init__(self):
            self._sharing = MagicMock()
            self._store = MagicMock()
            self._namespace = ""

        def learn(self, *args, **kwargs):
            raise NotImplementedError

    mem = _DummyMemOS()
    item = MemoryItem(id="1", content="alpha", tags=["research"])
    mem._store.list_all.return_value = [item]
    req = ShareRequest(source_agent="a", target_agent="b", scope=ShareScope.TAG, scope_key="research")

    resolved = mem._resolve_share_scope(req)

    assert resolved == [item]
