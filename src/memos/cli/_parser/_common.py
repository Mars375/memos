"""Shared helpers for CLI argument parser construction."""

from __future__ import annotations

import os

BACKEND_CHOICES = ["memory", "chroma", "qdrant", "pinecone"]
BACKEND_CHOICES_WITH_JSON = ["memory", "json", "chroma", "qdrant", "pinecone"]


def _add_backend_arg(
    parser,
    choices: list[str] | None = None,
    default: str | None = None,
) -> None:
    """Add the standard ``--backend`` argument to *parser*."""
    if choices is None:
        choices = BACKEND_CHOICES
    if default is None:
        default = os.environ.get("MEMOS_BACKEND", "memory")
    parser.add_argument(
        "--backend",
        default=default,
        choices=choices,
    )
