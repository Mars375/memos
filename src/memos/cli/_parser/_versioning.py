"""Versioning commands: history, diff, rollback, snapshot-at, recall-at, version-stats, version-gc."""

from __future__ import annotations

from ._common import _add_backend_arg


def build(sub) -> None:
    # history
    hist = sub.add_parser("history", help="Show version history for a memory")
    hist.add_argument("item_id", help="Memory item ID")
    hist.add_argument("--json", action="store_true", help="JSON output")
    _add_backend_arg(hist)

    # diff
    diff_p = sub.add_parser("diff", help="Show diff between two versions")
    diff_p.add_argument("item_id", help="Memory item ID")
    diff_p.add_argument("--v1", type=int, help="First version number")
    diff_p.add_argument("--v2", type=int, help="Second version number")
    diff_p.add_argument("--latest", action="store_true", help="Diff last two versions")
    diff_p.add_argument("--json", action="store_true", help="JSON output")
    _add_backend_arg(diff_p)

    # rollback
    rb = sub.add_parser("rollback", help="Roll back a memory to a previous version")
    rb.add_argument("item_id", help="Memory item ID")
    rb.add_argument("--version", type=int, required=True, help="Target version number")
    rb.add_argument("--yes", action="store_true", help="Confirm rollback")
    rb.add_argument("--dry-run", action="store_true", help="Preview only")
    _add_backend_arg(rb)

    # snapshot-at
    snap = sub.add_parser("snapshot-at", help="Show all memories at a point in time")
    snap.add_argument("timestamp", help="Timestamp (epoch, ISO 8601, or relative like 1h, 2d)")
    snap.add_argument("--json", action="store_true", help="JSON output")
    _add_backend_arg(snap)

    # recall-at
    rcat = sub.add_parser("recall-at", help="Time-travel recall - query memories at a past time")
    rcat.add_argument("query", help="Search query")
    rcat.add_argument("--at", dest="timestamp", required=True, help="Timestamp (epoch, ISO 8601, or relative)")
    rcat.add_argument("--top", "-n", type=int, default=5)
    rcat.add_argument("--min-score", type=float, default=0.0)
    rcat.add_argument("--json", action="store_true", help="JSON output")
    _add_backend_arg(rcat)

    # version-stats
    vstats = sub.add_parser("version-stats", help="Show versioning statistics")
    vstats.add_argument("--json", action="store_true", help="JSON output")
    _add_backend_arg(vstats)

    # version-gc
    vgc = sub.add_parser("version-gc", help="Garbage collect old memory versions")
    vgc.add_argument("--max-age-days", type=float, default=90.0, help="Remove versions older than N days")
    vgc.add_argument("--keep-latest", type=int, default=3, help="Keep at least N latest versions per item")
    vgc.add_argument("--dry-run", action="store_true", help="Preview only")
    _add_backend_arg(vgc)
