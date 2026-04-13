"""Tests for KnowledgeGraph.backlinks() — P7: backlinks as first-class queries."""
import pytest

from memos.knowledge_graph import KnowledgeGraph


@pytest.fixture
def kg():
    kg = KnowledgeGraph(db_path=":memory:")
    # Alice -[works_on]-> ProjectX
    # Bob   -[works_on]-> ProjectX
    # Carol -[reviews]->  ProjectX
    # Alice -[leads]->    TeamA
    kg.add_fact("Alice", "works_on", "ProjectX")
    kg.add_fact("Bob", "works_on", "ProjectX")
    kg.add_fact("Carol", "reviews", "ProjectX")
    kg.add_fact("Alice", "leads", "TeamA")
    yield kg
    kg.close()


class TestBacklinks:
    def test_backlinks_returns_incoming_edges(self, kg):
        links = kg.backlinks("ProjectX")
        assert len(links) == 3
        subjects = {f["subject"] for f in links}
        assert subjects == {"Alice", "Bob", "Carol"}

    def test_backlinks_no_incoming_edges(self, kg):
        links = kg.backlinks("Alice")
        assert links == []

    def test_backlinks_predicate_filter(self, kg):
        links = kg.backlinks("ProjectX", predicate="works_on")
        assert len(links) == 2
        subjects = {f["subject"] for f in links}
        assert subjects == {"Alice", "Bob"}

    def test_backlinks_predicate_no_match(self, kg):
        links = kg.backlinks("ProjectX", predicate="manages")
        assert links == []

    def test_backlinks_nonexistent_entity(self, kg):
        links = kg.backlinks("Nobody")
        assert links == []

    def test_backlinks_excludes_invalidated_by_default(self, kg):
        fid = kg.add_fact("Dave", "uses", "ProjectX")
        kg.invalidate(fid)
        links = kg.backlinks("ProjectX")
        subjects = {f["subject"] for f in links}
        assert "Dave" not in subjects

    def test_backlinks_includes_invalidated_when_requested(self, kg):
        fid = kg.add_fact("Dave", "uses", "ProjectX")
        kg.invalidate(fid)
        links = kg.backlinks("ProjectX", active_only=False)
        subjects = {f["subject"] for f in links}
        assert "Dave" in subjects

    def test_backlinks_result_structure(self, kg):
        links = kg.backlinks("TeamA")
        assert len(links) == 1
        f = links[0]
        assert f["subject"] == "Alice"
        assert f["predicate"] == "leads"
        assert f["object"] == "TeamA"
        assert "confidence" in f
        assert "confidence_label" in f
        assert "created_at" in f


class TestCLI:
    def test_backlinks_cli(self, kg, capsys):
        import argparse
        from unittest.mock import patch

        from memos.cli import cmd_kg_backlinks

        ns = argparse.Namespace(entity="ProjectX", predicate=None, show_all=False, kg_db=None)
        with patch("memos.cli.commands_knowledge._get_kg", return_value=kg):
            cmd_kg_backlinks(ns)
        out = capsys.readouterr().out
        assert "ProjectX" in out
        assert "Alice" in out
        assert "Bob" in out
        assert "Carol" in out
        assert "3 backlink(s)" in out

    def test_backlinks_cli_predicate_filter(self, kg, capsys):
        import argparse
        from unittest.mock import patch

        from memos.cli import cmd_kg_backlinks

        ns = argparse.Namespace(entity="ProjectX", predicate="works_on", show_all=False, kg_db=None)
        with patch("memos.cli.commands_knowledge._get_kg", return_value=kg):
            cmd_kg_backlinks(ns)
        out = capsys.readouterr().out
        assert "2 backlink(s)" in out

    def test_backlinks_cli_no_results(self, kg, capsys):
        import argparse
        from unittest.mock import patch

        from memos.cli import cmd_kg_backlinks

        ns = argparse.Namespace(entity="Alice", predicate=None, show_all=False, kg_db=None)
        with patch("memos.cli.commands_knowledge._get_kg", return_value=kg):
            cmd_kg_backlinks(ns)
        out = capsys.readouterr().out
        assert "No backlinks" in out
