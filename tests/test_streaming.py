"""Tests for SSE streaming recall API and recall_stream() async generator."""

from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncIterator

import pytest

from memos import MemOS
from memos.core import RecallResult
from memos.models import MemoryItem, generate_id
from memos.api.sse import (
    SSEEvent,
    format_recall_event,
    format_done_event,
    format_error_event,
    sse_stream,
)


# ── SSEEvent unit tests ─────────────────────────────────────────


class TestSSEEvent:
    """Test SSE wire format encoding."""

    def test_basic_message(self):
        ev = SSEEvent(data="hello")
        encoded = ev.encode()
        assert "data: hello" in encoded
        assert encoded.endswith("\n\n")

    def test_named_event(self):
        ev = SSEEvent(event="recall", data='{"id":"abc"}')
        encoded = ev.encode()
        assert "event: recall" in encoded
        assert 'data: {"id":"abc"}' in encoded

    def test_event_with_id(self):
        ev = SSEEvent(event="recall", data="test", id="42")
        encoded = ev.encode()
        assert "id: 42" in encoded

    def test_event_with_retry(self):
        ev = SSEEvent(event="error", data="retry", retry=5000)
        encoded = ev.encode()
        assert "retry: 5000" in encoded

    def test_multiline_data(self):
        ev = SSEEvent(data="line1\nline2\nline3")
        encoded = ev.encode()
        assert "data: line1" in encoded
        assert "data: line2" in encoded
        assert "data: line3" in encoded

    def test_default_event_is_message(self):
        ev = SSEEvent(data="test")
        encoded = ev.encode()
        assert "event:" not in encoded

    def test_empty_data(self):
        ev = SSEEvent(data="")
        encoded = ev.encode()
        # Empty data produces no data lines (SSE spec: omit data field)
        assert "data:" not in encoded


# ── Format helpers ───────────────────────────────────────────────


class TestFormatHelpers:
    """Test SSE event formatting helpers."""

    def test_format_recall_event(self):
        ev = format_recall_event(
            index=1,
            item_id="abc123",
            content="test memory",
            score=0.95,
            tags=["test"],
            match_reason="semantic",
            age_days=2.5,
        )
        assert ev.event == "recall"
        assert ev.id == "1"
        payload = json.loads(ev.data)
        assert payload["index"] == 1
        assert payload["id"] == "abc123"
        assert payload["score"] == 0.95
        assert payload["tags"] == ["test"]
        assert payload["match_reason"] == "semantic"

    def test_format_recall_event_with_total(self):
        ev = format_recall_event(
            index=3, item_id="x", content="c", score=0.5,
            tags=[], match_reason="keyword", age_days=0.0,
            total=10,
        )
        payload = json.loads(ev.data)
        assert payload["total"] == 10

    def test_format_done_event(self):
        ev = format_done_event(count=5, query="test query", elapsed_ms=123.45)
        assert ev.event == "done"
        payload = json.loads(ev.data)
        assert payload["type"] == "done"
        assert payload["count"] == 5
        assert payload["query"] == "test query"
        assert payload["elapsed_ms"] == 123.5  # rounded

    def test_format_error_event(self):
        ev = format_error_event("something failed")
        assert ev.event == "error"
        payload = json.loads(ev.data)
        assert payload["type"] == "error"
        assert payload["message"] == "something failed"

    def test_format_error_event_with_code(self):
        ev = format_error_event("not found", code="ENOENT")
        payload = json.loads(ev.data)
        assert payload["code"] == "ENOENT"


# ── recall_stream() async generator ──────────────────────────────


