"""Tests for issue #1655: `as_of` date parsing divergence.

The REST route validator and the service helper (`parse_as_of_timestamp`)
used to disagree on basic-format ISO dates (`20260726`) and on the
sub-second cutoff. These tests pin a single shared rule:

- Extended format (``2026-07-26``)         → end of day (UTC)
- Basic format   (``20260726``)            → end of day (UTC) — was start-of-day
- ISO week date  (``2026-W30-7``)          → end of day (UTC)
- ISO datetime   (``2026-07-26T14:30:00``) → exact instant
- ISO datetime Z (``2026-07-26T14:30:00Z``) → exact instant

REST and CLI/MCP paths must agree to the microsecond.
"""

from datetime import date, datetime, time, timezone

import pytest
from pydantic import ValidationError

from memanto.app.routes.memory import RecallAsOfRequest
from memanto.app.utils.temporal_helpers import parse_as_of_timestamp


def _end_of_utc(yyyy: int, mm: int, dd: int) -> datetime:
    """Helper: end-of-day in UTC (microsecond precision like ``time.max``)."""
    return datetime.combine(date(yyyy, mm, dd), time.max, tzinfo=timezone.utc)


class TestParseAsOfTimestamp:
    """Service-helper path: CLI / MCP / Python clients."""

    def test_extended_format_date_is_end_of_day(self):
        assert parse_as_of_timestamp("2026-07-26") == _end_of_utc(2026, 7, 26)

    def test_basic_format_date_is_end_of_day(self):
        # Previously fell through to parse_iso_timestamp → start of day.
        assert parse_as_of_timestamp("20260726") == _end_of_utc(2026, 7, 26)

    def test_iso_week_date_is_end_of_day(self):
        # 2026-W30-7 = 2026-07-26 (Sunday of ISO week 30).
        assert parse_as_of_timestamp("2026-W30-7") == _end_of_utc(2026, 7, 26)

    def test_iso_datetime_is_preserved_exactly(self):
        assert parse_as_of_timestamp("2026-07-26T14:30:00") == datetime(
            2026, 7, 26, 14, 30, 0, tzinfo=timezone.utc
        )

    def test_iso_datetime_z_suffix_is_utc(self):
        result = parse_as_of_timestamp("2026-07-26T14:30:00Z")
        assert result == datetime(2026, 7, 26, 14, 30, 0, tzinfo=timezone.utc)
        assert result.tzinfo == timezone.utc

    def test_iso_datetime_with_offset_is_normalized_to_utc(self):
        # +02:00 input → same instant in UTC.
        result = parse_as_of_timestamp("2026-07-26T16:30:00+02:00")
        assert result == datetime(2026, 7, 26, 14, 30, 0, tzinfo=timezone.utc)

    def test_invalid_string_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_as_of_timestamp("not a date")


class TestRestAndServiceHelperAgree:
    """Issue #1655's core fix: the two parse paths must not diverge."""

    @pytest.mark.parametrize(
        "raw",
        [
            "2026-07-26",   # extended
            "20260726",     # basic — previously diverged by 24 hours
            "2026-W30-7",   # ISO week
        ],
    )
    def test_date_only_inputs_match_between_paths(self, raw: str):
        rest = RecallAsOfRequest(as_of=raw).as_of
        helper = parse_as_of_timestamp(raw)
        assert rest == helper, (
            f"REST={rest!r} helper={helper!r} — issue #1655 regression"
        )

    @pytest.mark.parametrize(
        "raw",
        [
            "2026-07-26T14:30:00",
            "2026-07-26T14:30:00Z",
            "2026-07-26T16:30:00+02:00",
        ],
    )
    def test_full_datetime_inputs_match_between_paths(self, raw: str):
        rest = RecallAsOfRequest(as_of=raw).as_of
        helper = parse_as_of_timestamp(raw)
        assert rest == helper

    def test_sub_second_cutoff_is_microsecond_precision(self):
        """Both paths must use ``time.max`` (23:59:59.999999), not 23:59:59."""
        expected = _end_of_utc(2026, 7, 26)
        assert parse_as_of_timestamp("2026-07-26") == expected
        assert RecallAsOfRequest(as_of="2026-07-26").as_of == expected
