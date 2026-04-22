"""Tests for the canonical parse_date helper in memos.utils."""

from __future__ import annotations

import time

import pytest

from memos.utils import parse_date


class TestParseDateNone:
    def test_none(self) -> None:
        assert parse_date(None) is None


class TestParseDateNumeric:
    def test_int_passthrough(self) -> None:
        assert parse_date(1700000000) == 1700000000.0

    def test_float_passthrough(self) -> None:
        assert parse_date(1700000000.5) == 1700000000.5

    def test_zero(self) -> None:
        # Must NOT return None for 0 (was a bug in the _memory.py version)
        assert parse_date(0) == 0.0


class TestParseDateIso8601:
    def test_iso_z(self) -> None:
        ts = parse_date("2024-01-15T10:30:00Z")
        assert isinstance(ts, float)
        assert ts > 0

    def test_iso_no_tz(self) -> None:
        ts = parse_date("2024-01-15T10:30:00")
        assert isinstance(ts, float)
        assert ts > 0

    def test_date_only(self) -> None:
        ts = parse_date("2024-01-15")
        assert isinstance(ts, float)
        assert ts > 0


class TestParseDateRelative:
    def test_relative_seconds(self) -> None:
        before = time.time()
        result = parse_date("30s")
        after = time.time()
        assert result is not None
        assert (before - 30) <= result <= (after - 30)

    def test_relative_minutes(self) -> None:
        before = time.time()
        result = parse_date("5m")
        after = time.time()
        assert result is not None
        assert (before - 300) <= result <= (after - 300)

    def test_relative_hours(self) -> None:
        before = time.time()
        result = parse_date("2h")
        after = time.time()
        assert result is not None
        assert (before - 7200) <= result <= (after - 7200)

    def test_relative_days(self) -> None:
        before = time.time()
        result = parse_date("1d")
        after = time.time()
        assert result is not None
        assert (before - 86400) <= result <= (after - 86400)

    def test_relative_weeks(self) -> None:
        before = time.time()
        result = parse_date("1w")
        after = time.time()
        assert result is not None
        assert (before - 604800) <= result <= (after - 604800)

    def test_relative_float(self) -> None:
        before = time.time()
        result = parse_date("1.5h")
        after = time.time()
        assert result is not None
        assert (before - 5400) <= result <= (after - 5400)


class TestParseDateFallback:
    def test_numeric_string(self) -> None:
        assert parse_date("1700000000") == 1700000000.0

    def test_empty_string(self) -> None:
        assert parse_date("") is None

    def test_whitespace_string(self) -> None:
        assert parse_date("   ") is None

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse date"):
            parse_date("not-a-date")
