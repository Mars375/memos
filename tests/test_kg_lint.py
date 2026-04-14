"""Tests for KnowledgeGraph.lint() — P2: quality linting."""


class TestLintClean:
    def test_empty_graph(self, kg):
        report = kg.lint()
        assert report["contradictions"] == []
        assert report["orphans"] == []
        assert report["sparse"] == []
        assert report["summary"]["active_facts"] == 0

    def test_clean_graph_no_issues(self, kg):
        kg.add_fact("Alice", "works_on", "ProjectX")
        kg.add_fact("Alice", "leads", "TeamA")
        kg.add_fact("Bob", "works_on", "ProjectX")
        kg.add_fact("Bob", "member_of", "TeamA")
        report = kg.lint(min_facts=2)
        assert report["contradictions"] == []
        # All entities above appear in ≥2 triples when counted as subject+object
        assert report["summary"]["active_facts"] == 4


class TestContradictions:
    def test_single_predicate_multiple_objects(self, kg):
        kg.add_fact("Alice", "works_at", "CompanyA")
        kg.add_fact("Alice", "works_at", "CompanyB")
        report = kg.lint()
        assert len(report["contradictions"]) == 1
        c = report["contradictions"][0]
        assert c["subject"] == "Alice"
        assert c["predicate"] == "works_at"
        assert set(c["objects"]) == {"CompanyA", "CompanyB"}

    def test_no_contradiction_different_predicates(self, kg):
        kg.add_fact("Alice", "works_at", "CompanyA")
        kg.add_fact("Alice", "lives_in", "CompanyA")
        report = kg.lint()
        assert report["contradictions"] == []

    def test_invalidated_fact_not_counted(self, kg):
        fid = kg.add_fact("Alice", "works_at", "CompanyA")
        kg.add_fact("Alice", "works_at", "CompanyB")
        kg.invalidate(fid)
        report = kg.lint()
        # Only CompanyB remains active — no contradiction
        assert report["contradictions"] == []

    def test_multiple_contradictions(self, kg):
        kg.add_fact("Alice", "works_at", "CompanyA")
        kg.add_fact("Alice", "works_at", "CompanyB")
        kg.add_fact("Bob", "lives_in", "Paris")
        kg.add_fact("Bob", "lives_in", "London")
        report = kg.lint()
        assert report["summary"]["contradictions"] == 2


class TestOrphans:
    def test_single_triple_both_ends_orphan(self, kg):
        kg.add_fact("Alice", "knows", "Bob")
        report = kg.lint()
        # Alice and Bob each appear in exactly one triple (degree=1)
        assert "Alice" in report["orphans"]
        assert "Bob" in report["orphans"]

    def test_high_degree_entity_not_orphan(self, kg):
        kg.add_fact("Alice", "knows", "Bob")
        kg.add_fact("Alice", "knows", "Carol")
        kg.add_fact("Alice", "works_on", "ProjectX")
        report = kg.lint()
        # Alice has degree 3 — not an orphan
        assert "Alice" not in report["orphans"]

    def test_orphan_detection_object_side(self, kg):
        kg.add_fact("Alice", "knows", "Bob")
        kg.add_fact("Carol", "knows", "Bob")
        # Bob appears as object twice (degree=2) — not an orphan
        report = kg.lint()
        assert "Bob" not in report["orphans"]


class TestSparse:
    def test_entity_with_one_fact_is_sparse(self, kg):
        kg.add_fact("Alice", "works_at", "CompanyA")
        report = kg.lint(min_facts=2)
        assert "Alice" in report["sparse"]

    def test_entity_with_enough_facts_not_sparse(self, kg):
        kg.add_fact("Alice", "works_at", "CompanyA")
        kg.add_fact("Alice", "lives_in", "Paris")
        report = kg.lint(min_facts=2)
        assert "Alice" not in report["sparse"]

    def test_min_facts_1_nothing_sparse(self, kg):
        kg.add_fact("Alice", "works_at", "CompanyA")
        report = kg.lint(min_facts=1)
        assert report["sparse"] == []

    def test_sparse_counts_subject_facts_only(self, kg):
        # CompanyA is only an object — it has 0 facts as subject
        kg.add_fact("Alice", "works_at", "CompanyA")
        report = kg.lint(min_facts=1)
        # CompanyA never appears as subject, so sparse doesn't count it
        assert "CompanyA" not in report["sparse"]


class TestCLI:
    def test_kg_lint_cli_clean(self, kg, capsys):
        import argparse
        from unittest.mock import patch

        from memos.cli import cmd_kg_lint

        kg.add_fact("Alice", "works_at", "CompanyA")
        kg.add_fact("Alice", "leads", "TeamA")
        kg.add_fact("Bob", "works_at", "CompanyA")
        kg.add_fact("Bob", "member_of", "TeamA")

        ns = argparse.Namespace(min_facts=2, kg_db=None)
        with patch("memos.cli.commands_knowledge._get_kg", return_value=kg):
            cmd_kg_lint(ns)
        out = capsys.readouterr().out
        assert "KG Lint Report" in out
        assert "No issues" in out

    def test_kg_lint_cli_with_issues(self, kg, capsys):
        import argparse
        from unittest.mock import patch

        from memos.cli import cmd_kg_lint

        kg.add_fact("Alice", "works_at", "CompanyA")
        kg.add_fact("Alice", "works_at", "CompanyB")

        ns = argparse.Namespace(min_facts=2, kg_db=None)
        with patch("memos.cli.commands_knowledge._get_kg", return_value=kg):
            cmd_kg_lint(ns)
        out = capsys.readouterr().out
        assert "CONTRADICTION" in out
        assert "CompanyA" in out
        assert "CompanyB" in out
