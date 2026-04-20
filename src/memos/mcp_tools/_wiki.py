"""Wiki tools: wiki_regenerate_index, wiki_lint."""

from __future__ import annotations

from typing import Any

from ._registry import _text, register_tool

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_WIKI_REGENERATE_INDEX = {
    "name": "wiki_regenerate_index",
    "description": "Regenerate the Karpathy-style Living Wiki index.md and return its content.",
    "inputSchema": {"type": "object", "properties": {}},
}

_WIKI_LINT = {
    "name": "wiki_lint",
    "description": "Run a comprehensive wiki health-check. Returns a structured report with orphan pages, missing cross-references, stale pages, empty pages, and contradictions.",
    "inputSchema": {"type": "object", "properties": {}},
}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _handle_wiki_regenerate_index(args: dict, memos: Any) -> dict:
    from ..wiki_living import LivingWikiEngine

    wiki = LivingWikiEngine(memos)
    content = wiki.regenerate_index()
    return _text(content)


def _handle_wiki_lint(args: dict, memos: Any) -> dict:
    from ..wiki_living import LivingWikiEngine

    wiki = LivingWikiEngine(memos)
    report = wiki.lint_report()
    summary = report["summary"]
    issues = report["issues"]
    lines = [
        f"Wiki Lint Report: {summary['total_pages']} pages checked",
        "",
        f"  Orphans: {summary['orphan_count']}",
        f"  Missing refs: {summary['missing_ref_count']}",
        f"  Stale pages: {summary['stale_count']}",
        f"  Empty pages: {summary['empty_count']}",
        f"  Contradictions: {summary['contradiction_count']}",
        "",
    ]
    for issue in issues:
        lines.append(f"  [{issue['severity'].upper()}] {issue['type']}: {issue['page']} — {issue['detail']}")
    return _text("\n".join(lines))


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

register_tool("wiki_regenerate_index", _WIKI_REGENERATE_INDEX, _handle_wiki_regenerate_index)
register_tool("wiki_lint", _WIKI_LINT, _handle_wiki_lint)
