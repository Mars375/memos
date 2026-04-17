"""Tests for improved wiki page summary extraction.

Verifies that garbage lines (quoted content, code, URLs, short fragments)
are NOT used as summaries, and that real natural-language sentences are
preferred.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from memos.wiki_living import LivingWikiEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _FakeMemOS:
    """Minimal stub so LivingWikiEngine can be constructed."""

    _persist_path: str = ""


@pytest.fixture
def engine(tmp_path):
    """Return a LivingWikiEngine with a temp wiki directory."""
    fake = _FakeMemOS()
    fake._persist_path = str(tmp_path / "data" / "memos.json")
    eng = LivingWikiEngine(fake, wiki_dir=str(tmp_path / "wiki"))
    eng._wiki_dir.mkdir(parents=True, exist_ok=True)
    pages_dir = eng._wiki_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    return eng


def _write_page(engine: LivingWikiEngine, entity_name: str, content: str) -> Path:
    """Helper: write *content* as the page for *entity_name*."""
    slug = engine._safe_slug(entity_name)
    page_path = engine._wiki_dir / "pages" / f"{slug}.md"
    page_path.write_text(content, encoding="utf-8")
    return page_path


# ---------------------------------------------------------------------------
# Tests — garbage lines should NOT be summaries
# ---------------------------------------------------------------------------


def test_summary_not_parentheses(engine):
    """> ()" or similar punctuation-only lines must not be the summary."""
    _write_page(
        engine,
        "TestEntity",
        """---
title: "TestEntity"
---
# TestEntity

> ()

Some real content about TestEntity that is long enough.
""",
    )
    summary = engine._get_page_summary("TestEntity")
    assert summary != "()"
    assert summary != "> ()"
    assert "real content" in summary


def test_summary_not_short_fragment(engine):
    """"a embeddings" and similar short fragments must not be summaries."""
    _write_page(
        engine,
        "Embeddings",
        """---
title: "Embeddings"
---
# Embeddings

a embeddings

Embeddings are dense vector representations of tokens used in NLP models.
""",
    )
    summary = engine._get_page_summary("Embeddings")
    # "a embeddings" is only 13 chars — but fails the alpha-ratio/quality test
    # depending on exact filtering.  The real sentence should win.
    assert summary != "a embeddings"
    assert "dense vector" in summary or "Embeddings" in summary


def test_summary_not_url_line(engine):
    """Lines containing URLs should be skipped."""
    _write_page(
        engine,
        "APIDoc",
        """---
title: "APIDoc"
---
# APIDoc

— POST http://localhost:8100/mcp with JSON-RPC 2.0 body.

The MCP server exposes a JSON-RPC endpoint for AI agent communication.
""",
    )
    summary = engine._get_page_summary("APIDoc")
    assert "http://localhost" not in summary
    assert "JSON-RPC" in summary or "MCP server" in summary


def test_summary_not_quoted_content(engine):
    """Lines starting with > (blockquotes) must be skipped."""
    _write_page(
        engine,
        "QuoteTest",
        """---
title: "QuoteTest"
---
# QuoteTest

> This is a quoted line from somewhere else.

Loïc deployed MemOS on Cortex for the first time today.
""",
    )
    summary = engine._get_page_summary("QuoteTest")
    assert not summary.startswith(">")
    assert "Loïc deployed MemOS" in summary


def test_summary_not_code_fence_content(engine):
    """Content inside code fences must be skipped."""
    _write_page(
        engine,
        "CodeTest",
        """---
title: "CodeTest"
---
# CodeTest

```python
result = do_something()
print(result)
```

The do_something function returns a result object with status fields.
""",
    )
    summary = engine._get_page_summary("CodeTest")
    assert "do_something()" not in summary
    assert "result" in summary.lower() or "function" in summary.lower()


def test_summary_not_heading(engine):
    """Markdown headings must not be used as summaries."""
    _write_page(
        engine,
        "HeadingTest",
        """---
title: "HeadingTest"
---
# HeadingTest

## Overview

## Details

There is no actual content here except this line right now.
""",
    )
    summary = engine._get_page_summary("HeadingTest")
    assert not summary.startswith("#")


# ---------------------------------------------------------------------------
# Tests — good lines SHOULD be summaries
# ---------------------------------------------------------------------------


def test_real_sentence_preferred(engine):
    """A natural-language sentence should be selected as summary."""
    _write_page(
        engine,
        "Deployment",
        """---
title: "Deployment"
---
# Deployment

Loïc deployed MemOS on Cortex for the first time today.
""",
    )
    summary = engine._get_page_summary("Deployment")
    assert "Loïc deployed MemOS on Cortex" in summary


def test_summary_truncated_at_sentence_boundary(engine):
    """Long summaries are truncated at ~100 chars, at a sentence boundary."""
    long_sentence = (
        "This is a very long first sentence that goes on and on about various things. "
        "This is a second sentence that should be cut off."
    )
    _write_page(
        engine,
        "LongContent",
        f"""---
title: "LongContent"
---
# LongContent

{long_sentence}
""",
    )
    summary = engine._get_page_summary("LongContent")
    assert len(summary) <= 102  # 100 + period wiggle
    # Should end at first sentence boundary
    assert summary.endswith(".")


def test_nonexistent_page_returns_empty(engine):
    """Nonexistent pages return empty string."""
    assert engine._get_page_summary("DoesNotExist") == ""


# ---------------------------------------------------------------------------
# Test api_response helper
# ---------------------------------------------------------------------------


def test_api_response_helper():
    """api_response merges data with a status field."""
    from memos.api.errors import api_response

    result = api_response({"id": "abc", "count": 5})
    assert result == {"status": "ok", "id": "abc", "count": 5}

    result = api_response({"task_id": "xyz"}, status="completed")
    assert result == {"status": "completed", "task_id": "xyz"}

    result = api_response({"message": "bad"}, status="error")
    assert result == {"status": "error", "message": "bad"}
