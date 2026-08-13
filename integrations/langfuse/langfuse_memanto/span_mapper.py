"""
Translate a finished OpenTelemetry span into the observation shape Memanto's
Langfuse rules already understand.

Langfuse's Python SDK (v3+) is built on OpenTelemetry and writes its own data
onto span attributes under the ``langfuse.observation.*`` namespace. That means
a plain ``SpanProcessor`` sees everything the public API would later return —
level, status message, model, cost, input/output — without calling Langfuse at
all.

Mapping those spans back onto the *same dict shape* the public API returns is
what lets ``memanto.cli.migrate.langfuse_rules`` be reused verbatim: the live
handler and ``memanto migrate langfuse`` then produce byte-identical memories
for the same failure, and there is exactly one place where grouping rules live.

Attribute names are read from ``langfuse.LangfuseOtelSpanAttributes`` when the
SDK is installed, and fall back to the literal strings otherwise — this package
does not depend on ``langfuse``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

# Verified against langfuse 4.14.3 / opentelemetry-sdk 1.44.0.
_ATTR_DEFAULTS = {
    "LEVEL": "langfuse.observation.level",
    "STATUS_MESSAGE": "langfuse.observation.status_message",
    "TYPE": "langfuse.observation.type",
    "MODEL": "langfuse.observation.model.name",
    "COST_DETAILS": "langfuse.observation.cost_details",
    "USAGE_DETAILS": "langfuse.observation.usage_details",
    "INPUT": "langfuse.observation.input",
    "OUTPUT": "langfuse.observation.output",
    "METADATA": "langfuse.observation.metadata",
    "ENVIRONMENT": "langfuse.environment",
}


def _resolve_attribute_names() -> dict[str, str]:
    """Prefer the SDK's own constants so a rename can't silently break us."""
    names = dict(_ATTR_DEFAULTS)
    try:
        from langfuse import LangfuseOtelSpanAttributes as A  # type: ignore
    except Exception:
        return names

    for key, const in (
        ("LEVEL", "OBSERVATION_LEVEL"),
        ("STATUS_MESSAGE", "OBSERVATION_STATUS_MESSAGE"),
        ("TYPE", "OBSERVATION_TYPE"),
        ("MODEL", "OBSERVATION_MODEL"),
        ("COST_DETAILS", "OBSERVATION_COST_DETAILS"),
        ("USAGE_DETAILS", "OBSERVATION_USAGE_DETAILS"),
        ("INPUT", "OBSERVATION_INPUT"),
        ("OUTPUT", "OBSERVATION_OUTPUT"),
        ("METADATA", "OBSERVATION_METADATA"),
        ("ENVIRONMENT", "ENVIRONMENT"),
    ):
        value = getattr(A, const, None)
        if isinstance(value, str) and value:
            names[key] = value
    return names


ATTRS = _resolve_attribute_names()


def _iso_from_ns(nanoseconds: int | None) -> str | None:
    """OTel timestamps are nanoseconds since the epoch; the API returns ISO."""
    if not nanoseconds:
        return None
    return datetime.fromtimestamp(nanoseconds / 1e9, tz=timezone.utc).isoformat()


def _maybe_json(value: Any) -> Any:
    """Span attributes are scalars, so dicts arrive JSON-encoded."""
    if isinstance(value, str) and value.startswith(("{", "[")):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
    return value


def _is_error(span: Any, level: Any) -> bool:
    """Whether the span failed.

    Langfuse sets its own ``level`` attribute, but a span can also carry only
    OTel's status — for instance when another instrumentation library recorded
    the error — so both are honoured.
    """
    if isinstance(level, str) and level.upper() == "ERROR":
        return True
    status = getattr(span, "status", None)
    code = getattr(getattr(status, "status_code", None), "name", "")
    return str(code).upper() == "ERROR"


def _exception_text(span: Any) -> str | None:
    """Message from a recorded exception event, when there is one."""
    for event in getattr(span, "events", None) or []:
        if getattr(event, "name", "") != "exception":
            continue
        attributes = getattr(event, "attributes", None) or {}
        kind = attributes.get("exception.type")
        message = attributes.get("exception.message")
        if kind and message:
            return f"{kind}: {message}"
        if message:
            return str(message)
    return None


def span_to_observation(span: Any) -> dict[str, Any] | None:
    """Map a finished span onto a Langfuse-API-shaped observation dict.

    Returns ``None`` for spans with no usable identity, which the handler
    skips. Never raises: this runs inside the application's tracing path.
    """
    try:
        context = (
            getattr(span, "context", None)
            or getattr(span, "get_span_context", lambda: None)()
        )
        if context is None:
            return None

        attributes = dict(getattr(span, "attributes", None) or {})
        level = attributes.get(ATTRS["LEVEL"])

        status = getattr(span, "status", None)
        status_message = (
            attributes.get(ATTRS["STATUS_MESSAGE"])
            or _exception_text(span)
            or getattr(status, "description", None)
        )

        observation: dict[str, Any] = {
            "id": format(context.span_id, "016x"),
            "traceId": format(context.trace_id, "032x"),
            "name": getattr(span, "name", None) or "unknown",
            "type": attributes.get(ATTRS["TYPE"]),
            "level": "ERROR" if _is_error(span, level) else (level or "DEFAULT"),
            "statusMessage": status_message,
            "startTime": _iso_from_ns(getattr(span, "start_time", None)),
            "endTime": _iso_from_ns(getattr(span, "end_time", None)),
            "providedModelName": attributes.get(ATTRS["MODEL"]),
            "costDetails": _maybe_json(attributes.get(ATTRS["COST_DETAILS"])),
            "usageDetails": _maybe_json(attributes.get(ATTRS["USAGE_DETAILS"])),
            "input": _maybe_json(attributes.get(ATTRS["INPUT"])),
            "output": _maybe_json(attributes.get(ATTRS["OUTPUT"])),
            "metadata": _maybe_json(attributes.get(ATTRS["METADATA"])),
            "environment": attributes.get(ATTRS["ENVIRONMENT"]),
        }
        return {k: v for k, v in observation.items() if v is not None}
    except Exception:
        return None
