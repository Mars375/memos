"""URL ingestion for MemOS — arXiv, tweets/X, PDFs, and generic webpages."""

from __future__ import annotations

import html
import ipaddress
import mimetypes
import os
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

from .engine import IngestResult
from .miner import chunk_text

# ── SSRF safety configuration ───────────────────────────────────

# Allow file:// scheme (disabled by default to prevent local file reads via SSRF).
_ALLOW_FILE_SCHEME: bool = os.environ.get("MEMOS_ALLOW_FILE_SCHEME", "false").lower() in (
    "true",
    "1",
    "yes",
)

# Allow fetching private/internal network URLs (disabled by default).
_ALLOW_PRIVATE_URLS: bool = os.environ.get("MEMOS_ALLOW_PRIVATE_URLS", "false").lower() in (
    "true",
    "1",
    "yes",
)

_MAX_REDIRECTS: int = int(os.environ.get("MEMOS_MAX_URL_REDIRECTS", "5"))


def _is_private_ip(addr: str) -> bool:
    """Return True if the IP address is private, loopback, link-local, or reserved."""
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified


def _resolve_host(hostname: str) -> list[str]:
    try:
        results = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        return [r[4][0] for r in results]
    except socket.gaierror:
        return []


_META_RE = re.compile(
    r"<meta[^>]+(?:name|property)=[\"'](?P<key>[^\"']+)[\"'][^>]+content=[\"'](?P<value>.*?)[\"'][^>]*>",
    re.IGNORECASE | re.DOTALL,
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_PDF_TEXT_RE = re.compile(rb"\(([^()]*)\)\s*Tj")
_PDF_TEXT_ARRAY_RE = re.compile(rb"\[(.*?)\]\s*TJ", re.DOTALL)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        value = value.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _decode_html(data: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _extract_meta_values(html_text: str, *keys: str) -> list[str]:
    wanted = {key.lower() for key in keys}
    values: list[str] = []
    for match in _META_RE.finditer(html_text):
        key = match.group("key").strip().lower()
        if key in wanted:
            values.append(html.unescape(match.group("value")).strip())
    return _dedupe(values)


def _extract_title(html_text: str) -> str:
    for candidate in _extract_meta_values(html_text, "citation_title", "og:title", "twitter:title"):
        if candidate:
            return candidate
    match = _TITLE_RE.search(html_text)
    return html.unescape(match.group(1)).strip() if match else ""


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._ignore_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._ignore_depth += 1
        elif tag.lower() in {"p", "div", "section", "article", "li", "br", "h1", "h2", "h3", "h4"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._ignore_depth:
            self._ignore_depth -= 1
        elif tag.lower() in {"p", "div", "section", "article", "li", "br", "h1", "h2", "h3", "h4"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if self._ignore_depth:
            return
        text = data.strip()
        if text:
            self._parts.append(text)

    def get_text(self) -> str:
        text = html.unescape(" ".join(self._parts))
        text = re.sub(r"\n\s*\n+", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()


def _extract_visible_text(html_text: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(html_text)
    return parser.get_text()


def _clean_tweet_text(text: str) -> str:
    text = text.strip().strip('"')
    text = re.sub(r"\s+/\s+X\s*$", "", text)
    text = re.sub(r"\s+on\s+X:\s*", ": ", text)
    return text.strip()


def _decode_pdf_literal(raw: bytes) -> str:
    text = raw.decode("latin-1", errors="ignore")
    text = text.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
    return text.strip()


def _extract_pdf_text(data: bytes) -> str:
    try:
        import fitz  # type: ignore

        doc = fitz.open(stream=data, filetype="pdf")
        try:
            text = "\n\n".join(page.get_text("text") for page in doc)
        finally:
            doc.close()
        if text.strip():
            return text.strip()
    except Exception:
        pass

    parts: list[str] = []
    for match in _PDF_TEXT_RE.finditer(data):
        decoded = _decode_pdf_literal(match.group(1))
        if decoded:
            parts.append(decoded)
    for match in _PDF_TEXT_ARRAY_RE.finditer(data):
        array_bytes = match.group(1)
        for inner in re.finditer(rb"\(([^()]*)\)", array_bytes):
            decoded = _decode_pdf_literal(inner.group(1))
            if decoded:
                parts.append(decoded)
    return "\n".join(_dedupe(parts)).strip()


@dataclass
class _FetchedURL:
    url: str
    data: bytes
    content_type: str


class URLIngestor:
    """Ingest remote or file URLs into MemOS-ready chunks."""

    def __init__(
        self, *, timeout: float = 20.0, user_agent: str = "MemOS/0.x (+https://github.com/Mars375/memos)"
    ) -> None:
        self._timeout = timeout
        self._user_agent = user_agent

    def ingest(
        self,
        url: str,
        *,
        tags: list[str] | None = None,
        importance: float = 0.5,
        max_chunk: int = 2000,
    ) -> IngestResult:
        result = IngestResult()
        url = (url or "").strip()
        if not url:
            result.errors.append("URL is required")
            return result

        fetched = self._fetch(url)
        if isinstance(fetched, str):
            result.errors.append(fetched)
            return result

        parsed = urlparse(fetched.url)
        host = parsed.netloc.lower()
        source_tags = list(tags or [])

        try:
            if fetched.content_type.startswith("application/pdf") or parsed.path.lower().endswith(".pdf"):
                chunks = self._ingest_pdf(fetched, source_tags=source_tags, importance=importance, max_chunk=max_chunk)
            elif "arxiv.org" in host and "/abs/" in parsed.path:
                chunks = self._ingest_arxiv(
                    fetched, source_tags=source_tags, importance=importance, max_chunk=max_chunk
                )
            elif host.endswith("twitter.com") or host.endswith("x.com"):
                chunks = self._ingest_tweet(
                    fetched, source_tags=source_tags, importance=importance, max_chunk=max_chunk
                )
            else:
                chunks = self._ingest_html(fetched, source_tags=source_tags, importance=importance, max_chunk=max_chunk)
        except Exception as exc:
            result.errors.append(f"Failed to ingest URL: {exc}")
            return result

        result.chunks = chunks
        result.total_chunks = len(chunks)
        if not chunks:
            result.skipped = 1
        return result

    def _fetch(self, url: str) -> _FetchedURL | str:
        parsed = urlparse(url)

        if parsed.scheme == "file":
            if not _ALLOW_FILE_SCHEME:
                return "file:// scheme is disabled; set MEMOS_ALLOW_FILE_SCHEME=true to enable"
            path = Path(unquote(parsed.path))
            if not path.exists():
                return f"File not found: {path}"
            if not path.is_file():
                return f"Not a file: {path}"
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            return _FetchedURL(url=url, data=path.read_bytes(), content_type=content_type)

        if parsed.scheme not in {"http", "https"}:
            return f"Unsupported URL scheme: {parsed.scheme or 'missing'}"

        if not _ALLOW_PRIVATE_URLS:
            hostname = parsed.hostname
            if not hostname:
                return "URL has no hostname"
            resolved = _resolve_host(hostname)
            if not resolved:
                return f"Cannot resolve hostname: {hostname}"
            for ip in resolved:
                if _is_private_ip(ip):
                    return (
                        f"Hostname {hostname} resolves to private/internal address {ip}; "
                        "set MEMOS_ALLOW_PRIVATE_URLS=true to allow"
                    )

        headers = {"User-Agent": self._user_agent}
        try:
            with httpx.Client(
                timeout=self._timeout,
                follow_redirects=True,
                max_redirects=_MAX_REDIRECTS,
                headers=headers,
            ) as client:
                response = client.get(url)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "text/html").split(";")[0].strip().lower()
                return _FetchedURL(url=str(response.url), data=response.content, content_type=content_type)
        except httpx.TooManyRedirects:
            return f"Too many redirects (max {_MAX_REDIRECTS})"
        except Exception as exc:
            return f"Fetch error: {exc}"

    def _build_chunks(
        self,
        text: str,
        *,
        url: str,
        source_type: str,
        tags: list[str],
        importance: float,
        max_chunk: int,
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        text = text.strip()
        if not text:
            return []
        pieces = chunk_text(text, size=max_chunk, overlap=min(120, max(0, max_chunk // 10))) or [text]
        base_meta = {"source": url, "type": "url", "source_type": source_type}
        if metadata:
            base_meta.update(metadata)
        return [
            {
                "content": piece,
                "tags": _dedupe(tags),
                "importance": importance,
                "metadata": dict(base_meta),
            }
            for piece in pieces
        ]

    def _ingest_arxiv(
        self, fetched: _FetchedURL, *, source_tags: list[str], importance: float, max_chunk: int
    ) -> list[dict[str, Any]]:
        html_text = _decode_html(fetched.data)
        title = _extract_title(html_text)
        authors = _extract_meta_values(html_text, "citation_author")
        abstract_candidates = _extract_meta_values(
            html_text, "citation_abstract", "description", "og:description", "twitter:description"
        )
        abstract = ""
        for candidate in abstract_candidates:
            cleaned = candidate.replace("Abstract:", "").strip()
            if cleaned:
                abstract = cleaned
                break
        parts = [
            part
            for part in [
                title,
                f"Authors: {', '.join(authors)}" if authors else "",
                f"Abstract: {abstract}" if abstract else "",
            ]
            if part
        ]
        tags = source_tags + ["url", "arxiv", "paper"]
        parsed = urlparse(fetched.url)
        arxiv_id = parsed.path.split("/abs/", 1)[-1].strip("/") if "/abs/" in parsed.path else ""
        metadata = {"title": title, "authors": authors, "arxiv_id": arxiv_id, "content_type": fetched.content_type}
        return self._build_chunks(
            "\n\n".join(parts),
            url=fetched.url,
            source_type="arxiv",
            tags=tags,
            importance=importance,
            max_chunk=max_chunk,
            metadata=metadata,
        )

    def _ingest_tweet(
        self, fetched: _FetchedURL, *, source_tags: list[str], importance: float, max_chunk: int
    ) -> list[dict[str, Any]]:
        html_text = _decode_html(fetched.data)
        parsed = urlparse(fetched.url)
        path_parts = [part for part in parsed.path.split("/") if part]
        handle = path_parts[0] if path_parts else ""
        desc = ""
        for candidate in _extract_meta_values(html_text, "og:description", "twitter:description", "description"):
            desc = _clean_tweet_text(candidate)
            if desc:
                break
        if not desc:
            desc = _extract_visible_text(html_text)
        title = _extract_title(html_text) or (f"Tweet by @{handle}" if handle else "Tweet")
        body = f"{title}\n\n{desc}".strip() if desc else title
        tags = source_tags + ["url", "tweet"]
        if handle:
            tags.append(f"author:{handle.lstrip('@')}")
        metadata = {"title": title, "author": handle.lstrip("@"), "content_type": fetched.content_type}
        return self._build_chunks(
            body,
            url=fetched.url,
            source_type="tweet",
            tags=tags,
            importance=importance,
            max_chunk=max_chunk,
            metadata=metadata,
        )

    def _ingest_pdf(
        self, fetched: _FetchedURL, *, source_tags: list[str], importance: float, max_chunk: int
    ) -> list[dict[str, Any]]:
        text = _extract_pdf_text(fetched.data)
        title = Path(urlparse(fetched.url).path).name or "document.pdf"
        tags = source_tags + ["url", "pdf"]
        if "arxiv.org" in urlparse(fetched.url).netloc.lower():
            tags.extend(["arxiv", "paper"])
        metadata = {"title": title, "content_type": fetched.content_type}
        return self._build_chunks(
            text,
            url=fetched.url,
            source_type="pdf",
            tags=tags,
            importance=importance,
            max_chunk=max_chunk,
            metadata=metadata,
        )

    def _ingest_html(
        self, fetched: _FetchedURL, *, source_tags: list[str], importance: float, max_chunk: int
    ) -> list[dict[str, Any]]:
        html_text = _decode_html(fetched.data)
        title = _extract_title(html_text)
        description = ""
        for candidate in _extract_meta_values(html_text, "description", "og:description", "twitter:description"):
            if candidate:
                description = candidate
                break
        visible = _extract_visible_text(html_text)
        parts = [part for part in [title, description, visible] if part]
        metadata = {"title": title, "content_type": fetched.content_type}
        return self._build_chunks(
            "\n\n".join(parts),
            url=fetched.url,
            source_type="webpage",
            tags=source_tags + ["url", "webpage"],
            importance=importance,
            max_chunk=max_chunk,
            metadata=metadata,
        )
