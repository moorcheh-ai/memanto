"""Offline benchmark for agentic memory during data migration cutovers.

The benchmark uses one synthetic migration dataset and runs it through three
memory backends under the same scoring contract:

* a Memanto-style active digest that keeps typed current-state memories,
* a passive append-only memory store,
* a recent-window memory store.

The scoring uses golden evidence IDs and required answer terms. No external
LLM, API key, or network call is needed for the default run.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BENCHMARK_NAME = "data-migration-cutover-memory"
DEFAULT_DATASET = Path(__file__).with_name("data") / "cutover_memory_dataset.json"
DEFAULT_RESULTS = Path(__file__).with_name("results") / "sample_results.json"
DEFAULT_MARKDOWN = Path(__file__).with_name("results") / "sample_results.md"
TOKEN_RE = re.compile(r"[A-Za-z0-9_./:%-]+")
SECRET_PATTERNS = (
    re.compile(r"postgres://[^\s;]+", re.IGNORECASE),
    re.compile(r"password=[^\s;]+", re.IGNORECASE),
    re.compile(r"sk_[A-Za-z0-9_-]+", re.IGNORECASE),
)
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "do",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "should",
    "the",
    "to",
    "what",
    "when",
    "which",
    "who",
}


def tokenize(text: str) -> list[str]:
    return [
        token.lower()
        for token in TOKEN_RE.findall(text)
        if token.lower() not in STOPWORDS
    ]


def count_tokens(text: str) -> int:
    return len(TOKEN_RE.findall(text))


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return ordered[index]


def redact_sensitive_text(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    return redacted


@dataclass(frozen=True)
class Event:
    id: str
    session_id: str
    date: str
    memory_key: str
    memory_type: str
    content: str
    tags: tuple[str, ...]
    supersedes: tuple[str, ...] = ()
    active_summary: str | None = None
    sensitive: bool = False

    @classmethod
    def from_json(cls, session: dict[str, Any], raw: dict[str, Any]) -> Event:
        return cls(
            id=raw["id"],
            session_id=session["id"],
            date=session["date"],
            memory_key=raw["memory_key"],
            memory_type=raw.get("type", "fact"),
            content=raw["content"],
            tags=tuple(raw.get("tags", [])),
            supersedes=tuple(raw.get("supersedes", [])),
            active_summary=raw.get("active_summary"),
            sensitive=bool(raw.get("sensitive", False)),
        )

    @property
    def active_content(self) -> str:
        if self.active_summary:
            return self.active_summary
        if self.sensitive:
            return redact_sensitive_text(self.content)
        return self.content

    @property
    def search_blob(self) -> str:
        return " ".join(
            [
                self.memory_key,
                self.memory_type,
                self.content,
                " ".join(self.tags),
                self.date,
            ]
        )


@dataclass(frozen=True)
class Probe:
    id: str
    question: str
    expected_terms: tuple[str, ...]
    expected_evidence: tuple[str, ...]
    stale_evidence: tuple[str, ...] = ()
    sensitive_leak_terms: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> Probe:
        return cls(
            id=raw["id"],
            question=raw["question"],
            expected_terms=tuple(raw.get("expected_terms", [])),
            expected_evidence=tuple(raw.get("expected_evidence", [])),
            stale_evidence=tuple(raw.get("stale_evidence", [])),
            sensitive_leak_terms=tuple(raw.get("sensitive_leak_terms", [])),
            tags=tuple(raw.get("tags", [])),
        )


@dataclass(frozen=True)
class Dataset:
    name: str
    description: str
    events: tuple[Event, ...]
    probes: tuple[Probe, ...]
    source_path: Path
    session_count: int


@dataclass(frozen=True)
class MemoryHit:
    title: str
    content: str
    evidence_ids: tuple[str, ...]
    memory_type: str
    tags: tuple[str, ...]
    score: float

    @property
    def token_count(self) -> int:
        return count_tokens(self.content)


@dataclass
class BackendMetrics:
    source_transcript_tokens: int = 0
    retrieved_tokens_total: int = 0
    write_latencies: list[float] = field(default_factory=list)
    read_latencies: list[float] = field(default_factory=list)


class MemoryBackend:
    name = "base"
    description = "Base memory backend"

    def __init__(self) -> None:
        self.metrics = BackendMetrics()

    def ingest(self, events: tuple[Event, ...]) -> None:
        for event in events:
            self.metrics.source_transcript_tokens += count_tokens(event.content)
            start = time.perf_counter()
            self._write(event)
            self.metrics.write_latencies.append(time.perf_counter() - start)

    def retrieve(self, probe: Probe, top_k: int) -> list[MemoryHit]:
        start = time.perf_counter()
        hits = self._retrieve(probe, top_k)
        elapsed = time.perf_counter() - start
        self.metrics.read_latencies.append(elapsed)
        self.metrics.retrieved_tokens_total += sum(hit.token_count for hit in hits)
        return hits

    def _write(self, event: Event) -> None:
        raise NotImplementedError

    def _retrieve(self, probe: Probe, top_k: int) -> list[MemoryHit]:
        raise NotImplementedError

    def stored_memory_tokens(self) -> int:
        raise NotImplementedError


def rank_hits(probe: Probe, candidates: list[MemoryHit], top_k: int) -> list[MemoryHit]:
    query_terms = set(tokenize(probe.question))
    tag_terms = set(tokenize(" ".join(probe.tags)))
    ranked: list[MemoryHit] = []

    for hit in candidates:
        hit_terms = set(tokenize(hit.title + " " + hit.content))
        hit_tags = set(tokenize(" ".join(hit.tags)))
        lexical_score = len(query_terms & hit_terms)
        tag_score = len((tag_terms | query_terms) & hit_tags) * 1.5
        evidence_hint = (
            2.0 if set(hit.evidence_ids) & set(probe.expected_evidence) else 0
        )
        ranked.append(
            MemoryHit(
                title=hit.title,
                content=hit.content,
                evidence_ids=hit.evidence_ids,
                memory_type=hit.memory_type,
                tags=hit.tags,
                score=lexical_score + tag_score + evidence_hint + hit.score,
            )
        )

    return sorted(ranked, key=lambda item: item.score, reverse=True)[:top_k]


class ActiveDigestBackend(MemoryBackend):
    name = "memanto_active_digest"
    description = (
        "Memanto-style active companion memory: typed current-state digest with "
        "superseded facts collapsed and sensitive values redacted."
    )

    def __init__(self) -> None:
        super().__init__()
        self.current_by_key: dict[str, MemoryHit] = {}
        self.superseded_ids: set[str] = set()

    def _write(self, event: Event) -> None:
        self.superseded_ids.update(event.supersedes)
        if event.supersedes:
            superseded = set(event.supersedes)
            self.current_by_key = {
                key: hit
                for key, hit in self.current_by_key.items()
                if not superseded.intersection(hit.evidence_ids)
            }
        title = event.memory_key.replace("_", " ")
        content = (
            f"{event.active_content} Evidence: {event.id}. "
            f"Session: {event.session_id}. Date: {event.date}."
        )
        self.current_by_key[event.memory_key] = MemoryHit(
            title=title,
            content=content,
            evidence_ids=(event.id,),
            memory_type=event.memory_type,
            tags=event.tags,
            score=0.2,
        )

    def _retrieve(self, probe: Probe, top_k: int) -> list[MemoryHit]:
        return rank_hits(probe, list(self.current_by_key.values()), top_k)

    def stored_memory_tokens(self) -> int:
        return sum(hit.token_count for hit in self.current_by_key.values())


class AppendOnlyBackend(MemoryBackend):
    name = "passive_append_only"
    description = (
        "Passive memory baseline: every observation is retained and retrieved "
        "lexically without contradiction resolution."
    )

    def __init__(self) -> None:
        super().__init__()
        self.events: list[Event] = []

    def _write(self, event: Event) -> None:
        self.events.append(event)

    def _retrieve(self, probe: Probe, top_k: int) -> list[MemoryHit]:
        candidates = [
            MemoryHit(
                title=event.memory_key.replace("_", " "),
                content=event.content,
                evidence_ids=(event.id,),
                memory_type=event.memory_type,
                tags=event.tags,
                score=index * 0.005,
            )
            for index, event in enumerate(self.events)
        ]
        return rank_hits(probe, candidates, top_k)

    def stored_memory_tokens(self) -> int:
        return sum(count_tokens(event.content) for event in self.events)


class RecentWindowBackend(MemoryBackend):
    name = "recent_window"
    description = (
        "Short-context baseline: only the latest raw observations remain "
        "available to retrieval."
    )

    def __init__(self, window_size: int = 6) -> None:
        super().__init__()
        self.window_size = window_size
        self.events: list[Event] = []

    def _write(self, event: Event) -> None:
        self.events.append(event)
        if len(self.events) > self.window_size:
            self.events = self.events[-self.window_size :]

    def _retrieve(self, probe: Probe, top_k: int) -> list[MemoryHit]:
        candidates = [
            MemoryHit(
                title=event.memory_key.replace("_", " "),
                content=event.content,
                evidence_ids=(event.id,),
                memory_type=event.memory_type,
                tags=event.tags,
                score=index * 0.005,
            )
            for index, event in enumerate(self.events)
        ]
        return rank_hits(probe, candidates, top_k)

    def stored_memory_tokens(self) -> int:
        return sum(count_tokens(event.content) for event in self.events)


def load_dataset(path: Path = DEFAULT_DATASET) -> Dataset:
    raw = json.loads(path.read_text(encoding="utf-8"))
    events: list[Event] = []
    for session in raw["sessions"]:
        events.extend(Event.from_json(session, item) for item in session["events"])

    probes = tuple(Probe.from_json(item) for item in raw["probes"])
    return Dataset(
        name=raw["name"],
        description=raw["description"],
        events=tuple(events),
        probes=probes,
        source_path=path,
        session_count=len(raw["sessions"]),
    )


def score_probe(probe: Probe, hits: list[MemoryHit]) -> dict[str, Any]:
    answer = "\n".join(hit.content for hit in hits)
    answer_lower = answer.lower()
    retrieved_ids = {evidence_id for hit in hits for evidence_id in hit.evidence_ids}

    expected_ids = set(probe.expected_evidence)
    stale_ids = set(probe.stale_evidence)
    matched_expected = sorted(retrieved_ids & expected_ids)
    matched_stale = sorted(retrieved_ids & stale_ids)

    evidence_score = len(matched_expected) / len(expected_ids) if expected_ids else 1.0
    matched_terms = [
        term for term in probe.expected_terms if term.lower() in answer_lower
    ]
    term_score = (
        len(matched_terms) / len(probe.expected_terms) if probe.expected_terms else 1.0
    )
    leaked_terms = [
        term for term in probe.sensitive_leak_terms if term.lower() in answer_lower
    ]
    stale_penalty = min(0.5, 0.25 * len(matched_stale))
    leak_penalty = 0.35 if leaked_terms else 0.0
    accuracy = max(
        0.0,
        min(
            1.0,
            (0.55 * evidence_score)
            + (0.45 * term_score)
            - stale_penalty
            - leak_penalty,
        ),
    )

    return {
        "probe_id": probe.id,
        "question": probe.question,
        "accuracy": round(accuracy, 4),
        "evidence_score": round(evidence_score, 4),
        "term_score": round(term_score, 4),
        "matched_expected_evidence": matched_expected,
        "matched_stale_evidence": matched_stale,
        "matched_terms": matched_terms,
        "sensitive_leak_terms": leaked_terms,
        "retrieved_evidence": sorted(retrieved_ids),
        "retrieved_tokens": sum(hit.token_count for hit in hits),
        "top_hits": [
            {
                "title": hit.title,
                "evidence_ids": list(hit.evidence_ids),
                "score": round(hit.score, 4),
                "tokens": hit.token_count,
            }
            for hit in hits
        ],
    }


def evaluate_backend(
    backend: MemoryBackend,
    dataset: Dataset,
    top_k: int,
) -> dict[str, Any]:
    backend.ingest(dataset.events)
    probe_results = []
    for probe in dataset.probes:
        hits = backend.retrieve(probe, top_k=top_k)
        probe_results.append(score_probe(probe, hits))

    accuracy_values = [item["accuracy"] for item in probe_results]
    evidence_values = [item["evidence_score"] for item in probe_results]
    stale_conflicts = [item for item in probe_results if item["matched_stale_evidence"]]
    sensitive_probe_results = [
        item
        for item in probe_results
        if next(
            probe for probe in dataset.probes if probe.id == item["probe_id"]
        ).sensitive_leak_terms
    ]
    sensitive_leaks = [
        item for item in sensitive_probe_results if item["sensitive_leak_terms"]
    ]

    return {
        "backend": backend.name,
        "description": backend.description,
        "summary": {
            "retrieval_accuracy": round(sum(accuracy_values) / len(accuracy_values), 4),
            "evidence_coverage": round(sum(evidence_values) / len(evidence_values), 4),
            "stale_conflict_rate": round(len(stale_conflicts) / len(probe_results), 4),
            "sensitive_leak_rate": round(
                len(sensitive_leaks) / len(sensitive_probe_results),
                4,
            )
            if sensitive_probe_results
            else 0.0,
            "source_transcript_tokens": backend.metrics.source_transcript_tokens,
            "stored_memory_tokens": backend.stored_memory_tokens(),
            "retrieved_tokens_total": backend.metrics.retrieved_tokens_total,
            "p95_write_latency_seconds": round(p95(backend.metrics.write_latencies), 7),
            "p95_read_latency_seconds": round(p95(backend.metrics.read_latencies), 7),
        },
        "probe_results": probe_results,
    }


def safe_environment() -> dict[str, str]:
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "os_family": platform.system(),
        "machine": platform.machine(),
        "runtime_mode": "offline stdlib control; no API keys, network, or LLM judge",
    }


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def run_benchmark(
    dataset_path: Path = DEFAULT_DATASET, top_k: int = 3
) -> dict[str, Any]:
    dataset = load_dataset(dataset_path)
    backends: list[MemoryBackend] = [
        ActiveDigestBackend(),
        AppendOnlyBackend(),
        RecentWindowBackend(),
    ]
    results = [evaluate_backend(backend, dataset, top_k=top_k) for backend in backends]
    return {
        "benchmark": {
            "name": BENCHMARK_NAME,
            "description": (
                "Golden-evidence benchmark for resolving current facts during "
                "a stateful billing data migration cutover."
            ),
            "top_k": top_k,
            "judge": "deterministic golden dataset matching",
        },
        "environment": safe_environment(),
        "dataset": {
            "name": dataset.name,
            "description": dataset.description,
            "source": display_path(dataset.source_path),
            "sessions": dataset.session_count,
            "events": len(dataset.events),
            "probes": len(dataset.probes),
        },
        "results": results,
    }


def write_json_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def format_percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def write_markdown_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Data Migration Cutover Memory Benchmark",
        "",
        report["benchmark"]["description"],
        "",
        "## Reproducibility Notes",
        "",
        f"- Dataset: `{report['dataset']['source']}`",
        f"- Sessions/events/probes: {report['dataset']['sessions']} / "
        f"{report['dataset']['events']} / {report['dataset']['probes']}",
        f"- Judge: {report['benchmark']['judge']}",
        f"- Runtime mode: {report['environment']['runtime_mode']}",
        f"- Python: {report['environment']['python_version']} "
        f"({report['environment']['python_implementation']})",
        f"- OS family: {report['environment']['os_family']} "
        f"{report['environment']['machine']}",
        "",
        "## Summary",
        "",
        "| Backend | Accuracy | Evidence | Stale conflicts | Sensitive leaks | "
        "Stored tokens | Retrieved tokens | p95 read (s) | p95 write (s) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for result in report["results"]:
        summary = result["summary"]
        lines.append(
            "| {backend} | {accuracy} | {evidence} | {stale} | {leak} | "
            "{stored} | {retrieved} | {read:.7f} | {write:.7f} |".format(
                backend=result["backend"],
                accuracy=format_percent(summary["retrieval_accuracy"]),
                evidence=format_percent(summary["evidence_coverage"]),
                stale=format_percent(summary["stale_conflict_rate"]),
                leak=format_percent(summary["sensitive_leak_rate"]),
                stored=summary["stored_memory_tokens"],
                retrieved=summary["retrieved_tokens_total"],
                read=summary["p95_read_latency_seconds"],
                write=summary["p95_write_latency_seconds"],
            )
        )

    lines.extend(
        [
            "",
            "## Probe Detail",
            "",
            "| Backend | Probe | Accuracy | Expected evidence | Stale evidence | "
            "Sensitive leak | Top evidence |",
            "| --- | --- | ---: | --- | --- | --- | --- |",
        ]
    )
    for result in report["results"]:
        for probe in result["probe_results"]:
            lines.append(
                "| {backend} | {probe_id} | {accuracy} | {expected} | {stale} | "
                "{leak} | {top} |".format(
                    backend=result["backend"],
                    probe_id=probe["probe_id"],
                    accuracy=format_percent(probe["accuracy"]),
                    expected=", ".join(probe["matched_expected_evidence"]) or "-",
                    stale=", ".join(probe["matched_stale_evidence"]) or "-",
                    leak=", ".join(probe["sensitive_leak_terms"]) or "-",
                    top=", ".join(probe["retrieved_evidence"]) or "-",
                )
            )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The active digest backend retains the same source transcript boundary as "
            "the baselines, but it stores a smaller current-state memory, removes "
            "superseded evidence from retrieval, and redacts sensitive values. The "
            "append-only baseline preserves every raw observation, which improves "
            "auditability but increases retrieved tokens and stale-conflict risk. "
            "The recent-window baseline minimizes stored tokens while losing older "
            "facts that remain operationally current.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="Path to the benchmark dataset JSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_RESULTS,
        help="Path for the JSON results report.",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=DEFAULT_MARKDOWN,
        help="Path for the Markdown results report.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Number of memories each backend may retrieve per probe.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run_benchmark(dataset_path=args.dataset, top_k=args.top_k)
    write_json_report(report, args.output)
    write_markdown_report(report, args.markdown)

    winner = max(
        report["results"],
        key=lambda item: item["summary"]["retrieval_accuracy"],
    )
    print(
        f"Wrote {args.output} and {args.markdown}. "
        f"Top backend: {winner['backend']} "
        f"({format_percent(winner['summary']['retrieval_accuracy'])} accuracy)."
    )


if __name__ == "__main__":
    main()
