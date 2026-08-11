"""
Langfuse -> Memanto capture rules: filter, group, and shape.

Single source of truth for *which* Langfuse observations become memories and
*what* those memories look like. Both the one-shot sync (``memanto migrate
langfuse``, via ``mappers.map_langfuse``) and the UI's migrate tile import from
here, so a memory reads the same no matter which path wrote it.

The central rule is **one memory per signature, not per occurrence**. Memanto
performs no deduplication on write (``memory_write_service.store_memory``), so
a single bad deploy would otherwise write thousands of near-identical memories
and drown recall.

What Langfuse does and does not guarantee, and how that shapes this module:

* ``level`` is populated identically by every project, so ``errors`` is the
  one mode that works with zero configuration. It is the default.
* ``statusMessage`` is a **free-form string** with no template — the docs' own
  examples are sentences like "Model returned malformed output". Signatures
  therefore group on the *normalized message*, not on a parsed exception
  class; the class name is only used to give the memory a better title when
  one happens to be present.
* Score names, data types, and numeric ranges are **all user-defined**, and
  Langfuse documents no convention for whether higher is better. There is no
  threshold that would be correct for everyone, so scores are matched by
  explicit user-written rules (see ``langfuse_config.ScoreRule``).
* Latency and cost budgets are project- and operation-specific. Users set
  either an absolute budget or a percentile of their own traffic; nothing is
  assumed on their behalf.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from memanto.cli.migrate.langfuse_config import (
    CAPTURE_MODES,
    ProjectConfig,
    ScoreRule,
    unconfigured_modes,
)

# Footer/title helpers are shared with the other providers' mappers so the
# `[Supporting data]` convention and the content cap stay in one place.
# `mappers` imports this module lazily inside `map_langfuse`, so importing it
# here at module level does not create a cycle.
from memanto.cli.migrate.mappers import (
    _attach_footer,
    _format_supporting_data,
    _parse_dt,
    _title_from,
)

# Most actionable first: an observation that both errored and ran slow is an
# error, not a latency anomaly.
_MODE_PRIORITY = ("errors", "low_score", "costly", "slow", "success")

_MODE_TO_MEMORY_TYPE = {
    "errors": "error",
    "low_score": "learning",
    "slow": "observation",
    "costly": "observation",
    "success": "learning",
}

_MAX_MESSAGE_CHARS = 400
_MAX_DETAIL_CHARS = 1200
_MAX_NORMALIZED_CHARS = 160
_MAX_LABEL_CHARS = 60
_MAX_SAMPLE_TRACES = 3
_MAX_TAGS = 20
_TAG_MAX_CHARS = 64

# When grouping works, a handful of signatures absorb thousands of rows. When
# it doesn't — a message shape whose volatile parts we fail to normalize — the
# ratio approaches 1 and the sync would write a memory per occurrence. We do
# not block on it, but the caller is told so it can be fixed with --group-by.
CARDINALITY_WARN_RATIO = 0.5
CARDINALITY_WARN_MIN_ROWS = 20

_ERROR_CLASS_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9_]*(?:Error|Exception|Failure|Timeout|Fault))\b"
)

# Volatile fragments stripped before hashing, so the same fault recorded a
# thousand times with different ids, users, and durations collapses to one
# signature. Order matters: broader patterns run before narrower ones.
_URL_RE = re.compile(r"https?://\S+")
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b")
_ISO_TS_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?\b")
_IP_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_PATH_RE = re.compile(r"(?:[A-Za-z]:)?(?:[\\/][\w.\-]+){2,}")
_B64_RE = re.compile(r"\b[A-Za-z0-9+/]{24,}={0,2}\b")
_HEX_RE = re.compile(r"\b0x[0-9a-fA-F]+\b|\b[0-9a-fA-F]{8,}\b")
_QUOTED_RE = re.compile(r"'[^']*'|\"[^\"]*\"")
_NUM_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_WS_RE = re.compile(r"\s+")

# Leading clause of a free-form message, used as a title when no exception
# class is present — which the Langfuse docs' own examples show is the norm.
_CLAUSE_SPLIT_RE = re.compile(r"[:.;,(\[{]|\s+-\s+")

# Moorcheh stores tags comma-joined (`core.MemoryRecord.to_moorcheh_document`),
# so a comma inside a tag corrupts filtering. Keep tags to a safe charset.
_TAG_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._=-]+")


def parse_capture_modes(values: Iterable[str] | None) -> frozenset[str]:
    """Normalize user-supplied mode names, accepting ``low-score`` for ``low_score``.

    Shared by the CLI flag and the UI tile so the two can't drift; each
    caller renders the raised ``ValueError`` in its own idiom.
    """
    modes = {
        part.strip().lower().replace("-", "_")
        for value in (values or ["errors"])
        for part in str(value).split(",")
        if part.strip()
    }
    if not modes:
        raise ValueError("At least one capture mode is required.")
    unknown = modes - set(CAPTURE_MODES)
    if unknown:
        raise ValueError(
            f"Unknown capture mode(s): {', '.join(sorted(unknown))}. "
            f"Valid: {', '.join(m.replace('_', '-') for m in CAPTURE_MODES)}"
        )
    return frozenset(modes)


@dataclass(frozen=True)
class CaptureConfig:
    """Runtime view of a project's capture settings.

    Built from a :class:`~memanto.cli.migrate.langfuse_config.ProjectConfig`;
    kept separate so the classification code has no file-format concerns.
    """

    modes: frozenset[str] = frozenset({"errors"})
    score_fail_rules: tuple[ScoreRule, ...] = ()
    score_pass_rules: tuple[ScoreRule, ...] = ()
    latency_ms: float | None = None
    latency_percentile: float | None = None
    cost_usd: float | None = None
    cost_percentile: float | None = None
    group_by: str | None = None

    def __post_init__(self) -> None:
        unknown = set(self.modes) - set(CAPTURE_MODES)
        if unknown:
            raise ValueError(
                f"Unknown capture mode(s): {sorted(unknown)}. "
                f"Valid: {', '.join(CAPTURE_MODES)}"
            )
        if not self.modes:
            raise ValueError("At least one capture mode is required.")

    def unconfigured_modes(self) -> dict[str, str]:
        """Enabled modes that cannot fire yet, and what each one needs."""
        return unconfigured_modes(
            modes=self.modes,
            score_fail_rules=self.score_fail_rules,
            score_pass_rules=self.score_pass_rules,
            latency_ms=self.latency_ms,
            latency_percentile=self.latency_percentile,
            cost_usd=self.cost_usd,
            cost_percentile=self.cost_percentile,
        )

    @classmethod
    def from_project(cls, project: ProjectConfig) -> CaptureConfig:
        return cls(
            modes=project.capture,
            score_fail_rules=tuple(project.score_fail_rules),
            score_pass_rules=tuple(project.score_pass_rules),
            latency_ms=project.latency_ms,
            latency_percentile=project.latency_percentile,
            cost_usd=project.cost_usd,
            cost_percentile=project.cost_percentile,
            group_by=project.group_by,
        )


@dataclass
class SignatureGroup:
    """One distinct failure/anomaly, plus every occurrence folded into it."""

    signature: str
    mode: str
    name: str
    label: str
    message: str = ""
    detail: str = ""
    count: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    trace_ids: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    environments: list[str] = field(default_factory=list)
    total_cost: float = 0.0
    max_latency_ms: float = 0.0
    score_names: list[str] = field(default_factory=list)
    score_values: list[Any] = field(default_factory=list)
    project_id: str | None = None


# --------------------------------------------------------------------------
# Field extraction
# --------------------------------------------------------------------------


def _as_text(value: Any) -> str:
    """Flatten an observation input/output field to searchable text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def error_text(obs: dict[str, Any]) -> str:
    """The most error-bearing text on an observation."""
    for key in ("statusMessage", "output", "input"):
        text = _as_text(obs.get(key))
        if text:
            return text
    return ""


