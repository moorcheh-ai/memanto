"""Transparent golden-marker scoring and statistical helpers."""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass
from statistics import mean

from .dataset import Probe

_MARKER_RE = re.compile(r"(?:STATE|POISON)_[A-Z0-9_-]+")


@dataclass(frozen=True)
class ProbeScore:
    """Auditable metrics for a single retrieval."""

    hit: bool
    reciprocal_rank: float
    stale_exposure: bool
    poison_exposure: bool
    foreign_exposure: bool
    retrieved_tokens: int


def approximate_tokens(text: str) -> int:
    """Estimate tokens with a deterministic, dependency-free tokenizer."""

    return len(re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE))


def score_probe(probe: Probe, retrieved: list[str]) -> ProbeScore:
    """Score ranked retrieved strings against the probe's golden markers."""

    marker_sets = [set(_MARKER_RE.findall(text)) for text in retrieved]
    expected_rank = next(
        (
            rank
            for rank, markers in enumerate(marker_sets, start=1)
            if probe.expected_marker in markers
        ),
        None,
    )
    all_markers = set().union(*marker_sets) if marker_sets else set()
    return ProbeScore(
        hit=expected_rank is not None,
        reciprocal_rank=0.0 if expected_rank is None else 1.0 / expected_rank,
        stale_exposure=bool(all_markers.intersection(probe.stale_markers)),
        poison_exposure=bool(all_markers.intersection(probe.poison_markers)),
        foreign_exposure=bool(all_markers.intersection(probe.foreign_markers)),
        retrieved_tokens=sum(approximate_tokens(text) for text in retrieved),
    )


def percentile(values: list[float], percentile_value: float) -> float:
    """Return a linearly interpolated percentile."""

    if not values:
        raise ValueError("values must not be empty")
    if not 0 <= percentile_value <= 100:
        raise ValueError("percentile must be between 0 and 100")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile_value / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def paired_bootstrap_ci(
    left: list[float], right: list[float], *, seed: int, samples: int = 10_000
) -> tuple[float, float, float]:
    """Return mean paired difference and a deterministic 95% bootstrap CI."""

    if len(left) != len(right) or not left:
        raise ValueError("paired samples must be non-empty and equal length")
    if samples < 100:
        raise ValueError("samples must be at least 100")
    differences = [a - b for a, b in zip(left, right, strict=True)]
    rng = random.Random(seed)
    estimates = sorted(
        mean(rng.choice(differences) for _ in differences) for _ in range(samples)
    )
    return (
        mean(differences),
        percentile(estimates, 2.5),
        percentile(estimates, 97.5),
    )
