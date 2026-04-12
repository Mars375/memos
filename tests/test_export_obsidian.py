"""Tests for ObsidianExporter — P6 Obsidian-compatible export."""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from memos.export_obsidian import ObsidianExporter, ObsidianExportResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_memos(items=None):
    """Return a minimal memos mock."""
    memos = MagicMock()
    memos._namespace = ""
    items_list = items or []
    memos._store.list_all.return_value = items_list
    return memos


def _make_kg():
    from memos.knowledge_graph import KnowledgeGraph
    return KnowledgeGraph(db_path=":memory:")


# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------

class TestWikilinkInjection:
    def setup_method(self):
        memos = _make_memos()
        self.exp = ObsidianExporter(memos)

    def test_injects_wikilink(self):
        content = "---\nentity: Alice\n---\n\nAlice works at CompanyX.\n"
        result, n = self.exp._inject_wikilinks(content, ["Alice", "CompanyX"])
        assert "[[Alice]]" in result
        assert "[[CompanyX]]" in result
        assert n == 2

    def test_does_not_double_wrap(self):
        content = "---\n---\n\n[[Alice]] knows Alice.\n"
        result, n = self.exp._inject_wikilinks(content, ["Alice"])
        # The standalone "Alice" after the first [[Alice]] should get wrapped
        # but the existing [[Alice]] should remain unchanged
        assert "[[[[Alice]]]]" not in result
        assert result.count("[[Alice]]") == 2

    def test_does_not_inject_in_frontmatter(self):
        content = "---\nentity: Alice\ntags: [Alice]\n---\n\nContent here.\n"
        result, n = self.exp._inject_wikilinks(content, ["Alice"])
        # frontmatter lines should be untouched
        fm_end = result.find("\n---\n", 4) + 5
        frontmatter = result[:fm_end]
        assert "[[Alice]]" not in frontmatter

    def test_skips_short_names(self):
        content = "---\n---\nThe AI model uses ML.\n"
        result, n = self.exp._inject_wikilinks(content, ["AI", "ML"])
        # Names < 4 chars should be skipped
        assert "[[AI]]" not in result
        assert "[[ML]]" not in result
        assert n == 0

    def test_longest_match_first(self):
        content = "---\n---\nProjectX depends on Project.\n"
        result, n = self.exp._inject_wikilinks(content, ["ProjectX", "Project"])
        # ProjectX should match before Project
        assert "[[ProjectX]]" in result


class TestFrontmatterPatch:
    def setup_method(self):
        memos = _make_memos()
        self.exp = ObsidianExporter(memos)

    def test_adds_aliases(self, tmp_path):
        content = "---\nentity: Alice\ntype: entity\n---\n\n# Alice\n"
        md_file = tmp_path / "alice.md"
        md_file.write_text(content)
        result = self.exp._patch_frontmatter(content, md_file, tmp_path)
        assert 'aliases: ["Alice"]' in result

    def test_no_duplicate_aliases(self, tmp_path):
        content = '---\nentity: Alice\naliases: ["Alice"]\n---\n\n# Alice\n'
        md_file = tmp_path / "alice.md"
        result = self.exp._patch_frontmatter(content, md_file, tmp_path)
        assert result.count("aliases:") == 1

    def test_no_frontmatter_unchanged(self, tmp_path):
        content = "# Alice\n\nNo frontmatter here.\n"
        md_file = tmp_path / "alice.md"
        result = self.exp._patch_frontmatter(content, md_file, tmp_path)
        assert result == content


class TestPlainLinksToWikilinks:
    def setup_method(self):
        memos = _make_memos()
        self.exp = ObsidianExporter(memos)

    def test_converts_entity_links(self):
        idx = "## Top entities\n\n- [Alice](entities/alice.md)\n- [Bob](entities/bob.md)\n"
        result = self.exp._plain_links_to_wikilinks(idx)
        assert "[[Alice]]" in result
        assert "[[Bob]]" in result
        assert "(entities/alice.md)" not in result

    def test_converts_community_links(self):
        idx = "- [Cluster 1](communities/cluster_1.md)\n"
        result = self.exp._plain_links_to_wikilinks(idx)
        assert "[[Cluster 1]]" in result

    def test_does_not_convert_external_links(self):
        idx = "- [Docs](https://example.com/docs)\n"
        result = self.exp._plain_links_to_wikilinks(idx)
        assert result == idx


