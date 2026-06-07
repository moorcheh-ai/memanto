"""Deterministic long-horizon dataset with explicit ground truth."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class FactSpec:
    key: str
    label: str
    query: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class Event:
    event_id: str
    session: int
    fact_key: str
    value: str
    previous_values: tuple[str, ...]
    title: str
    content: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class Probe:
    probe_id: str
    checkpoint: int
    fact_key: str
    query: str
    expected_value: str
    stale_values: tuple[str, ...]


FACTS = (
    FactSpec(
        key="production_region",
        label="Production region",
        query="What is the current production deployment region?",
        values=(
            "us-east-1",
            "eu-west-1",
            "ap-southeast-2",
            "eu-central-1",
            "ca-central-1",
            "us-west-2",
        ),
    ),
    FactSpec(
        key="payment_rail",
        label="Payment rail",
        query="Which payment rail is currently authoritative?",
        values=(
            "stripe",
            "adyen",
            "checkout-com",
            "braintree",
            "worldpay",
            "stripe-v2",
        ),
    ),
    FactSpec(
        key="primary_database",
        label="Primary database",
        query="What is the current primary production database?",
        values=(
            "postgres-15",
            "cockroach-23",
            "postgres-16",
            "aurora-postgres-16",
            "alloydb-16",
            "postgres-17",
        ),
    ),
    FactSpec(
        key="retention_days",
        label="Retention policy",
        query="What is the current customer event retention period?",
        values=("365", "180", "90", "45", "30", "14"),
    ),
    FactSpec(
        key="incident_channel",
        label="Incident channel",
        query="Which incident channel should responders use now?",
        values=(
            "ops-sev",
            "incident-core",
            "prod-war-room",
            "reliability-live",
            "sev-command",
            "incident-bridge",
        ),
    ),
    FactSpec(
        key="release_window",
        label="Release window",
        query="What is the current production release window?",
        values=(
            "tuesday-1400-utc",
            "wednesday-0900-utc",
            "thursday-1600-utc",
            "monday-1200-utc",
            "friday-0700-utc",
            "wednesday-1800-utc",
        ),
    ),
    FactSpec(
        key="oncall_owner",
        label="On-call owner",
        query="Which team currently owns the production on-call rotation?",
        values=(
            "platform",
            "reliability",
            "core-services",
            "runtime",
            "production-engineering",
            "site-operations",
        ),
    ),
    FactSpec(
        key="feature_gate",
        label="Feature gate",
        query="What is the current checkout feature gate name?",
        values=(
            "checkout-v2",
            "payments-unified",
            "checkout-orchestrator",
            "payflow-next",
            "checkout-edge",
            "payments-router-v3",
        ),
    ),
)

NOISE_NOTES = (
    "The design review moved to the larger conference room.",
    "A documentation typo was corrected in the internal handbook.",
    "The staging dashboard color palette was refreshed.",
    "A non-production demo account was archived.",
    "The monthly architecture reading list was published.",
    "The office network maintenance notice was acknowledged.",
    "A test fixture name was clarified without changing behavior.",
    "The team calendar now includes the quarterly planning session.",
)


def canonical_marker(key: str, value: str) -> str:
    return f"CANONICAL[{key}={value}]"


def generate_scenario(
    *,
    seed: int,
    sessions: int = 48,
    checkpoints: tuple[int, ...] = (8, 16, 24, 32, 48),
) -> tuple[list[Event], list[Probe]]:
    """Generate one paired scenario for all benchmark backends.

    Each eight-session epoch updates every mutable fact exactly once. The key
    order and distractor notes vary by seed, while the ground truth remains
    fully deterministic and inspectable.
    """
    if sessions < len(FACTS):
        raise ValueError(f"sessions must be at least {len(FACTS)}")
    if sessions > len(FACTS) * len(FACTS[0].values):
        raise ValueError("sessions exceed the available unique fact versions")
    if any(point < len(FACTS) or point > sessions for point in checkpoints):
        raise ValueError("checkpoints must be between 8 and sessions")
    if any(point % len(FACTS) for point in checkpoints):
        raise ValueError("checkpoints must fall on complete eight-session epochs")

    rng = random.Random(seed)
    fact_by_key = {fact.key: fact for fact in FACTS}
    value_index = {fact.key: 0 for fact in FACTS}
    history: dict[str, list[str]] = {fact.key: [] for fact in FACTS}
    current: dict[str, str] = {}
    events: list[Event] = []
    probes: list[Probe] = []

    session = 0
    while session < sessions:
        epoch_keys = [fact.key for fact in FACTS]
        rng.shuffle(epoch_keys)
        for key in epoch_keys:
            if session >= sessions:
                break
            session += 1
            fact = fact_by_key[key]
            index = value_index[key]
            value = fact.values[index]
            previous = tuple(history[key])
            noise = rng.sample(NOISE_NOTES, k=2)
            content = "\n".join(
                (
                    f"Operational state update from session {session:02d}.",
                    canonical_marker(key, value),
                    f"{fact.label} is now {value}. This supersedes prior values.",
                    f"Non-authoritative note: {noise[0]}",
                    f"Non-authoritative note: {noise[1]}",
                )
            )
            events.append(
                Event(
                    event_id=f"s{session:02d}-{key}",
                    session=session,
                    fact_key=key,
                    value=value,
                    previous_values=previous,
                    title=f"{fact.label} update {index + 1}",
                    content=content,
                    tags=("benchmark", "long-horizon", key, f"session-{session:02d}"),
                )
            )
            history[key].append(value)
            current[key] = value
            value_index[key] += 1

            if session in checkpoints:
                for probe_fact in FACTS:
                    expected = current[probe_fact.key]
                    stale = tuple(history[probe_fact.key][:-1])
                    probes.append(
                        Probe(
                            probe_id=(f"seed-{seed}-c{session:02d}-{probe_fact.key}"),
                            checkpoint=session,
                            fact_key=probe_fact.key,
                            query=(
                                f"{probe_fact.query} Return the exact canonical "
                                "value and ignore superseded settings."
                            ),
                            expected_value=expected,
                            stale_values=stale,
                        )
                    )

    return events, probes
