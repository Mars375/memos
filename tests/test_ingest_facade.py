"""Structural regression tests for the IngestFacade mixin extraction.

Verifies that IngestFacade methods exist on MemOS via inheritance, have correct
signatures, and that delegation to the ingest engine works as expected.
"""

import inspect
from unittest.mock import MagicMock, patch

from memos._ingest_facade import IngestFacade
from memos.core import MemOS

INGEST_METHODS = ("ingest", "ingest_url")


class TestIngestFacadeInheritance:
    def test_memos_inherits_ingest_facade(self):
        assert issubclass(MemOS, IngestFacade)

    def test_ingest_facade_is_mixin(self):
        assert "__init__" not in IngestFacade.__dict__, "IngestFacade should not define __init__"

    def test_memos_instance_has_all_ingest_methods(self):
        mem = MemOS(backend="memory", sanitize=False)
        for name in INGEST_METHODS:
            assert hasattr(mem, name), f"MemOS instance missing method: {name}"
            assert callable(getattr(mem, name)), f"MemOS.{name} is not callable"


class TestMethodSignatures:
    def test_ingest_signature(self):
        sig = inspect.signature(MemOS.ingest)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "path" in params
        assert "tags" in params
        assert "importance" in params
        assert "max_chunk" in params
        assert "dry_run" in params

    def test_ingest_url_signature(self):
        sig = inspect.signature(MemOS.ingest_url)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "url" in params
        assert "tags" in params
        assert "importance" in params
        assert "max_chunk" in params
        assert "dry_run" in params
        assert "skip_sanitization" in params


class TestNoDuplicationInCore:
    def test_methods_defined_on_facade(self):
        for name in INGEST_METHODS:
            assert name in IngestFacade.__dict__, f"{name} should be defined on IngestFacade, not just inherited"


class TestIngestDelegation:
    """Verify that ingest delegates to ingest_file and calls self.learn per chunk."""

    def _make_dummy(self):
        class _Dummy(IngestFacade):
            def __init__(self):
                self.learn_calls = []
                self._namespace = ""
                self._events = MagicMock()
                self._store = MagicMock()
                self._retrieval = MagicMock()
                self._versioning = MagicMock()

            def learn(self, content, *, tags=None, importance=0.5, metadata=None):
                from memos.models import MemoryItem

                item = MemoryItem(
                    id=f"learned-{len(self.learn_calls)}",
                    content=content,
                    tags=tags or [],
                    importance=importance,
                )
                self.learn_calls.append({"content": content, "tags": tags, "importance": importance})
                return item

        return _Dummy()

    def test_ingest_calls_learn_for_each_chunk(self):
        mem = self._make_dummy()

        from memos.ingest.engine import IngestResult

        fake_result = IngestResult(
            total_chunks=2,
            chunks=[
                {"content": "chunk A", "tags": ["a"], "importance": 0.5},
                {"content": "chunk B", "tags": ["b"], "importance": 0.7},
            ],
        )

        with patch("memos.ingest.engine.ingest_file", return_value=fake_result) as mock_ingest:
            result = mem.ingest("/fake/path.md", tags=["test"])

        mock_ingest.assert_called_once_with("/fake/path.md", tags=["test"], importance=0.5, max_chunk=2000)
        assert len(mem.learn_calls) == 2
        assert mem.learn_calls[0]["content"] == "chunk A"
        assert mem.learn_calls[1]["content"] == "chunk B"
        assert result.total_chunks == 2

    def test_ingest_dry_run_does_not_store(self):
        mem = self._make_dummy()

        from memos.ingest.engine import IngestResult

        fake_result = IngestResult(
            total_chunks=1,
            chunks=[{"content": "chunk X", "tags": [], "importance": 0.5}],
        )

        with patch("memos.ingest.engine.ingest_file", return_value=fake_result):
            result = mem.ingest("/fake/path.md", dry_run=True)

        assert len(mem.learn_calls) == 0
        assert result.total_chunks == 1

    def test_ingest_records_errors_from_learn(self):
        mem = self._make_dummy()

        mem.learn = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("store down"))

        from memos.ingest.engine import IngestResult

        fake_result = IngestResult(
            total_chunks=1,
            chunks=[{"content": "failing chunk", "tags": [], "importance": 0.5}],
        )

        with patch("memos.ingest.engine.ingest_file", return_value=fake_result):
            result = mem.ingest("/fake/path.md")

        assert len(result.errors) == 1
        assert "store down" in result.errors[0]


class TestIngestUrlDelegation:
    """Verify ingest_url delegates to URLIngestor and stores chunks."""

    def _make_dummy(self):
        class _Dummy(IngestFacade):
            def __init__(self):
                self.learn_calls = []
                self._namespace = ""
                self._events = MagicMock()
                self._store = MagicMock()
                self._retrieval = MagicMock()
                self._versioning = MagicMock()

            def learn(self, content, *, tags=None, importance=0.5, metadata=None):
                from memos.models import MemoryItem

                item = MemoryItem(
                    id=f"learned-{len(self.learn_calls)}",
                    content=content,
                    tags=tags or [],
                    importance=importance,
                )
                self.learn_calls.append({"content": content, "tags": tags, "importance": importance})
                return item

        return _Dummy()

    def test_ingest_url_calls_learn_for_chunks(self):
        mem = self._make_dummy()

        from memos.ingest.engine import IngestResult

        fake_result = IngestResult(
            total_chunks=1,
            chunks=[{"content": "web content", "tags": ["web"], "importance": 0.6}],
        )

        mock_ingestor = MagicMock()
        mock_ingestor.ingest.return_value = fake_result

        with patch("memos.ingest.url.URLIngestor", return_value=mock_ingestor):
            result = mem.ingest_url("https://example.com", tags=["test"])

        assert len(mem.learn_calls) == 1
        assert mem.learn_calls[0]["content"] == "web content"
        assert result.total_chunks == 1

    def test_ingest_url_dry_run(self):
        mem = self._make_dummy()

        from memos.ingest.engine import IngestResult

        fake_result = IngestResult(
            total_chunks=1,
            chunks=[{"content": "web content", "tags": [], "importance": 0.5}],
        )

        mock_ingestor = MagicMock()
        mock_ingestor.ingest.return_value = fake_result

        with patch("memos.ingest.url.URLIngestor", return_value=mock_ingestor):
            mem.ingest_url("https://example.com", dry_run=True)

        assert len(mem.learn_calls) == 0

    def test_ingest_url_skip_sanitization_uses_store_directly(self):
        mem = self._make_dummy()

        from memos.ingest.engine import IngestResult

        fake_result = IngestResult(
            total_chunks=1,
            chunks=[{"content": "raw content", "tags": [], "importance": 0.5}],
        )

        mock_ingestor = MagicMock()
        mock_ingestor.ingest.return_value = fake_result

        with patch("memos.ingest.url.URLIngestor", return_value=mock_ingestor):
            mem.ingest_url("https://example.com", skip_sanitization=True)

        assert len(mem.learn_calls) == 0
        mem._store.upsert.assert_called_once()
        mem._retrieval.index.assert_called_once()
        mem._versioning.record_version.assert_called_once()
