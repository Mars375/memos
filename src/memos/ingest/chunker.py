"""Paragraph-aware text chunking, content hashing, and room/tag detection."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import List


def chunk_text(
    text: str,
    size: int = 800,
    overlap: int = 100,
) -> List[str]:
    """Split text into chunks respecting paragraph boundaries.

    Strategy (MemPalace-inspired):
    1. Split on double-newlines (paragraphs)
    2. Accumulate paragraphs until chunk is full
    3. When a chunk is committed, carry the last `overlap` chars into next chunk
    4. Never cut mid-paragraph unless a single paragraph > size

    Args:
        text: Raw text to chunk
        size: Target max chars per chunk (default 800)
        overlap: How many chars to carry over to next chunk (default 100)

    Returns:
        List of chunk strings
    """
    text = text.strip()
    if not text:
        return []

    # Split into paragraphs (preserve single-newline within paragraphs)
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

    if not paragraphs:
        return []

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)

        # Single paragraph larger than size — split by sentence
        if para_len > size:
            # Flush current buffer first
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0

            # Split oversized paragraph by sentences
            sentences = re.split(r"(?<=[.!?])\s+", para)
            buf = ""
            for sent in sentences:
                if len(buf) + len(sent) + 1 <= size:
                    buf = f"{buf} {sent}".strip() if buf else sent
                else:
                    if buf:
                        chunks.append(buf)
                    buf = sent
            if buf:
                chunks.append(buf)
            continue

        # Would adding this paragraph overflow the chunk?
        sep_len = 2 if current else 0  # "\n\n" separator
        if current_len + sep_len + para_len > size and current:
            # Commit current chunk
            chunk_text_str = "\n\n".join(current)
            chunks.append(chunk_text_str)

            # Overlap: carry last `overlap` chars as context for next chunk
            if overlap > 0 and chunk_text_str:
                overlap_text = chunk_text_str[-overlap:].strip()
                if overlap_text:
                    current = [overlap_text]
                    current_len = len(overlap_text)
                else:
                    current = []
                    current_len = 0
            else:
                current = []
                current_len = 0

        current.append(para)
        current_len += len(para) + (2 if len(current) > 1 else 0)

    if current:
        chunks.append("\n\n".join(current))

    return [c for c in chunks if c.strip()]


def content_hash(text: str) -> str:
    """SHA-256 hash of normalized content (lowercase, collapsed whitespace)."""
    normalized = re.sub(r"\s+", " ", text.lower().strip())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


_ROOM_KEYWORDS: dict[str, List[str]] = {
    "auth": ["auth", "login", "password", "token", "oauth", "jwt", "session", "credential"],
    "deployment": ["deploy", "docker", "kubernetes", "k8s", "ci", "cd", "pipeline", "release", "helm"],
    "database": ["sql", "postgres", "mysql", "sqlite", "redis", "mongo", "migration", "schema"],
    "api": ["api", "endpoint", "rest", "graphql", "webhook", "request", "response", "route"],
    "frontend": ["react", "vue", "angular", "css", "html", "component", "ui", "ux", "tailwind"],
    "backend": ["server", "fastapi", "flask", "django", "express", "node", "python", "go"],
    "testing": ["test", "pytest", "jest", "mock", "coverage", "assertion", "fixture"],
    "security": ["security", "ssl", "tls", "xss", "csrf", "vulnerability", "permission"],
    "performance": ["perf", "latency", "throughput", "cache", "optimize", "memory", "cpu"],
    "devops": ["infra", "terraform", "ansible", "monitoring", "grafana", "prometheus", "alert"],
    "docs": ["readme", "documentation", "wiki", "spec", "design", "architecture"],
    "ai": ["llm", "gpt", "claude", "embedding", "vector", "prompt", "model", "inference"],
}


def detect_room(path: Path, text: str = "", top_n: int = 2) -> List[str]:
    """Detect room tags from file path → filename → keyword frequency.

    Strategy:
    1. Path components (e.g. src/auth/login.py → "auth")
    2. Filename keywords
    3. Top-N keyword matches in text content
    4. Fallback: file extension as tag
    """
    tags: List[str] = []

    # 1. Path components
    parts = [p.lower() for p in path.parts]
    for room, keywords in _ROOM_KEYWORDS.items():
        if any(kw in part for part in parts for kw in keywords):
            if room not in tags:
                tags.append(room)

    # 2. Filename
    stem = path.stem.lower()
    for room, keywords in _ROOM_KEYWORDS.items():
        if any(kw in stem for kw in keywords) and room not in tags:
            tags.append(room)

    if len(tags) >= top_n:
        return tags[:top_n]

    # 3. Keyword frequency in text
    if text:
        text_lower = text.lower()
        scores: dict[str, int] = {}
        for room, keywords in _ROOM_KEYWORDS.items():
            if room in tags:
                continue
            score = sum(text_lower.count(kw) for kw in keywords)
            if score > 0:
                scores[room] = score
        for room in sorted(scores, key=lambda r: -scores[r]):
            if room not in tags:
                tags.append(room)
            if len(tags) >= top_n:
                break

    # 4. Extension fallback
    ext = path.suffix.lstrip(".")
    if ext and ext not in ("md", "txt", "json") and ext not in tags:
        tags.append(ext)

    return tags[:top_n] if tags else []
