"""Deterministic research decision memory benchmark.

The benchmark compares memory strategies on a product-research decision trail
where early assumptions are superseded by later evidence. It intentionally uses
only the Python standard library so reviewers can run it without credentials.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


SECRET_MARKERS = ("sk-test-", "private_token_", "secret=")


@dataclass(frozen=True)
class DecisionRecord:
    turn: int
    session: str
    slot: str
    value: str
    evidence_id: str
    status: str
    rationale: str
    relevant_terms: tuple[str, ...]
    stale_terms: tuple[str, ...] = ()
    secret: str | None = None


@dataclass(frozen=True)
class Probe:
    name: str
    question: str
    slots: tuple[str, ...]
    expected_terms: tuple[str, ...]
    expected_evidence: tuple[str, ...]
    stale_terms: tuple[str, ...]
    relevant_evidence: tuple[str, ...]


@dataclass(frozen=True)
class Answer:
    backend: str
    probe: str
    answer: str
    evidence_ids: tuple[str, ...]
    retrieved_tokens: int
    latency_ms: float


@dataclass(frozen=True)
class BackendSummary:
    backend: str
    accuracy: float
    evidence_coverage: float
    stale_conflict_rate: float
    secret_leak_rate: float
    avg_retrieved_tokens: float
    p95_latency_ms: float
    signal_noise_ratio: float


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_.:$-]+", text.lower())


def token_count(text: str) -> int:
    return len(tokenize(text))


def contains_all(text: str, terms: Iterable[str]) -> bool:
    lowered = text.lower()
    return all(term.lower() in lowered for term in terms)


def contains_any(text: str, terms: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def percentile_95(values: list[float]) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=20, method="inclusive")[18]


def decision_records() -> list[DecisionRecord]:
    return [
        DecisionRecord(
            turn=1,
            session="s1-hypothesis",
            slot="target_segment",
            value="Initial target segment is consumer creators.",
            evidence_id="ev-001",
            status="superseded",
            rationale="Founder hunch from an early market scan.",
            relevant_terms=("target", "segment", "consumer", "creators"),
            stale_terms=("consumer creators",),
        ),
        DecisionRecord(
            turn=2,
            session="s1-hypothesis",
            slot="pricing",
            value="Initial pricing hypothesis is $49 per team per month.",
            evidence_id="ev-002",
            status="superseded",
            rationale="Anchored on a competitor roundup, before support-team interviews.",
            relevant_terms=("pricing", "$49", "team", "month"),
            stale_terms=("$49 per team per month",),
        ),
        DecisionRecord(
            turn=3,
            session="s2-interviews",
            slot="target_segment",
            value="Current target segment is support operations teams.",
            evidence_id="ev-003",
            status="current",
            rationale="Nine of twelve interviews had an urgent cross-session handoff pain.",
            relevant_terms=("target", "segment", "support", "operations", "teams"),
        ),
        DecisionRecord(
            turn=4,
            session="s2-interviews",
            slot="pricing",
            value="Current pricing is a usage-based pilot at $0.08 per resolved ticket.",
            evidence_id="ev-004",
            status="current",
            rationale="Budget owners preferred tying price to support resolution volume.",
            relevant_terms=("pricing", "usage", "$0.08", "resolved", "ticket"),
        ),
        DecisionRecord(
            turn=5,
            session="s3-architecture",
            slot="deployment",
            value=(
                "Current deployment decision is self-hosted beta only; no EU "
                "customer data leaves the customer VPC."
            ),
            evidence_id="ev-005",
            status="current",
            rationale="Enterprise legal review rejected shared SaaS for the first pilot.",
            relevant_terms=("deployment", "self-hosted", "eu", "vpc"),
            stale_terms=("shared SaaS",),
        ),
        DecisionRecord(
            turn=6,
            session="s3-architecture",
            slot="launch_readiness",
            value="Do not publish the public benchmark until the win-rate chart is reproduced.",
            evidence_id="ev-006",
            status="superseded",
            rationale="The initial chart used a mixed judge prompt.",
            relevant_terms=("launch", "benchmark", "publish", "win-rate", "chart"),
            stale_terms=("do not publish",),
        ),
        DecisionRecord(
            turn=7,
            session="s3-architecture",
            slot="data_handling",
            value="Rejected assumption: raw support logs are safe to store without redaction.",
            evidence_id="ev-007",
            status="rejected",
            rationale="Security review found synthetic keys in exported transcript fixtures.",
            relevant_terms=("data", "logs", "redaction", "raw", "safe"),
            stale_terms=("raw support logs are safe",),
            secret="sk-test-123456",
        ),
        DecisionRecord(
            turn=8,
            session="s4-correction",
            slot="data_handling",
            value="Current data handling requires redaction before logs enter memory.",
            evidence_id="ev-008",
            status="current",
            rationale="The fixture pipeline now strips synthetic tokens before ingestion.",
            relevant_terms=("data", "logs", "redaction", "memory"),
        ),
        DecisionRecord(
            turn=9,
            session="s4-correction",
            slot="launch_readiness",
            value="Current launch decision is publish after the win-rate chart is reproduced.",
            evidence_id="ev-009",
            status="current",
            rationale="The judge prompt was fixed and rerun on the frozen probe set.",
            relevant_terms=("launch", "benchmark", "publish", "win-rate", "chart"),
        ),
        DecisionRecord(
            turn=10,
            session="s5-pilot",
            slot="customer_owner",
            value="Acme pilot is blocked on DPA redlines; Lina owns it by June 18.",
            evidence_id="ev-010",
            status="current",
            rationale="Customer success reassigned the owner after procurement escalation.",
            relevant_terms=("customer", "owner", "acme", "dpa", "lina", "june"),
            stale_terms=("Mara owns",),
        ),
        DecisionRecord(
            turn=11,
            session="s5-pilot",
            slot="model_routing",
            value="Use a small local reranker for triage; GPT-4.1 only handles synthesis.",
            evidence_id="ev-011",
            status="current",
            rationale="The local reranker kept cost down without hurting final synthesis.",
            relevant_terms=("model", "routing", "local", "reranker", "gpt-4.1"),
            stale_terms=("GPT-4.1 for every turn",),
        ),
        DecisionRecord(
            turn=12,
            session="s5-pilot",
            slot="primary_metric",
            value="Primary benchmark metric is decision freshness accuracy.",
            evidence_id="ev-012",
            status="current",
            rationale="The team chose freshness over generic user satisfaction surveys.",
            relevant_terms=("primary", "metric", "decision", "freshness", "accuracy"),
            stale_terms=("user satisfaction",),
        ),
    ]


def probes() -> list[Probe]:
    return [
        Probe(
            name="target_segment",
            question="Who is the current target segment?",
            slots=("target_segment",),
            expected_terms=("support operations teams",),
            expected_evidence=("ev-003",),
            stale_terms=("consumer creators",),
            relevant_evidence=("ev-003",),
        ),
        Probe(
            name="pricing",
            question="What is the current pricing decision?",
            slots=("pricing",),
            expected_terms=("$0.08 per resolved ticket",),
            expected_evidence=("ev-004",),
            stale_terms=("$49 per team per month",),
            relevant_evidence=("ev-004",),
        ),
        Probe(
            name="deployment",
            question="What deployment constraint is active for the beta?",
            slots=("deployment",),
            expected_terms=("self-hosted beta", "no eu customer data leaves"),
            expected_evidence=("ev-005",),
            stale_terms=("shared saas",),
            relevant_evidence=("ev-005",),
        ),
        Probe(
            name="launch_readiness",
            question="When can the public benchmark be published?",
            slots=("launch_readiness",),
            expected_terms=("publish after the win-rate chart is reproduced",),
            expected_evidence=("ev-009",),
            stale_terms=("do not publish",),
            relevant_evidence=("ev-009",),
        ),
        Probe(
            name="data_handling",
            question="What is the current log-handling decision?",
            slots=("data_handling",),
            expected_terms=("redaction before logs enter memory",),
            expected_evidence=("ev-008",),
            stale_terms=("raw support logs are safe", "sk-test-123456"),
            relevant_evidence=("ev-008",),
        ),
        Probe(
            name="customer_owner",
            question="Who owns the current Acme pilot blocker?",
            slots=("customer_owner",),
            expected_terms=("acme pilot is blocked", "lina", "june 18"),
            expected_evidence=("ev-010",),
            stale_terms=("mara owns",),
            relevant_evidence=("ev-010",),
        ),
        Probe(
            name="model_routing",
            question="How should the agent route model calls now?",
            slots=("model_routing",),
            expected_terms=("small local reranker", "gpt-4.1 only handles synthesis"),
            expected_evidence=("ev-011",),
            stale_terms=("gpt-4.1 for every turn",),
            relevant_evidence=("ev-011",),
        ),
        Probe(
            name="primary_metric",
            question="What is the primary benchmark metric?",
            slots=("primary_metric",),
            expected_terms=("decision freshness accuracy",),
            expected_evidence=("ev-012",),
            stale_terms=("user satisfaction",),
            relevant_evidence=("ev-012",),
        ),
    ]


class MemoryBackend:
    name = "base"

    def __init__(self, records: list[DecisionRecord]) -> None:
        self.records = records

    def answer(self, probe: Probe) -> Answer:
        start = time.perf_counter()
        selected = self.retrieve(probe)
        answer = self.render_answer(selected)
        latency_ms = (time.perf_counter() - start) * 1000
        return Answer(
            backend=self.name,
            probe=probe.name,
            answer=answer,
            evidence_ids=tuple(record.evidence_id for record in selected),
            retrieved_tokens=sum(self.record_tokens(record) for record in selected),
            latency_ms=latency_ms,
        )

    def retrieve(self, probe: Probe) -> list[DecisionRecord]:
        raise NotImplementedError

    def render_answer(self, records: list[DecisionRecord]) -> str:
        if not records:
            return "No decision found."
        parts = []
        for record in records:
            value = record.value
            if record.secret:
                value = f"{value} {record.secret}"
            parts.append(f"{record.slot}: {value} Evidence: {record.evidence_id}.")
        return " ".join(parts)

    @staticmethod
    def record_tokens(record: DecisionRecord) -> int:
        secret = f" {record.secret}" if record.secret else ""
        return token_count(f"{record.slot} {record.value} {record.rationale}{secret}")


class ActiveDecisionDigest(MemoryBackend):
    name = "active_decision_digest"

    def __init__(self, records: list[DecisionRecord]) -> None:
        super().__init__(records)
        self.current_by_slot: dict[str, DecisionRecord] = {}
        for record in records:
            if record.status == "current":
                self.current_by_slot[record.slot] = record
            elif record.status in {"superseded", "rejected"}:
                self.current_by_slot.pop(record.slot, None)

    def retrieve(self, probe: Probe) -> list[DecisionRecord]:
        return [
            self.current_by_slot[slot]
            for slot in probe.slots
            if slot in self.current_by_slot
        ]


class PassiveGraphHistory(MemoryBackend):
    name = "passive_graph_history"

    def retrieve(self, probe: Probe) -> list[DecisionRecord]:
        return [record for record in self.records if record.slot in probe.slots]

    def render_answer(self, records: list[DecisionRecord]) -> str:
        if not records:
            return "No decision node found."
        grouped: dict[str, list[DecisionRecord]] = {}
        for record in records:
            grouped.setdefault(record.slot, []).append(record)
        parts = []
        for slot, slot_records in grouped.items():
            states = []
            for record in slot_records:
                value = record.value
                if record.secret:
                    value = f"{value} {record.secret}"
                states.append(f"{record.status}: {value} ({record.evidence_id})")
            parts.append(f"{slot} possible states: {' | '.join(states)}.")
        return " ".join(parts)


class AppendOnlyLog(MemoryBackend):
    name = "append_only_log"

    def retrieve(self, probe: Probe) -> list[DecisionRecord]:
        query_terms = set(tokenize(probe.question))
        selected = []
        for record in self.records:
            record_terms = set(record.relevant_terms) | set(tokenize(record.value))
            if record.slot in probe.slots or query_terms.intersection(record_terms):
                selected.append(record)
        return selected


class RecentWindowLog(MemoryBackend):
    name = "recent_window_log"

    def __init__(self, records: list[DecisionRecord], window_size: int = 4) -> None:
        super().__init__(records)
        self.window_size = window_size

    def retrieve(self, probe: Probe) -> list[DecisionRecord]:
        window = self.records[-self.window_size :]
        return [record for record in window if record.slot in probe.slots]


def score_answers(answers: list[Answer], expected: list[Probe]) -> BackendSummary:
    expected_by_name = {probe.name: probe for probe in expected}
    correct = 0
    evidence_hits = 0
    evidence_total = 0
    stale_conflicts = 0
    secret_leaks = 0
    relevant_evidence_hits = 0
    retrieved_evidence_total = 0

    for answer in answers:
        probe = expected_by_name[answer.probe]
        has_expected_terms = contains_all(answer.answer, probe.expected_terms)
        has_expected_evidence = all(
            evidence in answer.evidence_ids for evidence in probe.expected_evidence
        )
        has_stale = contains_any(answer.answer, probe.stale_terms)
        leaked_secret = contains_any(answer.answer, SECRET_MARKERS)
        if has_expected_terms and has_expected_evidence and not has_stale and not leaked_secret:
            correct += 1
        evidence_hits += sum(
            evidence in answer.evidence_ids for evidence in probe.expected_evidence
        )
        evidence_total += len(probe.expected_evidence)
        stale_conflicts += int(has_stale)
        secret_leaks += int(leaked_secret)
        relevant_evidence_hits += sum(
            evidence in probe.relevant_evidence for evidence in answer.evidence_ids
        )
        retrieved_evidence_total += len(answer.evidence_ids)

    total = len(answers)
    tokens = [answer.retrieved_tokens for answer in answers]
    latencies = [answer.latency_ms for answer in answers]
    return BackendSummary(
        backend=answers[0].backend if answers else "unknown",
        accuracy=correct / total if total else 0.0,
        evidence_coverage=evidence_hits / evidence_total if evidence_total else 0.0,
        stale_conflict_rate=stale_conflicts / total if total else 0.0,
        secret_leak_rate=secret_leaks / total if total else 0.0,
        avg_retrieved_tokens=sum(tokens) / total if total else 0.0,
        p95_latency_ms=percentile_95(latencies),
        signal_noise_ratio=(
            relevant_evidence_hits / retrieved_evidence_total
            if retrieved_evidence_total
            else 0.0
        ),
    )


def run() -> dict[str, object]:
    records = decision_records()
    expected = probes()
    backends: list[MemoryBackend] = [
        ActiveDecisionDigest(records),
        PassiveGraphHistory(records),
        AppendOnlyLog(records),
        RecentWindowLog(records),
    ]
    all_answers: dict[str, list[Answer]] = {}
    summaries: list[BackendSummary] = []
    for backend in backends:
        answers = [backend.answer(probe) for probe in expected]
        all_answers[backend.name] = answers
        summaries.append(score_answers(answers, expected))

    return {
        "scenario": "research-decision-memory",
        "records": [asdict(record) for record in records],
        "probes": [asdict(probe) for probe in expected],
        "summaries": [asdict(summary) for summary in summaries],
        "answers": {
            backend: [asdict(answer) for answer in answers]
            for backend, answers in all_answers.items()
        },
    }


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def summary_rows(payload: dict[str, object]) -> list[dict[str, object]]:
    return list(payload["summaries"])  # type: ignore[arg-type]


def markdown_report(payload: dict[str, object]) -> str:
    rows = summary_rows(payload)
    lines = [
        "# Research Decision Memory Results",
        "",
        "| Backend | Accuracy | Evidence | Stale Conflicts | Secret Leaks | Avg Tokens | p95 ms | Signal/Noise |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| {backend} | {accuracy:.2%} | {evidence_coverage:.2%} | "
            "{stale_conflict_rate:.2%} | {secret_leak_rate:.2%} | "
            "{avg_retrieved_tokens:.2f} | {p95_latency_ms:.4f} | "
            "{signal_noise_ratio:.2%} |".format(**row)
        )
    lines.append("")
    lines.append("Generated with `run_benchmark.py` using only stdlib components.")
    return "\n".join(lines) + "\n"


def write_markdown(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown_report(payload), encoding="utf-8")


def print_summary(payload: dict[str, object]) -> None:
    print(markdown_report(payload))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON output path.",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=None,
        help="Optional Markdown report path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run()
    if args.output:
        write_json(args.output, payload)
    if args.markdown:
        write_markdown(args.markdown, payload)
    print_summary(payload)


if __name__ == "__main__":
    main()
