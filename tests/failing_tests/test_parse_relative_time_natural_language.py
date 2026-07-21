"""
Failing test: parse_relative_time silently returns None for natural-language
relative times ("last week", "last month", "last year"), causing timeline-amnesia
in any caller that treats None as "no filter" rather than "invalid input."

Reproduction for moorcheh-ai/memanto bounty issue #770.

Bug class: timeline amnesia / temporal recall accuracy (bounty severity matrix: Critical/High).
"""
from memanto.app.utils.temporal_helpers import parse_relative_time


def test_last_week_returns_approximately_7_days_ago():
    """User typing 'last week' expects ~7 days ago, not None (no filter = all memories)."""
    result = parse_relative_time("last week")
    assert result is not None, (
        "parse_relative_time('last week') returned None — caller treats this as "
        "'no filter' and returns ALL memories including ones years old. "
        "This is the timeline-amnesia bug class the bounty calls out."
    )


def test_last_month_returns_approximately_30_days_ago():
    result = parse_relative_time("last month")
    assert result is not None, "Same bug: 'last month' silently means 'no filter'."


def test_last_year_returns_approximately_365_days_ago():
    result = parse_relative_time("last year")
    assert result is not None, "Same bug: 'last year' silently means 'no filter'."


def test_past_N_days_synonym():
    """Common synonym for 'last N days' should also work."""
    result = parse_relative_time("past 7 days")
    assert result is not None, "'past 7 days' silently means 'no filter'."


def test_word_numbers_are_handled():
    """Users naturally type 'seven' not '7'."""
    result = parse_relative_time("last seven days")
    assert result is not None, "'last seven days' silently means 'no filter'."


if __name__ == "__main__":
    # Quick visual confirmation of the bug
    import sys
    cases = ["last week", "last month", "last year", "past 7 days", "last seven days"]
    failed = []
    for c in cases:
        r = parse_relative_time(c)
        status = "BUG: returns None" if r is None else f"OK: {r}"
        print(f"  {c!r:<25} → {status}")
        if r is None:
            failed.append(c)
    print()
    print(f"Failed cases: {len(failed)}/{len(cases)}")
    sys.exit(1 if failed else 0)
