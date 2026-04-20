"""Tag management commands: tags list/rename/delete, classify."""

from __future__ import annotations

from ._common import _add_backend_arg


def build(sub) -> None:
    # tags
    tags_p = sub.add_parser("tags", help="List and manage memory tags")
    tags_sub = tags_p.add_subparsers(dest="tags_action")

    tags_list = tags_sub.add_parser("list", help="List all tags with counts")
    tags_list.add_argument("--sort", dest="tags_sort", default="count", choices=["count", "name"], help="Sort order")
    tags_list.add_argument("--limit", dest="tags_limit", type=int, default=0, help="Max tags (0=all)")
    tags_list.add_argument("--json", action="store_true", help="JSON output")
    _add_backend_arg(tags_list)

    tags_rename = tags_sub.add_parser("rename", help="Rename a tag across all memories")
    tags_rename.add_argument("old_tag", help="Current tag name")
    tags_rename.add_argument("new_tag", help="New tag name")
    _add_backend_arg(tags_rename)

    tags_delete = tags_sub.add_parser("delete", help="Delete a tag from all memories")
    tags_delete.add_argument("tag", help="Tag name to remove")
    _add_backend_arg(tags_delete)

    # classify
    classify_p = sub.add_parser("classify", help="Classify text into memory type tags")
    classify_p.add_argument("text", help="Text to classify")
    classify_p.add_argument("--detailed", action="store_true", help="Show matched patterns")
