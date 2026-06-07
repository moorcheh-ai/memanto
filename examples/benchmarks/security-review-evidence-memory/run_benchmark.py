#!/usr/bin/env python3
"""Deterministic memory benchmark for security-review evidence retention.

The benchmark intentionally avoids external services so maintainers can run it
without API keys. The active backend models a Memanto-style digest that keeps
current facts, source evidence, and redaction policy instead of raw transcripts.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


SECRET_PATTERNS = (
    re.compile(r"GITHUB_TOKEN_FAKE_[A-Z_]+"),
    re.compile(r"ghp_[A-Za-z0-9_]+"),
    re.compile(r"sk_live_[A-Za-z0-9_]+"),
)


def redact_secrets(text: str) -> str:
    """Replace synthetic credential values with a stable redaction marker."""
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED_SECRET]", text)
    return text


def token_count(text: str) -> int:
    """Approximate retrieval footprint with a deterministic word-token count."""
    return len(re.findall(r"\b[\w:-]+\b", text))


@dataclass(frozen=True)
class Fact:
    """Current normalized state for a security finding."""

    finding_id: str
    status: str
    severity: str
    owner: str
    evidence: str
    summary: str

    def render(self) -> str:
        """Serialize the fact into the context returned by a memory backend."""
        return (
            f"{self.finding_id} status={self.status} severity={self.severity} "
            f"owner={self.owner} evidence={self.evidence} summary={self.summary}"
        )


@dataclass(frozen=True)
class SessionEvent:
    """One review session with raw transcript text and normalized facts."""

    session: str
    raw: str
    facts: Sequence[Fact]


@dataclass(frozen=True)
class Probe:
    """Question and term expectations used to score retrieval quality."""

    question: str
    required_terms: Sequence[str]
    forbidden_terms: Sequence[str] = field(default_factory=tuple)


DATASET: Sequence[SessionEvent] = (
    SessionEvent(
        session="s1-initial-review",
        raw=(
            "Initial review opened F-101 critical GitHub Actions token exposure "
            "with synthetic value GITHUB_TOKEN_FAKE_FOR_TEST_ONLY in ci-log-77. "
            "Opened F-102 high SSRF to metadata service from image proxy, evidence zap-17. "
            "Opened F-103 medium weak TLS scanner alert from scanner-a."
        ),
        facts=(
            Fact("F-101", "open", "critical", "platform", "ci-log-77", "Synthetic GitHub token observed in build log GITHUB_TOKEN_FAKE_FOR_TEST_ONLY."),
            Fact("F-102", "open", "high", "appsec", "zap-17", "Image proxy can still reach metadata service."),
            Fact("F-103", "open", "medium", "netsec", "scanner-a", "Scanner reported weak TLS on admin endpoint."),
        ),
    ),
    SessionEvent(
        session="s2-triage-and-retTest",
        raw=(
            "Retest update: F-101 resolved after token rotation, log purge, and revocation ticket SEC-900. "
            "Do not include the raw token value in reports. "
            "F-103 false_positive because mTLS terminates upstream and scanner-a lacked the required client certificate."
        ),
        facts=(
            Fact("F-101", "resolved", "none", "platform", "SEC-900", "Token rotated, affected logs purged, raw token must remain redacted."),
            Fact("F-103", "false_positive", "none", "netsec", "mTLS-client-cert-review", "mTLS terminates upstream; scanner lacked client certificate."),
        ),
    ),
    SessionEvent(
        session="s3-follow-up-review",
        raw=(
            "Follow-up opened F-104 critical cross-tenant authorization bypass, owner identity-platform, evidence authz-replay-12. "
            "F-102 is still open high because a retry can still reach metadata service from a sidecar route. "
            "F-105 dependency CVE is false_positive because the vendored path is not imported or packaged."
        ),
        facts=(
            Fact("F-104", "open", "critical", "identity-platform", "authz-replay-12", "Cross-tenant authorization bypass reproduced."),
            Fact("F-102", "open", "high", "appsec", "zap-31", "Sidecar route can still reach metadata service."),
            Fact("F-105", "false_positive", "none", "supply-chain", "import-graph-4", "Vendored vulnerable path is not imported or packaged."),
        ),
    ),
    SessionEvent(
        session="s4-remediation-review",
        raw=(
            "Final update: F-102 resolved. IMDS egress deny rule passed zap-42 and proxy integration test proxy-it-8. "
            "F-104 downgraded to high but remains open; owner identity-platform must complete prod retest using authz-replay-31 by 2026-06-09. "
            "Opened F-106 low audit log clock skew, evidence ntp-check-2."
        ),
        facts=(
            Fact("F-102", "resolved", "none", "appsec", "zap-42 proxy-it-8", "IMDS egress deny rule passed retest."),
            Fact("F-104", "open", "high", "identity-platform", "authz-replay-31", "Mitigation reduced impact, but prod retest remains due 2026-06-09."),
            Fact("F-106", "open", "low", "secops", "ntp-check-2", "Audit log clock skew remains low priority."),
        ),
    ),
)


PROBES: Sequence[Probe] = (
    Probe(
        question="Which high-or-critical security issues are currently open?",
        required_terms=("F-104", "open", "high", "identity-platform"),
        forbidden_terms=("F-101 status=open", "F-102 status=open", "F-103 status=open", "GITHUB_TOKEN_FAKE"),
    ),
    Probe(
        question="What is the current status of SSRF finding F-102?",
        required_terms=("F-102", "resolved", "zap-42"),
        forbidden_terms=("still open high", "zap-17", "zap-31"),
    ),
    Probe(
        question="Which scanner finding was a false positive and why?",
        required_terms=("F-103", "false_positive", "mTLS", "client certificate"),
        forbidden_terms=("F-103 status=open",),
    ),
    Probe(
        question="Who owns F-104 and what evidence remains?",
        required_terms=("identity-platform", "authz-replay-31", "prod retest"),
        forbidden_terms=("authz-replay-12",),
    ),
    Probe(
        question="Should the old GitHub token value be shown in the report?",
        required_terms=("redacted", "raw token"),
        forbidden_terms=("GITHUB_TOKEN_FAKE",),
    ),
    Probe(
        question="What low-priority issue remains?",
        required_terms=("F-106", "open", "low", "clock skew"),
        forbidden_terms=(),
    ),
)


CHECKPOINT_PROBES: Sequence[tuple[str, Probe]] = (
    (
        "s1-initial-review",
        Probe(
            question="After session 1, which high-or-critical findings are open?",
            required_terms=("F-101", "critical", "F-102", "high"),
            forbidden_terms=("F-103 false_positive", "F-104"),
        ),
    ),
    (
        "s2-triage-and-retTest",
        Probe(
            question="After session 2, what remediation and false-positive decisions are current?",
            required_terms=("F-101", "resolved", "F-103", "false_positive", "client certificate"),
            forbidden_terms=("F-101 status=open", "GITHUB_TOKEN_FAKE"),
        ),
    ),
    (
        "s3-follow-up-review",
        Probe(
            question="After session 3, which critical finding is current and what remains open?",
            required_terms=("F-104", "critical", "authz-replay-12", "F-102", "open", "zap-31"),
            forbidden_terms=("F-101 status=open", "F-103 status=open", "GITHUB_TOKEN_FAKE"),
        ),
    ),
    (
        "s4-remediation-review",
        Probe(
            question="After session 4, which findings are current after remediation?",
            required_terms=("F-102", "resolved", "zap-42", "F-104", "high", "authz-replay-31"),
            forbidden_terms=("F-102 status=open", "zap-31", "F-104 status=open severity=critical", "authz-replay-12"),
        ),
    ),
)


class MemoryBackend:
    """Common interface for deterministic memory backends."""

    name = "backend"

    def ingest(self, event: SessionEvent) -> None:
        """Store a session event in the backend."""
        raise NotImplementedError

    def retrieve(self, question: str) -> str:
        """Return the context that would be supplied to an answering agent."""
        raise NotImplementedError


class AppendOnlyLog(MemoryBackend):
    """Baseline that stores every raw observation forever."""

    name = "append_only_log"

    def __init__(self) -> None:
        """Create an empty raw transcript log."""
        self.records: List[str] = []

    def ingest(self, event: SessionEvent) -> None:
        """Append raw session text without normalization or redaction."""
        self.records.append(event.raw)

    def retrieve(self, question: str) -> str:
        """Return the complete historical transcript."""
        return "\n".join(self.records)


class RecentWindowLog(MemoryBackend):
    """Baseline that keeps only the most recent raw sessions."""

    name = "recent_window_log"

    def __init__(self, window_size: int = 2) -> None:
        """Create a sliding-window transcript log."""
        self.window_size = window_size
        self.records: List[str] = []

    def ingest(self, event: SessionEvent) -> None:
        """Append raw text and drop sessions outside the configured window."""
        self.records.append(event.raw)
        self.records = self.records[-self.window_size :]

    def retrieve(self, question: str) -> str:
        """Return the recent transcript window."""
        return "\n".join(self.records)


class PassiveGraphMemory(MemoryBackend):
    """Competitor-style fact graph that keeps historical states."""

    name = "passive_graph_memory"

    def __init__(self) -> None:
        """Create an empty finding timeline graph."""
        self.finding_histories: Dict[str, List[Fact]] = {}

    def ingest(self, event: SessionEvent) -> None:
        """Append each normalized fact as a historical graph node."""
        for fact in event.facts:
            self.finding_histories.setdefault(fact.finding_id, []).append(fact)

    def retrieve(self, question: str) -> str:
        """Return all fact nodes without active stale-state resolution."""
        rendered = ["passive graph memory returns historical fact nodes"]
        for finding_id in sorted(self.finding_histories):
            for fact in self.finding_histories[finding_id]:
                rendered.append(fact.render())
        return "\n".join(rendered)


class ActiveSecurityDigest(MemoryBackend):
    """Memanto-style digest that keeps latest facts and redacts secrets."""

    name = "active_security_digest"

    def __init__(self) -> None:
        """Create an empty active finding digest."""
        self.findings: Dict[str, Fact] = {}
        self.reporting_policy = "raw token values must stay redacted"

    def ingest(self, event: SessionEvent) -> None:
        """Merge normalized facts by finding id while preserving latest state."""
        for fact in event.facts:
            redacted_fact = Fact(
                finding_id=fact.finding_id,
                status=fact.status,
                severity=fact.severity,
                owner=fact.owner,
                evidence=fact.evidence,
                summary=redact_secrets(fact.summary),
            )
            self.findings[fact.finding_id] = redacted_fact

    def retrieve(self, question: str) -> str:
        """Return current policy and findings as compact review context."""
        rendered = [self.reporting_policy]
        rendered.extend(fact.render() for fact in sorted(self.findings.values(), key=lambda item: item.finding_id))
        return "\n".join(rendered)


def score_probe(context: str, probe: Probe) -> Dict[str, object]:
    """Score one probe against required terms, stale terms, and secret leaks."""
    lowered = context.lower()
    required_hits = [term for term in probe.required_terms if term.lower() in lowered]
    forbidden_hits = [term for term in probe.forbidden_terms if term.lower() in lowered]
    secret_leak = any(pattern.search(context) for pattern in SECRET_PATTERNS)
    passed = len(required_hits) == len(probe.required_terms) and not forbidden_hits and not secret_leak
    return {
        "question": probe.question,
        "passed": passed,
        "required_hits": required_hits,
        "missing_terms": [term for term in probe.required_terms if term not in required_hits],
        "forbidden_hits": forbidden_hits,
        "secret_leak": secret_leak,
        "retrieved_tokens": token_count(context),
    }


def percentile_95(values: Sequence[float]) -> float:
    """Return the inclusive p95 for a short deterministic latency sample."""
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=20, method="inclusive")[18]


def evaluate_backend(backend: MemoryBackend) -> Dict[str, object]:
    """Run all sessions and probes for one backend and compute metrics."""
    checkpoint_results: List[Dict[str, object]] = []

    for event in DATASET:
        backend.ingest(event)
        for session, probe in CHECKPOINT_PROBES:
            if session == event.session:
                checkpoint = score_probe(backend.retrieve(probe.question), probe)
                checkpoint["after_session"] = event.session
                checkpoint_results.append(checkpoint)

    probe_results: List[Dict[str, object]] = []
    latencies_ms: List[float] = []

    for probe in PROBES:
        started = time.perf_counter()
        context = backend.retrieve(probe.question)
        latencies_ms.append((time.perf_counter() - started) * 1000)
        probe_results.append(score_probe(context, probe))

    total = len(probe_results)
    passed = sum(1 for result in probe_results if result["passed"])
    token_values = [int(result["retrieved_tokens"]) for result in probe_results]
    forbidden_failures = sum(1 for result in probe_results if result["forbidden_hits"])
    secret_leaks = sum(1 for result in probe_results if result["secret_leak"])
    required_total = sum(len(probe.required_terms) for probe in PROBES)
    required_hit_total = sum(len(result["required_hits"]) for result in probe_results)

    avg_tokens = statistics.mean(token_values)
    signal_to_noise = required_hit_total / max(sum(token_values), 1)
    session_accuracy_curve = [
        {
            "after_session": result["after_session"],
            "accuracy": 1.0 if result["passed"] else 0.0,
        }
        for result in checkpoint_results
    ]
    checkpoint_accuracy = statistics.mean(point["accuracy"] for point in session_accuracy_curve) if session_accuracy_curve else 0.0

    return {
        "backend": backend.name,
        "accuracy": round(passed / total, 4),
        "avg_retrieved_tokens": round(avg_tokens, 2),
        "p95_latency_ms": round(percentile_95(latencies_ms), 4),
        "cross_session_degradation_rate": round(1.0 - checkpoint_accuracy, 4),
        "stale_conflict_rate": round(forbidden_failures / total, 4),
        "secret_leak_rate": round(secret_leaks / total, 4),
        "evidence_coverage": round(required_hit_total / required_total, 4),
        "signal_to_noise": round(signal_to_noise, 4),
        "session_accuracy_curve": session_accuracy_curve,
        "checkpoint_results": checkpoint_results,
        "probe_results": probe_results,
    }


def run_benchmark() -> Dict[str, object]:
    """Evaluate all memory backends for the security-review scenario."""
    backends: Iterable[MemoryBackend] = (
        ActiveSecurityDigest(),
        PassiveGraphMemory(),
        AppendOnlyLog(),
        RecentWindowLog(),
    )
    results = [evaluate_backend(backend) for backend in backends]
    return {
        "benchmark": "security-review-evidence-memory",
        "scenario": "Long-lived security review evidence with stale finding suppression and secret redaction",
        "probe_count": len(PROBES),
        "checkpoint_count": len(CHECKPOINT_PROBES),
        "session_count": len(DATASET),
        "results": results,
    }


def write_markdown(result: Dict[str, object], path: Path) -> None:
    """Write a compact Markdown table for benchmark results."""
    lines = [
        "# Security Review Evidence Memory Results",
        "",
        "| Backend | Accuracy | Avg Retrieved Tokens | p95 Latency ms | Cross-Session Degradation | Stale Conflict Rate | Secret Leak Rate | Evidence Coverage | Signal/Noise |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in result["results"]:
        lines.append(
            "| {backend} | {accuracy:.2%} | {avg_retrieved_tokens:.2f} | {p95_latency_ms:.4f} | "
            "{cross_session_degradation_rate:.2%} | {stale_conflict_rate:.2%} | {secret_leak_rate:.2%} | "
            "{evidence_coverage:.2%} | {signal_to_noise:.4f} |".format(**item)
        )
    lines.extend(["", "## Session Accuracy Curves", ""])
    for item in result["results"]:
        curve = ", ".join(
            f"{point['after_session']}={point['accuracy']:.0%}" for point in item["session_accuracy_curve"]
        )
        lines.append(f"- `{item['backend']}`: {curve}")
    lines.extend(
        [
            "",
            "The active security digest keeps current normalized facts, redacts synthetic secrets, and suppresses stale statuses.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    """Parse command-line output paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="examples/benchmarks/security-review-evidence-memory/results/sample_results.json",
        help="Path for JSON results.",
    )
    parser.add_argument(
        "--markdown",
        default="examples/benchmarks/security-review-evidence-memory/results/sample_results.md",
        help="Path for Markdown summary.",
    )
    return parser.parse_args()


def main() -> None:
    """Run the benchmark and write JSON plus Markdown outputs."""
    args = parse_args()
    result = run_benchmark()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    write_markdown(result, Path(args.markdown))
    print(json.dumps({item["backend"]: item["accuracy"] for item in result["results"]}, indent=2))


if __name__ == "__main__":
    main()
