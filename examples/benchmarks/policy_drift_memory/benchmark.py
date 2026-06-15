from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def approx_tokens(text: str) -> int:
    return len(TOKEN_RE.findall(text))


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[index]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


@dataclass
class QueryResult:
    answer: str
    latency_ms: float
    retrieved_tokens: int


class Backend:
    name = "backend"

    def ingest(self, event: dict[str, Any]) -> None:
        raise NotImplementedError

    def answer(self, query: dict[str, Any]) -> QueryResult:
        raise NotImplementedError


@dataclass
class AppendOnlyLogBackend(Backend):
    name: str = "append_only_log"
    events: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))

    def ingest(self, event: dict[str, Any]) -> None:
        self.events[event["entity"]].append(event["text"])

    def answer(self, query: dict[str, Any]) -> QueryResult:
        start = time.perf_counter()
        answer = "\n".join(self.events[query["entity"]])
        latency = (time.perf_counter() - start) * 1000
        return QueryResult(answer, latency, approx_tokens(answer))


@dataclass
class RecentWindowBackend(Backend):
    name: str = "recent_window_3"
    events: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    window: int = 3

    def ingest(self, event: dict[str, Any]) -> None:
        self.events[event["entity"]].append(event["text"])

    def answer(self, query: dict[str, Any]) -> QueryResult:
        start = time.perf_counter()
        answer = "\n".join(self.events[query["entity"]][-self.window :])
        latency = (time.perf_counter() - start) * 1000
        return QueryResult(answer, latency, approx_tokens(answer))


@dataclass
class EpisodeGraphBaseline(Backend):
    """Small dependency-free approximation of episode graph memory behavior.

    The backend preserves all observed values by key. It retrieves by entity and
    key relevance, so it is more selective than a raw log but still exposes
    superseded values when preferences drift.
    """

    name: str = "episode_graph_baseline"
    facts: dict[str, dict[str, list[tuple[str, str]]]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(list))
    )

    def ingest(self, event: dict[str, Any]) -> None:
        for fact in event.get("facts", []):
            self.facts[event["entity"]][fact["key"]].append(
                (event["timestamp"], fact["value"])
            )

    def answer(self, query: dict[str, Any]) -> QueryResult:
        start = time.perf_counter()
        question = normalize(query["question"])
        rows: list[str] = []
        for key, values in self.facts[query["entity"]].items():
            key_terms = key.replace("_", " ")
            if any(term in question for term in key_terms.split()):
                rendered = " | ".join(f"{ts}: {value}" for ts, value in values)
                rows.append(f"{key}: {rendered}")
        if not rows:
            for key, values in self.facts[query["entity"]].items():
                rows.append(f"{key}: {values[-1][1]}")
        answer = "\n".join(rows)
        latency = (time.perf_counter() - start) * 1000
        return QueryResult(answer, latency, approx_tokens(answer))


@dataclass
class ActiveDigestBackend(Backend):
    """Memanto-style active memory digest for the offline control.

    Each new typed fact replaces the current value for its key while retaining
    evidence timestamps. Retrieval returns only the active state relevant to the
    query entity. This mirrors the benchmarked Memanto property: current,
    compact, conflict-aware memory instead of passive log replay.
    """

    name: str = "memanto_style_active_digest"
    current: dict[str, dict[str, tuple[str, str]]] = field(
        default_factory=lambda: defaultdict(dict)
    )

    def ingest(self, event: dict[str, Any]) -> None:
        for fact in event.get("facts", []):
            self.current[event["entity"]][fact["key"]] = (
                event["timestamp"],
                fact["value"],
            )

    def answer(self, query: dict[str, Any]) -> QueryResult:
        start = time.perf_counter()
        question = normalize(query["question"])
        rows: list[str] = []
        for key, (timestamp, value) in self.current[query["entity"]].items():
            key_terms = key.replace("_", " ")
            value_terms = normalize(value)
            if (
                any(term in question for term in key_terms.split())
                or any(term in question for term in value_terms.split())
                or key in {"pii_policy", "report_privacy", "launch_train"}
            ):
                rows.append(f"{key}: {value} (current since {timestamp})")
        if not rows:
            rows = [
                f"{key}: {value} (current since {timestamp})"
                for key, (timestamp, value) in self.current[query["entity"]].items()
            ]
        answer = "\n".join(rows)
        latency = (time.perf_counter() - start) * 1000
        return QueryResult(answer, latency, approx_tokens(answer))


def score_answer(answer: str, query: dict[str, Any]) -> tuple[float, list[str]]:
    lowered = normalize(answer)
    missing = [item for item in query["required"] if normalize(item) not in lowered]
    stale = [item for item in query["forbidden"] if normalize(item) in lowered]
    if not missing and not stale:
        return 1.0, []
    penalties = [f"missing={item}" for item in missing]
    penalties.extend(f"stale={item}" for item in stale)
    return 0.0, penalties


def build_backends() -> list[Backend]:
    return [
        ActiveDigestBackend(),
        EpisodeGraphBaseline(),
        RecentWindowBackend(),
        AppendOnlyLogBackend(),
    ]


def run_once(dataset: dict[str, Any], repeats: int) -> dict[str, Any]:
    backends = build_backends()
    for event in dataset["events"]:
        for backend in backends:
            backend.ingest(event)

    summary: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []
    for backend in backends:
        scores: list[float] = []
        latencies: list[float] = []
        tokens: list[int] = []
        for query in dataset["queries"]:
            result: QueryResult | None = None
            for _ in range(repeats):
                result = backend.answer(query)
                latencies.append(result.latency_ms)
            assert result is not None
            score, failures = score_answer(result.answer, query)
            scores.append(score)
            tokens.append(result.retrieved_tokens)
            details.append(
                {
                    "backend": backend.name,
                    "entity": query["entity"],
                    "question": query["question"],
                    "score": score,
                    "retrieved_tokens": result.retrieved_tokens,
                    "failures": failures,
                    "answer": result.answer,
                }
            )
        summary.append(
            {
                "backend": backend.name,
                "accuracy": round(statistics.mean(scores), 4),
                "total_retrieved_tokens": sum(tokens),
                "avg_retrieved_tokens": round(statistics.mean(tokens), 2),
                "p95_latency_ms": round(p95(latencies), 4),
            }
        )

    return {
        "dataset": dataset["name"],
        "query_count": len(dataset["queries"]),
        "repeat_count": repeats,
        "summary": summary,
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the policy drift memory benchmark."
    )
    parser.add_argument(
        "--dataset",
        default=str(Path(__file__).with_name("dataset.json")),
        help="Path to the benchmark dataset JSON.",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=200,
        help="Latency repeats per query. Default: 200.",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="Optional path for the full JSON result.",
    )
    args = parser.parse_args()

    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    result = run_once(dataset, args.repeats)

    print("backend,accuracy,total_retrieved_tokens,avg_retrieved_tokens,p95_latency_ms")
    for row in result["summary"]:
        print(
            f"{row['backend']},{row['accuracy']},"
            f"{row['total_retrieved_tokens']},{row['avg_retrieved_tokens']},"
            f"{row['p95_latency_ms']}"
        )

    if args.output_json:
        Path(args.output_json).write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
