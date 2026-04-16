"""Tests for Obsidian-compatible YAML frontmatter on wiki pages (Task 3.4)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from memos.core import MemOS
from memos.wiki_living import LivingPage, LivingWikiEngine, _frontmatter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mem():
    m = MemOS()
    m.learn("Alice works on Project Phoenix with Bob", tags=["project", "team"])
    m.learn("Project Phoenix is a search tool for MemOS", tags=["project"])
    return m


@pytest.fixture
def engine(mem, tmp_path):
    return LivingWikiEngine(mem, wiki_dir=str(tmp_path / "wiki"))


# ---------------------------------------------------------------------------
# Module-level _frontmatter() tests
# ---------------------------------------------------------------------------

class TestModuleFrontmatter:
    """Tests for the module-level _frontmatter(meta) function."""

    def test_produces_yaml_with_delimiters(self):
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
        # Extract YAML between delimiters
        yaml_str = fm.split("\n", 1)[1].rsplit("\n---", 1)[0]
        parsed = yaml.safe_load(yaml_str)
        assert parsed is not None

    def test_maps_entity_to_title(self):
        meta = {"entity": "MyEntity", "type": "person"}
        fm = _frontmatter(meta)
        assert 'title: "MyEntity"' in fm

    def test_maps_memory_count_to_sources(self):
        meta = {"entity": "X", "type": "default", "memory_count": 7}
        fm = _frontmatter(meta)
        assert "sources: 7" in fm

    def test_tags_list_rendered(self):
        meta = {"entity": "X", "type": "topic", "tags": ["alpha", "beta"]}
        fm = _frontmatter(meta)
        assert "tags: [alpha, beta]" in fm

    def test_empty_tags_fallback(self):
        meta = {"entity": "X", "type": "default", "tags": []}
        fm = _frontmatter(meta)
        assert "tags: [auto, entity]" in fm

    def test_no_tags_key_fallback(self):
        meta = {"entity": "X", "type": "default"}
        fm = _frontmatter(meta)
        assert "tags: [auto, entity]" in fm

    def test_date_fields(self):
        meta = {"entity": "X", "type": "default", "created": "2024-03-14", "updated": "2025-01-01"}
        fm = _frontmatter(meta)
        assert "created: 2024-03-14" in fm
        assert "updated: 2025-01-01" in fm

    def test_complete_frontmatter_is_valid_yaml(self):
        meta = {
            "entity": "Complete Test",
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
        assert parsed["title"] == "Complete Test"
        assert parsed["type"] == "project"
        assert parsed["sources"] == 5
        assert str(parsed["created"]) == "2024-01-01"
        assert str(parsed["updated"]) == "2025-06-15"


# ---------------------------------------------------------------------------
# Instance method _frontmatter(self, page) tests
# ---------------------------------------------------------------------------

class TestInstanceFrontmatter:
    """Tests for LivingWikiEngine._frontmatter(self, page) method."""

    def test_with_living_page(self, engine):
        import time

        page = LivingPage(
            entity="Alice",
            entity_type="person",
            path=Path("/tmp/alice.md"),
            memory_ids=["m1", "m2"],
            backlinks=["Bob"],
            created_at=time.time(),
            updated_at=time.time(),
            size_bytes=100,
        )
        fm = engine._frontmatter(page)
        assert 'title: "Alice"' in fm
        assert "type: person" in fm
        assert "sources: 2" in fm
        assert fm.startswith("---\n")
        assert fm.strip().endswith("---")

    def test_with_living_page_no_tags(self, engine):
        page = LivingPage(
            entity="Test",
            entity_type="concept",
            path=Path("/tmp/test.md"),
        )
        fm = engine._frontmatter(page)
        assert "tags: [auto, entity]" in fm

    def test_with_living_page_custom_tags(self, engine):
        LivingPage(
            entity="Tagged",
            entity_type="topic",
            path=Path("/tmp/tagged.md"),
        )
        # LivingPage doesn't have a tags field, but let's use a mock-like object
        class TaggedPage:
            entity = "Tagged"
            entity_type = "topic"
            tags = ["python", "ml"]
            memory_ids = ["m1"]
            created_at = None
        fm = engine._frontmatter(TaggedPage())
        assert "tags: [python, ml]" in fm
        assert "sources: 1" in fm

    def test_output_is_valid_yaml(self, engine):
        import time as t

        page = LivingPage(
            entity="YAML Test",
            entity_type="project",
            path=Path("/tmp/yaml.md"),
            memory_ids=["a", "b", "c"],
            created_at=t.time(),
        )
        fm = engine._frontmatter(page)
        lines = fm.strip().split("\n")
        yaml_body = "\n".join(lines[1:-1])
        parsed = yaml.safe_load(yaml_body)
        assert parsed["title"] == "YAML Test"
        assert parsed["type"] == "project"
        assert parsed["sources"] == 3
        # created should be a date string
        assert re.match(r"\d{4}-\d{2}-\d{2}", str(parsed["created"]))


# ---------------------------------------------------------------------------
# Integration: pages written to disk contain valid frontmatter
# ---------------------------------------------------------------------------

class TestFrontmatterIntegration:
    """Tests that pages written by the engine contain valid Obsidian frontmatter."""

    def test_created_pages_have_frontmatter(self, engine):
        engine.update(force=True)

        pages_dir = Path(engine._wiki_dir) / "pages"
        assert pages_dir.exists()

        for page_file in pages_dir.glob("*.md"):
            content = page_file.read_text(encoding="utf-8")
            # Must start with frontmatter
            assert content.startswith("---\n"), f"{page_file.name} missing frontmatter"
            # Find closing ---
            lines = content.split("\n")
            assert lines[0] == "---"
            # Find second ---
            end_idx = None
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    end_idx = i
                    break
            assert end_idx is not None, f"{page_file.name} has no closing ---"

            # Parse YAML
            yaml_body = "\n".join(lines[1:end_idx])
            parsed = yaml.safe_load(yaml_body)
            assert parsed is not None, f"{page_file.name} frontmatter is not valid YAML"
            assert "title" in parsed, f"{page_file.name} missing 'title' in frontmatter"
            assert "type" in parsed, f"{page_file.name} missing 'type' in frontmatter"
            assert "tags" in parsed, f"{page_file.name} missing 'tags' in frontmatter"
            assert "created" in parsed, f"{page_file.name} missing 'created' in frontmatter"
            assert "updated" in parsed, f"{page_file.name} missing 'updated' in frontmatter"
            assert "sources" in parsed, f"{page_file.name} missing 'sources' in frontmatter"

    def test_frontmatter_title_matches_entity(self, engine):
        engine.update(force=True)
        page = engine.read_page("Alice")
        assert page is not None
        assert 'title: "Alice"' in page

    def test_frontmatter_type_is_set(self, engine):
        engine.update(force=True)
        page = engine.read_page("Alice")
        assert page is not None
        # Alice should be a person type
        assert "type: person" in page

    def test_frontmatter_sources_increments(self, engine):
        engine.update(force=True)
        page = engine.read_page("Project Phoenix")
        assert page is not None
        # Project Phoenix appears in 2 memories
        assert "sources:" in page
        # Extract sources value
        match = re.search(r"sources: (\d+)", page)
        assert match is not None
        sources = int(match.group(1))
        assert sources >= 2

    def test_read_page_returns_full_content_with_frontmatter(self, engine):
        engine.update(force=True)
        content = engine.read_page("Alice")
        assert content is not None
        assert content.startswith("---\n")
        assert 'title: "Alice"' in content

    def test_create_page_includes_frontmatter(self, engine):
        engine.init()
        result = engine.create_page("TestEntity", entity_type="concept", content="Some notes")
        assert result["status"] == "created"

        page = engine.read_page("TestEntity")
        assert page is not None
        assert 'title: "TestEntity"' in page
        assert "type: concept" in page

        # Verify YAML is valid
        lines = page.split("\n")
        end_idx = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_idx = i
                break
        assert end_idx is not None
        yaml_body = "\n".join(lines[1:end_idx])
        parsed = yaml.safe_load(yaml_body)
        assert parsed["title"] == "TestEntity"
        assert parsed["type"] == "concept"

    def test_update_for_item_produces_frontmatter(self, engine):
        engine.update(force=True)
        # Learn a new memory and update incrementally
        mem = engine._memos
        item = mem.learn("Charlie joined Project Phoenix recently")
        engine.update_for_item(item)

        page = engine.read_page("Charlie")
        assert page is not None
        assert 'title: "Charlie"' in page

        # Verify YAML validity
        lines = page.split("\n")
        end_idx = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_idx = i
                break
        assert end_idx is not None
        yaml_body = "\n".join(lines[1:end_idx])
        parsed = yaml.safe_load(yaml_body)
        assert isinstance(parsed, dict)
        assert "title" in parsed

    def test_frontmatter_updated_on_page_update(self, engine):
        engine.update(force=True)

        # Read initial page
        page1 = engine.read_page("Alice")
        assert page1 is not None

        # Learn new content about Alice
        mem = engine._memos
        item = mem.learn("Alice also knows Charlie")
        engine.update_for_item(item)

        page2 = engine.read_page("Alice")
        assert page2 is not None

        # Sources should have increased
        sources_match = re.search(r"sources: (\d+)", page2)
        assert sources_match is not None
        assert int(sources_match.group(1)) >= 2
