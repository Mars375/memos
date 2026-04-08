"""Tests for list_tags functionality (core + CLI + API)."""

from __future__ import annotations

import json

import pytest

from memos.cli import build_parser, main
from memos.core import MemOS
from memos.storage.memory_backend import InMemoryBackend


# ── Core tests ──────────────────────────────────────────────────────────────


class TestListTagsCore:
    def setup_method(self):
        self.memos = MemOS(backend=InMemoryBackend())

    def test_empty(self):
        assert self.memos.list_tags() == []

    def test_single_tag(self):
        self.memos.learn("hello", tags=["greet"])
        tags = self.memos.list_tags()
        assert tags == [("greet", 1)]

    def test_multiple_tags_counted(self):
        self.memos.learn("a", tags=["x", "y"])
        self.memos.learn("b", tags=["x"])
        tags = self.memos.list_tags()
        assert tags == [("x", 2), ("y", 1)]

    def test_sort_by_count_desc(self):
        self.memos.learn("a", tags=["lo", "mid", "hi"])
        self.memos.learn("b", tags=["mid", "hi"])
        self.memos.learn("c", tags=["hi"])
        tags = self.memos.list_tags(sort="count")
        counts = [c for _, c in tags]
        assert counts == sorted(counts, reverse=True)
        assert tags[0] == ("hi", 3)

    def test_sort_by_name(self):
        self.memos.learn("a", tags=["zeta", "alpha", "beta"])
        tags = self.memos.list_tags(sort="name")
        names = [t for t, _ in tags]
        assert names == sorted(names)

    def test_limit(self):
        for i in range(10):
            self.memos.learn(f"item-{i}", tags=[f"tag-{i:02d}"])
        tags = self.memos.list_tags(limit=3)
        assert len(tags) == 3

    def test_limit_zero_returns_all(self):
        for i in range(5):
            self.memos.learn(f"item-{i}", tags=[f"t{i}"])
        tags = self.memos.list_tags(limit=0)
        assert len(tags) == 5


# ── CLI tests ───────────────────────────────────────────────────────────────


class TestTagsCLI:
    def test_tags_list_parser(self):
        p = build_parser()
        ns = p.parse_args(["tags", "list"])
        assert ns.command == "tags"
        assert ns.tags_action == "list"

    def test_tags_list_sort_parser(self):
        p = build_parser()
        ns = p.parse_args(["tags", "list", "--sort", "name", "--limit", "5"])
        assert ns.tags_sort == "name"
        assert ns.tags_limit == 5

    def test_tags_list_empty(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        main(["init"])
        main(["tags", "list"])
        captured = capsys.readouterr()
        assert "No tags found" in captured.out

    def test_tags_list_with_data(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        main(["init"])
        main(["learn", "hello world", "--tags", "foo,bar"])
        capsys.readouterr()  # clear init+learn output
        main(["tags", "list"])
        captured = capsys.readouterr()
        assert "foo" in captured.out
        assert "bar" in captured.out

    def test_tags_list_json(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        main(["init"])
        main(["learn", "test content", "--tags", "json-tag"])
        capsys.readouterr()  # clear init+learn output
        main(["tags", "list", "--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        tag_names = [d["tag"] for d in data]
        assert "json-tag" in tag_names

    def test_tags_list_limit(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        main(["init"])
        for i in range(5):
            main(["learn", f"item {i}", "--tags", f"lim{i}"])
        capsys.readouterr()  # clear init+learn output
        main(["tags", "list", "--limit", "2"])
        captured = capsys.readouterr()
        lines = [l.strip() for l in captured.out.strip().split("\n") if l.strip()]
        assert len(lines) == 2


# ── API tests ───────────────────────────────────────────────────────────────


class TestTagsAPI:
    def test_api_tags_endpoint(self):
        from memos.api import create_fastapi_app
        from fastapi.testclient import TestClient

        m = MemOS(backend=InMemoryBackend())
        m.learn("api test a", tags=["api-foo", "api-bar"])
        m.learn("api test b", tags=["api-foo"])

        app = create_fastapi_app(memos=m)
        client = TestClient(app)

        resp = client.get("/api/v1/tags")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        tag_map = {d["tag"]: d["count"] for d in data}
        assert tag_map["api-foo"] == 2
        assert tag_map["api-bar"] == 1

    def test_api_tags_sort_name(self):
        from memos.api import create_fastapi_app
        from fastapi.testclient import TestClient

        m = MemOS(backend=InMemoryBackend())
        m.learn("test", tags=["z-tag", "a-tag"])

        app = create_fastapi_app(memos=m)
        client = TestClient(app)

        resp = client.get("/api/v1/tags", params={"sort": "name"})
        data = resp.json()
        names = [d["tag"] for d in data]
        assert names == sorted(names)

    def test_api_tags_limit(self):
        from memos.api import create_fastapi_app
        from fastapi.testclient import TestClient

        m = MemOS(backend=InMemoryBackend())
        for i in range(10):
            m.learn(f"item-{i}", tags=[f"t{i}"])

        app = create_fastapi_app(memos=m)
        client = TestClient(app)

        resp = client.get("/api/v1/tags", params={"limit": 3})
        data = resp.json()
        assert len(data) == 3

    def test_api_tags_empty(self):
        from memos.api import create_fastapi_app
        from fastapi.testclient import TestClient

        m = MemOS(backend=InMemoryBackend())
        app = create_fastapi_app(memos=m)
        client = TestClient(app)

        resp = client.get("/api/v1/tags")
        assert resp.status_code == 200
        assert resp.json() == []
