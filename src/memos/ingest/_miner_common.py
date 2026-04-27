"""Shared types and file iteration helpers for memory mining."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, List, Optional


@dataclass
class MineResult:
    """Aggregate result for a mining operation."""

    imported: int = 0
    skipped_duplicates: int = 0
    skipped_empty: int = 0
    skipped_cached: int = 0
    errors: List[str] = field(default_factory=list)
    chunks: List[dict] = field(default_factory=list)  # populated in dry_run
    memory_ids: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"MineResult(imported={self.imported}, "
            f"dupes={self.skipped_duplicates}, "
            f"cached={self.skipped_cached}, "
            f"empty={self.skipped_empty}, "
            f"errors={len(self.errors)})"
        )

    def merge(self, other: "MineResult") -> None:
        """Merge another result into this one."""
        self.imported += other.imported
        self.skipped_duplicates += other.skipped_duplicates
        self.skipped_empty += other.skipped_empty
        self.skipped_cached += other.skipped_cached
        self.errors.extend(other.errors)
        self.chunks.extend(other.chunks)
        self.memory_ids.extend(other.memory_ids)


_DEFAULT_IGNORE = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "node_modules",
    ".pytest_cache",
    "dist",
    "build",
    ".mypy_cache",
    ".ruff_cache",
    "*.pyc",
    "*.pyo",
    "*.egg-info",
}

_MINEABLE_EXTENSIONS = {
    ".md",
    ".markdown",
    ".txt",
    ".rst",
    ".py",
    ".js",
    ".ts",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".sql",
    ".sh",
    ".bash",
    ".zsh",
}


def iter_files(
    directory: Path,
    extensions: Optional[set] = None,
    max_files: int = 5000,
) -> Iterator[Path]:
    """Walk a directory yielding mineable files, respecting common ignores."""
    if extensions is None:
        extensions = _MINEABLE_EXTENSIONS

    count = 0
    for path in directory.rglob("*"):
        if count >= max_files:
            break
        if not path.is_file():
            continue
        if any(part.startswith(".") or part in _DEFAULT_IGNORE for part in path.parts):
            continue
        if path.suffix.lower() not in extensions:
            continue
        count += 1
        yield path


__all__ = ["MineResult", "iter_files"]