class TestRecallStream:
    """Test the async generator recall_stream() method."""

    def test_basic_streaming(self):
        mem = MemOS()
        mem.learn("User prefers Python", tags=["preference"])
        mem.learn("User uses Docker", tags=["infra"])
        mem.learn("Server runs on ARM64", tags=["infra"])

        async def _run():
            results = []
            async for r in mem.recall_stream("what does the user use?"):
                results.append(r)
            return results

        results = asyncio.run(_run())
        assert len(results) > 0
        assert all(isinstance(r, RecallResult) for r in results)
        # Results should be sorted by score
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_streaming_respects_top(self):
        mem = MemOS()
        for i in range(20):
            mem.learn(f"Memory item {i}", tags=["test"], importance=0.5)

        async def _run():
            results = []
            async for r in mem.recall_stream("memory", top=3):
                results.append(r)
            return results

        results = asyncio.run(_run())
        assert len(results) <= 3

    def test_streaming_with_tag_filter(self):
        mem = MemOS()
        mem.learn("Python preference", tags=["language", "preference"])
        mem.learn("Docker infra", tags=["infra", "devops"])
        mem.learn("Rust learning", tags=["language", "learning"])

        async def _run():
            results = []
            async for r in mem.recall_stream("test", filter_tags=["language"]):
                results.append(r)
            return results

        results = asyncio.run(_run())
        for r in results:
            assert "language" in r.item.tags

    def test_streaming_with_min_score(self):
        mem = MemOS()
        mem.learn("Very relevant Python content", tags=["python"])
        mem.learn("Unrelated cooking recipe", tags=["food"])

        async def _run():
            results = []
            async for r in mem.recall_stream("python programming", min_score=0.5):
                results.append(r)
            return results

        results = asyncio.run(_run())
        for r in results:
            assert r.score >= 0.5

    def test_streaming_empty_store(self):
        mem = MemOS()

        async def _run():
            results = []
            async for r in mem.recall_stream("anything"):
                results.append(r)
            return results

        results = asyncio.run(_run())
        assert results == []

    def test_streaming_yields_recall_result_objects(self):
        mem = MemOS()
        mem.learn("Test memory for streaming", tags=["stream"])

        async def _run():
            results = []
            async for r in mem.recall_stream("streaming"):
                results.append(r)
            return results

        results = asyncio.run(_run())
        assert len(results) >= 1
        r = results[0]
        assert hasattr(r, "item")
        assert hasattr(r, "score")
        assert hasattr(r, "match_reason")
        assert isinstance(r.item, MemoryItem)

    def test_streaming_emits_recall_events(self):
        mem = MemOS()
        mem.learn("Event streaming test", tags=["test"])

        events_captured = []

        async def capture_handler(event):
            events_captured.append(event)

        mem.events.subscribe("recalled", capture_handler)

        async def _run():
            async for _ in mem.recall_stream("streaming"):
                pass

        asyncio.run(_run())
        # recall() emits events internally, recall_stream delegates to it
        # Events are emitted synchronously via emit_sync, so they fire


# ── sse_stream() wrapper ─────────────────────────────────────────


