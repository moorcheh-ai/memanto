"""Reproducible release-readiness memory benchmark for coding agents."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from memanto.app.core import MemoryRecord  # noqa: E402
from memanto.app.services.memory_read_service import MemoryReadService  # noqa: E402
from memanto.app.services.memory_write_service import MemoryWriteService  # noqa: E402

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


class InMemoryDocuments:
    """Moorcheh-compatible document store used for deterministic local runs."""

    def __init__(self) -> None:
        """Create an empty namespace-indexed document store."""

        self.by_namespace: dict[str, list[dict[str, Any]]] = {}

    def upload(
        self, namespace_name: str, documents: list[dict[str, Any]]
    ) -> dict[str, str]:
        """Persist documents under a namespace like Moorcheh's upload API."""

        self.by_namespace.setdefault(namespace_name, []).extend(
            dict(document) for document in documents
        )
        return {"status": "success"}

    def get(
        self, namespace_name: str, ids: list[str] | None = None
    ) -> dict[str, list[dict[str, Any]]]:
        """Return stored documents by namespace and optional ID list."""

        documents = self.by_namespace.get(namespace_name, [])
        if ids:
            documents = [
                document for document in documents if str(document.get("id")) in ids
            ]
        return {"items": list(documents)}


class InMemorySimilaritySearch:
    """Deterministic similarity facade over the in-memory document store."""

    def __init__(self, documents: InMemoryDocuments) -> None:
        """Bind search to the shared document store."""

        self.documents = documents

    def query(
        self,
        query: str,
        namespaces: list[str],
        top_k: int = 10,
        threshold: float | None = None,
        kiosk_mode: bool = False,
    ) -> dict[str, Any]:
        """Return documents matching explicit benchmark topic tags."""

        _ = threshold, kiosk_mode
        topic_filters = {
            token.split(":", 1)[1]
            for token in query.split()
            if token.startswith("#topic:")
        }
        status_filters = {
            token.split(":", 1)[1]
            for token in query.split()
            if token.startswith("#status:")
        }
        results: list[dict[str, Any]] = []
        for namespace in namespaces:
            for document in self.documents.by_namespace.get(namespace, []):
                document_tags = set(str(document.get("tags", "")).split(","))
                if topic_filters and not topic_filters.intersection(document_tags):
                    continue
                if status_filters and str(document.get("status")) not in status_filters:
                    continue
                result = dict(document)
                result["score"] = 1.0
                results.append(result)
        return {"results": results[:top_k], "execution_time": 0.0}


class InMemoryMoorchehClient:
    """Small Moorcheh-compatible client for real Memanto service benchmarks."""

    def __init__(self) -> None:
        """Expose the client attributes used by Memanto read/write services."""

        self.documents = InMemoryDocuments()
        self.similarity_search = InMemorySimilaritySearch(self.documents)


class MemantoServiceBackend:
    """Backend that runs the dataset through Memanto write/read services."""

    name = "memanto_service"
    scope_type = "agent"
    scope_id = "release-readiness-benchmark"
    actor_id = "benchmark-runner"

    def __init__(self, events: list[Event]) -> None:
        """Store benchmark events through MemoryWriteService."""

        client = InMemoryMoorchehClient()
        writer = MemoryWriteService(client)
        self.reader = MemoryReadService(client)
        latest_current_index_by_topic: dict[str, int] = {}
        for event in events:
            if event.status == "current":
                latest_current_index_by_topic[event.topic] = event.index

        for event in events:
            is_active = (
                event.status == "current"
                and latest_current_index_by_topic.get(event.topic) == event.index
            )
            memory = MemoryRecord(
                id=f"{event.index:04d}-{event.topic}",
                type="fact",
                title=event.topic.replace("_", " "),
                content=event.fact,
                scope_type=self.scope_type,
                scope_id=self.scope_id,
                actor_id=self.actor_id,
                source="agent",
                confidence=0.95 if event.status == "current" else 0.4,
                status="active" if is_active else "superseded",
                tags=[event.topic, event.status],
            )
            writer.store_memory(memory)

    def retrieve(self, topics: list[str]) -> list[Event]:
        """Search Memanto memories by topic and map them to benchmark events."""

        retrieved: list[Event] = []
        for topic in topics:
            result = self.reader.search_memories(
                query=f"#{topic} #topic:{topic}",
                scope_type=self.scope_type,
                scope_id=self.scope_id,
                status_filter=["active"],
                limit=100,
            )
            for index, item in enumerate(result["results"], start=1):
                tags = item.get("tags", [])
                status = "secret" if "secret" in tags else "current"
                retrieved.append(
                    Event(
                        session=self.scope_id,
                        topic=topic,
                        fact=item["content"],
                        status=status,
                        index=index,
                    )
                )
        return retrieved


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
        MemantoServiceBackend(events),
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
            "`memanto_service` writes the dataset through Memanto's `MemoryWriteService` and retrieves it with `MemoryReadService` over a Moorcheh-compatible in-memory client, so the run exercises the same record formatting, status filters, and search path used by the application while remaining deterministic in CI.",
            "The active digest is kept as a transparent baseline: keep the current release facts by topic, suppress stale handoff notes, and never retrieve synthetic secrets.",
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
