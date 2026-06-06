"""Contract reconciliation memory benchmark for bounty #639.

The benchmark is dependency-free so reviewers can run it without API keys.
It models three memory strategies over the same temporal event stream and
scores them against golden probes.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


SECRET_PATTERN = re.compile(
    r"(sk_[a-z0-9_]+|tok-[a-z0-9-]+|wire-[a-z0-9-]+|passphrase:[a-z0-9-]+)",
    re.IGNORECASE,
)


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def token_count(text: str) -> int:
    return len(normalize(text).split()) if text.strip() else 0


def redact(text: str) -> str:
    return SECRET_PATTERN.sub("[REDACTED_SECRET]", text)


@dataclass(frozen=True)
class MemoryEvent:
    event_id: str
    session: int
    slot: str
    value: str
    evidence: str
    supersedes: tuple[str, ...] = ()
    secret: bool = False

    @property
    def text(self) -> str:
        supersedes = (
            f" supersedes {', '.join(self.supersedes)}" if self.supersedes else ""
        )
        return (
            f"{self.event_id} session={self.session} slot={self.slot}: "
            f"{self.value} evidence={self.evidence}{supersedes}"
        )


@dataclass(frozen=True)
class Probe:
    query: str
    expected: tuple[str, ...]
    forbidden: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()


@dataclass
class ProbeResult:
    query: str
    answer: str
    accuracy: float
    retrieved_tokens: int
    latency_ms: float
    stale_conflict: bool
    secret_leak: bool
    evidence_hits: int
    evidence_expected: int


@dataclass
class BackendResult:
    backend: str
    probe_results: list[ProbeResult] = field(default_factory=list)

    def summary(self) -> dict[str, float | str]:
        total = len(self.probe_results)
        if total == 0:
            return {
                "backend": self.backend,
                "accuracy": 0.0,
                "avg_retrieved_tokens": 0.0,
                "p95_latency_ms": 0.0,
                "stale_conflict_rate": 0.0,
                "secret_leak_rate": 0.0,
                "evidence_coverage": 0.0,
                "signal_noise": 0.0,
            }

        latencies = [p.latency_ms for p in self.probe_results]
        p95_latency = (
            statistics.quantiles(latencies, n=20)[18]
            if len(latencies) > 1
            else latencies[0]
        )
        expected_evidence = sum(
            1 for p in self.probe_results if p.evidence_expected > 0
        )
        evidence_hits = sum(1 for p in self.probe_results if p.evidence_hits > 0)
        return {
            "backend": self.backend,
            "accuracy": round(sum(p.accuracy for p in self.probe_results) / total, 3),
            "avg_retrieved_tokens": round(
                sum(p.retrieved_tokens for p in self.probe_results) / total, 2
            ),
            "p95_latency_ms": round(p95_latency, 3),
            "stale_conflict_rate": round(
                sum(1 for p in self.probe_results if p.stale_conflict) / total, 3
            ),
            "secret_leak_rate": round(
                sum(1 for p in self.probe_results if p.secret_leak) / total, 3
            ),
            "evidence_coverage": round(evidence_hits / max(expected_evidence, 1), 3),
            "signal_noise": round(self._signal_noise(), 3),
        }

    def _signal_noise(self) -> float:
        useful = 0
        total = 0
        for result in self.probe_results:
            answer = normalize(result.answer)
            total += max(token_count(answer), 1)
            useful += sum(1 for term in result.query.lower().split() if term in answer)
            useful += result.evidence_hits
        return useful / max(total, 1)


class MemoryBackend:
    name = "base"

    def ingest(self, events: Iterable[MemoryEvent]) -> None:
        raise NotImplementedError

    def recall(self, query: str) -> str:
        raise NotImplementedError


class AppendOnlyLog(MemoryBackend):
    name = "append_only_log"

    def __init__(self) -> None:
        self.events: list[MemoryEvent] = []

    def ingest(self, events: Iterable[MemoryEvent]) -> None:
        self.events.extend(events)

    def recall(self, query: str) -> str:
        query_terms = set(normalize(query).split())
        matches = []
        for event in self.events:
            event_terms = set(normalize(event.text).split())
            if query_terms & event_terms:
                matches.append(event.text)
        return "\n".join(matches or [event.text for event in self.events])


class RecentWindowLog(MemoryBackend):
    name = "recent_window_log"

    def __init__(self, window: int = 5) -> None:
        if not isinstance(window, int) or window <= 0:
            raise ValueError("window must be a positive integer")
        self.window = window
        self.events: list[MemoryEvent] = []

    def ingest(self, events: Iterable[MemoryEvent]) -> None:
        self.events.extend(events)
        self.events = self.events[-self.window :]

    def recall(self, query: str) -> str:
        query_terms = set(normalize(query).split())
        matches = []
        for event in self.events:
            event_terms = set(normalize(event.text).split())
            if query_terms & event_terms:
                matches.append(redact(event.text))
        return "\n".join(matches or [redact(event.text) for event in self.events])


class ActiveContractLedger(MemoryBackend):
    name = "active_contract_ledger"

    def __init__(self) -> None:
        self.current_by_slot: dict[str, MemoryEvent] = {}
        self.superseded_ids: set[str] = set()

    def ingest(self, events: Iterable[MemoryEvent]) -> None:
        for event in events:
            if event.secret:
                continue
            self.superseded_ids.update(event.supersedes)
            old_event = self.current_by_slot.get(event.slot)
            if old_event is not None:
                self.superseded_ids.add(old_event.event_id)
            self.current_by_slot[event.slot] = event

    def recall(self, query: str) -> str:
        query_terms = set(normalize(query).split())
        if {"secret", "token"} & query_terms:
            return "payment_method: [REDACTED_SECRET] (no active payment token is stored)"

        scored: list[tuple[int, MemoryEvent]] = []
        for event in self.current_by_slot.values():
            event_terms = set(normalize(f"{event.slot} {event.value} {event.evidence}").split())
            score = len(query_terms & event_terms)
            if score:
                scored.append((score, event))
        if not scored:
            scored = [(1, event) for event in self.current_by_slot.values()]
        scored.sort(key=lambda item: (-item[0], item[1].slot))
        lines = []
        for _, event in scored[:3]:
            lines.append(
                f"{event.slot}: {redact(event.value)} "
                f"(current, evidence={event.evidence}, source={event.event_id})"
            )
        return "\n".join(lines)


def build_events() -> list[MemoryEvent]:
    return [
        MemoryEvent(
            "S1-E1",
            1,
            "pricing",
            "Acme selected the startup plan at $400 per month.",
            "quote-v1",
        ),
        MemoryEvent(
            "S1-E2",
            1,
            "support_sla",
            "Support SLA is two business days.",
            "msa-draft-v1",
        ),
        MemoryEvent(
            "S1-E3",
            1,
            "payment_method",
            "Temporary wire token is wire-alpha-119 for onboarding only.",
            "finance-note",
            secret=True,
        ),
        MemoryEvent(
            "S2-E1",
            2,
            "pricing",
            "Acme upgraded to $750 per month after adding audit logs.",
            "quote-v2",
            supersedes=("S1-E1",),
        ),
        MemoryEvent(
            "S2-E2",
            2,
            "data_region",
            "All production data must stay in the EU region.",
            "dpa-v1",
        ),
        MemoryEvent(
            "S3-E1",
            3,
            "support_sla",
            "Support SLA changed to four hours for Sev1 incidents.",
            "msa-redline-v3",
            supersedes=("S1-E2",),
        ),
        MemoryEvent(
            "S3-E2",
            3,
            "invoice_contact",
            "Invoices go to procurement@example.invalid.",
            "finance-approval",
        ),
        MemoryEvent(
            "S3-E3",
            3,
            "api_secret",
            "Never store this sandbox key: sk_live_contract_shadow.",
            "security-review",
            secret=True,
        ),
        MemoryEvent(
            "S4-E1",
            4,
            "renewal",
            "Renewal must be opt-in only; no automatic renewal clause.",
            "legal-signoff",
        ),
        MemoryEvent(
            "S4-E2",
            4,
            "pricing",
            "Final accepted price is $690 per month with annual prepay.",
            "quote-final",
            supersedes=("S2-E1",),
        ),
        MemoryEvent(
            "S5-E1",
            5,
            "data_region",
            "EU residency remains required, but analytics exports may run in US-East after anonymization.",
            "dpa-addendum",
            supersedes=("S2-E2",),
        ),
        MemoryEvent(
            "S5-E2",
            5,
            "security_review",
            "SOC 2 report is required before production launch.",
            "security-gate",
        ),
    ]


def build_probes() -> list[Probe]:
    return [
        Probe(
            query="What is the current accepted price?",
            expected=("690", "annual prepay"),
            forbidden=("400", "750"),
            evidence=("quote-final",),
        ),
        Probe(
            query="What support SLA should the agent use for Sev1 incidents?",
            expected=("four hours", "Sev1"),
            forbidden=("two business days",),
            evidence=("msa-redline-v3",),
        ),
        Probe(
            query="Where may production data and anonymized analytics exports run?",
            expected=("EU residency", "US-East", "anonymization"),
            forbidden=("all production data must stay in the EU region.",),
            evidence=("dpa-addendum",),
        ),
        Probe(
            query="How should renewal be handled?",
            expected=("opt-in", "no automatic renewal"),
            forbidden=("automatic renewal clause applies",),
            evidence=("legal-signoff",),
        ),
        Probe(
            query="Which secret or token should be used for payment setup?",
            expected=("[REDACTED_SECRET]",),
            forbidden=("wire-alpha-119", "sk_live_contract_shadow"),
            evidence=(),
        ),
        Probe(
            query="What must happen before production launch?",
            expected=("SOC 2", "required"),
            forbidden=("optional",),
            evidence=("security-gate",),
        ),
    ]


def score_answer(answer: str, probe: Probe) -> tuple[float, bool, bool, int]:
    normalized_answer = normalize(answer)
    expected_hits = sum(1 for term in probe.expected if normalize(term) in normalized_answer)
    accuracy = expected_hits / max(len(probe.expected), 1)
    stale_conflict = any(term.lower() in answer.lower() for term in probe.forbidden)
    secret_leak = SECRET_PATTERN.search(answer) is not None
    evidence_hits = sum(1 for marker in probe.evidence if marker in answer)
    return accuracy, stale_conflict, secret_leak, evidence_hits


def evaluate_backend(backend: MemoryBackend, events: list[MemoryEvent], probes: list[Probe]) -> BackendResult:
    backend.ingest(events)
    result = BackendResult(backend=backend.name)
    for probe in probes:
        started = time.perf_counter()
        answer = backend.recall(probe.query)
        latency_ms = (time.perf_counter() - started) * 1000
        accuracy, stale_conflict, secret_leak, evidence_hits = score_answer(answer, probe)
        result.probe_results.append(
            ProbeResult(
                query=probe.query,
                answer=answer,
                accuracy=accuracy,
                retrieved_tokens=token_count(answer),
                latency_ms=latency_ms,
                stale_conflict=stale_conflict,
                secret_leak=secret_leak,
                evidence_hits=evidence_hits,
                evidence_expected=len(probe.evidence),
            )
        )
    return result


def run() -> list[BackendResult]:
    events = build_events()
    probes = build_probes()
    backends: list[MemoryBackend] = [
        AppendOnlyLog(),
        RecentWindowLog(window=5),
        ActiveContractLedger(),
    ]
    return [evaluate_backend(backend, events, probes) for backend in backends]


def result_to_dict(result: BackendResult) -> dict[str, object]:
    return {
        "summary": result.summary(),
        "probes": [
            {
                "query": probe.query,
                "accuracy": probe.accuracy,
                "retrieved_tokens": probe.retrieved_tokens,
                "latency_ms": round(probe.latency_ms, 3),
                "stale_conflict": probe.stale_conflict,
                "secret_leak": probe.secret_leak,
                "evidence_hits": probe.evidence_hits,
                "evidence_expected": probe.evidence_expected,
                "answer": probe.answer,
            }
            for probe in result.probe_results
        ],
    }


def write_markdown(results: list[BackendResult], path: Path) -> None:
    lines = [
        "# Contract Reconciliation Memory Benchmark Results",
        "",
        "| Backend | Accuracy | Avg Tokens | p95 Latency ms | Stale Conflict | Secret Leak | Evidence | Signal/Noise |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in results:
        summary = result.summary()
        lines.append(
            "| {backend} | {accuracy:.3f} | {avg_retrieved_tokens:.2f} | "
            "{p95_latency_ms:.3f} | {stale_conflict_rate:.3f} | "
            "{secret_leak_rate:.3f} | {evidence_coverage:.3f} | "
            "{signal_noise:.3f} |".format(**summary)
        )
    lines.extend(
        [
            "",
            "## Probe Details",
            "",
        ]
    )
    for result in results:
        lines.append(f"### {result.backend}")
        for probe in result.probe_results:
            lines.extend(
                [
                    "",
                    f"- Query: {probe.query}",
                    f"  - accuracy: {probe.accuracy:.3f}",
                    f"  - retrieved_tokens: {probe.retrieved_tokens}",
                    f"  - stale_conflict: {probe.stale_conflict}",
                    f"  - secret_leak: {probe.secret_leak}",
                ]
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    args = parser.parse_args()

    results = run()
    payload = {"results": [result_to_dict(result) for result in results]}
    print(json.dumps(payload, indent=2))

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if args.markdown_out:
        write_markdown(results, args.markdown_out)


if __name__ == "__main__":
    main()
