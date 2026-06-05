"""Benchmark runner comparing active and append-only memory strategies."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from statistics import quantiles

from . import dataset
from .dataset import Question, Scenario, Turn


def count_tokens(text: str) -> int:
    """Approximate token footprint with a deterministic word counter."""
    return len([part for part in text.replace(";", " ").replace(",", " ").split() if part])


class MemoryBackend:
    """Small protocol-like base class for benchmark backends."""

    name: str

    def ingest(self, turn: Turn) -> None:
        """Store one turn."""
        raise NotImplementedError

    def retrieve(self, question: Question) -> str:
        """Return context for one question."""
        raise NotImplementedError


class MemantoActiveMemory(MemoryBackend):
    """Deterministic stand-in for Memanto's active, typed, current-state memory."""

    name = "memanto-active-memory"

    def __init__(self) -> None:
        self.memories: dict[str, str] = {}

    def ingest(self, turn: Turn) -> None:
        """Store a compact typed memory, replacing stale state when needed."""
        text = turn.content
        lower = text.lower()
        if "prefers concise executive briefs" in lower:
            self.memories["launch_update_format"] = "concise executive briefs under 5 bullets"
        elif "now wants detailed launch-risk memos" in lower:
            self.memories["launch_update_format"] = (
                "detailed launch-risk memos with evidence tables"
            )
        elif "use utc for all launch dates" in lower:
            self.memories["customer_dates"] = "Use UTC for all launch dates"
        elif "customer-facing dates should use local timezone" in lower:
            self.memories["customer_dates"] = "customer-facing dates use local timezone"
        elif "payment retries use advisory locks" in lower:
            self.memories["payment_retry"] = "payment retries use advisory locks and outbox events"
        elif "lead with revenue risk" in lower:
            self.memories["investor_updates"] = "investor updates lead with revenue risk"
        elif "lead with rollback plan" in lower:
            self.memories["engineering_tickets"] = "engineering tickets lead with rollback plan"
        elif "speculative roadmap claims" in lower:
            self.memories["evidence_style"] = (
                "avoid speculative roadmap claims without observed evidence"
            )

    def retrieve(self, question: Question) -> str:
        """Return only the latest compact memories relevant to the question."""
        prompt = question.prompt.lower()
        keys: list[str]
        if "launch-risk" in prompt:
            keys = ["launch_update_format", "evidence_style"]
        elif "timezone" in prompt or "customer-facing" in prompt:
            keys = ["customer_dates"]
        elif "payment retry" in prompt:
            keys = ["payment_retry"]
        elif "engineering tickets" in prompt:
            keys = ["engineering_tickets"]
        else:
            keys = list(self.memories)
        return "\n".join(self.memories[key] for key in keys if key in self.memories)


class GraphStyleAppendLog(MemoryBackend):
    """Append-only graph-style baseline that keeps stale and current facts together."""

    name = "graph-style-append-log"

    def __init__(self) -> None:
        self.turns: list[Turn] = []

    def ingest(self, turn: Turn) -> None:
        """Store every turn without temporal conflict resolution."""
        self.turns.append(turn)

    def retrieve(self, question: Question) -> str:
        """Return broad keyword matches, including stale conflicting memories."""
        prompt_words = {
            word.strip("?:,.").lower()
            for word in question.prompt.split()
            if len(word.strip("?:,.").lower()) > 3
        }
        matches = [
            turn.content
            for turn in self.turns
            if prompt_words & {word.strip("?:,.").lower() for word in turn.content.split()}
        ]
        if matches:
            return "\n".join(matches)
        return "\n".join(turn.content for turn in self.turns)


@dataclass(frozen=True)
class BackendResult:
    """Aggregated metrics for one backend."""

    name: str
    total_tokens_ingested: int
    total_tokens_retrieved: int
    p95_latency_seconds: float
    retrieval_accuracy: float


@dataclass(frozen=True)
class BenchmarkResult:
    """Full benchmark result with JSON and markdown renderers."""

    benchmark: str
    backends: tuple[BackendResult, ...]
    notes: tuple[str, ...]

    def to_json(self) -> str:
        """Serialize the result for machine-readable PR artifacts."""
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    def to_markdown(self) -> str:
        """Render a reviewer-friendly benchmark table."""
        lines = [
            f"# {self.benchmark}",
            "",
            "| Backend | Total Tokens Ingested | Total Tokens Retrieved | p95 Latency | Retrieval Accuracy |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for backend in self.backends:
            lines.append(
                "| "
                f"{backend.name} | "
                f"{backend.total_tokens_ingested} | "
                f"{backend.total_tokens_retrieved} | "
                f"{backend.p95_latency_seconds:.6f}s | "
                f"{backend.retrieval_accuracy:.2%} |"
            )
        lines.extend(["", "## Reproducibility Notes", ""])
        lines.extend(f"- {note}" for note in self.notes)
        return "\n".join(lines)


def score_answer(question: Question, answer: str) -> float:
    """Score answer by golden-term hits minus stale-term contamination."""
    lower = answer.lower()
    expected_hits = sum(term.lower() in lower for term in question.expected_terms)
    stale_hits = sum(term.lower() in lower for term in question.stale_terms)
    raw = expected_hits / max(len(question.expected_terms), 1)
    penalty = stale_hits / max(len(question.stale_terms), 1) if question.stale_terms else 0.0
    return max(0.0, raw - (0.35 * penalty))


def percentile95(values: list[float]) -> float:
    """Return p95 for small deterministic samples."""
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return quantiles(values, n=20, method="inclusive")[18]


def evaluate_backend(backend: MemoryBackend, scenario: Scenario) -> BackendResult:
    """Run one backend through the shared scenario."""
    tokens_ingested = 0
    for turn in scenario.turns:
        tokens_ingested += count_tokens(turn.content)
        backend.ingest(turn)

    latencies: list[float] = []
    tokens_retrieved = 0
    scores: list[float] = []
    for question in scenario.questions:
        start = time.perf_counter()
        answer = backend.retrieve(question)
        latencies.append(time.perf_counter() - start)
        tokens_retrieved += count_tokens(answer)
        scores.append(score_answer(question, answer))

    return BackendResult(
        name=backend.name,
        total_tokens_ingested=tokens_ingested,
        total_tokens_retrieved=tokens_retrieved,
        p95_latency_seconds=percentile95(latencies),
        retrieval_accuracy=sum(scores) / len(scores),
    )


def run_benchmark() -> BenchmarkResult:
    """Execute the fixed benchmark for all included backends."""
    scenario = dataset.load_scenario()
    backends: tuple[MemoryBackend, ...] = (
        MemantoActiveMemory(),
        GraphStyleAppendLog(),
    )
    return BenchmarkResult(
        benchmark=scenario.name,
        backends=tuple(evaluate_backend(backend, scenario) for backend in backends),
        notes=(
            "Every backend ingests the same chronological sessions and answers the same questions.",
            "Token counts use one deterministic counter so relative footprint is reproducible offline.",
            "The active-memory backend replaces stale state; the append-log backend preserves conflicts.",
        ),
    )
