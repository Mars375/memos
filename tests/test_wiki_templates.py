"""Direct tests for wiki_templates module — page templates and frontmatter generation."""

from __future__ import annotations

import time

import yaml

# Direct import from the split module
from memos.wiki_templates import _PAGE_TEMPLATES, _frontmatter

# ---------------------------------------------------------------------------
# _frontmatter function
# ---------------------------------------------------------------------------


class TestFrontmatterFunction:
    """Tests for the module-level _frontmatter(meta) helper."""

    def test_produces_yaml_with_delimiters(self) -> None:
        meta = {
            "entity": "TestEntity",
            "type": "concept",
            "created": "2025-01-01",
            "updated": "2025-06-15",
            "memory_count": 3,
            "tags": ["auto", "test"],
        }
        fm = _frontmatter(meta)
        assert fm.startswith("---\n")
        assert fm.endswith("\n---")

    def test_maps_entity_to_title(self) -> None:
        meta = {"entity": "MyEntity", "type": "person"}
        fm = _frontmatter(meta)
        assert 'title: "MyEntity"' in fm

    def test_maps_memory_count_to_sources(self) -> None:
        meta = {"entity": "X", "type": "default", "memory_count": 7}
        fm = _frontmatter(meta)
        assert "sources: 7" in fm

    def test_tags_list_rendered(self) -> None:
        meta = {"entity": "X", "type": "topic", "tags": ["alpha", "beta"]}
        fm = _frontmatter(meta)
        assert "tags: [alpha, beta]" in fm

    def test_empty_tags_fallback(self) -> None:
        meta = {"entity": "X", "type": "default", "tags": []}
        fm = _frontmatter(meta)
        assert "tags: [auto, entity]" in fm

    def test_no_tags_key_fallback(self) -> None:
        meta = {"entity": "X", "type": "default"}
        fm = _frontmatter(meta)
        assert "tags: [auto, entity]" in fm

    def test_date_fields(self) -> None:
        meta = {"entity": "X", "type": "default", "created": "2024-03-14", "updated": "2025-01-01"}
        fm = _frontmatter(meta)
        assert "created: 2024-03-14" in fm
        assert "updated: 2025-01-01" in fm

    def test_valid_yaml_output(self) -> None:
        meta = {
            "entity": "Complete",
            "type": "project",
            "created": "2024-01-01",
            "updated": "2025-06-15",
            "memory_count": 5,
            "tags": ["important"],
        }
        fm = _frontmatter(meta)
        lines = fm.split("\n")
        assert lines[0] == "---"
        assert lines[-1] == "---"
        yaml_body = "\n".join(lines[1:-1])
        parsed = yaml.safe_load(yaml_body)
        assert parsed["title"] == "Complete"
        assert parsed["type"] == "project"
        assert parsed["sources"] == 5

    def test_default_date_when_missing(self) -> None:
        """When created/updated are not provided, uses today's date."""
        meta = {"entity": "Y", "type": "default"}
        fm = _frontmatter(meta)
        today = time.strftime("%Y-%m-%d")
        assert f"created: {today}" in fm
        assert f"updated: {today}" in fm

    def test_sources_fallback_to_sources_key(self) -> None:
        """When memory_count is missing but sources is present, uses sources."""
        meta = {"entity": "Z", "type": "default", "sources": 10}
        fm = _frontmatter(meta)
        assert "sources: 10" in fm

    def test_default_sources_zero(self) -> None:
        meta = {"entity": "W", "type": "default"}
        fm = _frontmatter(meta)
        assert "sources: 0" in fm


# ---------------------------------------------------------------------------
# _PAGE_TEMPLATES
# ---------------------------------------------------------------------------


class TestPageTemplates:
    """Tests for the _PAGE_TEMPLATES dictionary."""

    EXPECTED_TYPES = {"person", "project", "concept", "topic", "resource", "contact", "default"}

    def test_all_expected_types_present(self) -> None:
        for t in self.EXPECTED_TYPES:
            assert t in _PAGE_TEMPLATES, f"Missing template for type '{t}'"

    def test_each_template_is_callable(self) -> None:
        for t in self.EXPECTED_TYPES:
            assert callable(_PAGE_TEMPLATES[t]), f"Template for '{t}' is not callable"

    def test_person_template_output(self) -> None:
        meta = {"entity": "Alice", "type": "person", "created": "2025-01-01", "updated": "2025-01-01"}
        content = _PAGE_TEMPLATES["person"]("Alice", meta)
        assert "# Alice" in content
        assert "## Overview" in content
        assert "## Key Facts" in content
        assert "---\n" in content  # frontmatter

    def test_project_template_output(self) -> None:
        meta = {"entity": "Phoenix", "type": "project"}
        content = _PAGE_TEMPLATES["project"]("Phoenix", meta)
        assert "# Phoenix" in content
        assert "## Status" in content
        assert "## Architecture" in content

    def test_concept_template_output(self) -> None:
        meta = {"entity": "Entropy", "type": "concept"}
        content = _PAGE_TEMPLATES["concept"]("Entropy", meta)
        assert "# Entropy" in content
        assert "## Definition" in content
        assert "## Related" in content

    def test_topic_template_output(self) -> None:
        meta = {"entity": "Physics", "type": "topic"}
        content = _PAGE_TEMPLATES["topic"]("Physics", meta)
        assert "# Physics" in content
        assert "## Summary" in content

    def test_resource_template_output(self) -> None:
        meta = {"entity": "API", "type": "resource"}
        content = _PAGE_TEMPLATES["resource"]("API", meta)
        assert "# API" in content
        assert "## Details" in content

    def test_contact_template_output(self) -> None:
        meta = {"entity": "bob@example.com", "type": "contact"}
        content = _PAGE_TEMPLATES["contact"]("bob@example.com", meta)
        assert "# bob@example.com" in content
        assert "## Contact Info" in content

    def test_default_template_output(self) -> None:
        meta = {"entity": "Thing", "type": "default"}
        content = _PAGE_TEMPLATES["default"]("Thing", meta)
        assert "# Thing" in content
        assert "## Notes" in content

    def test_templates_produce_frontmatter(self) -> None:
        """Every template output starts with YAML frontmatter."""
        for t in self.EXPECTED_TYPES:
            meta = {"entity": "E", "type": t}
            content = _PAGE_TEMPLATES[t]("E", meta)
            assert content.startswith("---\n"), f"Template '{t}' doesn't start with frontmatter"
            # Closing ---
            assert "\n---\n" in content or content.strip().endswith("---"), (
                f"Template '{t}' missing closing frontmatter delimiter"
            )

    def test_templates_contain_entity_name(self) -> None:
        """Each template should embed the entity name as an H1 heading."""
        for t in self.EXPECTED_TYPES:
            meta = {"entity": "TestName", "type": t}
            content = _PAGE_TEMPLATES[t]("TestName", meta)
            assert "# TestName" in content, f"Template '{t}' missing H1 for entity name"


# ---------------------------------------------------------------------------
# Backward compatibility — import from wiki_living shim
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    """Legacy import path from wiki_living resolves to same objects."""

    def test_frontmatter_same_function(self) -> None:
        from memos.wiki_living import _frontmatter as shim_fm

        assert shim_fm is _frontmatter

    def test_templates_same_dict(self) -> None:
        from memos.wiki_living import _PAGE_TEMPLATES as shim_templates

        assert shim_templates is _PAGE_TEMPLATES
