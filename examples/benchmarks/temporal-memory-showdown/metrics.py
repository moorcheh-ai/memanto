"""Deterministic scoring and statistics for the memory benchmark."""

from __future__ import annotations

import math
import random
import re
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from statistics import mean

import tiktoken
from dataset import QueryCase

_ENCODING = tiktoken.get_encoding("cl100k_base")


@dataclass(frozen=True)
class QueryScore:
    query_id: str
    category: str
    coverage: float
    stale_leak: bool
    exact: bool
    matched_required: int
    required_total: int
    matched_forbidden: int

    def to_dict(self) -> dict:
        return asdict(self)


def count_tokens(text: str) -> int:
    return len(_ENCODING.encode(text))


def percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be between 0 and 1")
    ordered = sorted(values)
    rank = max(1, math.ceil(quantile * len(ordered)))
    return ordered[min(rank - 1, len(ordered) - 1)]


def normalize(text: str) -> str:
    lowered = text.casefold()
    return re.sub(r"\s+", " ", lowered).strip()


def _group_matches(text: str, aliases: Iterable[str]) -> bool:
    return any(normalize(alias) in text for alias in aliases)


def score_query(case: QueryCase, retrieved_text: str) -> QueryScore:
    normalized = normalize(retrieved_text)
    required_hits = sum(
        _group_matches(normalized, aliases) for aliases in case.required
    )
    forbidden_hits = sum(
        _group_matches(normalized, aliases) for aliases in case.forbidden
    )
    coverage = required_hits / len(case.required)
    stale_leak = forbidden_hits > 0
    return QueryScore(
        query_id=case.query_id,
        category=case.category,
        coverage=round(coverage, 6),
        stale_leak=stale_leak,
        exact=coverage == 1.0 and not stale_leak,
        matched_required=required_hits,
        required_total=len(case.required),
        matched_forbidden=forbidden_hits,
    )


def summarize_scores(scores: Sequence[QueryScore]) -> dict:
    if not scores:
        return {
            "mean_coverage": 0.0,
            "exact_accuracy": 0.0,
            "stale_leak_rate": 0.0,
            "by_category": {},
        }

    by_category: dict[str, list[QueryScore]] = {}
    for score in scores:
        by_category.setdefault(score.category, []).append(score)

    return {
        "mean_coverage": round(mean(s.coverage for s in scores), 6),
        "exact_accuracy": round(mean(float(s.exact) for s in scores), 6),
        "stale_leak_rate": round(mean(float(s.stale_leak) for s in scores), 6),
        "by_category": {
            category: {
                "mean_coverage": round(mean(s.coverage for s in rows), 6),
                "exact_accuracy": round(mean(float(s.exact) for s in rows), 6),
                "stale_leak_rate": round(mean(float(s.stale_leak) for s in rows), 6),
                "queries": len(rows),
            }
            for category, rows in sorted(by_category.items())
        },
    }


def paired_bootstrap_delta(
    baseline: Sequence[QueryScore],
    challenger: Sequence[QueryScore],
    *,
    samples: int = 5000,
    seed: int = 639,
) -> dict:
    if len(baseline) != len(challenger) or not baseline:
        raise ValueError("Paired bootstrap requires equal non-empty score lists")
    rng = random.Random(seed)
    deltas: list[float] = []
    count = len(baseline)
    for _ in range(samples):
        indices = [rng.randrange(count) for _ in range(count)]
        baseline_mean = mean(baseline[i].coverage for i in indices)
        challenger_mean = mean(challenger[i].coverage for i in indices)
        deltas.append(challenger_mean - baseline_mean)

    ordered = sorted(deltas)
    lower = ordered[max(0, math.floor(0.025 * samples))]
    upper = ordered[min(samples - 1, math.ceil(0.975 * samples) - 1)]
    observed = mean(s.coverage for s in challenger) - mean(s.coverage for s in baseline)
    return {
        "observed_delta": round(observed, 6),
        "ci95": [round(lower, 6), round(upper, 6)],
        "samples": samples,
        "seed": seed,
    }
