"""Tests for expanded SVO regex patterns in kg_bridge.py fact extraction."""

from __future__ import annotations

import pytest

from memos.kg_bridge import KGBridge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract(text: str) -> list[tuple[str, str, str]]:
    """Shortcut: extract facts from a single string."""
    return KGBridge.extract_facts(text)


def _first(text: str) -> tuple[str, str, str] | None:
    """Return the first extracted fact, or None."""
    facts = _extract(text)
    return facts[0] if facts else None


# ===========================================================================
# Existing patterns — regression
# ===========================================================================

class TestExistingPatterns:
    """Ensure the original 4 patterns still work after reordering."""

    def test_is(self):
        f = _first("Python is great")
        assert f is not None
        assert f[1] == "is"
        assert f[0] == "Python"
        assert f[2] == "great"

    def test_works_at(self):
        f = _first("Alice works at Acme Corp")
        assert f is not None
        assert f[1] == "works_at"
        assert f[0] == "Alice"
        assert f[2] == "Acme Corp"

    def test_arrow(self):
        f = _first("Kafka → Zookeeper")
        assert f is not None
        assert f[1] == "arrow"
        assert "Kafka" in f[0]
        assert "Zookeeper" in f[2]

    def test_from_to(self):
        f = _first("from: Paris to: Berlin")
        assert f is not None
        assert f[1] == "from_to"


# ===========================================================================
# New pattern: active_verb (broader catch for verbs without dedicated patterns)
# ===========================================================================

class TestActiveVerb:
    """X supports/implements/provides/etc Y — broader verb catch."""

    @pytest.mark.parametrize(
        "text,subject,object_",
        [
            ("Redis supports Clustering", "Redis", "Clustering"),
            ("Prometheus monitors Grafana", "Prometheus", "Grafana"),
            ("Terraform configures AWS", "Terraform", "AWS"),
            ("Nginx powers Frontend", "Nginx", "Frontend"),
            ("Argo orchestrates Workflows", "Argo", "Workflows"),
            ("Istio provides Networking", "Istio", "Networking"),
            ("Consul implements Discovery", "Consul", "Discovery"),
        ],
    )
    def test_active_verb_verbs(self, text, subject, object_):
        f = _first(text)
        assert f is not None, f"No fact extracted from: {text!r}"
        assert f[0] == subject
        assert f[2] == object_
        # These verbs are caught by active_verb or fine-grained patterns
        assert f[1] in ("active_verb", "uses", "manages", "runs_on",
                        "deployed_on", "hosts", "contains", "depends_on")

    def test_no_match_for_non_listed_verb(self):
        """A line with none of the listed verbs should NOT match active_verb."""
        facts = _extract("Bob visited Paris")
        for s, p, o in facts:
            assert p != "active_verb"


# ===========================================================================
# Fine-grained verb patterns (extracted by opencode run)
# ===========================================================================

class TestFineGrainedVerbs:
    """Dedicated patterns for common verbs: uses, manages, runs_on, etc."""

    def test_uses(self):
        f = _first("Our service uses PostgreSQL")
        assert f is not None
        assert f[1] == "uses"
        assert f[0] == "Our service"
        assert f[2] == "PostgreSQL"

    def test_manages(self):
        f = _first("Kubernetes manages Pods")
        assert f is not None
        assert f[1] == "manages"
        assert f[0] == "Kubernetes"
        assert f[2] == "Pods"

    def test_runs_on(self):
        f = _first("Docker runs on Linux")
        assert f is not None
        assert f[1] == "runs_on"
        assert f[0] == "Docker"
        assert f[2] == "Linux"

    def test_depends_on(self):
        f = _first("Frontend depends on API")
        assert f is not None
        assert f[1] == "depends_on"
        assert f[0] == "Frontend"
        assert f[2] == "API"

    def test_contains(self):
        f = _first("Cluster contains Nodes")
        assert f is not None
        assert f[1] == "contains"
        assert f[0] == "Cluster"
        assert f[2] == "Nodes"

    def test_deployed_on(self):
        f = _first("Team deployed Nginx on AWS")
        assert f is not None
        assert f[1] == "deployed_on"
        assert f[0] == "Team"
        assert f[2] == "AWS"

    def test_hosts(self):
        f = _first("Server hosts Application")
        assert f is not None
        assert f[1] == "hosts"
        assert f[0] == "Server"
        assert f[2] == "Application"

    def test_built_with(self):
        f = _first("Backend built with Python")
        assert f is not None
        assert f[1] == "built_with"
        assert f[0] == "Backend"
        assert f[2] == "Python"

    def test_part_of(self):
        f = _first("Pod is part of Cluster")
        assert f is not None
        assert f[1] == "part_of"
        # Multi-word subject pattern captures "Pod is" with optional-is construct
        assert "Pod" in f[0]
        assert f[2] == "Cluster"

    def test_connected_to(self):
        f = _first("Database is connected to Cache")
        assert f is not None
        assert f[1] == "connected_to"
        # Multi-word subject pattern captures "Database is" with optional-is construct
        assert "Database" in f[0]
        assert f[2] == "Cache"


# ===========================================================================
# New pattern: is_type_of
# ===========================================================================

