"""Server-Sent Events (SSE) utilities for streaming recall results."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional


@dataclass
class SSEEvent:
    """A single SSE event."""

    event: str = "message"
    data: str = ""
    id: Optional[str] = None
    retry: Optional[int] = None

    def encode(self) -> str:
        """Encode as SSE wire format."""
        lines: list[str] = []
        if self.event != "message":
            lines.append(f"event: {self.event}")
        if self.id is not None:
            lines.append(f"id: {self.id}")
        if self.retry is not None:
            lines.append(f"retry: {self.retry}")
        # Multi-line data: each line prefixed with "data: "
        for line in self.data.splitlines():
            lines.append(f"data: {line}")
        lines.append("")  # blank line terminates event
        lines.append("")  # extra newline
        return "\n".join(lines)


def format_recall_event(
    index: int,
    item_id: str,
    content: str,
    score: float,
    tags: list[str],
    match_reason: str,
    age_days: float,
    *,
    total: Optional[int] = None,
) -> SSEEvent:
    """Format a single recall result as an SSE event."""
    payload: dict[str, Any] = {
        "index": index,
        "id": item_id,
        "content": content,
        "score": round(score, 4),
        "tags": tags,
        "match_reason": match_reason,
        "age_days": round(age_days, 1),
    }
    if total is not None:
        payload["total"] = total
    return SSEEvent(
        event="recall",
        data=json.dumps(payload),
        id=str(index),
    )


def format_done_event(count: int, query: str, elapsed_ms: float) -> SSEEvent:
    """Format a completion event."""
    return SSEEvent(
        event="done",
        data=json.dumps(
            {
                "type": "done",
                "count": count,
                "query": query,
                "elapsed_ms": round(elapsed_ms, 1),
            }
        ),
    )


def format_error_event(message: str, code: Optional[str] = None) -> SSEEvent:
    """Format an error event."""
    payload: dict[str, Any] = {"type": "error", "message": message}
    if code:
        payload["code"] = code
    return SSEEvent(
        event="error",
        data=json.dumps(payload),
    )


async def sse_stream(
    recall_gen: AsyncIterator,
    query: str,
    *,
    include_done: bool = True,
) -> AsyncIterator[str]:
    """Wrap an async recall generator into SSE-formatted strings.

    Yields encoded SSEEvent strings suitable for StreamingResponse.
    """
    start = time.monotonic()
    count = 0

    try:
        async for result in recall_gen:
            count += 1
            event = format_recall_event(
                index=count,
                item_id=result.item.id,
                content=result.item.content,
                score=result.score,
                tags=result.item.tags,
                match_reason=result.match_reason,
                age_days=(time.time() - result.item.created_at) / 86400,
            )
            yield event.encode()

        if include_done:
            elapsed = (time.monotonic() - start) * 1000
            done_event = format_done_event(count, query, elapsed)
            yield done_event.encode()
    except Exception as exc:
        error_event = format_error_event(str(exc))
        yield error_event.encode()