def error_class(text: str) -> str | None:
    """Extract an exception class name (``RateLimitError``) from *text*."""
    match = _ERROR_CLASS_RE.search(text or "")
    return match.group(1) if match else None


def normalize_message(text: str) -> str:
    """Strip volatile fragments so repeat occurrences hash identically."""
    normalized = text or ""
    normalized = _URL_RE.sub("<url>", normalized)
    normalized = _EMAIL_RE.sub("<email>", normalized)
    normalized = _ISO_TS_RE.sub("<ts>", normalized)
    normalized = _UUID_RE.sub("<uuid>", normalized)
    normalized = _IP_RE.sub("<ip>", normalized)
    normalized = _PATH_RE.sub("<path>", normalized)
    normalized = _B64_RE.sub("<token>", normalized)
    normalized = _HEX_RE.sub("<hex>", normalized)
    normalized = _QUOTED_RE.sub("<str>", normalized)
    normalized = _NUM_RE.sub("<n>", normalized)
    normalized = _WS_RE.sub(" ", normalized).strip()
    return normalized[:_MAX_NORMALIZED_CHARS]


def derive_label(text: str) -> str:
    """A short human label for a fault, used as the memory title.

    Prefers an exception class when the message carries one. Most messages
    don't — Langfuse's ``statusMessage`` is free-form prose — so the fallback
    is the leading clause of the normalized message, which turns "Model
    returned malformed output" into a usable title instead of a generic one.
    """
    cls = error_class(text)
    if cls:
        return cls

    normalized = normalize_message(text)
    if not normalized:
        return "Unlabelled failure"

    clause = _CLAUSE_SPLIT_RE.split(normalized, maxsplit=1)[0].strip()
    if not clause:
        clause = normalized
    if len(clause) > _MAX_LABEL_CHARS:
        clause = clause[: _MAX_LABEL_CHARS - 3].rstrip() + "..."
    return clause


