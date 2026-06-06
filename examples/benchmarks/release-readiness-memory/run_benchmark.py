"""Deterministic release-readiness memory benchmark for coding agents."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = ROOT / "dataset.json"


@dataclass(frozen=True)
class Event:
    """A single memory event from an agent handoff stream."""

    session: str
    topic: str
    fact: str
    status: str
    index: int


def load_dataset(path: Path = DEFAULT_DATASET) -> dict:
    """Load the benchmark dataset from disk."""

    return json.loads(path.read_text(encoding="utf-8"))


def iter_events(dataset: dict) -> Iterable[Event]:
    """Yield events with stable chronological indexes."""

    index = 0
    for session in dataset["sessions"]:
        for event in session["events"]:
            index += 1
            yield Event(
                session=session["id"],
                topic=event["topic"],
                fact=event["fact"],
                status=event["status"],
                index=index,
            )


def token_count(text: str) -> int:
    """Approximate retrieved context tokens with whitespace tokens."""

    return len(text.split())


def p95(values: list[float]) -> float:
    """Return a deterministic p95 for small benchmark samples."""

    if not values:
        return 0.0
    ordered = sorted(values)
    position = max(0, round(0.95 * (len(ordered) - 1)))
    return ordered[position]


class AppendOnlyLog:
    """Baseline that retrieves every matching fact ever seen."""

    name = "append_only_log"

    def __init__(self, events: list[Event]) -> None:
        """Store the full chronological event stream."""

        self.events = events

    def retrieve(self, topics: list[str]) -> list[Event]:
        """Return every event whose topic was requested."""

        return [event for event in self.events if event.topic in topics]


class RecentWindowLog:
    """Baseline that retrieves only the last N matching facts."""

    name = "recent_window_log"

    def __init__(self, events: list[Event], window: int = 5) -> None:
        """Store the event stream and matching-topic window size."""

        self.events = events
        self.window = window

    def retrieve(self, topics: list[str]) -> list[Event]:
        """Return the most recent matching events in chronological order."""

        topic_set = set(topics)
        matches: list[Event] = []
        for event in reversed(self.events):
            if event.topic in topic_set:
                matches.append(event)
                if len(matches) == self.window:
                    break
        return list(reversed(matches))


class ActiveReleaseDigest:
    """Memanto-style active digest that keeps current facts and suppresses secrets."""

    name = "active_release_digest"

    def __init__(self, events: list[Event]) -> None:
        """Build a current-fact digest while ignoring secret events."""

        self.current_by_topic: dict[str, Event] = {}
        for event in events:
            if event.status == "secret":
                continue
            if event.status == "current":
                self.current_by_topic[event.topic] = event

    def retrieve(self, topics: list[str]) -> list[Event]:
        """Return current non-secret facts for the requested topics."""

        return [
            self.current_by_topic[topic]
            for topic in topics
            if topic in self.current_by_topic
        ]


def score_query(query: dict, retrieved: list[Event]) -> dict:
    """Score one query against required and forbidden evidence."""

    context = " ".join(event.fact for event in retrieved)
    lowered = context.lower()
    found = [
        phrase
        for phrase in query["must_include"]
        if phrase.lower() in lowered
    ]
    forbidden = [
        phrase
        for phrase in query["must_not_include"]
        if phrase.lower() in lowered
    ]
    stale_events = [event.fact for event in retrieved if event.status == "stale"]
    secret_events = [event.fact for event in retrieved if event.status == "secret"]
    passed = len(found) == len(query["must_include"]) and not forbidden
    return {
        "query_id": query["id"],
        "passed": passed,
        "required_found": found,
        "forbidden_found": forbidden,
        "retrieved_tokens": token_count(context),
        "retrieved_events": [event.fact for event in retrieved],
        "stale_conflicts": stale_events,
        "secret_leaks": secret_events,
    }


def evaluate_backend(name: str, backend: object, queries: list[dict]) -> dict:
    """Evaluate one backend over all queries."""

    query_results = []
    latencies_ms = []
    for query in queries:
        start = time.perf_counter()
        retrieved = backend.retrieve(query["topics"])
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies_ms.append(elapsed_ms)
        query_results.append(score_query(query, retrieved))

    total = len(query_results)
    passed = sum(1 for result in query_results if result["passed"])
    total_tokens = sum(result["retrieved_tokens"] for result in query_results)
    stale_conflicts = sum(len(result["stale_conflicts"]) for result in query_results)
    secret_leaks = sum(len(result["secret_leaks"]) for result in query_results)
    return {
        "backend": name,
        "accuracy": round(passed / total, 4),
        "passed": passed,
        "total": total,
        "avg_retrieved_tokens": round(total_tokens / total, 2),
        "total_retrieved_tokens": total_tokens,
        "p95_latency_ms": round(p95(latencies_ms), 4),
        "mean_latency_ms": round(statistics.fmean(latencies_ms), 4),
        "stale_conflict_rate": round(stale_conflicts / total, 4),
        "secret_leak_rate": round(secret_leaks / total, 4),
        "query_results": query_results,
    }


def run(dataset_path: Path = DEFAULT_DATASET) -> dict:
    """Run the benchmark and return a structured result document."""

    dataset = load_dataset(dataset_path)
    events = list(iter_events(dataset))
    backends = [
        ActiveReleaseDigest(events),
        AppendOnlyLog(events),
        RecentWindowLog(events, window=1),
    ]
    results = [
        evaluate_backend(backend.name, backend, dataset["queries"])
        for backend in backends
    ]
    return {
        "benchmark": dataset["name"],
        "dataset": {
            "sessions": len(dataset["sessions"]),
            "events": len(events),
            "queries": len(dataset["queries"]),
        },
        "results": results,
    }


def write_markdown(report: dict, path: Path) -> None:
    """Write a compact benchmark summary for PR reviewers."""

    lines = [
        "# Release Readiness Memory Benchmark Results",
        "",
        "| Backend | Accuracy | Avg retrieved tokens | p95 latency ms | Stale conflict rate | Secret leak rate |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in report["results"]:
        lines.append(
            "| {backend} | {accuracy:.1%} | {avg_retrieved_tokens} | {p95_latency_ms} | {stale_conflict_rate:.1%} | {secret_leak_rate:.1%} |".format(
                **result
            )
        )
    lines.extend(
        [
            "",
            "The active digest represents a Memanto-style strategy: keep the current release facts by topic, suppress stale handoff notes, and never retrieve synthetic secrets.",
            "The append-only and recent-window baselines model common memory shortcuts that either over-retrieve stale state or miss older still-current constraints.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    """CLI entrypoint."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()

    report = run(args.dataset)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        write_markdown(report, args.markdown)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
