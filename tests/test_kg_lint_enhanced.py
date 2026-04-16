"""Tests for Task 1.7: KG lint enhancements.

Tests for enhanced lint() detecting:
- Contradictory facts (same subject+predicate, different objects, both valid)
- Orphan entities (appearing in only one fact)
- Suggested new facts based on transitive relationships
- Structured report format
"""


class TestLintEnhancedReport:
    def test_report_has_suggested_facts_key(self, kg):
        report = kg.lint()
        assert "suggested_facts" in report
        assert isinstance(report["suggested_facts"], list)
        assert "suggested_facts" in report["summary"]

    def test_contradiction_includes_fact_ids(self, kg):
        fid1 = kg.add_fact("Alice", "works_at", "CompanyA")
        fid2 = kg.add_fact("Alice", "works_at", "CompanyB")
        report = kg.lint()
        assert len(report["contradictions"]) == 1
        c = report["contradictions"][0]
        assert "fact_ids" in c
        assert fid1 in c["fact_ids"]
        assert fid2 in c["fact_ids"]

    def test_empty_graph_has_empty_suggestions(self, kg):
        report = kg.lint()
        assert report["suggested_facts"] == []
        assert report["summary"]["suggested_facts"] == 0


class TestSuggestedFactsTransitive:
    def test_simple_transitive_chain(self, kg):
        """A→B and B→C suggests A→C (same predicate)."""
        kg.add_fact("Alice", "knows", "Bob")
        kg.add_fact("Bob", "knows", "Carol")
        report = kg.lint()

        suggestions = report["suggested_facts"]
        assert len(suggestions) >= 1

        # Find the Alice→Carol suggestion
        ac = [s for s in suggestions if s["subject"] == "Alice" and s["object"] == "Carol"]
        assert len(ac) == 1
        s = ac[0]
        assert s["predicate"] == "knows"
        assert s["reason"] == "transitive_inference"
        assert s["via"] == ["Alice", "Bob", "Carol"]

    def test_no_suggestion_if_fact_exists(self, kg):
        """Don't suggest A→C if that fact already exists."""
        kg.add_fact("Alice", "knows", "Bob")
        kg.add_fact("Bob", "knows", "Carol")
        kg.add_fact("Alice", "knows", "Carol")  # already exists
        report = kg.lint()

        ac = [s for s in report["suggested_facts"] if s["subject"] == "Alice" and s["object"] == "Carol"]
        assert len(ac) == 0

    def test_no_self_loop_suggestion(self, kg):
        """Don't suggest A→A."""
        kg.add_fact("Alice", "knows", "Bob")
        kg.add_fact("Bob", "knows", "Alice")
        report = kg.lint()

        self_loops = [s for s in report["suggested_facts"] if s["subject"] == s["object"]]
        assert len(self_loops) == 0

    def test_multi_hop_chain(self, kg):
        """Longer chain: A→B, B→C, C→D should suggest A→C, A→D, B→D."""
        kg.add_fact("A", "part_of", "B")
        kg.add_fact("B", "part_of", "C")
        kg.add_fact("C", "part_of", "D")
        report = kg.lint()

        suggestions = report["suggested_facts"]
        suggested_tuples = {(s["subject"], s["predicate"], s["object"]) for s in suggestions}
        # A→C (A→B→C)
        assert ("A", "part_of", "C") in suggested_tuples
        # B→D (B→C→D)
        assert ("B", "part_of", "D") in suggested_tuples

    def test_different_predicates_no_transitive(self, kg):
        """Facts with different predicates should not generate same-predicate suggestions."""
        kg.add_fact("Alice", "works_at", "OpenAI")
        kg.add_fact("OpenAI", "located_in", "SF")
        report = kg.lint()

        # No same-predicate transitive suggestion for these different predicates
        same_pred = [s for s in report["suggested_facts"]
                     if s["predicate"] == "works_at" and s["object"] == "SF"]
        # works_at doesn't chain with itself here
        assert len(same_pred) == 0


class TestSuggestedFactsCrossPredicate:
    def test_cross_predicate_transitivity(self, kg):
        """A works_at B, B located_in C → suggest A located_in C."""
        kg.add_fact("Alice", "works_at", "OpenAI")
        kg.add_fact("OpenAI", "located_in", "SF")
        report = kg.lint()

        cross = [s for s in report["suggested_facts"]
                 if s["reason"] == "cross_predicate_transitive"
                 and s["subject"] == "Alice" and s["object"] == "SF"]
        assert len(cross) == 1
        assert cross[0]["predicate"] == "located_in"
        assert cross[0]["via"] == ["Alice", "OpenAI", "SF"]

    def test_cross_predicate_no_duplicate(self, kg):
        """Cross-predicate suggestion should not duplicate existing fact."""
        kg.add_fact("Alice", "works_at", "OpenAI")
        kg.add_fact("OpenAI", "located_in", "SF")
        kg.add_fact("Alice", "located_in", "SF")  # already exists
        report = kg.lint()

        cross = [s for s in report["suggested_facts"]
                 if s["subject"] == "Alice" and s["predicate"] == "located_in"]
        assert len(cross) == 0


class TestOrphanDetection:
    def test_orphan_in_single_triple(self, kg):
        kg.add_fact("Alice", "knows", "Bob")
        report = kg.lint()
        assert "Alice" in report["orphans"]
        assert "Bob" in report["orphans"]

    def test_non_orphan_with_multiple_edges(self, kg):
        kg.add_fact("Alice", "knows", "Bob")
        kg.add_fact("Alice", "works_with", "Carol")
        kg.add_fact("Alice", "mentors", "Dave")
        report = kg.lint()
        assert "Alice" not in report["orphans"]

    def test_orphan_count_in_summary(self, kg):
        kg.add_fact("X", "relates_to", "Y")
        report = kg.lint()
        assert report["summary"]["orphans"] == 2


class TestContradictionWithValidity:
    def test_contradiction_only_active_facts(self, kg):
        """Only active (non-invalidated) facts should be considered contradictions."""
        fid1 = kg.add_fact("Alice", "lives_in", "Paris")
        kg.add_fact("Alice", "lives_in", "London")
        # Invalidate one — no more contradiction
        kg.invalidate(fid1)
        report = kg.lint()
        assert report["summary"]["contradictions"] == 0

    def test_contradiction_all_active(self, kg):
        """Multiple active facts with same subject+predicate → contradiction."""
        kg.add_fact("Bob", "role", "engineer")
        kg.add_fact("Bob", "role", "manager")
        report = kg.lint()
        assert report["summary"]["contradictions"] == 1
        c = report["contradictions"][0]
        assert set(c["objects"]) == {"engineer", "manager"}

    def test_no_contradiction_different_predicates(self, kg):
        kg.add_fact("Alice", "works_at", "Google")
        kg.add_fact("Alice", "lives_in", "Google")
        report = kg.lint()
        assert report["contradictions"] == []