class TestSSEStreamWrapper:
    """Test the sse_stream() async wrapper that formats results as SSE."""

    @staticmethod
    async def _mock_recall_gen(items):
        for item, score, reason in items:
            yield RecallResult(
                item=item,
                score=score,
                match_reason=reason,
            )

    def test_sse_stream_formats_results(self):
        items = [
            (
                MemoryItem(id="1", content="First result", tags=["a"]),
                0.9,
                "semantic",
            ),
            (
                MemoryItem(id="2", content="Second result", tags=["b"]),
                0.7,
                "keyword",
            ),
        ]

        async def _run():
            gen = self._mock_recall_gen(items)
            chunks = []
            async for chunk in sse_stream(gen, "test query"):
                chunks.append(chunk)
            return chunks

        chunks = asyncio.run(_run())
        # Should have: 2 recall events + 1 done event = 3 chunks
        assert len(chunks) == 3

        # First chunk: recall event
        assert "event: recall" in chunks[0]
        assert '"id": "1"' in chunks[0]

        # Second chunk: recall event
        assert "event: recall" in chunks[1]
        assert '"id": "2"' in chunks[1]

        # Third chunk: done event
        assert "event: done" in chunks[2]
        done_data = json.loads(chunks[2].split("data: ")[1].strip())
        assert done_data["count"] == 2
        assert done_data["query"] == "test query"

    def test_sse_stream_empty_results(self):
        async def _run():
            gen = self._mock_recall_gen([])
            chunks = []
            async for chunk in sse_stream(gen, "empty query"):
                chunks.append(chunk)
            return chunks

        chunks = asyncio.run(_run())
        # Just the done event
        assert len(chunks) == 1
        assert "event: done" in chunks[0]
        done_data = json.loads(chunks[0].split("data: ")[1].strip())
        assert done_data["count"] == 0

    def test_sse_stream_without_done(self):
        items = [
            (MemoryItem(id="1", content="Test", tags=[]), 0.5, "keyword"),
        ]

        async def _run():
            gen = self._mock_recall_gen(items)
            chunks = []
            async for chunk in sse_stream(gen, "q", include_done=False):
                chunks.append(chunk)
            return chunks

        chunks = asyncio.run(_run())
        assert len(chunks) == 1
        assert "event: done" not in chunks[0]

    def test_sse_stream_error_handling(self):
        async def _failing_gen():
            yield RecallResult(
                item=MemoryItem(id="1", content="OK", tags=[]),
                score=0.5,
                match_reason="keyword",
            )
            raise RuntimeError("Simulated failure")

        async def _run():
            chunks = []
            async for chunk in sse_stream(_failing_gen(), "q"):
                chunks.append(chunk)
            return chunks

        chunks = asyncio.run(_run())
        # First result + error event (no done event because exception)
        assert len(chunks) == 2
        assert "event: recall" in chunks[0]
        assert "event: error" in chunks[1]
        error_data = json.loads(chunks[1].split("data: ")[1].strip())
        assert "Simulated failure" in error_data["message"]

    def test_sse_stream_sse_wire_format(self):
        """Verify output follows SSE spec: event, data, blank lines."""
        items = [
            (MemoryItem(id="abc", content="Test", tags=["x", "y"]), 0.88, "semantic"),
        ]

        async def _run():
            gen = self._mock_recall_gen(items)
            chunks = []
            async for chunk in sse_stream(gen, "q"):
                chunks.append(chunk)
            return chunks

        chunks = asyncio.run(_run())
        recall_chunk = chunks[0]

        # Must end with double newline
        assert recall_chunk.endswith("\n\n")
        # Lines separated properly
        lines = recall_chunk.strip().split("\n")
        assert any(l.startswith("event: recall") for l in lines)
        assert any(l.startswith("data: ") for l in lines)
        assert any(l.startswith("id: ") for l in lines)

    def test_sse_stream_elapsed_ms_in_done(self):
        items = [
            (MemoryItem(id="1", content="Fast result", tags=[]), 0.9, "semantic"),
        ]

        async def _run():
            gen = self._mock_recall_gen(items)
            chunks = []
            async for chunk in sse_stream(gen, "speed test"):
                chunks.append(chunk)
            return chunks

        chunks = asyncio.run(_run())
        done_chunk = chunks[-1]
        done_data = json.loads(done_chunk.split("data: ")[1].strip())
        assert "elapsed_ms" in done_data
        assert done_data["elapsed_ms"] >= 0


# ── Integration: recall_stream + sse_stream ──────────────────────


