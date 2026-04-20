"""Sharing commands: share-offer, share-accept, share-reject, share-revoke, share-export, share-import, share-list, share-stats."""

from __future__ import annotations

from ._common import _add_backend_arg


def build(sub) -> None:
    # share-offer
    share_offer = sub.add_parser("share-offer", help="Offer to share memories with another agent")
    share_offer.add_argument("--target", required=True, help="Target agent ID")
    share_offer.add_argument("--scope", default="items", choices=["items", "tag", "namespace"], help="Share scope")
    share_offer.add_argument("--scope-key", default="", help="IDs (comma-sep), tag name, or namespace")
    share_offer.add_argument(
        "--permission", default="read", choices=["read", "read_write", "admin"], help="Permission level"
    )
    share_offer.add_argument("--expires", type=float, default=None, help="TTL in seconds from now")
    _add_backend_arg(share_offer)

    # share-accept
    share_accept = sub.add_parser("share-accept", help="Accept a pending share")
    share_accept.add_argument("share_id", help="Share request ID")
    _add_backend_arg(share_accept)

    # share-reject
    share_reject = sub.add_parser("share-reject", help="Reject a pending share")
    share_reject.add_argument("share_id", help="Share request ID")
    _add_backend_arg(share_reject)

    # share-revoke
    share_revoke = sub.add_parser("share-revoke", help="Revoke a share you offered")
    share_revoke.add_argument("share_id", help="Share request ID")
    _add_backend_arg(share_revoke)

    # share-export
    share_export = sub.add_parser("share-export", help="Export memories for an accepted share")
    share_export.add_argument("share_id", help="Share request ID")
    share_export.add_argument("--output", default=None, help="Output file path (default: stdout)")
    _add_backend_arg(share_export)

    # share-import
    share_import = sub.add_parser("share-import", help="Import memories from an envelope file")
    share_import.add_argument("input_file", help="Envelope JSON file to import")
    _add_backend_arg(share_import)

    # share-list
    share_list = sub.add_parser("share-list", help="List shares")
    share_list.add_argument("--agent", default=None, help="Filter by agent ID")
    share_list.add_argument(
        "--status",
        default=None,
        choices=["pending", "accepted", "rejected", "revoked", "expired"],
        help="Filter by status",
    )
    share_list.add_argument("--json", action="store_true", help="JSON output")
    _add_backend_arg(share_list)

    # share-stats
    share_stats = sub.add_parser("share-stats", help="Show sharing statistics")
    share_stats.add_argument("--json", action="store_true", help="JSON output")
    _add_backend_arg(share_stats)
