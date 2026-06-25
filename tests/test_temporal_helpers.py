from datetime import timezone

from memanto.app.utils.temporal_helpers import parse_iso_timestamp


def test_parse_iso_timestamp_normalizes_offset_to_utc():
    parsed = parse_iso_timestamp("2026-01-15T08:30:00-05:00")

    assert parsed.tzinfo == timezone.utc
    assert parsed.isoformat() == "2026-01-15T13:30:00+00:00"


def test_parse_iso_timestamp_assumes_naive_values_are_utc():
    parsed = parse_iso_timestamp("2026-01-15T13:30:00")

    assert parsed.tzinfo == timezone.utc
    assert parsed.isoformat() == "2026-01-15T13:30:00+00:00"