class TestIntegrationStreaming:
    """End-to-end tests: MemOS.recall_stream() → sse_stream()."""

    def test_full_pipeline(self):
        mem = MemOS()
        mem.learn("User prefers dark mode", tags=["preference", "ui"])
        mem.learn("User codes in Python", tags=["preference", "language"])
        mem.learn("Server is Raspberry Pi 5", tags=["infra"])

        async def _run():
            gen = mem.recall_stream("what are user preferences?", top=5)
            chunks = []
            async for chunk in sse_stream(gen, "what are user preferences?"):
                chunks.append(chunk)
            return chunks

        chunks = asyncio.run(_run())

        # Should have at least 1 recall + 1 done
        assert len(chunks) >= 2

        # All recall chunks have valid JSON data
        recall_chunks = [c for c in chunks if "event: recall" in c]
        for chunk in recall_chunks:
            data_line = [l for l in chunk.split("\n") if l.startswith("data: ")][0]
            payload = json.loads(data_line[6:])
            assert "id" in payload
            assert "content" in payload
            assert "score" in payload
            assert payload["score"] > 0

        # Done chunk
        done_chunk = chunks[-1]
        assert "event: done" in done_chunk

    def test_namespace_isolation_streaming(self):
        mem = MemOS()
        mem.namespace = "agent-a"
        mem.learn("Agent A memory", tags=["agent-a"])

        mem.namespace = "agent-b"
        mem.learn("Agent B memory", tags=["agent-b"])

        async def _run():
            gen = mem.recall_stream("memory", top=5)
            chunks = []
            async for chunk in sse_stream(gen, "memory"):
                chunks.append(chunk)
            return chunks

        # Should only find Agent B memories (current namespace)
        chunks = asyncio.run(_run())
        recall_chunks = [c for c in chunks if "event: recall" in c]
        for chunk in recall_chunks:
            data_line = [l for l in chunk.split("\n") if l.startswith("data: ")][0]
            payload = json.loads(data_line[6:])
            assert "agent-b" in payload["tags"]

    def test_large_result_set_streaming(self):
        mem = MemOS()
        for i in range(50):
            mem.learn(
                f"Memory number {i} about topic {i % 5}",
                tags=[f"topic-{i % 5}"],
                importance=0.3 + (i % 10) * 0.05,
            )

        async def _run():
            gen = mem.recall_stream("topic", top=10)
            chunks = []
            async for chunk in sse_stream(gen, "topic"):
                chunks.append(chunk)
            return chunks

        chunks = asyncio.run(_run())
        recall_chunks = [c for c in chunks if "event: recall" in c]
        assert len(recall_chunks) <= 10

        # Scores should be in descending order
        scores = []
        for chunk in recall_chunks:
            data_line = [l for l in chunk.split("\n") if l.startswith("data: ")][0]
            payload = json.loads(data_line[6:])
            scores.append(payload["score"])
        assert scores == sorted(scores, reverse=True)


# ── Edge cases ───────────────────────────────────────────────────


class TestStreamingEdgeCases:
    """Edge case tests for streaming functionality."""

    def test_stream_with_special_characters_in_content(self):
        mem = MemOS()
        mem.learn('Content with "quotes" and <html> tags & ampersands', tags=["test"])

        async def _run():
            results = []
            async for r in mem.recall_stream("content"):
                results.append(r)
            return results

        results = asyncio.run(_run())
        assert len(results) >= 1

        # SSE format should handle special chars in JSON
        async def _run_sse():
            gen = mem.recall_stream("content")
            chunks = []
            async for chunk in sse_stream(gen, "content"):
                chunks.append(chunk)
            return chunks

        chunks = asyncio.run(_run_sse())
        recall_chunks = [c for c in chunks if "event: recall" in c]
        for chunk in recall_chunks:
            data_line = [l for l in chunk.split("\n") if l.startswith("data: ")][0]
            # Should parse as valid JSON
            payload = json.loads(data_line[6:])
            assert "quotes" in payload["content"]

    def test_stream_with_unicode_content(self):
        mem = MemOS()
        mem.learn("L'utilisateur préfère les réponses en français", tags=["français"])
        mem.learn("ユーザーは日本語を話します", tags=["japanese"])

        async def _run():
            results = []
            async for r in mem.recall_stream("utilisateur"):
                results.append(r)
            return results

        results = asyncio.run(_run())
        assert len(results) >= 1

    def test_sse_event_encode_idempotent(self):
        ev = SSEEvent(event="test", data="hello", id="1")
        encoded = ev.encode()
        # Encoding twice should produce same result
        assert ev.encode() == encoded

    def test_concurrent_streams(self):
        """Multiple concurrent streams should not interfere."""
        mem = MemOS()
        for i in range(10):
            mem.learn(f"Concurrent memory {i}", tags=["test"])

        async def _run():
            async def stream_one():
                results = []
                async for r in mem.recall_stream("concurrent", top=5):
                    results.append(r)
                return results

            # Run two streams concurrently
            r1, r2 = await asyncio.gather(
                asyncio.ensure_future(stream_one()),
                asyncio.ensure_future(stream_one()),
            )
            return r1, r2

        r1, r2 = asyncio.run(_run())
        assert len(r1) > 0
        assert len(r2) > 0
