"""Wiki commands: wiki-compile, wiki-list, wiki-read, wiki-living, wiki-graph."""

from __future__ import annotations

from ._common import _add_backend_arg

_WIKI_BACKEND_CHOICES = ["memory", "chroma", "qdrant", "pinecone", "json"]


def build(sub) -> None:
    # wiki-compile
    wiki_compile_p = sub.add_parser("wiki-compile", help="Compile memories into markdown pages per tag")
    wiki_compile_p.add_argument("--tags", nargs="*", help="Only compile these tags")
    wiki_compile_p.add_argument("--wiki-dir", dest="wiki_dir", help="Output directory (default: ~/.memos/wiki)")
    _add_backend_arg(wiki_compile_p, choices=_WIKI_BACKEND_CHOICES)
    wiki_compile_p.add_argument("--persist-path", dest="persist_path", help="Path for json backend")

    # wiki-list
    wiki_list_p = sub.add_parser("wiki-list", help="List compiled wiki pages")
    wiki_list_p.add_argument("--wiki-dir", dest="wiki_dir", help="Wiki directory")
    _add_backend_arg(wiki_list_p, choices=_WIKI_BACKEND_CHOICES)
    wiki_list_p.add_argument("--persist-path", dest="persist_path", help="Path for json backend")

    # wiki-read
    wiki_read_p = sub.add_parser("wiki-read", help="Read a compiled wiki page by tag")
    wiki_read_p.add_argument("tag", help="Tag name to read")
    wiki_read_p.add_argument("--wiki-dir", dest="wiki_dir", help="Wiki directory")
    _add_backend_arg(wiki_read_p, choices=_WIKI_BACKEND_CHOICES)
    wiki_read_p.add_argument("--persist-path", dest="persist_path", help="Path for json backend")

    # wiki-living
    wl_sp = sub.add_parser("wiki-living", help="Living wiki: init/update/lint/index/log/read/search/list/stats")
    wl_sub = wl_sp.add_subparsers(dest="wl_action")
    wl_sub.add_parser("init", help="Initialize living wiki structure")

    wl_update = wl_sub.add_parser("update", help="Scan memories, extract entities, update pages")
    wl_update.add_argument("--force", action="store_true", help="Force full rebuild")
    wl_update.add_argument("--wiki-dir", dest="wiki_dir", help="Wiki directory")
    _add_backend_arg(wl_update, choices=_WIKI_BACKEND_CHOICES)
    wl_update.add_argument("--persist-path", dest="persist_path", help="Path for json backend")

    wl_lint = wl_sub.add_parser("lint", help="Detect orphans, contradictions, empty pages")
    _add_backend_arg(wl_lint, choices=_WIKI_BACKEND_CHOICES)
    wl_lint.add_argument("--persist-path", dest="persist_path", help="Path for json backend")

    wl_idx = wl_sub.add_parser("index", help="Regenerate index.md")
    wl_idx.add_argument("--wiki-dir", dest="wiki_dir", help="Wiki directory")
    _add_backend_arg(wl_idx, choices=_WIKI_BACKEND_CHOICES)
    wl_idx.add_argument("--persist-path", dest="persist_path", help="Path for json backend")

    wl_log = wl_sub.add_parser("log", help="Show activity log")
    wl_log.add_argument("--limit", type=int, default=20, help="Max entries")
    _add_backend_arg(wl_log, choices=_WIKI_BACKEND_CHOICES)
    wl_log.add_argument("--persist-path", dest="persist_path", help="Path for json backend")

    wl_read = wl_sub.add_parser("read", help="Read a living page")
    wl_read.add_argument("entity", help="Entity name")
    wl_read.add_argument("--wiki-dir", dest="wiki_dir", help="Wiki directory")
    _add_backend_arg(wl_read, choices=_WIKI_BACKEND_CHOICES)
    wl_read.add_argument("--persist-path", dest="persist_path", help="Path for json backend")

    wl_search = wl_sub.add_parser("search", help="Search across living pages")
    wl_search.add_argument("query", help="Search query")
    wl_search.add_argument("--wiki-dir", dest="wiki_dir", help="Wiki directory")
    _add_backend_arg(wl_search, choices=_WIKI_BACKEND_CHOICES)
    wl_search.add_argument("--persist-path", dest="persist_path", help="Path for json backend")

    wl_list = wl_sub.add_parser("list", help="List all living pages")
    wl_list.add_argument("--wiki-dir", dest="wiki_dir", help="Wiki directory")
    _add_backend_arg(wl_list, choices=_WIKI_BACKEND_CHOICES)
    wl_list.add_argument("--persist-path", dest="persist_path", help="Path for json backend")

    wl_stats = wl_sub.add_parser("stats", help="Living wiki statistics")
    wl_stats.add_argument("--wiki-dir", dest="wiki_dir", help="Wiki directory")
    _add_backend_arg(wl_stats, choices=_WIKI_BACKEND_CHOICES)
    wl_stats.add_argument("--persist-path", dest="persist_path", help="Path for json backend")

    # wiki-graph
    wg = sub.add_parser("wiki-graph", help="Generate or read graph community wiki pages from the knowledge graph")
    wg.add_argument("--output", dest="output", help="Output directory (default: alongside kg.db in wiki/graph)")
    wg.add_argument("--community", help="Read an existing community page by ID")
    wg.add_argument("--update", action="store_true", help="Incrementally update only changed pages")
    wg.add_argument("--db", dest="kg_db", default=None, help="Path to kg.db")
