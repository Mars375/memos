"""MemOS CLI — memory palace commands."""

from __future__ import annotations

import argparse
import sys

from ._common import _get_memos, _get_palace


def cmd_palace_init(ns: argparse.Namespace) -> None:
    """Initialise the Palace schema (creates tables if absent)."""
    palace = _get_palace(ns)
    palace.close()
    print("Palace schema initialised.")


def cmd_palace_wing_create(ns: argparse.Namespace) -> None:
    """Create a Wing in the Palace."""
    palace = _get_palace(ns)
    try:
        wing_id = palace.create_wing(ns.name, description=ns.description)
        print(f"Wing created: {ns.name} [{wing_id}]")
    finally:
        palace.close()


def cmd_palace_wing_list(ns: argparse.Namespace) -> None:
    """List all Wings."""
    palace = _get_palace(ns)
    try:
        wings = palace.list_wings()
        if not wings:
            print("No wings found.")
            return
        print(f"{'NAME':<24} {'ROOMS':>6} {'MEMORIES':>9}  DESCRIPTION")
        print("-" * 65)
        for w in wings:
            print(f"{w['name']:<24} {w['room_count']:>6} {w['memory_count']:>9}  {w['description']}")
    finally:
        palace.close()


def cmd_palace_room_create(ns: argparse.Namespace) -> None:
    """Create a Room inside a Wing."""
    palace = _get_palace(ns)
    try:
        room_id = palace.create_room(ns.wing, ns.room, description=ns.description)
        print(f"Room created: {ns.wing}/{ns.room} [{room_id}]")
    except KeyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        palace.close()


def cmd_palace_room_list(ns: argparse.Namespace) -> None:
    """List Rooms, optionally filtered by wing."""
    palace = _get_palace(ns)
    try:
        rooms = palace.list_rooms(wing_name=ns.wing)
        if not rooms:
            print("No rooms found.")
            return
        print(f"{'WING':<20} {'ROOM':<20} {'MEMORIES':>9}  DESCRIPTION")
        print("-" * 65)
        for r in rooms:
            print(f"{r['wing_name']:<20} {r['name']:<20} {r['memory_count']:>9}  {r['description']}")
    except KeyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        palace.close()


def cmd_palace_assign(ns: argparse.Namespace) -> None:
    """Assign a memory to a Wing (and optionally a Room)."""
    palace = _get_palace(ns)
    try:
        palace.assign(ns.memory_id, ns.wing, room_name=ns.room)
        room_str = f"/{ns.room}" if ns.room else ""
        print(f"Assigned [{ns.memory_id}] -> {ns.wing}{room_str}")
    except KeyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        palace.close()


def cmd_palace_recall(ns: argparse.Namespace) -> None:
    """Scoped recall using Palace wing/room filter."""
    from ..palace import PalaceRecall

    palace = _get_palace(ns)
    memos = _get_memos(ns)
    try:
        pr = PalaceRecall(palace)
        results = pr.palace_recall(
            memos,
            ns.query,
            wing_name=ns.wing,
            room_name=ns.room,
            top=ns.top,
        )
        if not results:
            print("No memories found.")
            return
        for r in results:
            tags_str = f" [{', '.join(r.item.tags)}]" if r.item.tags else ""
            print(f"  {r.score:.3f} {r.item.content[:120]}{tags_str}")
        print(f"\n{len(results)} result(s)")
    finally:
        palace.close()


def cmd_palace_stats(ns: argparse.Namespace) -> None:
    """Show Palace statistics."""
    palace = _get_palace(ns)
    try:
        s = palace.stats()
        print(f"  Total wings:       {s['total_wings']}")
        print(f"  Total rooms:       {s['total_rooms']}")
        print(f"  Assigned memories: {s['assigned_memories']}")
    finally:
        palace.close()
