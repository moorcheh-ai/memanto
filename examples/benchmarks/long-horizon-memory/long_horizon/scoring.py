"""Framework-neutral retrieval scoring and statistical summaries."""

from __future__ import annotations

import math
import random
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .dataset import Probe

_MARKER = re.compile(r"CANONICAL\[([a-z_]+)=([^\]]+)\]")


@dataclass(frozen=True)
class RetrievedItem:
    """Backend-neutral ranked retrieval result."""

    text: str
    rank: int
    score: float | None = None


@dataclass(frozen=True)
class ProbeScore:
    """Deterministic quality and context-footprint metrics for one probe."""

    top1_correct: bool
    current_recalled: bool
    strict_correct: bool
    stale_conflict: bool
    current_rank: int | None
    reciprocal_rank: float
    retrieved_tokens: int
    signal_tokens: int
    signal_to_noise: float


def parse_markers(text: str) -> set[tuple[str, str]]:
    """Extract canonical fact markers from retrieved text."""

    return {(key, value) for key, value in _MARKER.findall(text)}


def score_probe(
    probe: Probe,
    items: Sequence[RetrievedItem],
    token_counter: Callable[[str], int],
) -> ProbeScore:
    """Score one ranked result list against a probe's current and stale values."""

    expected = (probe.fact_key, probe.expected_value)
    stale = {(probe.fact_key, value) for value in probe.stale_values}
    current_rank: int | None = None
    stale_conflict = False
    total_tokens = 0
    signal_tokens = 0

    for item in items:
        markers = parse_markers(item.text)
        tokens = token_counter(item.text)
        total_tokens += tokens
        if expected in markers:
            signal_tokens += tokens
            if current_rank is None:
                current_rank = item.rank
        if markers & stale:
            stale_conflict = True

    current_recalled = current_rank is not None
    return ProbeScore(
        top1_correct=current_rank == 1,
        current_recalled=current_recalled,
        strict_correct=current_recalled and not stale_conflict,
        stale_conflict=stale_conflict,
        current_rank=current_rank,
        reciprocal_rank=0.0 if current_rank is None else 1.0 / current_rank,
        retrieved_tokens=total_tokens,
        signal_tokens=signal_tokens,
        signal_to_noise=0.0 if total_tokens == 0 else signal_tokens / total_tokens,
    )


def percentile(values: Sequence[float], percentage: float) -> float:
    """Calculate a linearly interpolated percentile."""

    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * percentage / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    fraction = position - lower
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction)


def bootstrap_mean_ci(
    values: Sequence[float],
    *,
    confidence: float = 0.95,
    samples: int = 4000,
    seed: int = 20260606,
) -> tuple[float, float]:
    """Return a deterministic percentile-bootstrap interval for a mean."""

    if not values:
        return (0.0, 0.0)
    if len(values) == 1:
        value = float(values[0])
        return (value, value)
    rng = random.Random(seed)
    means = []
    for _ in range(samples):
        draw = [values[rng.randrange(len(values))] for _ in values]
        means.append(sum(draw) / len(draw))
    tail = (1.0 - confidence) / 2.0
    return (
        percentile(means, tail * 100.0),
        percentile(means, (1.0 - tail) * 100.0),
    )
