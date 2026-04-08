#!/usr/bin/env python3
"""Migrate existing markdown memory files into MemOS.

Usage:
    python tools/migrate_markdown.py [FILE_OR_DIR ...] [options]

Examples:
    python tools/migrate_markdown.py ~/.openclaw/workspace-labs/MEMORY.md
    python tools/migrate_markdown.py ~/.openclaw/workspace-labs/memory/ --tags daily
    python tools/migrate_markdown.py ~/.claude/projects/-home-orion/memory/ --dry-run
    python tools/migrate_markdown.py ~/my-notes/ --backend json --persist-path ~/.memos/store.json
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_frontmatter(text: str) -> Tuple[dict, str]:
    """Extract YAML-like frontmatter (--- block at top of file)."""
    fm: dict = {}
    if not text.startswith("---"):
        return fm, text
    end = text.find("\n---", 3)
    if end == -1:
        return fm, text
    block = text[3:end].strip()
    body = text[end + 4:].lstrip("\n")
    for line in block.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip().lower()] = v.strip()
    return fm, body


def _tags_from_filename(path: Path) -> List[str]:
    """Derive tags from filename patterns."""
    tags = []
    name = path.stem
    # Date prefixes: 2026-04-07, 2026-04-07-something
    date_re = re.match(r"^(\d{4}-\d{2}-\d{2})(?:-(.+))?$", name)
    if date_re:
        tags.append("daily")
        slug = date_re.group(2)
        if slug:
            tags.append(slug.replace("-", "_"))
    else:
        # Slug: use filename as tag
        tag = re.sub(r"[^a-z0-9_]", "_", name.lower())
        if tag and tag != "memory":
            tags.append(tag)
    return tags


@dataclass
class ParsedMemory:
    content: str
    tags: List[str]
    importance: float = 0.5
    source_file: str = ""
    section: str = ""


def _clean_content(text: str) -> str:
    """Strip markdown decorations, collapse whitespace."""
    # Remove horizontal rules
    text = re.sub(r"^-{3,}\s*$", "", text, flags=re.MULTILINE)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_markdown_file(path: Path, extra_tags: Optional[List[str]] = None) -> List[ParsedMemory]:
    """Parse a markdown file into a list of ParsedMemory objects.

    Strategy:
    - If file has H2/H3 sections, each section becomes a memory
    - Small files (< 200 chars) → single memory
    - Frontmatter tags merged with filename tags
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    fm, body = _parse_frontmatter(text)

    # Base tags from frontmatter + filename
    base_tags: List[str] = []
    if "tags" in fm:
        for t in re.split(r"[,\s]+", fm["tags"]):
            t = t.strip().strip('"\'[]')
            if t:
                base_tags.append(t)
    base_tags.extend(_tags_from_filename(path))
    if extra_tags:
        base_tags.extend(extra_tags)
    base_tags = list(dict.fromkeys(base_tags))  # deduplicate, preserve order

    source = str(path)

    # Split by H2 (##) sections — H1 is treated as file title/metadata
    sections = re.split(r"^#{2}\s+", body, flags=re.MULTILINE)

    memories: List[ParsedMemory] = []

    if len(sections) <= 1:
        # No H2 sections — also try H3
        sections = re.split(r"^#{3}\s+", body, flags=re.MULTILINE)

    if len(sections) <= 1:
        # No headers at all → single memory
        content = _clean_content(body)
        if len(content) >= 20:
            memories.append(ParsedMemory(
                content=content[:2000],  # cap to 2k chars
                tags=base_tags,
                importance=0.5,
                source_file=source,
                section="",
            ))
        return memories

    # First chunk before any header = preamble, often file title/intro — skip if short
    preamble = _clean_content(sections[0])
    if len(preamble) >= 40:
        memories.append(ParsedMemory(
            content=preamble[:2000],
            tags=base_tags,
            importance=0.5,
            source_file=source,
            section="(preamble)",
        ))

    for chunk in sections[1:]:
        # First line of chunk = section title
        lines = chunk.splitlines()
        section_title = lines[0].strip() if lines else ""
        section_body = "\n".join(lines[1:]).strip()
        content = _clean_content(f"**{section_title}**\n\n{section_body}" if section_title else section_body)

        if len(content) < 20:
            continue

        # Derive section tags from title
        sec_tags = list(base_tags)
        # Slugify section title as additional tag if meaningful
        title_slug = re.sub(r"[^a-z0-9_]", "_", section_title.lower())
        title_slug = re.sub(r"_+", "_", title_slug).strip("_")
        if title_slug and len(title_slug) > 2 and title_slug not in sec_tags:
            sec_tags.append(title_slug)

        # Importance heuristic: longer sections → more important
        importance = min(0.9, 0.4 + len(content) / 3000)

        memories.append(ParsedMemory(
            content=content[:2000],
            tags=sec_tags,
            importance=round(importance, 2),
            source_file=source,
            section=section_title,
        ))

    return memories


