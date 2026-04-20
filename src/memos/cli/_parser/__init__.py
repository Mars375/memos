"""MemOS CLI — argument parser (domain-modular)."""

from __future__ import annotations

import argparse

from ... import __version__
from . import _admin, _context, _io, _kg, _memory, _namespace, _palace, _server, _sharing, _tags, _versioning, _wiki


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="memos",
        description="MemOS — Memory Operating System for LLM Agents",
    )
    p.add_argument("--version", action="version", version=f"memos {__version__}")
    sub = p.add_subparsers(dest="command")

    _memory.build(sub)
    _tags.build(sub)
    _namespace.build(sub)
    _server.build(sub)
    _io.build(sub)
    _wiki.build(sub)
    _kg.build(sub)
    _versioning.build(sub)
    _context.build(sub)
    _admin.build(sub)
    _sharing.build(sub)
    _palace.build(sub)

    return p
