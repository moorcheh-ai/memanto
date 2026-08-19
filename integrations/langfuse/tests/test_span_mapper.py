"""Tests for OTel span -> Langfuse-API-shaped observation mapping.

The whole point of this mapping is that ``langfuse_rules`` can be reused
verbatim, so these tests pin the field names the rules read.
"""

from __future__ import annotations

import types

from conftest import make_span

from langfuse_memanto.span_mapper import span_to_observation


def test_maps_the_fields_the_rules_read():
    obs = span_to_observation(make_span())

    assert obs["name"] == "generate"
    assert obs["level"] == "ERROR"
    assert obs["statusMessage"] == "Model returned malformed output"
    assert obs["traceId"] == "0123456789abcdef0123456789abcdef"
    assert obs["id"] == "0123456789abcdef"


def test_nanosecond_timestamps_become_iso():
    """OTel counts nanoseconds; the public API returns ISO strings."""
    obs = span_to_observation(make_span())

    assert obs["startTime"].startswith("2026-")
    assert obs["startTime"].endswith("+00:00")

    from memanto.cli.migrate.langfuse_rules import latency_ms

    assert latency_ms(obs) == 1000.0  # 1s span


def test_otel_status_alone_marks_an_error():
    """Another instrumentation library may set only the OTel status."""
    span = make_span(level=None, status_message=None, status_code="ERROR")
    span.status.description = "boom"

    obs = span_to_observation(span)

    assert obs["level"] == "ERROR"
    assert obs["statusMessage"] == "boom"


def test_a_healthy_span_is_not_an_error():
    obs = span_to_observation(
        make_span(level="DEFAULT", status_message=None, status_code="OK")
    )
    assert obs["level"] == "DEFAULT"


def test_exception_events_supply_a_message():
    event = types.SimpleNamespace(
        name="exception",
        attributes={
            "exception.type": "ValueError",
            "exception.message": "bad input",
        },
    )
    span = make_span(status_message=None, events=[event])
    span.status.description = None

    obs = span_to_observation(span)

    assert obs["statusMessage"] == "ValueError: bad input"


def test_json_encoded_attributes_are_decoded():
    """Span attributes are scalars, so Langfuse JSON-encodes dicts."""
    span = make_span(
        attributes={
            "langfuse.observation.cost_details": '{"total": 0.0042}',
            # Note the `.name` suffix — verified against langfuse 4.14.3.
            "langfuse.observation.model.name": "claude-opus-5",
            "langfuse.environment": "production",
        }
    )

    obs = span_to_observation(span)

    assert obs["costDetails"] == {"total": 0.0042}
    assert obs["providedModelName"] == "claude-opus-5"
    assert obs["environment"] == "production"

    from memanto.cli.migrate.langfuse_rules import cost_usd

    assert cost_usd(obs) == 0.0042


def test_malformed_json_is_left_as_text_rather_than_crashing():
    span = make_span(attributes={"langfuse.observation.output": "{not json"})
    assert span_to_observation(span)["output"] == "{not json"


def test_a_span_without_context_is_skipped():
    span = make_span()
    span.context = None
    assert span_to_observation(span) is None


def test_mapping_never_raises_on_a_junk_object():
    """This runs inside the application's tracing path."""
    assert span_to_observation(object()) is None
    assert span_to_observation(None) is None


def test_mapped_spans_flow_through_the_shared_rules():
    """The mapping is only useful if the sync's own code accepts it."""
    from memanto.cli.migrate.langfuse_rules import (
        CaptureConfig,
        group_observations,
        to_memory_payload,
    )

    observations = [
        span_to_observation(make_span(span_id=i, status_message="Boom happened"))
        for i in range(1, 13)
    ]
    groups = group_observations(
        observations, CaptureConfig(modes=frozenset({"errors"}))
    )

    assert len(groups) == 1
    assert groups[0].count == 12
    payload = to_memory_payload(groups[0], "https://cloud.langfuse.com")
    assert payload["type"] == "error"
    assert payload["source"] == "langfuse"
    assert payload["title"] == "Boom happened in generate"
