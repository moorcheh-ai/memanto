"""Regression tests for as-of date-only parsing.

`as_of` is normalised in two places -- the REST request validator
(`RecallAsOfRequest.parse_as_of`) and the service-level helper
(`parse_as_of_timestamp`, used by the CLI, MCP and the Python clients). Both
implement the same documented rule: a date-only cutoff means the END of that day.

They used to detect "date-only" differently. The helper matched on shape
(`len == 10` plus hyphens at 4 and 7), which silently rejected the ISO-8601
basic format `20260726` -- a valid date that `date.fromisoformat` accepts -- so
it fell through to the datetime parser and became midnight, the START of the
day. The same string sent to REST resolved to the end of the day, leaving the
two paths 23:59:59 apart. The two also disagreed by 0.999999s on hyphenated
dates (`time.max` vs `time(23, 59, 59)`).

Each test below fails on the pre-fix code.
"""

from datetime import datetime, time, timezone

import pytest

from memanto.app.routes.memory import RecallAsOfRequest
from memanto.app.utils import temporal_helpers
from memanto.app.utils.temporal_helpers import parse_as_of_timestamp

DATE_SPELLINGS = ["2026-07-26", "20260726"]
# Expressed as a literal rather than via the new END_OF_DAY constant, so these
# assertions run against the pre-fix source and fail on the bug itself.
EXPECTED = datetime(2026, 7, 26, 23, 59, 59, 999999, tzinfo=timezone.utc)


@pytest.mark.parametrize("raw", DATE_SPELLINGS)
def test_service_helper_treats_date_only_as_end_of_day(raw):
    """Both ISO date spellings resolve to the end of the day, not midnight."""
    assert parse_as_of_timestamp(raw) == EXPECTED


@pytest.mark.parametrize("raw", DATE_SPELLINGS)
def test_rest_validator_matches_service_helper(raw):
    """The REST validator and the service helper must not drift apart."""
    assert RecallAsOfRequest(as_of=raw).as_of == parse_as_of_timestamp(raw)


def test_basic_format_is_not_parsed_as_start_of_day():
    """`20260726` must not silently exclude the whole of 26 July."""
    parsed = parse_as_of_timestamp("20260726")
    assert parsed.time() != time(0, 0, 0), (
        "basic-format ISO date parsed as start-of-day; a point-in-time recall "
        "would silently drop that entire day"
    )


def test_datetime_inputs_are_untouched():
    """A full ISO datetime keeps its own time component."""
    assert parse_as_of_timestamp("2026-07-26T12:00:00Z") == datetime(
        2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc
    )


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-07-26", True),
        ("20260726", True),
        ("2026-07-26T12:00:00Z", False),
        ("2026-07-26 12:00:00", False),
        ("not-a-date", False),
        ("", False),
    ],
)
def test_is_date_only(raw, expected):
    assert temporal_helpers.is_date_only(raw) is expected


@pytest.mark.parametrize("raw", ["20261345", "20260732", "1234567", "abcdefgh"])
def test_basic_format_detection_rejects_non_dates(raw):
    """Eight characters is not enough -- the value must be a real calendar date."""
    assert temporal_helpers.is_date_only(raw) is False


def test_basic_format_does_not_depend_on_python_311_stdlib(monkeypatch):
    """The un-hyphenated form must resolve on the 3.10 baseline too.

    ``date.fromisoformat`` only learned the basic ``20260726`` form in Python
    3.11, but ``requires-python`` is ">=3.10" and CI runs 3.10. This simulates
    the 3.10 stdlib to prove detection does not silently regress to
    start-of-day there.
    """
    from datetime import date as real_date

    class Py310Date(real_date):
        @classmethod
        def fromisoformat(cls, value):
            if "-" not in value:
                raise ValueError(f"Invalid isoformat string: {value!r}")
            return real_date.fromisoformat(value)

    monkeypatch.setattr(temporal_helpers, "date", Py310Date)

    assert temporal_helpers.is_date_only("20260726") is True
    assert parse_as_of_timestamp("20260726") == EXPECTED
    assert parse_as_of_timestamp("2026-07-26") == EXPECTED