# ---------------------------------------------------------------------------
# Batch import
# ---------------------------------------------------------------------------

def collect_files(paths: List[Path], recursive: bool = True) -> List[Path]:
    """Expand directories to .md files."""
    files: List[Path] = []
    for p in paths:
        if p.is_file() and p.suffix == ".md":
            files.append(p)
        elif p.is_dir():
            glob = p.rglob("*.md") if recursive else p.glob("*.md")
            files.extend(sorted(glob))
    return files


def migrate(
    paths: List[Path],
    memos,
    extra_tags: Optional[List[str]] = None,
    batch_size: int = 20,
    dry_run: bool = False,
    verbose: bool = False,
) -> Tuple[int, int]:
    """Migrate markdown files into MemOS.

    Returns:
        (imported_count, error_count)
    """
    files = collect_files(paths)
    if not files:
        print("No markdown files found.", file=sys.stderr)
        return 0, 0

    print(f"Found {len(files)} markdown file(s)")

    all_memories: List[ParsedMemory] = []
    parse_errors = 0

    for f in files:
        try:
            parsed = parse_markdown_file(f, extra_tags=extra_tags)
            if verbose:
                print(f"  {f.name}: {len(parsed)} memories")
            all_memories.extend(parsed)
        except Exception as exc:
            print(f"  [ERROR] {f}: {exc}", file=sys.stderr)
            parse_errors += 1

    print(f"Parsed {len(all_memories)} memories from {len(files)} files")

    if dry_run:
        print("\n[DRY RUN] Would import:")
        for m in all_memories[:20]:
            print(f"  [{m.importance:.1f}] [{', '.join(m.tags)}] {m.content[:80]!r}")
        if len(all_memories) > 20:
            print(f"  ... and {len(all_memories) - 20} more")
        return len(all_memories), parse_errors

    # Batch import
    imported = 0
    import_errors = 0
    batches = [all_memories[i:i+batch_size] for i in range(0, len(all_memories), batch_size)]

    for i, batch in enumerate(batches):
        try:
            items = [
                {"content": m.content, "tags": m.tags, "importance": m.importance}
                for m in batch
            ]
            # Use batch_learn if available, fallback to individual learn
            if hasattr(memos, "batch_learn"):
                results = memos.batch_learn(items)
                imported += len(results)
            else:
                for item in items:
                    memos.learn(item["content"], tags=item["tags"], importance=item["importance"])
                    imported += 1
            if verbose or (i % 5 == 0):
                print(f"  Batch {i+1}/{len(batches)}: {imported} imported so far")
        except Exception as exc:
            print(f"  [ERROR] batch {i+1}: {exc}", file=sys.stderr)
            import_errors += len(batch)

    return imported, parse_errors + import_errors


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Migrate markdown memory files into MemOS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("paths", nargs="+", type=Path, help="Files or directories to migrate")
    p.add_argument("--tags", nargs="*", help="Additional tags to apply to all imported memories")
    p.add_argument("--batch-size", type=int, default=20, metavar="N", help="Import batch size (default: 20)")
    p.add_argument("--dry-run", action="store_true", help="Parse only, don't import")
    p.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    p.add_argument("--backend", default="json", choices=["memory", "json", "chroma", "qdrant"],
                   help="MemOS backend (default: json)")
    p.add_argument("--persist-path", default=str(Path.home() / ".memos" / "store.json"),
                   metavar="PATH", help="Storage path for json backend")
    p.add_argument("--namespace", default="", help="MemOS namespace")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    # Initialize MemOS
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from memos.core import MemOS

    kwargs: dict = {"backend": args.backend}
    if args.backend == "json":
        Path(args.persist_path).parent.mkdir(parents=True, exist_ok=True)
        kwargs["persist_path"] = args.persist_path
    memos = MemOS(**kwargs)
    if args.namespace:
        memos.namespace = args.namespace

    t0 = time.time()
    imported, errors = migrate(
        paths=args.paths,
        memos=memos,
        extra_tags=args.tags or [],
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )
    elapsed = time.time() - t0

    status = "dry-run" if args.dry_run else "imported"
    print(f"\n✓ {imported} memories {status}, {errors} error(s) — {elapsed:.1f}s")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
