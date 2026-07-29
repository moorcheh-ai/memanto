from datetime import timezone

import pytest

from memanto.app.routes.memory import RecallRequest
from memanto.app.services.memory_read_service import MemoryReadService
from memanto.app.utils.temporal_helpers import (
    build_temporal_query,
    parse_as_of_timestamp,
    parse_iso_timestamp,
    parse_relative_time,
)


def test_parse_iso_timestamp_normalizes_offset_to_utc():
    parsed = parse_iso_timestamp("2026-01-15T08:30:00-05:00")

    assert parsed.tzinfo == timezone.utc
    assert parsed.isoformat() == "2026-01-15T13:30:00+00:00"


def test_parse_relative_time_rejects_non_positive_windows():
    assert parse_relative_time("last 0 days") is None
    assert parse_relative_time("last -1 days") is None
    assert parse_relative_time("last 0 hours") is None
    assert parse_relative_time("last -2 hours") is None


def test_parse_iso_timestamp_assumes_naive_values_are_utc():
    parsed = parse_iso_timestamp("2026-01-15T13:30:00")

    assert parsed.tzinfo == timezone.utc
    assert parsed.isoformat() == "2026-01-15T13:30:00+00:00"


def test_temporal_filter_skips_malformed_memory_timestamps_per_record():
    service = MemoryReadService(object())

    results = [
        {"id": "old", "created_at": "2025-01-01T00:00:00Z"},
        {"id": "new", "created_at": "2025-02-01T00:00:00Z"},
        {"id": "bad", "created_at": "not-a-timestamp"},
    ]

    filtered = service._apply_temporal_filter(
        results, created_after="2025-01-15T00:00:00Z"
    )

    assert [memory["id"] for memory in filtered] == ["new"]


def test_temporal_query_payload_is_accepted_by_recall_request_model():
    payload = build_temporal_query(
        "http://localhost:8000",
        "agent-1",
        "deployment notes",
        relative_time="last 7 days",
    )["json"]

    request = RecallRequest.model_validate(payload)

    assert payload["created_after"] is not None
    assert request.created_after is not None


def test_build_temporal_query_rejects_invalid_relative_time():
    with pytest.raises(ValueError, match="Invalid relative_time"):
        build_temporal_query(
            "http://localhost:8000",
            "agent-1",
            "deployment notes",
            relative_time="last 0 days",
        )


def test_parse_as_of_timestamp_treats_date_only_as_end_of_day():
    parsed = parse_as_of_timestamp("2026-01-15")

    assert parsed.tzinfo == timezone.utc
    assert parsed.isoformat() == "2026-01-15T23:59:59.999999+00:00"


def test_parse_as_of_timestamp_preserves_explicit_time():
    parsed = parse_as_of_timestamp("2026-01-15T13:30:00Z")

    assert parsed.isoformat() == "2026-01-15T13:30:00+00:00"