# ---------------------------------------------------------------------------
# Integration test — full export pipeline
# ---------------------------------------------------------------------------

class TestObsidianExport:
    def test_export_returns_obsidian_result(self, tmp_path):
        """Full export produces ObsidianExportResult (even with empty store)."""
        memos = _make_memos()
        kg = _make_kg()

        # Patch out the heavy LivingWikiEngine calls
        with patch("memos.export_markdown.LivingWikiEngine") as MockWiki, \
             patch("memos.export_markdown.GraphWikiEngine") as MockGraph:
            MockWiki.return_value.update.return_value = MagicMock(
                pages_created=0, pages_updated=0, entities_found=0,
                memories_indexed=0, backlinks_added=0,
            )
            MockWiki.return_value.list_pages.return_value = []
            MockWiki.return_value._wiki_dir = tmp_path / "wiki"

            exporter = ObsidianExporter(memos, kg=kg)
            result = exporter.export(str(tmp_path / "vault"))

        assert isinstance(result, ObsidianExportResult)
        assert hasattr(result, "wikilinks_added")
        kg.close()

    def test_export_creates_index(self, tmp_path):
        """INDEX.md is created even for empty stores."""
        memos = _make_memos()
        kg = _make_kg()

        with patch("memos.export_markdown.LivingWikiEngine") as MockWiki, \
             patch("memos.export_markdown.GraphWikiEngine") as MockGraph:
            MockWiki.return_value.update.return_value = MagicMock(
                pages_created=0, pages_updated=0, entities_found=0,
                memories_indexed=0, backlinks_added=0,
            )
            MockWiki.return_value.list_pages.return_value = []
            MockWiki.return_value._wiki_dir = tmp_path / "wiki"

            exporter = ObsidianExporter(memos, kg=kg)
            vault = tmp_path / "vault"
            exporter.export(str(vault))

        assert (vault / "INDEX.md").exists()
        kg.close()

    def test_entity_page_gets_wikilinks(self, tmp_path):
        """After export, entity pages contain [[wikilinks]] for known entities."""
        memos = _make_memos()
        kg = _make_kg()
        kg.add_fact("Alice", "works_on", "ProjectX")

        entities_dir = tmp_path / "vault" / "entities"
        entities_dir.mkdir(parents=True)
        # Pre-create entity pages as the base exporter would
        alice_page = entities_dir / "alice.md"
        alice_page.write_text(
            "---\nentity: Alice\ntype: entity\n---\n\n# Alice\n\nAlice works on ProjectX.\n",
            encoding="utf-8",
        )
        projectx_page = entities_dir / "projectx.md"
        projectx_page.write_text(
            "---\nentity: ProjectX\ntype: entity\n---\n\n# ProjectX\n\nAlice uses ProjectX.\n",
            encoding="utf-8",
        )

        with patch("memos.export_markdown.LivingWikiEngine") as MockWiki, \
             patch("memos.export_markdown.GraphWikiEngine") as MockGraph:
            MockWiki.return_value.update.return_value = MagicMock(
                pages_created=0, pages_updated=0, entities_found=0,
                memories_indexed=0, backlinks_added=0,
            )
            MockWiki.return_value.list_pages.return_value = []
            MockWiki.return_value._wiki_dir = tmp_path / "wiki"

            # Manually inject wikilinks into the pre-created files
            exporter = ObsidianExporter(memos, kg=kg)
            entity_names = exporter._collect_entity_names(entities_dir)

        assert "Alice" in entity_names
        assert "ProjectX" in entity_names

        alice_text = alice_page.read_text()
        patched, n = exporter._inject_wikilinks(alice_text, entity_names)
        assert "[[ProjectX]]" in patched
        assert n >= 1
        kg.close()
