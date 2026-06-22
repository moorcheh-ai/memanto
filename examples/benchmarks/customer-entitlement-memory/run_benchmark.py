#!/usr/bin/env python3
"""Deterministic customer entitlement memory benchmark.

The benchmark compares three retrieval strategies on the same support timeline:

* active_entitlement_digest: a Memanto-style current-state digest that
  supersedes stale facts and redacts private facts.
* append_only_log: an append-only memory that retrieves every matching
  historical fact.
* recent_window_log: a recency window that retrieves only the newest events.

It is intentionally credential-free so maintainers can run it in CI without
Moorcheh, LLM, or external service keys.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_FIXTURE = ROOT / "fixtures" / "customer_timeline.json"


@dataclass(frozen=True)
class Fact:
    event_id: str
    date: str
    key: str
    scope: str
    value: str
    exposable: bool
    redaction: str | None = None

    @property
    def identity(self) -> tuple[str, str]:
        return (self.key, self.scope)

    def exposed_value(self) -> str:
        if self.exposable:
            return self.value
        return self.redaction or "private fact exists but must not be surfaced"

    def render(self) -> str:
        return (
            f"{self.key}[{self.scope}] = {self.exposed_value()} "
            f"(evidence: {self.event_id}, {self.date})"
        )


@dataclass(frozen=True)
class Query:
    query_id: str
    question: str
    lookups: tuple[tuple[str, str], ...]
    must_include: tuple[str, ...]
    must_not_include: tuple[str, ...]
    gold_evidence: tuple[str, ...]


@dataclass(frozen=True)
class Retrieval:
    backend: str
    query: Query
    answer: str
    evidence_ids: tuple[str, ...]
    retrieved_token_count: int
    scanned_token_count: int
    latency_proxy_ms: float


class MemoryBackend:
    name = "base"

    def __init__(self, facts: list[Fact]) -> None:
        self.facts = facts

    def answer(self, query: Query) -> Retrieval:
        selected, scanned = self.retrieve(query)
        if selected:
            rendered = "; ".join(fact.render() for fact in selected)
            answer = f"{query.question} {rendered}"
        else:
            answer = f"{query.question} No publishable memory found."
        evidence_ids = tuple(dict.fromkeys(fact.event_id for fact in selected))
        retrieved_tokens = estimate_tokens(answer)
        scanned_tokens = sum(estimate_tokens(fact.render()) for fact in scanned)
        return Retrieval(
            backend=self.name,
            query=query,
            answer=answer,
            evidence_ids=evidence_ids,
            retrieved_token_count=retrieved_tokens,
            scanned_token_count=scanned_tokens,
            latency_proxy_ms=self.latency_proxy_ms(scanned_tokens, retrieved_tokens),
        )

    def retrieve(self, query: Query) -> tuple[list[Fact], list[Fact]]:
        raise NotImplementedError

    def latency_proxy_ms(self, scanned_tokens: int, retrieved_tokens: int) -> float:
        # Deterministic CI-safe proxy: a small base cost plus per-token scan and
        # answer assembly costs. This avoids pretending that network-free sample
        # timings are production latency.
        return round(2.0 + scanned_tokens * 0.035 + retrieved_tokens * 0.015, 3)


class ActiveEntitlementDigest(MemoryBackend):
    name = "active_entitlement_digest"

    def __init__(self, facts: list[Fact]) -> None:
        super().__init__(facts)
        current: dict[tuple[str, str], Fact] = {}
        for fact in facts:
            current[fact.identity] = fact
        self.current = current

    def retrieve(self, query: Query) -> tuple[list[Fact], list[Fact]]:
        selected = [
            self.current[lookup]
            for lookup in query.lookups
            if lookup in self.current
        ]
        return selected, selected


class AppendOnlyLog(MemoryBackend):
    name = "append_only_log"

    def retrieve(self, query: Query) -> tuple[list[Fact], list[Fact]]:
        lookups = set(query.lookups)
        selected = [fact for fact in self.facts if fact.identity in lookups]
        return selected, self.facts


class RecentWindowLog(MemoryBackend):
    name = "recent_window_log"

    def __init__(self, facts: list[Fact], window_events: int = 3) -> None:
        super().__init__(facts)
        event_order = list(dict.fromkeys(fact.event_id for fact in facts))
        self.allowed_events = set(event_order[-window_events:])

    def retrieve(self, query: Query) -> tuple[list[Fact], list[Fact]]:
        lookups = set(query.lookups)
        scanned = [fact for fact in self.facts if fact.event_id in self.allowed_events]
        selected = [fact for fact in scanned if fact.identity in lookups]
        return selected, scanned


def estimate_tokens(text: str) -> int:
    # Stable approximation used for relative footprint, not provider billing.
    return max(1, math.ceil(len(text) / 4))


def load_fixture(path: Path) -> tuple[dict[str, Any], list[Fact], list[Query]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    facts: list[Fact] = []
    for event in raw["events"]:
        for fact in event["facts"]:
            facts.append(
                Fact(
                    event_id=event["id"],
                    date=event["date"],
                    key=fact["key"],
                    scope=fact["scope"],
                    value=fact["value"],
                    exposable=fact.get("exposable", True),
                    redaction=fact.get("redaction"),
                )
            )
    queries = [
        Query(
            query_id=item["id"],
            question=item["question"],
            lookups=tuple((lookup["key"], lookup["scope"]) for lookup in item["lookups"]),
            must_include=tuple(item["must_include"]),
            must_not_include=tuple(item["must_not_include"]),
            gold_evidence=tuple(item["gold_evidence"]),
        )
        for item in raw["queries"]
    ]
    return raw, facts, queries


def score_retrieval(retrieval: Retrieval) -> dict[str, Any]:
    answer_lower = retrieval.answer.lower()
    includes = [
        phrase
        for phrase in retrieval.query.must_include
        if phrase.lower() in answer_lower
    ]
    forbidden = [
        phrase
        for phrase in retrieval.query.must_not_include
        if phrase.lower() in answer_lower
    ]
    evidence_hits = [
        evidence
        for evidence in retrieval.query.gold_evidence
        if evidence in retrieval.evidence_ids
    ]
    passed = (
        len(includes) == len(retrieval.query.must_include)
        and not forbidden
        and len(evidence_hits) == len(retrieval.query.gold_evidence)
    )
    return {
        "query_id": retrieval.query.query_id,
        "question": retrieval.query.question,
        "passed": passed,
        "included_required": includes,
        "forbidden_hits": forbidden,
        "evidence_hits": evidence_hits,
        "evidence_ids": list(retrieval.evidence_ids),
        "retrieved_tokens": retrieval.retrieved_token_count,
        "scanned_tokens": retrieval.scanned_token_count,
        "latency_proxy_ms": retrieval.latency_proxy_ms,
        "answer": retrieval.answer,
    }


def summarize_backend(name: str, scored: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(scored)
    passed = sum(1 for row in scored if row["passed"])
    stale_conflicts = sum(1 for row in scored if row["forbidden_hits"])
    retrieved_tokens = [row["retrieved_tokens"] for row in scored]
    scanned_tokens = [row["scanned_tokens"] for row in scored]
    latencies = [row["latency_proxy_ms"] for row in scored]
    return {
        "backend": name,
        "accuracy": round(passed / total, 4),
        "passed": passed,
        "total": total,
        "stale_conflict_rate": round(stale_conflicts / total, 4),
        "avg_retrieved_tokens": round(statistics.mean(retrieved_tokens), 2),
        "avg_scanned_tokens": round(statistics.mean(scanned_tokens), 2),
        "p95_latency_proxy_ms": percentile(latencies, 95),
    }


def percentile(values: list[float], pct: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = math.ceil((pct / 100) * len(ordered)) - 1
    return round(ordered[max(0, min(index, len(ordered) - 1))], 3)


def run_benchmark(fixture_path: Path) -> dict[str, Any]:
    raw, facts, queries = load_fixture(fixture_path)
    backends: list[MemoryBackend] = [
        ActiveEntitlementDigest(facts),
        AppendOnlyLog(facts),
        RecentWindowLog(facts),
    ]
    by_backend: dict[str, list[dict[str, Any]]] = {}
    summaries = []
    for backend in backends:
        scored = [score_retrieval(backend.answer(query)) for query in queries]
        by_backend[backend.name] = scored
        summaries.append(summarize_backend(backend.name, scored))

    return {
        "benchmark": "customer-entitlement-memory",
        "fixture_version": raw["fixture_version"],
        "account": raw["account"],
        "methodology": {
            "token_metric": "ceil(character_count / 4), deterministic relative footprint",
            "latency_metric": "deterministic proxy in milliseconds from scanned and retrieved tokens",
            "accuracy_metric": "required phrases present, forbidden stale/private phrases absent, and gold evidence returned",
            "network_or_llm_calls": 0,
        },
        "summary": summaries,
        "results": by_backend,
    }


def to_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Customer Entitlement Memory Benchmark",
        "",
        f"Fixture version: `{result['fixture_version']}`",
        f"Account: `{result['account']}`",
        "",
        "## Summary",
        "",
        "| Backend | Accuracy | Passed | Stale conflict rate | Avg retrieved tokens | Avg scanned tokens | p95 latency proxy (ms) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in result["summary"]:
        lines.append(
            "| {backend} | {accuracy:.0%} | {passed}/{total} | {stale:.0%} | "
            "{retrieved:.2f} | {scanned:.2f} | {latency:.3f} |".format(
                backend=row["backend"],
                accuracy=row["accuracy"],
                passed=row["passed"],
                total=row["total"],
                stale=row["stale_conflict_rate"],
                retrieved=row["avg_retrieved_tokens"],
                scanned=row["avg_scanned_tokens"],
                latency=row["p95_latency_proxy_ms"],
            )
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The active entitlement digest keeps one current fact per key and scope, "
            "so it preserves long-lived facts like SSO and SLA while suppressing "
            "stale billing, escalation, beta, and compliance states.",
            "",
            "The append-only log retains full history but surfaces stale and private "
            "facts. The recent-window log avoids some stale history, but it forgets "
            "older facts that are still operationally current.",
            "",
            "## Per-query Failures",
            "",
        ]
    )

    for backend, rows in result["results"].items():
        failures = [row for row in rows if not row["passed"]]
        lines.append(f"### {backend}")
        if not failures:
            lines.append("")
            lines.append("No failures.")
            lines.append("")
            continue
        lines.append("")
        for row in failures:
            lines.append(
                "- `{}`: forbidden={}, evidence={}, answer={}".format(
                    row["query_id"],
                    row["forbidden_hits"],
                    row["evidence_hits"],
                    row["answer"],
                )
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()

    result = run_benchmark(args.fixture)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(to_markdown(result), encoding="utf-8")
    if not args.output and not args.markdown:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