def latency_ms(obs: dict[str, Any]) -> float:
    """Observation duration in milliseconds.

    Derived from ``startTime``/``endTime`` when both are present, which is
    unambiguous. The ``latency`` field is only a fallback and is read as
    seconds, matching Langfuse's documented unit for observation latency.
    """
    start = _parse_dt(obs.get("startTime"))
    end = _parse_dt(obs.get("endTime"))
    if start and end and end >= start:
        return (end - start).total_seconds() * 1000.0

    raw = obs.get("latency")
    if isinstance(raw, (int, float)):
        return float(raw) * 1000.0
    return 0.0


def cost_usd(obs: dict[str, Any]) -> float:
    """Total cost of an observation in USD.

    Returns 0.0 when the project has no cost data — self-hosted deployments
    without model pricing, and non-LLM spans, simply don't carry it. Callers
    check ``has_cost_data`` before enabling a cost budget so this doesn't look
    like "nothing was expensive".
    """
    details = obs.get("costDetails")
    if isinstance(details, dict):
        total = details.get("total")
        if isinstance(total, (int, float)):
            return float(total)
        return float(sum(v for v in details.values() if isinstance(v, (int, float))))
    return 0.0


def has_cost_data(observations: list[dict[str, Any]]) -> bool:
    """Whether any observation carries cost information at all."""
    return any(cost_usd(obs) > 0 for obs in observations if isinstance(obs, dict))


def _model_of(obs: dict[str, Any]) -> str | None:
    for key in ("providedModelName", "model"):
        value = obs.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _operation_name(obs: dict[str, Any]) -> str:
    for key in ("name", "traceName", "type"):
        value = obs.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "unknown"