class TestIsTypeOf:
    """X is a/an TYPE of Y"""

    @pytest.mark.parametrize(
        "text,subject,object_",
        [
            ("Kubernetes is a platform of Cloud", "Kubernetes", "Cloud"),
            ("Redis is an example of Database", "Redis", "Database"),
            ("Python is a kind of Language", "Python", "Language"),
            ("Memcached is a variant of Cache", "Memcached", "Cache"),
        ],
    )
    def test_various_type_of(self, text, subject, object_):
        f = _first(text)
        assert f is not None, f"No fact extracted from: {text!r}"
        assert f[1] == "is_type_of"
        assert f[0] == subject
        assert f[2] == object_

    def test_generic_is_not_type_of(self):
        """Plain 'X is Y' should match 'is', not 'is_type_of'."""
        f = _first("Python is great")
        assert f is not None
        assert f[1] == "is"

    def test_is_type_of_with_an(self):
        f = _first("Elasticsearch is an instance of Search")
        assert f is not None
        assert f[1] == "is_type_of"
        assert f[0] == "Elasticsearch"
        assert f[2] == "Search"


# ===========================================================================
# New pattern: located
# ===========================================================================

class TestLocated:
    """X is located/running/hosted on/in Y"""

    @pytest.mark.parametrize(
        "text,subject,object_",
        [
            ("Redis is located on AWS", "Redis", "AWS"),
            ("The app is running in Kubernetes", "The app", "Kubernetes"),
            ("Grafana is hosted at DigitalOcean", "Grafana", "DigitalOcean"),
            ("PostgreSQL is deployed on GCP", "PostgreSQL", "GCP"),
            ("Nginx is based in Europe", "Nginx", "Europe"),
        ],
    )
    def test_various_located(self, text, subject, object_):
        f = _first(text)
        assert f is not None, f"No fact extracted from: {text!r}"
        assert f[1] == "located"
        assert f[0] == subject
        assert f[2] == object_

    def test_located_not_generic_is(self):
        """'X is located in Y' must match 'located', not generic 'is'."""
        f = _first("MinIO is located in Datacenter")
        assert f is not None
        assert f[1] == "located"


# ===========================================================================
# New pattern: version
# ===========================================================================

class TestVersion:
    """X version N"""

    @pytest.mark.parametrize(
        "text,subject,object_",
        [
            ("Python version 3.12", "Python", "3.12"),
            ("Node version 20", "Node", "20"),
            ("Kubernetes version 1.29.1", "Kubernetes", "1.29.1"),
            ("OpenSSL version 3.0.2", "OpenSSL", "3.0.2"),
        ],
    )
    def test_version_extraction(self, text, subject, object_):
        f = _first(text)
        assert f is not None, f"No fact extracted from: {text!r}"
        assert f[1] == "version"
        assert f[0] == subject
        assert f[2] == object_

    def test_version_with_extra_context(self):
        text = "We upgraded to Redis version 7.2"
        f = _first(text)
        assert f is not None
        assert f[1] == "version"
        assert f[2] == "7.2"


# ===========================================================================
# New pattern: general_svo (fallback)
# ===========================================================================

class TestGeneralSVO:
    """Capitalized + verb-ed + Capitalized fallback."""

    @pytest.mark.parametrize(
        "text,subject,object_",
        [
            ("Alice reviewed Code", "Alice", "Code"),
            ("Bob migrated Database", "Bob", "Database"),
            ("Carol refactored Service", "Carol", "Service"),
            ("Dave patched Kernel", "Dave", "Kernel"),
        ],
    )
    def test_general_svo(self, text, subject, object_):
        f = _first(text)
        assert f is not None, f"No fact extracted from: {text!r}"
        assert f[1] == "general_svo"
        assert f[0] == subject
        assert f[2] == object_

    def test_no_match_without_ed_verb(self):
        """A sentence with no past-tense (-ed) verb should not match general_svo."""
        facts = _extract("Alice visits Paris regularly")
        for s, p, o in facts:
            assert p != "general_svo"


# ===========================================================================
# New pattern: located_in (fine-grained)
# ===========================================================================

class TestLocatedIn:
    """X located in Y (with optional 'is')."""

    def test_located_in_simple(self):
        f = _first("Redis located in Datacenter")
        assert f is not None
        assert f[1] == "located_in"
        assert f[0] == "Redis"
        assert f[2] == "Datacenter"

    def test_located_in_with_is(self):
        # "X is located in Y" matches the broader "located" pattern first
        f = _first("Redis is located in Datacenter")
        assert f is not None
        assert f[1] == "located"  # broader "located" pattern takes priority
        assert f[0] == "Redis"
        assert f[2] == "Datacenter"


# ===========================================================================
# Multi-line / multi-fact extraction
# ===========================================================================

class TestMultiFact:
    """Multiple facts across multiple lines."""

    def test_two_different_patterns(self):
        text = (
            "Kubernetes manages Pods\n"
            "Redis is located on AWS\n"
        )
        facts = _extract(text)
        predicates = {f[1] for f in facts}
        assert "manages" in predicates
        assert "located" in predicates

    def test_first_match_wins_per_line(self):
        """Only one fact per line (first matching pattern wins)."""
        text = "Kubernetes is a platform of Cloud and runs on Nodes"
        facts = _extract(text)
        # Should match is_type_of (higher priority) not runs_on
        assert len(facts) == 1
        assert facts[0][1] == "is_type_of"

    def test_empty_lines_ignored(self):
        text = "\n\nRedis version 7.2\n\n"
        facts = _extract(text)
        assert len(facts) == 1
        assert facts[0][1] == "version"

    def test_arrow_and_version(self):
        text = (
            "Python version 3.12\n"
            "FastAPI → Django\n"
        )
        facts = _extract(text)
        assert len(facts) == 2
        predicates = {f[1] for f in facts}
        assert predicates == {"version", "arrow"}

    def test_three_lines_three_facts(self):
        text = (
            "Prometheus monitors Grafana\n"
            "PostgreSQL version 15.4\n"
            "Backend built with Rust\n"
        )
        facts = _extract(text)
        assert len(facts) == 3
        predicates = {f[1] for f in facts}
        assert predicates == {"active_verb", "version", "built_with"}
