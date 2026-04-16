"""Recall analytics for MemOS."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


@dataclass(slots=True)
class RecallEvent:
    """Stored recall event."""

    query: str
    result_count: int
    latency_ms: float
    created_at: float
    result_ids: list[str]


class RecallAnalytics:
    """SQLite-backed analytics for recall behavior."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        enabled: bool = True,
        retention_days: int = 90,
    ) -> None:
        self.enabled = enabled
        self.retention_days = max(1, int(retention_days))
        self.path = Path(path or Path.home() / ".memos" / "analytics.db").expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS recalls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    result_count INTEGER NOT NULL,
                    latency_ms REAL NOT NULL,
                    created_at REAL NOT NULL,
                    result_ids TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_recalls_created_at ON recalls(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_recalls_query ON recalls(query)")
            conn.commit()

    def _row_to_event(self, row: sqlite3.Row) -> RecallEvent:
        return RecallEvent(
            query=row["query"],
            result_count=int(row["result_count"]),
            latency_ms=float(row["latency_ms"]),
            created_at=float(row["created_at"]),
            result_ids=json.loads(row["result_ids"] or "[]"),
        )

    def _extract_result_ids(self, results: Iterable[Any]) -> list[str]:
        result_ids: list[str] = []
        for result in results:
            if isinstance(result, dict):
                item_id = result.get("id") or result.get("item_id")
            else:
                item = getattr(result, "item", None)
                item_id = getattr(item, "id", None)
                if item_id is None:
                    item_id = getattr(result, "id", None)
            if item_id:
                result_ids.append(str(item_id))
        return result_ids

    def _prune_old_locked(self, conn: sqlite3.Connection) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        conn.execute("DELETE FROM recalls WHERE created_at < ?", (cutoff.timestamp(),))

    def track_recall(self, query: str, results: Iterable[Any], latency_ms: float) -> None:
        """Store a recall event for later analytics."""
        if not self.enabled:
            return
        result_list = list(results)
        payload = RecallEvent(
            query=query,
            result_count=len(result_list),
            latency_ms=float(latency_ms),
            created_at=datetime.now(timezone.utc).timestamp(),
            result_ids=self._extract_result_ids(result_list),
        )
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO recalls (query, result_count, latency_ms, created_at, result_ids) VALUES (?, ?, ?, ?, ?)",
                (
                    payload.query,
                    payload.result_count,
                    payload.latency_ms,
                    payload.created_at,
                    json.dumps(payload.result_ids),
                ),
            )
            self._prune_old_locked(conn)
            conn.commit()

    def _rows(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._lock, self._connect() as conn:
            self._prune_old_locked(conn)
            return list(conn.execute(sql, params).fetchall())

    def _recall_rows(self, days: int | None = None) -> list[sqlite3.Row]:
        if days is None:
            return self._rows("SELECT * FROM recalls ORDER BY created_at DESC")
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))
        return self._rows(
            "SELECT * FROM recalls WHERE created_at >= ? ORDER BY created_at DESC",
            (cutoff.timestamp(),),
        )

    def top_recalled(self, n: int = 20) -> list[dict[str, Any]]:
        """Return the most recalled memory IDs."""
        counts: dict[str, int] = {}
        for row in self._recall_rows():
            event = self._row_to_event(row)
            for memory_id in event.result_ids:
                counts[memory_id] = counts.get(memory_id, 0) + 1
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[: max(0, n)]
        return [{"memory_id": memory_id, "count": count} for memory_id, count in ranked]

    def query_patterns(self, n: int = 20) -> list[dict[str, Any]]:
        """Return the most frequent queries."""
        rows = self._rows(
            """
            SELECT query, COUNT(*) AS count
            FROM recalls
            GROUP BY query
            ORDER BY count DESC, query ASC
            LIMIT ?
            """,
            (max(0, n),),
        )
        return [{"query": row["query"], "count": int(row["count"])} for row in rows]

    def recall_success_rate(self, days: int = 7) -> float:
        """Return success rate as a percentage."""
        rows = self._recall_rows(days=days)
        if not rows:
            return 0.0
        successful = sum(1 for row in rows if int(row["result_count"]) > 0)
        return round((successful / len(rows)) * 100.0, 1)

    def recall_success_rate_stats(self, days: int = 7) -> dict[str, Any]:
        """Return success rate plus raw counts."""
        rows = self._recall_rows(days=days)
        total = len(rows)
        successful = sum(1 for row in rows if int(row["result_count"]) > 0)
        return {
            "days": days,
            "success_rate": round((successful / total) * 100.0, 1) if total else 0.0,
            "total_recalls": total,
            "successful_recalls": successful,
            "failed_recalls": total - successful,
        }

    def latency_stats(self) -> dict[str, Any]:
        """Return latency summary with percentile data."""
        rows = self._recall_rows()
        latencies = sorted(float(row["latency_ms"]) for row in rows)
        if not latencies:
            return {"count": 0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0}

        def percentile(values: list[float], pct: float) -> float:
            if not values:
                return 0.0
            if len(values) == 1:
                return round(values[0], 2)
            index = (len(values) - 1) * pct
            lower = int(index)
            upper = min(lower + 1, len(values) - 1)
            fraction = index - lower
            result = values[lower] * (1 - fraction) + values[upper] * fraction
            return round(result, 2)

        return {
            "count": len(latencies),
            "avg": round(sum(latencies) / len(latencies), 2),
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
        }

    def daily_activity(self, days: int = 30) -> list[dict[str, Any]]:
        """Return recall counts per day over the requested window."""
        days = max(1, int(days))
        rows = self._recall_rows(days=days)
        counts: dict[str, int] = {}
        for row in rows:
            day = datetime.fromtimestamp(float(row["created_at"]), tz=timezone.utc).date().isoformat()
            counts[day] = counts.get(day, 0) + 1

        today = datetime.now(timezone.utc).date()
        series = []
        for offset in range(days - 1, -1, -1):
            day = today - timedelta(days=offset)
            key = day.isoformat()
            series.append({"date": key, "count": counts.get(key, 0)})
        return series

    def zero_result_queries(self, n: int = 20) -> list[dict[str, Any]]:
        """Return queries that produced no results most often."""
        rows = self._rows(
            """
            SELECT query, COUNT(*) AS count
            FROM recalls
            WHERE result_count = 0
            GROUP BY query
            ORDER BY count DESC, query ASC
            LIMIT ?
            """,
            (max(0, n),),
        )
        return [{"query": row["query"], "count": int(row["count"])} for row in rows]

    def preference_patterns(self, top_k: int = 10) -> list[dict[str, Any]]:
        """Extract preference patterns from recall history over the last 30 days.

        Groups recall events by tags/content keywords extracted from result IDs
        and query terms, returning the most frequently recalled topics.

        Returns:
            List of dicts with 'tags' (list of keywords) and 'frequency' (int),
            sorted by descending frequency.  Empty list when the recalls table
            does not exist or has no data.
        """
        try:
            rows = self._recall_rows(days=30)
        except Exception:
            return []

        if not rows:
            return []

        # Build frequency map keyed by canonical tag/keyword sets
        tag_freq: dict[str, int] = {}

        for row in rows:
            event = self._row_to_event(row)

            # Extract keywords from the query itself
            keywords = _extract_keywords(event.query)

            # Also use result_ids as signals (each id contributes)
            for _rid in event.result_ids:
                keywords.append(_rid)

            if not keywords:
                continue

            # Normalise: sort so that the same set of tags always hits the same key
            key = ",".join(sorted(set(keywords)))
            tag_freq[key] = tag_freq.get(key, 0) + 1

        # Build sorted output
        ranked = sorted(tag_freq.items(), key=lambda item: (-item[1], item[0]))[: max(0, top_k)]
        return [{"tags": key.split(","), "frequency": freq} for key, freq in ranked]

    def summary(self, days: int = 7) -> dict[str, Any]:
        """Return a compact analytics summary for dashboards."""
        return {
            "enabled": self.enabled,
            "retention_days": self.retention_days,
            "success": self.recall_success_rate_stats(days=days),
            "latency": self.latency_stats(),
            "top_queries": self.query_patterns(5),
            "zero_result_queries": self.zero_result_queries(5),
            "daily_activity": self.daily_activity(days=min(30, max(1, days))),
            "preference_patterns": self.preference_patterns(top_k=5),
        }


# ---------------------------------------------------------------------------
# Keyword extraction helper (module-level so it can be reused)
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"\b\w{3,}\b")


def _extract_keywords(text: str) -> list[str]:
    """Extract lowercase keywords (>= 3 chars) from *text*."""
    return [m.group(0).lower() for m in _WORD_RE.finditer(text.lower())]
