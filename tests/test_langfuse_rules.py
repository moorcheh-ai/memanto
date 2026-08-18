"""Tests for Langfuse capture rules: classification, signatures, payloads."""

from __future__ import annotations

from memanto.cli.migrate.langfuse_rules import (
    CaptureConfig,
    build_rows,
    classify,
    confidence_for,
    cost_usd,
    error_class,
    group_observations,
    latency_ms,
    normalize_message,
    signature_for,
    to_memory_payload,
)

ALL_MODES = CaptureConfig(
    modes=frozenset({"errors", "low_score", "slow", "costly", "success"})
)


def observation(**overrides):
    """A minimal errored observation; override any field."""
    base = {
        "id": "obs-1",
        "traceId": "trace-1",
        "projectId": "proj-1",
        "name": "summarize_node",
        "type": "GENERATION",
        "level": "ERROR",
        "statusMessage": "RateLimitError: quota exceeded",
        "startTime": "2026-08-01T12:00:00Z",
        "endTime": "2026-08-01T12:00:01Z",
        "providedModelName": "claude-opus-5",
        "environment": "production",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# Normalization and signatures
# --------------------------------------------------------------------------


def test_normalize_message_strips_volatile_fragments():
    text = (
        "Request 1a2b3c4d-1111-2222-3333-444455556666 to https://api.example.com/v1 "
        "failed at /var/log/app/run.log after 42 attempts (0xdeadbeef)"
    )
    normalized = normalize_message(text)

    assert "1a2b3c4d" not in normalized
    assert "https://" not in normalized
    assert "42" not in normalized
    assert "deadbeef" not in normalized
    assert "failed at" in normalized


def test_same_fault_with_different_ids_shares_one_signature():
    """The whole point of grouping: volatile detail must not fork the signature."""
    first = observation(
        statusMessage=(
            "RateLimitError: quota exceeded for request "
            "1a2b3c4d-1111-2222-3333-444455556666 after 30 attempts"
        )
    )
    second = observation(
        id="obs-2",
        traceId="trace-2",
        statusMessage=(
            "RateLimitError: quota exceeded for request "
            "9f8e7d6c-9999-8888-7777-666655554444 after 77 attempts"
        ),
    )

    assert signature_for(first, "errors") == signature_for(second, "errors")


def test_distinct_error_classes_get_distinct_signatures():
    rate_limit = observation(statusMessage="RateLimitError: quota exceeded")
    timeout = observation(statusMessage="TimeoutError: upstream did not respond")

    assert signature_for(rate_limit, "errors")[0] != signature_for(timeout, "errors")[0]


def test_same_error_in_different_operations_stays_separate():
    here = observation(name="summarize_node")
    there = observation(name="retrieve_node")

    assert signature_for(here, "errors")[0] != signature_for(there, "errors")[0]


def test_error_class_extraction():
    assert error_class("RateLimitError: nope") == "RateLimitError"
    assert error_class("raised ValueError somewhere") == "ValueError"
    assert error_class("everything is fine") is None


def test_free_form_messages_get_a_readable_label():
    """Langfuse's statusMessage follows no template — its own docs' examples
    are plain sentences, so a label must not depend on exception-class syntax."""
    cases = {
        "Model returned malformed output": "Model returned malformed output",
        "Operation failed with unexpected input": "Operation failed with unexpected input",
        "context deadline exceeded": "context deadline exceeded",
        "connection reset by peer": "connection reset by peer",
    }
    for message, expected in cases.items():
        _, label = signature_for(observation(statusMessage=message), "errors")
        assert label == expected


def test_label_prefers_an_exception_class_when_present():
    _, label = signature_for(
        observation(statusMessage="RateLimitError: quota exceeded"), "errors"
    )
    assert label == "RateLimitError"


def test_label_truncates_and_never_empties():
    _, long_label = signature_for(observation(statusMessage="x" * 500), "errors")
    assert len(long_label) <= 60

    _, empty_label = signature_for(
        {"name": "n", "level": "ERROR", "statusMessage": ""}, "errors"
    )
    assert empty_label == "Unlabelled failure"


# --------------------------------------------------------------------------
# Derived metrics
# --------------------------------------------------------------------------


def test_latency_prefers_timestamps_over_the_latency_field():
    obs = observation(
        startTime="2026-08-01T12:00:00Z",
        endTime="2026-08-01T12:00:45Z",
        latency=999,
    )
    assert latency_ms(obs) == 45_000.0


def test_latency_falls_back_to_seconds_field():
    obs = observation(startTime=None, endTime=None, latency=2.5)
    assert latency_ms(obs) == 2_500.0


def test_cost_reads_the_total_then_sums_the_parts():
    assert cost_usd(observation(costDetails={"total": 1.25, "input": 1.0})) == 1.25
    assert cost_usd(observation(costDetails={"input": 0.5, "output": 0.25})) == 0.75
    # No cost data is 0.0, not an error — many projects never record cost.
    assert cost_usd(observation()) == 0.0


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------


def test_error_level_classifies_as_errors():
    assert classify(observation(), ALL_MODES) == "errors"


def test_non_error_observation_is_ignored_when_only_errors_captured():
    config = CaptureConfig(modes=frozenset({"errors"}))
    assert classify(observation(level="DEFAULT"), config) is None


def test_thresholds_are_inert_until_the_user_sets_a_budget():
    """No invented defaults: 30s and $1 are meaningless across projects."""
    config = CaptureConfig(modes=frozenset({"slow", "costly"}))
    very_slow = observation(
        level="DEFAULT",
        startTime="2026-08-01T12:00:00Z",
        endTime="2026-08-01T13:00:00Z",
        costDetails={"total": 500.0},
    )

    assert classify(very_slow, config) is None
    assert set(config.unconfigured_modes()) == {"slow", "costly"}


def test_percentile_budget_calibrates_against_the_projects_own_traffic():
    from memanto.cli.migrate.langfuse_rules import build_baselines

    config = CaptureConfig(modes=frozenset({"slow"}), latency_percentile=90)
    # Nine fast calls and one outlier, all the same operation.
    fast = [
        observation(
            id=f"f{i}",
            level="DEFAULT",
            startTime="2026-08-01T12:00:00Z",
            endTime="2026-08-01T12:00:01Z",
        )
        for i in range(9)
    ]
    outlier = observation(
        id="slow",
        level="DEFAULT",
        startTime="2026-08-01T12:00:00Z",
        endTime="2026-08-01T12:00:30Z",
    )
    baselines = build_baselines(fast + [outlier], config)

    assert classify(outlier, config, {}, baselines) == "slow"
    assert classify(fast[0], config, {}, baselines) is None


def test_slow_and_costly_thresholds():
    config = CaptureConfig(
        modes=frozenset({"slow", "costly"}), latency_ms=30_000, cost_usd=1.0
    )
    slow = observation(
        level="DEFAULT",
        startTime="2026-08-01T12:00:00Z",
        endTime="2026-08-01T12:00:45Z",
    )
    costly = observation(level="DEFAULT", costDetails={"total": 2.5})
    cheap_and_fast = observation(level="DEFAULT")

    assert classify(slow, config) == "slow"
    assert classify(costly, config) == "costly"
    assert classify(cheap_and_fast, config) is None


def test_errors_outrank_slow_for_the_same_observation():
    """An errored slow call is an error, not a latency anomaly."""
    config = CaptureConfig(modes=frozenset({"errors", "slow"}), latency_ms=1_000)
    both = observation(startTime="2026-08-01T12:00:00Z", endTime="2026-08-01T12:00:45Z")
    assert classify(both, config) == "errors"


def test_scores_drive_low_score_and_success_via_user_rules():
    """Langfuse documents no direction convention, so the user's rule decides."""
    from memanto.cli.migrate.langfuse_config import parse_score_rule
    from memanto.cli.migrate.langfuse_rules import score_modes_by_trace

    config = CaptureConfig(
        modes=frozenset({"low_score", "success"}),
        score_fail_rules=(parse_score_rule("correctness<0.7"),),
        score_pass_rules=(parse_score_rule("correctness>=0.9"),),
    )
    scores = [
        {"traceId": "trace-1", "name": "correctness", "value": 0.2},
        {"traceId": "trace-9", "name": "correctness", "value": 0.9},
    ]
    by_trace = score_modes_by_trace(scores, config)

    assert classify(observation(level="DEFAULT"), config, by_trace) == "low_score"
    assert (
        classify(observation(level="DEFAULT", traceId="trace-9"), config, by_trace)
        == "success"
    )


def test_scores_link_to_traces_through_subject():
    """v3 scores carry linkage as subject:{kind,id}, not a flat traceId.

    Regression: reading only `traceId` left every live score unattached, so
    score rules silently matched nothing.
    """
    from memanto.cli.migrate.langfuse_config import parse_score_rule
    from memanto.cli.migrate.langfuse_rules import score_modes_by_trace, score_trace_id

    live_shape = {
        "name": "user-thumbs",
        "value": False,
        "dataType": "BOOLEAN",
        "subject": {"kind": "trace", "id": "trace-1"},
    }
    assert score_trace_id(live_shape) == "trace-1"

    config = CaptureConfig(
        modes=frozenset({"low_score"}),
        score_fail_rules=(parse_score_rule("user-thumbs=false"),),
    )
    by_trace = score_modes_by_trace([live_shape], config)

    assert by_trace["trace-1"]["capture_mode"] == "low_score"
    assert classify(observation(level="DEFAULT"), config, by_trace) == "low_score"


def test_non_trace_scoped_scores_are_skipped():
    """A score on a session or dataset run has no observation to attach to."""
    from memanto.cli.migrate.langfuse_rules import score_trace_id

    assert score_trace_id({"subject": {"kind": "session", "id": "s1"}}) is None
    assert score_trace_id({"subject": None}) is None
    assert score_trace_id({"traceId": "flat-1"}) == "flat-1"


def test_an_inverted_metric_is_handled_by_writing_the_rule_that_way():
    """A high toxicity score is a failure — a global 'below X is bad' inverts this."""
    from memanto.cli.migrate.langfuse_config import parse_score_rule
    from memanto.cli.migrate.langfuse_rules import score_modes_by_trace

    config = CaptureConfig(
        modes=frozenset({"low_score"}),
        score_fail_rules=(parse_score_rule("toxicity>0.3"),),
    )
    by_trace = score_modes_by_trace(
        [{"traceId": "trace-1", "name": "toxicity", "value": 0.9}], config
    )

    assert classify(observation(level="DEFAULT"), config, by_trace) == "low_score"


def test_scores_capture_nothing_without_rules():
    """No rule means no way to know which scores mean failure — so, nothing."""
    from memanto.cli.migrate.langfuse_rules import score_modes_by_trace

    config = CaptureConfig(modes=frozenset({"low_score", "success"}))
    by_trace = score_modes_by_trace(
        [{"traceId": "trace-1", "name": "correctness", "value": 0.2}], config
    )

    assert by_trace == {}
    assert "low_score" in config.unconfigured_modes()


def test_thresholds_are_not_captured_when_mode_is_off():
    config = CaptureConfig(modes=frozenset({"errors"}), latency_ms=1)
    slow_but_fine = observation(
        level="DEFAULT",
        startTime="2026-08-01T12:00:00Z",
        endTime="2026-08-01T12:00:45Z",
    )
    assert classify(slow_but_fine, config) is None


# --------------------------------------------------------------------------
# Grouping
# --------------------------------------------------------------------------


def test_grouping_collapses_many_occurrences_into_one_group():
    observations = [
        observation(
            id=f"obs-{i}",
            traceId=f"trace-{i}",
            statusMessage=f"RateLimitError: quota exceeded on attempt {i}",
            startTime=f"2026-08-01T12:{i:02d}:00Z",
        )
        for i in range(50)
    ]

    groups = group_observations(observations, ALL_MODES)

    assert len(groups) == 1
    assert groups[0].count == 50
    assert len(groups[0].trace_ids) == 3  # capped sample, not all 50
    assert groups[0].first_seen is not None
    assert groups[0].last_seen is not None
    assert groups[0].first_seen < groups[0].last_seen


def test_groups_are_ordered_loudest_first():
    observations = [observation(id="a", statusMessage="TimeoutError: slow")] + [
        observation(id=f"b{i}", statusMessage="RateLimitError: quota exceeded")
        for i in range(5)
    ]
    groups = group_observations(observations, ALL_MODES)

    assert [g.count for g in groups] == [5, 1]


def test_unclassified_observations_are_dropped():
    config = CaptureConfig(modes=frozenset({"errors"}))
    assert group_observations([observation(level="DEFAULT")], config) == []


# --------------------------------------------------------------------------
# Payload shaping
# --------------------------------------------------------------------------


def test_confidence_rises_with_recurrence_and_is_capped():
    assert confidence_for(1) == 0.60
    assert confidence_for(10) == 0.75
    assert confidence_for(100) == 0.90
    assert confidence_for(10_000) == 0.95
    assert confidence_for(0) == 0.60


def test_payload_respects_every_memanto_schema_cap():
    observations = [
        observation(
            id=f"obs-{i}",
            name="a,b,c node with spaces",  # commas and spaces must not reach tags
            statusMessage="RateLimitError: " + ("x" * 5_000),
            output={"trace": "y" * 50_000},
        )
        for i in range(3)
    ]
    group = group_observations(observations, ALL_MODES)[0]
    payload = to_memory_payload(group, "https://cloud.langfuse.com")

    assert len(payload["title"]) <= 100
    assert len(payload["content"]) <= 10_000
    assert len(payload["tags"]) <= 20
    assert all("," not in tag for tag in payload["tags"])
    assert all(len(tag) <= 64 for tag in payload["tags"])
    assert len(payload["source_ref"]) <= 512
    assert 0.0 <= payload["confidence"] <= 1.0


def test_payload_uses_langfuse_source_and_imported_provenance():
    group = group_observations([observation()], ALL_MODES)[0]
    payload = to_memory_payload(group, "https://cloud.langfuse.com")

    # `source` is deliberately open (constants.SourceType) and names the writer,
    # matching how map_mem0 stamps "mem0". `imported` is the only provenance
    # that preserves the source timestamps.
    assert payload["source"] == "langfuse"
    assert payload["provenance"] == "imported"
    assert payload["type"] == "error"
    assert payload["created_at"] == group.first_seen


def test_payload_links_back_to_the_langfuse_trace():
    group = group_observations([observation()], ALL_MODES)[0]
    payload = to_memory_payload(group, "https://cloud.langfuse.com")

    assert payload["source_ref"] == (
        "https://cloud.langfuse.com/project/proj-1/traces/trace-1"
    )


def test_payload_carries_signature_and_count_for_reconciliation():
    group = group_observations([observation(), observation(id="obs-2")], ALL_MODES)[0]
    payload = to_memory_payload(group, "https://cloud.langfuse.com")

    assert payload["signature"] == group.signature
    assert payload["occurrences"] == 2


def test_threshold_modes_get_distinct_self_describing_titles():
    """Two modes on one operation must not produce two identical titles."""
    from memanto.cli.migrate.langfuse_rules import CaptureConfig as CC

    slow_obs = observation(
        level="DEFAULT",
        startTime="2026-08-01T12:00:00Z",
        endTime="2026-08-01T12:00:45Z",
    )
    costly_obs = observation(id="c", level="DEFAULT", costDetails={"total": 9.0})

    slow = to_memory_payload(
        group_observations([slow_obs], CC(modes=frozenset({"slow"}), latency_ms=1))[0],
        "https://x",
    )
    costly = to_memory_payload(
        group_observations([costly_obs], CC(modes=frozenset({"costly"}), cost_usd=1))[
            0
        ],
        "https://x",
    )

    assert slow["title"] != costly["title"]
    assert slow["title"].startswith("Slow: summarize_node")
    assert costly["title"].startswith("Costly: summarize_node")
    # The model belongs in the title as a qualifier, not as the subject.
    assert "claude-opus-5" in slow["title"]


def test_error_titles_still_lead_with_the_fault():
    payload = to_memory_payload(
        group_observations([observation()], ALL_MODES)[0], "https://x"
    )
    assert payload["title"] == "RateLimitError in summarize_node"


def test_capture_mode_maps_to_memory_type():
    config = CaptureConfig(modes=frozenset({"slow"}), latency_ms=1_000)
    slow = observation(
        level="DEFAULT",
        startTime="2026-08-01T12:00:00Z",
        endTime="2026-08-01T12:00:45Z",
    )
    group = group_observations([slow], config)[0]

    assert to_memory_payload(group, "https://cloud.langfuse.com")["type"] == (
        "observation"
    )


# --------------------------------------------------------------------------
# End-to-end mapping
# --------------------------------------------------------------------------


def test_group_by_pins_grouping_to_a_field_the_user_controls():
    """The escape hatch for projects whose messages don't normalize well."""
    config = CaptureConfig(modes=frozenset({"errors"}), group_by="metadata.error_code")
    observations = [
        observation(
            id=f"o{i}",
            statusMessage=f"totally unique text {i} with no shared shape",
            metadata={"error_code": "E_QUOTA"},
        )
        for i in range(50)
    ]

    groups = group_observations(observations, config)

    assert len(groups) == 1
    assert groups[0].label == "E_QUOTA"
    assert groups[0].count == 50


def test_group_by_falls_back_when_the_field_is_missing():
    config = CaptureConfig(modes=frozenset({"errors"}), group_by="metadata.error_code")
    groups = group_observations([observation()], config)

    assert len(groups) == 1
    assert groups[0].label == "RateLimitError"


def test_high_cardinality_grouping_is_reported():
    from memanto.cli.migrate.langfuse_rules import cardinality_warning

    assert cardinality_warning(100, 90) is not None
    assert cardinality_warning(1000, 3) is None
    # Too few rows to judge.
    assert cardinality_warning(5, 5) is None


def test_volatile_fragments_that_would_fork_signatures_are_normalized():
    volatile = [
        "Failed for user alice@corp.com",
        "Failed for user bob@other.org",
    ]
    sigs = {signature_for(observation(statusMessage=m), "errors")[0] for m in volatile}
    assert len(sigs) == 1

    ips = {
        signature_for(observation(statusMessage=f"refused by {ip}"), "errors")[0]
        for ip in ("10.0.0.1", "192.168.44.9")
    }
    assert len(ips) == 1


def test_build_rows_maps_an_export_with_the_callers_config():
    export = {
        "api_base": "https://self-hosted.example.com",
        "summary": {"capture_modes": ["errors"]},
        "observations": [
            observation(id="a"),
            observation(id="b", level="DEFAULT"),  # not captured
        ],
        "scores": [],
    }

    rows = build_rows(export, CaptureConfig(modes=frozenset({"errors"})))

    assert len(rows) == 1
    assert rows[0]["source_ref"].startswith("https://self-hosted.example.com")


def test_build_rows_on_an_empty_export():
    empty = {"observations": [], "scores": [], "summary": {}}
    assert build_rows(empty, CaptureConfig(modes=frozenset({"errors"}))) == []
