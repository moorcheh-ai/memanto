"""
Inspect a Langfuse export so a user can choose their own capture settings.

Nothing about a Langfuse project is knowable in advance: score names and their
value ranges are user-defined, latency and cost distributions differ per
operation, and ``statusMessage`` is free-form prose. Rather than guess
thresholds on the user's behalf, this module reports what is actually in their
data — score names with observed ranges, per-operation latency and cost
percentiles, and the error labels grouping would produce — plus suggested
rules they can copy.

Consumed by ``memanto migrate langfuse --discover`` and the UI tile.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from memanto.cli.migrate.langfuse_rules import (
    cost_usd,
    derive_label,
    error_text,
    has_cost_data,
    latency_ms,
    normalize_message,
    percentile,
)

_PERCENTILES = (50, 90, 95, 99)
_MAX_OPERATIONS = 15
_MAX_ERROR_LABELS = 15
_MAX_CATEGORIES = 10


def _score_kind(values: list[Any]) -> str:
    """Infer a score's usable type from its observed values.

    Langfuse reports ``dataType``, but exports from older deployments may omit
    it, so fall back to what the values actually look like.
    """
    if not values:
        return "unknown"
    if all(isinstance(v, bool) for v in values):
        return "BOOLEAN"
    numeric = [v for v in values if isinstance(v, (int, float))]
    if len(numeric) == len(values):
        distinct = set(numeric)
        if distinct <= {0, 1} and len(distinct) <= 2:
            return "BOOLEAN"
        return "NUMERIC"
    return "CATEGORICAL"


def describe_scores(scores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per distinct score name, with the range actually observed."""
    by_name: dict[str, list[Any]] = {}
    declared: dict[str, str] = {}

    for score in scores:
        if not isinstance(score, dict):
            continue
        name = score.get("name")
        if not isinstance(name, str) or not name:
            continue
        by_name.setdefault(name, []).append(score.get("value"))
        data_type = score.get("dataType")
        if isinstance(data_type, str) and data_type:
            declared.setdefault(name, data_type.upper())

    rows: list[dict[str, Any]] = []
    for name, raw_values in sorted(by_name.items()):
        values = [v for v in raw_values if v is not None]
        kind = declared.get(name) or _score_kind(values)
        row: dict[str, Any] = {"name": name, "data_type": kind, "count": len(values)}

        numeric = [float(v) for v in values if isinstance(v, (int, float))]
        if kind in ("NUMERIC", "BOOLEAN") and numeric:
            row["min"] = round(min(numeric), 4)
            row["max"] = round(max(numeric), 4)
            row["p50"] = round(percentile(numeric, 50), 4)
        else:
            labels = Counter(str(v) for v in values)
            row["categories"] = [
                label for label, _ in labels.most_common(_MAX_CATEGORIES)
            ]

        row["suggestion"] = _suggest_rule(row)
        rows.append(row)
    return rows


def _suggest_rule(row: dict[str, Any]) -> str:
    """A copy-pasteable starting rule — direction is still the user's call.

    Branches on the data actually present, not on the declared type. A score
    Langfuse labels NUMERIC whose exported values are all strings has no
    observed range, and falling back to 0..1 would print "(observed 0..1)" for
    a range nobody ever saw — and suggest a threshold that captures nothing.
    """
    name = row["name"]
    kind = row["data_type"]
    has_range = "min" in row and "max" in row

    if kind == "BOOLEAN" and has_range:
        return f"--score-fail '{name}=false'   (or =true if this score flags a problem)"
    if kind == "NUMERIC" and has_range:
        low, high = row["min"], row["max"]
        midpoint = round(low + (high - low) * 0.6, 3)
        return (
            f"--score-fail '{name}<{midpoint}'   "
            f"(observed {low}..{high}; flip to > if higher is worse)"
        )
    categories = row.get("categories") or []
    sample = ",".join(categories[:2]) or "<label>"
    return f"--score-fail '{name} in {sample}'   (list the labels that mean failure)"


def describe_operations(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Latency and cost distribution per operation name."""
    by_op: dict[str, dict[str, list[float]]] = {}
    for obs in observations:
        if not isinstance(obs, dict):
            continue
        name = obs.get("name") or obs.get("traceName") or obs.get("type") or "unknown"
        bucket = by_op.setdefault(str(name), {"latency": [], "cost": []})
        bucket["latency"].append(latency_ms(obs))
        bucket["cost"].append(cost_usd(obs))

    rows = []
    for name, samples in by_op.items():
        row: dict[str, Any] = {"name": name, "count": len(samples["latency"])}
        for pct in _PERCENTILES:
            row[f"latency_p{pct}"] = round(percentile(samples["latency"], pct))
        row["cost_total"] = round(sum(samples["cost"]), 6)
        row["cost_p95"] = round(percentile(samples["cost"], 95), 6)
        rows.append(row)

    rows.sort(key=lambda r: r["count"], reverse=True)
    return rows[:_MAX_OPERATIONS]


def describe_errors(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The labels grouping would produce for errored observations.

    This is the honest preview of parsing quality: if these read like real
    faults, grouping is working; if they are long or nearly unique, the
    project wants ``--group-by``.
    """
    labels: Counter[str] = Counter()
    distinct_messages: set[str] = set()
    errored = 0

    for obs in observations:
        if not isinstance(obs, dict):
            continue
        if str(obs.get("level") or "").upper() != "ERROR":
            continue
        errored += 1
        text = error_text(obs)
        labels[derive_label(text)] += 1
        distinct_messages.add(normalize_message(text))

    rows = [
        {"label": label, "count": count}
        for label, count in labels.most_common(_MAX_ERROR_LABELS)
    ]
    return [
        {
            "errored_observations": errored,
            "distinct_signatures": len(distinct_messages),
            "labels": rows,
        }
    ]


def discover(export: dict[str, Any]) -> dict[str, Any]:
    """Full discovery report for one Langfuse export."""
    observations = export.get("observations") or []
    scores = export.get("scores") or []
    summary = export.get("summary") or {}
    error_info = describe_errors(observations)[0]

    notes: list[str] = []
    if not scores:
        notes.append(
            "No scores found in this window. The 'low-score' and 'success' "
            "capture modes need scores; without them they will capture nothing."
        )
    if not has_cost_data(observations):
        notes.append(
            "No cost data on any observation. The 'costly' mode will capture "
            "nothing — self-hosted Langfuse needs model pricing configured for "
            "costs to be recorded."
        )
    if error_info["errored_observations"] == 0:
        notes.append("No errored observations in this window.")
    elif error_info["distinct_signatures"] > max(
        10, error_info["errored_observations"] * 0.5
    ):
        notes.append(
            f"{error_info['distinct_signatures']} distinct error signatures from "
            f"{error_info['errored_observations']} errors — these messages do not "
            f"group well. Consider --group-by <field> to pin grouping to a stable "
            f"value your app sets."
        )

    return {
        "window": {
            "from": summary.get("from_time"),
            "to": summary.get("to_time"),
            "observation_count": len(observations),
            "score_count": len(scores),
        },
        "scores": describe_scores(scores),
        "operations": describe_operations(observations),
        "errors": error_info,
        "has_cost_data": has_cost_data(observations),
        "notes": notes,
    }
