"""Memory Palace commands: palace-init, palace-wing-create, palace-wing-list, palace-room-create, palace-room-list, palace-assign, palace-recall, palace-stats."""

from __future__ import annotations


def build(sub) -> None:
    palace_db_help = "Path to palace.db (default: ~/.memos/palace.db)"

    # palace-init
    palace_init = sub.add_parser("palace-init", help="Initialise the Palace schema")
    palace_init.add_argument("--db", dest="palace_db", default=None, help=palace_db_help)

    # palace-wing-create
    palace_wing_create = sub.add_parser("palace-wing-create", help="Create a Wing")
    palace_wing_create.add_argument("name", help="Wing name")
    palace_wing_create.add_argument("--description", default="", help="Wing description")
    palace_wing_create.add_argument("--db", dest="palace_db", default=None, help=palace_db_help)

    # palace-wing-list
    palace_wing_list = sub.add_parser("palace-wing-list", help="List Wings")
    palace_wing_list.add_argument("--db", dest="palace_db", default=None, help=palace_db_help)

    # palace-room-create
    palace_room_create = sub.add_parser("palace-room-create", help="Create a Room inside a Wing")
    palace_room_create.add_argument("wing", help="Wing name")
    palace_room_create.add_argument("room", help="Room name")
    palace_room_create.add_argument("--description", default="", help="Room description")
    palace_room_create.add_argument("--db", dest="palace_db", default=None, help=palace_db_help)

    # palace-room-list
    palace_room_list = sub.add_parser("palace-room-list", help="List Rooms")
    palace_room_list.add_argument("--wing", default=None, help="Filter by wing name")
    palace_room_list.add_argument("--db", dest="palace_db", default=None, help=palace_db_help)

    # palace-assign
    palace_assign = sub.add_parser("palace-assign", help="Assign a memory to a Wing/Room")
    palace_assign.add_argument("memory_id", help="Memory ID")
    palace_assign.add_argument("--wing", required=True, help="Wing name")
    palace_assign.add_argument("--room", default=None, help="Room name (optional)")
    palace_assign.add_argument("--db", dest="palace_db", default=None, help=palace_db_help)

    # palace-recall
    palace_recall = sub.add_parser("palace-recall", help="Scoped recall using Palace")
    palace_recall.add_argument("query", help="Recall query")
    palace_recall.add_argument("--wing", default=None, help="Scope to wing")
    palace_recall.add_argument("--room", default=None, help="Scope to room (requires --wing)")
    palace_recall.add_argument("--top", type=int, default=10, help="Max results (default 10)")
    palace_recall.add_argument("--db", dest="palace_db", default=None, help=palace_db_help)

    # palace-stats
    palace_stats = sub.add_parser("palace-stats", help="Show Palace statistics")
    palace_stats.add_argument("--db", dest="palace_db", default=None, help=palace_db_help)
