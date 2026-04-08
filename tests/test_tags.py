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


# ── Core rename tests ──────────────────────────────────────────────────────


class TestRenameTagCore:
    def setup_method(self):
        self.memos = MemOS(backend=InMemoryBackend())

    def test_rename_basic(self):
        self.memos.learn("hello", tags=["alpha"])
        count = self.memos.rename_tag("alpha", "beta")
        assert count == 1
        tags = self.memos.list_tags()
        tag_names = [t for t, _ in tags]
        assert "alpha" not in tag_names
        assert "beta" in tag_names

    def test_rename_multiple_memories(self):
        self.memos.learn("a", tags=["x", "y"])
        self.memos.learn("b", tags=["x"])
        self.memos.learn("c", tags=["z"])
        count = self.memos.rename_tag("x", "renamed")
        assert count == 2
        tags = dict(self.memos.list_tags())
        assert "x" not in tags
        assert tags["renamed"] == 2
        assert tags["y"] == 1
        assert tags["z"] == 1

    def test_rename_preserves_other_tags(self):
        self.memos.learn("multi", tags=["a", "b", "c"])
        count = self.memos.rename_tag("b", "renamed")
        assert count == 1
        item = self.memos._store.list_all()[0]
        assert "a" in item.tags
        assert "renamed" in item.tags
        assert "c" in item.tags
        assert "b" not in item.tags

    def test_rename_nonexistent_tag(self):
        self.memos.learn("hello", tags=["keep"])
        count = self.memos.rename_tag("missing", "new")
        assert count == 0

    def test_rename_case_insensitive(self):
        self.memos.learn("hello", tags=["MyTag"])
        count = self.memos.rename_tag("mytag", "newtag")
        assert count == 1
        tags = dict(self.memos.list_tags())
        assert "newtag" in tags

    def test_rename_empty_store(self):
        count = self.memos.rename_tag("a", "b")
        assert count == 0

    def test_rename_updates_accessed_at(self):
        import time
        self.memos.learn("hello", tags=["old"])
        item_before = self.memos._store.list_all()[0]
        ts_before = item_before.accessed_at
        time.sleep(0.01)
        self.memos.rename_tag("old", "new")
        item_after = self.memos._store.list_all()[0]
        assert item_after.accessed_at >= ts_before


# ── CLI rename tests ───────────────────────────────────────────────────────


class TestRenameTagCLI:
    def test_rename_parser(self):
        p = build_parser()
        ns = p.parse_args(["tags", "rename", "old", "new"])
        assert ns.tags_action == "rename"
        assert ns.old_tag == "old"
        assert ns.new_tag == "new"

    def test_rename_cli(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        main(["init"])
        main(["learn", "hello world", "--tags", "alpha,beta"])
        capsys.readouterr()
        main(["tags", "rename", "alpha", "gamma"])
        captured = capsys.readouterr()
        assert "gamma" in captured.out
        assert "1 memory(s) updated" in captured.out
        # Verify the tag was actually renamed
        main(["tags", "list", "--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        tag_names = [d["tag"] for d in data]
        assert "gamma" in tag_names
        assert "alpha" not in tag_names

    def test_rename_nonexistent_cli(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        main(["init"])
        capsys.readouterr()
        main(["tags", "rename", "ghost", "new"])
        captured = capsys.readouterr()
        assert "0 memory(s) updated" in captured.out


# ── API rename tests ───────────────────────────────────────────────────────


class TestRenameTagAPI:
    def test_api_rename(self):
        from memos.api import create_fastapi_app
        from fastapi.testclient import TestClient

        m = MemOS(backend=InMemoryBackend())
        m.learn("api test a", tags=["old-tag", "keep"])
        m.learn("api test b", tags=["old-tag"])

        app = create_fastapi_app(memos=m)
        client = TestClient(app)

        resp = client.post("/api/v1/tags/rename", json={"old": "old-tag", "new": "new-tag"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["renamed"] == 2
        assert data["old_tag"] == "old-tag"
        assert data["new_tag"] == "new-tag"

        # Verify via list
        resp = client.get("/api/v1/tags")
        tag_map = {d["tag"]: d["count"] for d in resp.json()}
        assert "new-tag" in tag_map
        assert tag_map["new-tag"] == 2
        assert "old-tag" not in tag_map

    def test_api_rename_missing_params(self):
        from memos.api import create_fastapi_app
        from fastapi.testclient import TestClient

        m = MemOS(backend=InMemoryBackend())
        app = create_fastapi_app(memos=m)
        client = TestClient(app)

        resp = client.post("/api/v1/tags/rename", json={"old": "x"})
        assert resp.status_code == 200
        assert "error" in resp.json()

    def test_api_rename_nonexistent(self):
        from memos.api import create_fastapi_app
        from fastapi.testclient import TestClient

        m = MemOS(backend=InMemoryBackend())
        app = create_fastapi_app(memos=m)
        client = TestClient(app)

        resp = client.post("/api/v1/tags/rename", json={"old": "ghost", "new": "new"})
        assert resp.status_code == 200
        assert resp.json()["renamed"] == 0
