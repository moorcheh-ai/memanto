"""
Failing test: parse_relative_time silently returns None for natural-language
relative times ("last week", "last month", "last year"), causing timeline-amnesia
in any caller that treats None as "no filter" rather than "invalid input."

Reproduction for moorcheh-ai/memanto bounty issue #770.

Bug class: timeline amnesia / temporal recall accuracy (bounty severity matrix: Critical/High).
"""
from datetime import datetime, timedelta, timezone

from memanto.app.utils.temporal_helpers import parse_relative_time


def _utcnow_naive() -> datetime:
    """Match the naive-UTC format parse_relative_time returns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _assert_iso_timestamp(value: str) -> datetime:
    """Parse a returned timestamp and assert it is a valid ISO string."""
    assert value is not None, "parse_relative_time returned None"
    assert value.endswith("Z"), f"expected Z-suffixed ISO timestamp, got {value!r}"
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def _assert_days_ago(value: str, expected_days: int, tolerance_days: int = 1) -> None:
    """Assert the timestamp is within tolerance of N days ago."""
    parsed = _assert_iso_timestamp(value)
    now = _utcnow_naive()
    delta = now - parsed
    target = timedelta(days=expected_days)
    lower = target - timedelta(days=tolerance_days)
    upper = target + timedelta(days=tolerance_days)
    assert lower <= delta <= upper, (
        f"timestamp {value!r} is {delta} ago; expected ~{expected_days} days "
        f"(within ±{tolerance_days}d). now={now.isoformat()}"
    )


def _assert_hours_ago(value: str, expected_hours: int, tolerance_hours: int = 1) -> None:
    """Assert the timestamp is within tolerance of N hours ago."""
    parsed = _assert_iso_timestamp(value)
    now = _utcnow_naive()
    delta = now - parsed
    target = timedelta(hours=expected_hours)
    lower = target - timedelta(hours=tolerance_hours)
    upper = target + timedelta(hours=tolerance_hours)
    assert lower <= delta <= upper, (
        f"timestamp {value!r} is {delta} ago; expected ~{expected_hours} hours "
        f"(within ±{tolerance_hours}h). now={now.isoformat()}"
    )


def test_last_week_returns_approximately_7_days_ago():
    """User typing 'last week' expects ~7 days ago, not None (no filter = all memories)."""
    result = parse_relative_time("last week")
    _assert_days_ago(result, expected_days=7, tolerance_days=1)


def test_last_month_returns_approximately_30_days_ago():
    result = parse_relative_time("last month")
    _assert_days_ago(result, expected_days=30, tolerance_days=1)


def test_last_year_returns_approximately_365_days_ago():
    result = parse_relative_time("last year")
    _assert_days_ago(result, expected_days=365, tolerance_days=1)


def test_past_N_days_synonym():
    """Common synonym for 'last N days' should also work."""
    result = parse_relative_time("past 7 days")
    _assert_days_ago(result, expected_days=7, tolerance_days=1)


def test_word_numbers_are_handled():
    """Users naturally type 'seven' not '7'."""
    result = parse_relative_time("last seven days")
    _assert_days_ago(result, expected_days=7, tolerance_days=1)


def test_numeric_last_N_days_returns_correct_timestamp():
    """Numeric form must return a timestamp N days ago, not just 'not None'."""
    result = parse_relative_time("last 14 days")
    _assert_days_ago(result, expected_days=14, tolerance_days=1)


def test_numeric_last_N_hours_returns_correct_timestamp():
    """Hours form must return a timestamp N hours ago."""
    result = parse_relative_time("last 48 hours")
    _assert_hours_ago(result, expected_hours=48, tolerance_hours=1)


def test_huge_input_returns_none_instead_of_crashing():
    """Pathological inputs (e.g. 'last 9999999999 days') must not raise OverflowError.

    Regression guard: get_last_n_days/hours build a timedelta that overflows for
    enormous N. Without the guard the caller crashes; with it we return None and
    the caller's existing 'invalid input' handling takes over.
    """
    result = parse_relative_time("last 9999999999 days")
    assert result is None, (
        f"expected None for overflow input, got {result!r} — OverflowError guard missing"
    )


def test_huge_hours_input_returns_none_instead_of_crashing():
    result = parse_relative_time("last 9999999999 hours")
    assert result is None, f"expected None for overflow input, got {result!r}"


if __name__ == "__main__":
    # Quick visual confirmation of the bug
    import sys
    cases = [
        "last week", "last month", "last year",
        "past 7 days", "last seven days",
        "last 14 days", "last 48 hours",
        "last 9999999999 days", "last 9999999999 hours",
    ]
    failed = []
    for c in cases:
        r = parse_relative_time(c)
        status = "BUG: returns None" if r is None else f"OK: {r}"
        print(f"  {c!r:<30} → {status}")
        # Don't count overflow cases as failures; they should return None.
        if r is None and "9999999999" not in c:
            failed.append(c)
    print()
    print(f"Failed cases: {len(failed)}/{len(cases)}")
    sys.exit(1 if failed else 0)