def _dig(obs: dict[str, Any], dotted: str) -> Any:
    """Read a dotted path such as ``metadata.error_code`` off an observation."""
    node: Any = obs
    for part in dotted.split("."):
        if isinstance(node, dict):
            node = node.get(part)
        else:
            return None
    return node


# --------------------------------------------------------------------------
# Percentile baselines
# --------------------------------------------------------------------------


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile of *values*."""
    if not values:
        return 0.0
    ordered = sorted(values)
    pct = min(100.0, max(0.0, pct))
    rank = math.ceil(pct / 100.0 * len(ordered))
    return ordered[max(0, min(len(ordered) - 1, rank - 1))]


def build_baselines(
    observations: list[dict[str, Any]], config: CaptureConfig
) -> dict[str, dict[str, float]]:
    """Per-operation latency/cost cutoffs derived from the pulled window.

    A percentile budget compares each observation against its *own* operation's
    distribution, so "slow" means slow for that step rather than slow against a
    number Memanto invented. Operations with too few samples are skipped —
    a p95 over three rows is noise.
    """
    if config.latency_percentile is None and config.cost_percentile is None:
        return {}

    by_op: dict[str, dict[str, list[float]]] = {}
    for obs in observations:
        if not isinstance(obs, dict):
            continue
        bucket = by_op.setdefault(_operation_name(obs), {"latency": [], "cost": []})
        bucket["latency"].append(latency_ms(obs))
        bucket["cost"].append(cost_usd(obs))

    baselines: dict[str, dict[str, float]] = {}
    for name, samples in by_op.items():
        if len(samples["latency"]) < 5:
            continue
        cutoffs: dict[str, float] = {}
        if config.latency_percentile is not None:
            cutoffs["latency_ms"] = percentile(
                samples["latency"], config.latency_percentile
            )
        if config.cost_percentile is not None:
            cutoffs["cost_usd"] = percentile(samples["cost"], config.cost_percentile)
        if cutoffs:
            baselines[name] = cutoffs
    return baselines


def _budget(
    obs: dict[str, Any],
    config: CaptureConfig,
    baselines: dict[str, dict[str, float]],
    kind: str,
) -> float | None:
    """The cutoff this observation must exceed, or ``None`` if unconfigured."""
    absolute = config.latency_ms if kind == "latency_ms" else config.cost_usd
    if absolute is not None:
        return absolute
    return baselines.get(_operation_name(obs), {}).get(kind)


# --------------------------------------------------------------------------
# Classification and signatures
# --------------------------------------------------------------------------


def score_trace_id(score: dict[str, Any]) -> str | None:
    """The trace a score is attached to.

    v3 scores carry their linkage as ``subject: {kind, id}`` — a score can be
    attached to a trace, an observation, a session, or a dataset run, and only
    trace-scoped ones can be mapped onto observations here. The flat
    ``traceId`` fallback covers hand-written exports.
    """
    subject = score.get("subject")
    if isinstance(subject, dict) and subject.get("kind") == "trace":
        trace_id = subject.get("id")
        if isinstance(trace_id, str) and trace_id:
            return trace_id

    trace_id = score.get("traceId")
    return trace_id if isinstance(trace_id, str) and trace_id else None


def score_modes_by_trace(
    scores: list[dict[str, Any]], config: CaptureConfig
) -> dict[str, dict[str, Any]]:
    """Map traceId -> the score that qualified its trace for capture.

    Matching is entirely rule-driven. Langfuse documents no direction
    convention for scores, so a trace is only a failure or a success because
    the user wrote a rule saying which of its scores means what.
    """
    by_trace: dict[str, dict[str, Any]] = {}
    if not config.score_fail_rules and not config.score_pass_rules:
        return by_trace

    for score in scores:
        if not isinstance(score, dict):
            continue
        trace_id = score_trace_id(score)
        if trace_id is None:
            continue

        mode: str | None = None
        if "low_score" in config.modes and any(
            rule.matches(score) for rule in config.score_fail_rules
        ):
            mode = "low_score"
        elif "success" in config.modes and any(
            rule.matches(score) for rule in config.score_pass_rules
        ):
            mode = "success"
        if mode is None:
            continue

        # A trace matching both keeps the higher-priority (failure) verdict.
        existing = by_trace.get(trace_id)
        if existing and _MODE_PRIORITY.index(
            str(existing.get("capture_mode"))
        ) <= _MODE_PRIORITY.index(mode):
            continue
        by_trace[trace_id] = {**score, "capture_mode": mode}
    return by_trace


def classify(
    obs: dict[str, Any],
    config: CaptureConfig,
    trace_scores: dict[str, dict[str, Any]] | None = None,
    baselines: dict[str, dict[str, float]] | None = None,
) -> str | None:
    """Return the capture mode an observation qualifies for, or ``None``."""
    trace_scores = trace_scores or {}
    baselines = baselines or {}

    if "errors" in config.modes and str(obs.get("level") or "").upper() == "ERROR":
        return "errors"

    trace_id = obs.get("traceId")
    scored = trace_scores.get(trace_id) if isinstance(trace_id, str) else None
    scored_mode = str(scored.get("capture_mode")) if scored else None
    if scored_mode == "low_score":
        return "low_score"

    if "costly" in config.modes:
        budget = _budget(obs, config, baselines, "cost_usd")
        if budget is not None and cost_usd(obs) > budget:
            return "costly"
    if "slow" in config.modes:
        budget = _budget(obs, config, baselines, "latency_ms")
        if budget is not None and latency_ms(obs) > budget:
            return "slow"

    if scored_mode == "success":
        return "success"
    return None


def signature_for(
    obs: dict[str, Any], mode: str, config: CaptureConfig | None = None
) -> tuple[str, str]:
    """Return ``(signature, label)`` for an observation in *mode*.

    Errors group on the normalized message — free-form text with its volatile
    parts removed — because ``statusMessage`` follows no template. Threshold
    modes group by operation, since the interesting unit there is "this step is
    slow/expensive", not the payload.

    ``group_by`` overrides all of it: when a project stamps a stable field such
    as ``metadata.error_code``, grouping on that beats any text heuristic.
    """
    name = _operation_name(obs)

    if config is not None and config.group_by:
        pinned = _dig(obs, config.group_by)
        if pinned not in (None, ""):
            label = str(pinned)[:_MAX_LABEL_CHARS]
            key = f"{mode}|{name}|{config.group_by}={pinned}"
            return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12], label

    if mode == "errors":
        text = error_text(obs)
        label = derive_label(text)
        key = f"{mode}|{name}|{normalize_message(text)}"
    else:
        label = _model_of(obs) or name
        key = f"{mode}|{name}|{label}"

    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12], label


def _remember(bucket: list[Any], value: Any, limit: int = 5) -> None:
    if value not in (None, "") and value not in bucket and len(bucket) < limit:
        bucket.append(value)


def group_observations(
    observations: list[dict[str, Any]],
    config: CaptureConfig,
    scores: list[dict[str, Any]] | None = None,
) -> list[SignatureGroup]:
    """Fold observations into one :class:`SignatureGroup` per distinct signal."""
    trace_scores = score_modes_by_trace(scores or [], config)
    baselines = build_baselines(observations, config)
    groups: dict[str, SignatureGroup] = {}

    for obs in observations:
        if not isinstance(obs, dict):
            continue
        mode = classify(obs, config, trace_scores, baselines)
        if mode is None:
            continue

        signature, label = signature_for(obs, mode, config)
        group = groups.get(signature)
        if group is None:
            group = SignatureGroup(
                signature=signature,
                mode=mode,
                name=_operation_name(obs),
                label=label,
            )
            groups[signature] = group

        group.count += 1

        start = _parse_dt(obs.get("startTime"))
        if start:
            if group.first_seen is None or start < group.first_seen:
                group.first_seen = start
            if group.last_seen is None or start > group.last_seen:
                group.last_seen = start

        _remember(group.trace_ids, obs.get("traceId"), _MAX_SAMPLE_TRACES)
        _remember(group.models, _model_of(obs))
        _remember(group.environments, obs.get("environment"))

        group.total_cost += cost_usd(obs)
        group.max_latency_ms = max(group.max_latency_ms, latency_ms(obs))
        if group.project_id is None and isinstance(obs.get("projectId"), str):
            group.project_id = obs["projectId"]

        # Keep the first non-empty message/detail as the representative sample.
        if not group.message:
            group.message = _as_text(obs.get("statusMessage"))[:_MAX_MESSAGE_CHARS]
        if not group.detail:
            group.detail = _as_text(obs.get("output"))[:_MAX_DETAIL_CHARS]

        trace_id = obs.get("traceId")
        scored = trace_scores.get(trace_id) if isinstance(trace_id, str) else None
        if scored:
            _remember(group.score_names, scored.get("name"))
            value = scored.get("value")
            if value is not None and len(group.score_values) < 5:
                group.score_values.append(
                    round(float(value), 4)
                    if isinstance(value, (int, float))
                    else str(value)
                )

    # Loudest first, so a truncated preview shows what matters.
    return sorted(groups.values(), key=lambda g: g.count, reverse=True)


def cardinality_warning(observations_matched: int, signature_count: int) -> str | None:
    """Warn when grouping barely collapsed anything.

    Not fatal: a project really can have many distinct one-off faults. But a
    ratio near 1 usually means a message shape whose volatile parts survived
    normalization, and the fix is ``--group-by <field>``.
    """
    if signature_count < CARDINALITY_WARN_MIN_ROWS or observations_matched <= 0:
        return None
    ratio = signature_count / observations_matched
    if ratio < CARDINALITY_WARN_RATIO:
        return None
    return (
        f"{signature_count} signatures from {observations_matched} matched "
        f"observations ({ratio:.0%}) — grouping barely collapsed anything, so "
        f"this sync will write a lot of near-duplicate memories. If these "
        f"messages embed varying values, pin grouping to a stable field with "
        f"--group-by (e.g. --group-by metadata.error_code)."
    )


# --------------------------------------------------------------------------
# Memory payload
# --------------------------------------------------------------------------


def confidence_for(count: int) -> float:
    """Confidence rises with recurrence: 1x -> 0.60, 10x -> 0.75, 100x -> 0.90."""
    return round(min(0.95, 0.60 + 0.15 * math.log10(max(count, 1))), 2)


def _tag(raw: Any) -> str | None:
    text = _TAG_UNSAFE_RE.sub("-", str(raw or "").strip()).strip("-")
    return text[:_TAG_MAX_CHARS] or None


def trace_url(host: str, group: SignatureGroup) -> str | None:
    """Canonical Langfuse URL for a representative trace of this group."""
    if not group.trace_ids:
        return None
    base = (host or "").rstrip("/")
    trace_id = group.trace_ids[0]
    if group.project_id:
        return f"{base}/project/{group.project_id}/traces/{trace_id}"[:512]
    return f"{base}/trace/{trace_id}"[:512]


def _title_for(group: SignatureGroup) -> str:
    """A self-describing memory title.

    Errors lead with the fault. Threshold modes lead with *what happened* —
    naming the model there would bury the point, and two modes hitting the
    same operation would produce two memories with identical titles.
    """
    if group.mode == "errors":
        return _title_from(f"{group.label} in {group.name}")

    prefix = {
        "slow": "Slow",
        "costly": "Costly",
        "low_score": "Failed eval",
        "success": "Worked well",
    }[group.mode]
    model = group.models[0] if group.models else None
    suffix = f" ({model})" if model else ""
    return _title_from(f"{prefix}: {group.name}{suffix}")


def _headline(group: SignatureGroup) -> str:
    plural = "s" if group.count != 1 else ""
    if group.mode == "errors":
        return (
            f"Langfuse recorded {group.count} failing '{group.name}' "
            f"observation{plural}: {group.label}."
        )
    if group.mode == "low_score":
        return (
            f"'{group.name}' was scored as a failure in {group.count} "
            f"observation{plural}."
        )
    if group.mode == "costly":
        return (
            f"'{group.name}' exceeded the cost budget in {group.count} "
            f"observation{plural} (${group.total_cost:.4f} total)."
        )
    if group.mode == "slow":
        return (
            f"'{group.name}' exceeded the latency budget in {group.count} "
            f"observation{plural} (peak {group.max_latency_ms:.0f} ms)."
        )
    return (
        f"'{group.name}' was scored as a success in {group.count} observation{plural}."
    )


def to_memory_payload(group: SignatureGroup, host: str) -> dict[str, Any]:
    """Shape one group into a ``SdkClient.batch_remember`` item.

    ``signature`` and ``occurrences`` ride along for reconciliation and for
    the dry-run preview; ``batch_remember`` reads only the keys it knows, so
    the extras are inert on write.
    """
    body = [_headline(group)]
    if group.message and group.message not in body[0]:
        body.append(group.message)

    if group.first_seen and group.last_seen and group.count > 1:
        body.append(
            f"Seen {group.count}x between {group.first_seen.isoformat()} "
            f"and {group.last_seen.isoformat()}."
        )

    if group.detail:
        body.append(f"Representative output:\n{group.detail}")

    footer = _format_supporting_data(
        [
            ("Signature", f"langfuse:{group.signature}"),
            ("Capture mode", group.mode),
            ("Operation", group.name),
            ("Occurrences", group.count),
            ("Models", group.models),
            ("Environments", group.environments),
            ("Peak latency (ms)", round(group.max_latency_ms) or None),
            ("Total cost (USD)", round(group.total_cost, 6) or None),
            ("Scores", group.score_names),
            ("Score values", group.score_values),
            ("Sample traces", group.trace_ids),
            (
                "First seen",
                group.first_seen.isoformat() if group.first_seen else None,
            ),
            ("Last seen", group.last_seen.isoformat() if group.last_seen else None),
        ]
    )

    content = _attach_footer("\n\n".join(part for part in body if part), footer)

    tags: list[str] = []
    for raw in (
        "langfuse",
        f"capture={group.mode}",
        f"sig={group.signature}",
        f"op={group.name}",
    ):
        tag = _tag(raw)
        if tag:
            tags.append(tag)
    for model in group.models[:2]:
        tag = _tag(f"model={model}")
        if tag:
            tags.append(tag)
    for env in group.environments[:2]:
        tag = _tag(f"env={env}")
        if tag:
            tags.append(tag)

    return {
        "title": _title_for(group),
        "content": content,
        "type": _MODE_TO_MEMORY_TYPE[group.mode],
        "tags": list(dict.fromkeys(tags))[:_MAX_TAGS],
        "confidence": confidence_for(group.count),
        "source": "langfuse",
        "source_ref": trace_url(host, group),
        "provenance": "imported",
        "created_at": group.first_seen,
        "updated_at": datetime.now(timezone.utc),
        "signature": group.signature,
        "occurrences": group.count,
    }


def build_rows(export: dict[str, Any], config: CaptureConfig) -> list[dict[str, Any]]:
    """Map a Langfuse export dict onto grouped Memanto memory payloads."""
    host = str(export.get("api_base") or "https://cloud.langfuse.com")
    groups = group_observations(
        export.get("observations") or [],
        config,
        export.get("scores") or [],
    )
    return [to_memory_payload(group, host) for group in groups]
