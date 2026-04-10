"""Tests for memory deduplication."""

from __future__ import annotations

import json

from memos import MemOS
from memos.dedup import DedupEngine
from memos.models import MemoryItem


class TestDedupEngine:
    def test_exact_duplicate_match(self):
        engine = DedupEngine()
        existing = [MemoryItem(id="a", content="User prefers dark mode")]

        match = engine.check("  user prefers dark mode  ", existing)

        assert match is not None
        assert match.reason == "exact"
        assert match.item.id == "a"

    def test_near_duplicate_match(self):
        engine = DedupEngine()
        existing = [MemoryItem(id="a", content="User prefers dark mode on desktop")]

        match = engine.check(
            "User prefers dark mode on desktop.",
            existing,
            threshold=0.9,
        )

        assert match is not None
        assert match.reason == "near"
        assert match.similarity >= 0.9

    def test_scan_finds_exact_and_near_duplicates(self):
        engine = DedupEngine()
        items = [
            MemoryItem(id="a", content="Docker runs on Raspberry Pi", importance=0.4),
            MemoryItem(id="b", content="docker runs on raspberry pi", importance=0.9),
            MemoryItem(id="c", content="Use dark mode in the editor"),
            MemoryItem(id="d", content="Use dark mode in the editor.", importance=0.8),
        ]

        result = engine.scan(items, threshold=0.9)

        assert result.groups_found == 2
        assert result.duplicates_found == 2
        assert {group.reason for group in result.details} == {"exact", "near"}


class TestMemOSDedup:
    def test_learn_skips_exact_duplicate_by_default(self):
        mem = MemOS(sanitize=False)

        first = mem.learn("User prefers concise answers", tags=["preference"])
        second = mem.learn(" user prefers concise answers ", tags=["different"])

        assert first.id == second.id
        assert mem.stats().total_memories == 1
        assert mem.history(first.id)[0].tags == ["preference"]
        assert len(mem.history(first.id)) == 1

    def test_learn_skips_near_duplicate_by_default(self):
        mem = MemOS(sanitize=False)

        first = mem.learn("User prefers dark mode on desktop")
        second = mem.learn("User prefers dark mode on desktop.")

        assert first.id == second.id
        assert mem.stats().total_memories == 1

    def test_allow_duplicate_bypasses_dedup_and_keeps_versions(self):
        mem = MemOS(sanitize=False)

        first = mem.learn("Versioned content", tags=["v1"], importance=0.2)
        second = mem.learn(
            "Versioned content",
            tags=["v2"],
            importance=0.8,
            allow_duplicate=True,
        )

        assert first.id == second.id
        assert mem.stats().total_memories == 1
        assert len(mem.history(first.id)) == 2
        assert mem.get(first.id).tags == ["v2"]

    def test_dedup_scan_fix_merges_and_removes_duplicates(self):
        mem = MemOS(sanitize=False)
        mem._store.upsert(MemoryItem(id="a", content="Repeated note", tags=["one"], importance=0.2))
        mem._store.upsert(MemoryItem(id="b", content="repeated note", tags=["two"], importance=0.9))

        result = mem.dedup_scan(fix=True)

        assert result.groups_found == 1
        assert result.duplicates_removed == 1
        kept = mem.get("b")
        assert kept is not None
        assert kept.tags == ["one", "two"]


class TestDedupCLI:
    def test_dedup_check_json(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)

        from memos.cli import main

        main(["learn", "CLI duplicate target"])
        capsys.readouterr()

        main(["dedup-check", "cli duplicate target", "--json"])
        data = json.loads(capsys.readouterr().out)

        assert data["is_duplicate"] is True
        assert data["match"]["reason"] == "exact"

    def test_dedup_scan_fix(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)

        from memos.cli import main
        from memos.storage.json_backend import JsonFileBackend

        main(["learn", "CLI scan duplicate"])
        capsys.readouterr()

        backend = JsonFileBackend(path=str(tmp_path / ".memos" / "store.json"))
        backend.upsert(MemoryItem(id="manual-dup", content="cli scan duplicate"))

        main(["dedup-scan", "--fix", "--verbose"])
        out = capsys.readouterr().out

        assert "Groups found: 1" in out
        assert "Duplicates removed: 1" in out


class TestDedupAPI:
    def test_dedup_check_endpoint(self):
        from fastapi.testclient import TestClient
        from memos.api import create_fastapi_app

        mem = MemOS(sanitize=False)
        mem.learn("API duplicate target")
        client = TestClient(create_fastapi_app(memos=mem))

        response = client.post("/api/v1/dedup/check", json={"content": "api duplicate target"})

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["is_duplicate"] is True
        assert data["match"]["reason"] == "exact"
