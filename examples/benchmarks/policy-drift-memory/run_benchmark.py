"""Run a deterministic benchmark for policy-drift memory retrieval behavior."""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_EVENTS = ROOT / "data" / "policy_events.json"
DEFAULT_QUERIES = ROOT / "data" / "golden_queries.json"

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "be",
    "current",
    "does",
    "for",
    "how",
    "in",
    "is",
    "now",
    "of",
    "only",
    "should",
    "still",
    "the",
    "to",
    "what",
    "where",
}
SECRET_PATTERNS = (
    re.compile(r"TOKEN-[A-Z0-9-]+"),
    re.compile(r"\b[0-9]+k internal budget\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class PolicyEvent:
    """Single policy-memory event used as benchmark corpus input."""

    id: str
    turn: int
    session: str
    scope: str
    key: str
    status: str
    statement: str
    tags: tuple[str, ...]
    supersedes: tuple[str, ...]
    sensitivity: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> PolicyEvent:
        """Create a policy event from the JSON fixture shape."""
        return cls(
            id=raw["id"],
            turn=int(raw["turn"]),
            session=raw["session"],
            scope=raw["scope"],
            key=raw["key"],
            status=raw["status"],
            statement=raw["statement"],
            tags=tuple(raw.get("tags", ())),
            supersedes=tuple(raw.get("supersedes", ())),
            sensitivity=raw.get("sensitivity", "normal"),
        )


@dataclass(frozen=True)
class GoldenQuery:
    """Expected retrieval behavior for one benchmark question."""

    id: str
    question: str
    tags: tuple[str, ...]
    required_event_ids: frozenset[str]
    forbidden_event_ids: frozenset[str]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> GoldenQuery:
        """Create a golden query from the JSON fixture shape."""
        return cls(
            id=raw["id"],
            question=raw["question"],
            tags=tuple(raw.get("tags", ())),
            required_event_ids=frozenset(raw.get("required_event_ids", ())),
            forbidden_event_ids=frozenset(raw.get("forbidden_event_ids", ())),
        )


@dataclass(frozen=True)
class RetrievedEvent:
    """Policy event text returned by a backend retrieval pass."""

    event: PolicyEvent
    text: str


@dataclass(frozen=True)
class Retrieval:
    """Backend retrieval result plus deterministic cost proxies."""

    items: tuple[RetrievedEvent, ...]
    scanned_tokens: int
    retrieved_tokens: int
    latency_proxy_ms: float


def load_events(path: Path = DEFAULT_EVENTS) -> list[PolicyEvent]:
    """Load policy events from a JSON fixture file."""
    raw_events = json.loads(path.read_text(encoding="utf-8"))
    return [PolicyEvent.from_dict(raw) for raw in raw_events]


def load_queries(path: Path = DEFAULT_QUERIES) -> list[GoldenQuery]:
    """Load golden queries from a JSON fixture file."""
    raw_queries = json.loads(path.read_text(encoding="utf-8"))
    return [GoldenQuery.from_dict(raw) for raw in raw_queries]


def tokenize(text: str) -> list[str]:
    """Tokenize benchmark text into comparable non-stopword terms."""
    return [
        token
        for token in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", text.lower())
        if token not in STOPWORDS
    ]


def token_count(text: str) -> int:
    """Count benchmark tokens after applying the shared tokenizer."""
    return len(tokenize(text))


def event_terms(event: PolicyEvent) -> set[str]:
    """Return searchable terms derived from a policy event."""
    terms = set(tokenize(event.statement))
    terms.update(tokenize(event.key.replace(".", " ")))
    terms.update(tokenize(event.scope))
    terms.update(event.tags)
    return terms


def query_terms(query: GoldenQuery) -> set[str]:
    """Return searchable terms derived from a golden query."""
    terms = set(tokenize(query.question))
    terms.update(query.tags)
    return terms


def relevance_score(event: PolicyEvent, query: GoldenQuery) -> int:
    """Score how strongly a policy event matches a query."""
    tag_score = len(set(event.tags).intersection(query.tags)) * 5
    term_score = len(event_terms(event).intersection(query_terms(query)))
    return tag_score + term_score


def redact_secret_text(text: str) -> str:
    """Replace benchmark secret patterns with a redaction marker."""
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[redacted]", redacted)
    return redacted


def contains_unredacted_secret(text: str) -> bool:
    """Check whether text still contains a benchmark secret pattern."""
    return redact_secret_text(text) != text


def dataset_path_label(path: Path) -> str:
    """Format dataset paths relative to the benchmark root when possible."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        try:
            return str(path.resolve().relative_to(ROOT))
        except ValueError:
            return str(path)


def percentile(values: list[float], pct: float) -> float:
    """Return the nearest-rank percentile for deterministic metric output."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil((pct / 100.0) * len(ordered)) - 1)
    return ordered[index]


class MemoryBackend:
    """Common interface for benchmark memory retrieval strategies."""

    name = "base"
    description = ""

    def __init__(self) -> None:
        """Initialize an empty backend corpus."""
        self.events: list[PolicyEvent] = []

    def ingest(self, events: list[PolicyEvent]) -> None:
        """Load policy events in chronological order."""
        self.events = sorted(events, key=lambda event: event.turn)

    @property
    def stored_tokens(self) -> int:
        """Return the number of tokens retained after ingestion."""
        return sum(token_count(event.statement) for event in self.events)

    def retrieve(self, query: GoldenQuery) -> Retrieval:
        """Retrieve policy events relevant to a golden query."""
        raise NotImplementedError

    def _build_retrieval(
        self,
        candidates: list[PolicyEvent],
        matches: list[RetrievedEvent],
    ) -> Retrieval:
        """Build a retrieval result with deterministic cost metrics."""
        scanned_tokens = sum(token_count(event.statement) for event in candidates)
        retrieved_tokens = sum(token_count(item.text) for item in matches)
        latency_proxy_ms = round(
            1.75 + (0.045 * scanned_tokens) + (0.02 * retrieved_tokens),
            3,
        )
        return Retrieval(
            items=tuple(matches),
            scanned_tokens=scanned_tokens,
            retrieved_tokens=retrieved_tokens,
            latency_proxy_ms=latency_proxy_ms,
        )


class AppendOnlyLog(MemoryBackend):
    """Baseline backend that searches all historical policy events."""

    name = "append_only_log"
    description = "Passive full-corpus retrieval without stale fact suppression."

    def retrieve(self, query: GoldenQuery) -> Retrieval:
        """Return every matching historical policy event."""
        scored = [
            (relevance_score(event, query), event)
            for event in self.events
            if relevance_score(event, query) > 0
        ]
        scored.sort(key=lambda pair: (-pair[0], pair[1].turn))
        matches = [
            RetrievedEvent(event=event, text=event.statement) for _, event in scored
        ]
        return self._build_retrieval(self.events, matches)


class RecentWindowLog(MemoryBackend):
    """Baseline backend that searches only the most recent events."""

    name = "recent_window_log"
    description = "Recent-window baseline with lower context but no durable state."

    def __init__(self, window_size: int = 7) -> None:
        """Initialize a fixed-size recent event window."""
        super().__init__()
        self.window_size = window_size

    @property
    def stored_tokens(self) -> int:
        """Return tokens retained in the recent event window."""
        return sum(
            token_count(event.statement) for event in self.events[-self.window_size :]
        )

    def retrieve(self, query: GoldenQuery) -> Retrieval:
        """Return matching policy events from the recent window."""
        candidates = self.events[-self.window_size :]
        scored = [
            (relevance_score(event, query), event)
            for event in candidates
            if relevance_score(event, query) > 0
        ]
        scored.sort(key=lambda pair: (-pair[0], pair[1].turn))
        matches = [
            RetrievedEvent(event=event, text=event.statement) for _, event in scored
        ]
        return self._build_retrieval(candidates, matches)


class MemantoActiveDigest(MemoryBackend):
    """Benchmark backend that keeps current facts and redacts secrets."""

    name = "memanto_active_digest"
    description = (
        "Active current-state digest with supersession and sensitive-fact redaction."
    )

    def __init__(self) -> None:
        """Initialize active-state storage."""
        super().__init__()
        self.active_events: list[PolicyEvent] = []

    def ingest(self, events: list[PolicyEvent]) -> None:
        """Keep the latest non-superseded event for each policy key."""
        super().ingest(events)
        superseded: set[str] = set()
        for event in self.events:
            superseded.update(event.supersedes)

        latest_by_key: dict[str, PolicyEvent] = {}
        for event in self.events:
            if event.id in superseded:
                continue
            latest_by_key[event.key] = event
        self.active_events = sorted(latest_by_key.values(), key=lambda item: item.turn)

    @property
    def stored_tokens(self) -> int:
        """Return tokens retained after active-state redaction."""
        return sum(
            token_count(redact_secret_text(event.statement))
            for event in self.active_events
        )

    def retrieve(self, query: GoldenQuery) -> Retrieval:
        """Return matching active policy facts with secrets redacted."""
        scored = [
            (relevance_score(event, query), event)
            for event in self.active_events
            if relevance_score(event, query) > 0
        ]
        scored.sort(key=lambda pair: (-pair[0], pair[1].turn))
        matches = [
            RetrievedEvent(event=event, text=redact_secret_text(event.statement))
            for _, event in scored
        ]
        return self._build_retrieval(self.active_events, matches)


def evaluate_backend(
    backend: MemoryBackend,
    events: list[PolicyEvent],
    queries: list[GoldenQuery],
) -> dict[str, Any]:
    """Evaluate one backend against the full query set."""
    backend.ingest(events)
    corpus_tokens = sum(token_count(event.statement) for event in events)
    query_results: list[dict[str, Any]] = []

    for query in queries:
        retrieval = backend.retrieve(query)
        retrieved_ids = {item.event.id for item in retrieval.items}
        forbidden = retrieved_ids.intersection(query.forbidden_event_ids)
        missing = query.required_event_ids.difference(retrieved_ids)
        sensitive = [
            item.event.id
            for item in retrieval.items
            if item.event.sensitivity == "secret"
            and contains_unredacted_secret(item.text)
        ]
        passed = not missing and not forbidden and not sensitive
        query_results.append(
            {
                "query_id": query.id,
                "passed": passed,
                "retrieved_event_ids": [item.event.id for item in retrieval.items],
                "missing_required_event_ids": sorted(missing),
                "forbidden_event_ids_retrieved": sorted(forbidden),
                "sensitive_event_ids_retrieved": sensitive,
                "retrieved_tokens": retrieval.retrieved_tokens,
                "scanned_tokens": retrieval.scanned_tokens,
                "latency_proxy_ms": retrieval.latency_proxy_ms,
            }
        )

    total_queries = len(query_results)
    passed_count = sum(1 for result in query_results if result["passed"])
    stale_count = sum(
        1 for result in query_results if result["forbidden_event_ids_retrieved"]
    )
    leak_count = sum(
        1 for result in query_results if result["sensitive_event_ids_retrieved"]
    )
    latencies = [result["latency_proxy_ms"] for result in query_results]
    retrieved_tokens = [result["retrieved_tokens"] for result in query_results]

    return {
        "name": backend.name,
        "description": backend.description,
        "metrics": {
            "accuracy": round(passed_count / total_queries, 4),
            "passed_queries": passed_count,
            "total_queries": total_queries,
            "stale_conflict_rate": round(stale_count / total_queries, 4),
            "sensitive_leak_rate": round(leak_count / total_queries, 4),
            "corpus_tokens_ingested": corpus_tokens,
            "stored_tokens_after_ingest": backend.stored_tokens,
            "avg_retrieved_tokens": round(mean(retrieved_tokens), 2),
            "p95_latency_proxy_ms": percentile(latencies, 95),
        },
        "queries": query_results,
    }


def run_benchmark(
    events_path: Path = DEFAULT_EVENTS,
    queries_path: Path = DEFAULT_QUERIES,
) -> dict[str, Any]:
    """Run all benchmark backends and return a JSON-serializable report."""
    events = load_events(events_path)
    queries = load_queries(queries_path)
    backends: list[MemoryBackend] = [
        MemantoActiveDigest(),
        AppendOnlyLog(),
        RecentWindowLog(),
    ]
    return {
        "benchmark": "policy-drift-memory",
        "version": 1,
        "dataset": {
            "events": len(events),
            "queries": len(queries),
            "source_events": dataset_path_label(events_path),
            "source_queries": dataset_path_label(queries_path),
        },
        "backends": [
            evaluate_backend(backend, events, queries) for backend in backends
        ],
    }


def format_markdown(report: dict[str, Any]) -> str:
    """Render a benchmark report as a markdown summary table."""
    lines = [
        "# Policy Drift Memory Benchmark Results",
        "",
        "| Backend | Accuracy | Stale conflicts | Sensitive leaks | "
        "Avg retrieved tokens | Stored tokens | p95 latency proxy |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for backend in report["backends"]:
        metrics = backend["metrics"]
        lines.append(
            "| {name} | {accuracy:.1%} | {stale:.1%} | {leak:.1%} | "
            "{avg_tokens:.2f} | {stored_tokens} | {p95:.3f} ms |".format(
                name=backend["name"],
                accuracy=metrics["accuracy"],
                stale=metrics["stale_conflict_rate"],
                leak=metrics["sensitive_leak_rate"],
                avg_tokens=metrics["avg_retrieved_tokens"],
                stored_tokens=metrics["stored_tokens_after_ingest"],
                p95=metrics["p95_latency_proxy_ms"],
            )
        )
    lines.extend(
        [
            "",
            "The latency number is a deterministic proxy computed from scanned and "
            "retrieved token counts; it is not wall-clock timing.",
            "",
        ]
    )
    return "\n".join(lines)


def write_text(path: Path, content: str) -> None:
    """Write text to a path, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> None:
    """Parse CLI options, run the benchmark, and emit requested outputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()

    report = run_benchmark(args.events, args.queries)
    markdown = format_markdown(report)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.markdown:
        write_text(args.markdown, markdown)

    print(markdown)


if __name__ == "__main__":
    main()
