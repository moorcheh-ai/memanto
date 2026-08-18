"""Tests for Langfuse project discovery.

Discovery is what makes the "user decides" design workable: nobody can choose a
latency budget or a score rule without first seeing what their own project
actually contains.
"""

from __future__ import annotations

from memanto.cli.migrate.langfuse_discover import (
    describe_errors,
    describe_operations,
    describe_scores,
    discover,
)


def obs(i=0, name="summarize", level="DEFAULT", seconds=1, **extra):
    return {
        "id": f"o{i}",
        "traceId": f"t{i}",
        "name": name,
        "level": level,
        "startTime": "2026-08-01T12:00:00Z",
        "endTime": f"2026-08-01T12:00:{seconds:02d}Z",
        **extra,
    }


def export(observations=None, scores=None):
    return {
        "api_base": "https://cloud.langfuse.com",
        "summary": {"from_time": "2026-07-01T00:00:00+00:00", "discover": True},
        "observations": observations if observations is not None else [],
        "scores": scores if scores is not None else [],
    }


# --------------------------------------------------------------------------
# Scores
# --------------------------------------------------------------------------


def test_numeric_scores_report_their_observed_range():
    scores = [
        {"name": "rating", "value": v, "dataType": "NUMERIC"} for v in (1, 3, 5, 4)
    ]
    row = describe_scores(scores)[0]

    assert row["name"] == "rating"
    assert row["data_type"] == "NUMERIC"
    assert (row["min"], row["max"]) == (1.0, 5.0)
    assert row["count"] == 4
    # The suggestion must reflect the real range, not a 0-1 assumption.
    assert "1.0" in row["suggestion"] and "5.0" in row["suggestion"]


def test_categorical_scores_list_their_labels():
    scores = [{"name": "verdict", "value": v} for v in ("ok", "refusal", "ok")]
    row = describe_scores(scores)[0]

    assert row["data_type"] == "CATEGORICAL"
    assert set(row["categories"]) == {"ok", "refusal"}
    assert "in" in row["suggestion"]


def test_boolean_scores_are_detected_and_direction_is_left_to_the_user():
    row = describe_scores([{"name": "thumbs_up", "value": v} for v in (0, 1, 1)])[0]

    assert row["data_type"] == "BOOLEAN"
    # The suggestion must not assert which direction means failure.
    assert "=false" in row["suggestion"] and "=true" in row["suggestion"]


def test_declared_data_type_wins_over_inference():
    row = describe_scores([{"name": "s", "value": 1, "dataType": "NUMERIC"}])[0]
    assert row["data_type"] == "NUMERIC"


def test_multiple_score_names_are_reported_separately():
    rows = describe_scores(
        [
            {"name": "correctness", "value": 0.4},
            {"name": "toxicity", "value": 0.9},
        ]
    )
    assert {r["name"] for r in rows} == {"correctness", "toxicity"}


# --------------------------------------------------------------------------
# Operations
# --------------------------------------------------------------------------


def test_operations_report_latency_percentiles():
    observations = [obs(i, seconds=1) for i in range(9)] + [obs(99, seconds=30)]
    row = describe_operations(observations)[0]

    assert row["name"] == "summarize"
    assert row["count"] == 10
    assert row["latency_p50"] == 1000
    assert row["latency_p99"] == 30000


def test_operations_are_ranked_by_volume():
    rows = describe_operations(
        [obs(i, name="hot") for i in range(10)] + [obs(99, name="rare")]
    )
    assert [r["name"] for r in rows] == ["hot", "rare"]


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


def test_error_labels_preview_what_grouping_would_produce():
    observations = [
        obs(i, level="ERROR", statusMessage="Model returned malformed output")
        for i in range(5)
    ] + [obs(9, level="ERROR", statusMessage="RateLimitError: quota exceeded")]

    info = describe_errors(observations)[0]

    assert info["errored_observations"] == 6
    assert info["distinct_signatures"] == 2
    labels = {row["label"]: row["count"] for row in info["labels"]}
    assert labels == {"Model returned malformed output": 5, "RateLimitError": 1}


# --------------------------------------------------------------------------
# Notes — the part that tells a user a mode will do nothing
# --------------------------------------------------------------------------


def test_no_scores_is_called_out():
    report = discover(export(observations=[obs()]))
    assert any("No scores" in note for note in report["notes"])


def test_absent_cost_data_is_called_out():
    report = discover(export(observations=[obs()]))

    assert report["has_cost_data"] is False
    assert any("cost data" in note for note in report["notes"])


def test_present_cost_data_is_not_flagged():
    report = discover(export(observations=[obs(costDetails={"total": 0.02})]))

    assert report["has_cost_data"] is True
    assert not any("cost data" in note for note in report["notes"])


def test_poorly_grouping_messages_are_called_out():
    """The honest signal that this project needs --group-by."""
    observations = [
        obs(i, level="ERROR", statusMessage=f"failure of kind {chr(65 + i)}")
        for i in range(30)
    ]

    report = discover(export(observations=observations))

    assert any("group" in note.lower() for note in report["notes"])


def test_well_grouping_messages_are_not_flagged():
    observations = [
        obs(i, level="ERROR", statusMessage=f"RateLimitError: retry {i}")
        for i in range(30)
    ]

    report = discover(export(observations=observations))

    assert not any("group" in note.lower() for note in report["notes"])


def test_discover_on_an_empty_export():
    report = discover(export())

    assert report["window"]["observation_count"] == 0
    assert report["scores"] == []
    assert report["operations"] == []
    assert len(report["notes"]) >= 1


def test_a_numeric_score_with_no_observed_range_is_not_given_fake_bounds():
    """Regression: a score Langfuse labels NUMERIC whose values are all strings
    has no observed min/max, and the suggestion fell back to 0..1 — printing
    '(observed 0..1)' for a range nobody saw, with a threshold matching nothing."""
    row = describe_scores(
        [
            {"name": "grade", "value": "A", "dataType": "NUMERIC"},
            {"name": "grade", "value": "B", "dataType": "NUMERIC"},
        ]
    )[0]

    assert "min" not in row
    assert "observed 0..1" not in row["suggestion"]
    assert "in" in row["suggestion"]  # falls back to the membership form


def test_a_real_numeric_range_still_reports_observed_bounds():
    row = describe_scores(
        [{"name": "rating", "value": v, "dataType": "NUMERIC"} for v in (1, 5)]
    )[0]
    assert "observed 1.0..5.0" in row["suggestion"]
