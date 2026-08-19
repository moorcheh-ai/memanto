"""Protocols, data structures, and shared formatting.

Contains:
- MemorySystem Protocol (what every adapter must implement)
- Dataset Protocol (what every dataset must implement)
- All dataclasses (RetrievedItem, QAPair, etc.)
- Metric computation and formatting utilities
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Protocol, runtime_checkable


@dataclass
class EvidenceSpan:
    """Ground-truth evidence — which turns / sessions support a QA answer."""

    session_id: str
    turn_ids: list[str]


@dataclass
class QAPair:
    """One question-answer pair with evidence annotations."""

    question: str
    answer: str
    category: str
    category_id: int | str
    evidence: list[EvidenceSpan]
    question_id: str = ""


@dataclass
class DialogueTurn:
    """A single turn in a conversation."""

    dia_id: str
    speaker: str
    text: str
    session_id: str


@dataclass
class Conversation:
    """A full conversation: turns + QA pairs."""

    sample_id: str
    turns: list[DialogueTurn]
    qa_pairs: list[QAPair]

    @property
    def session_ids(self) -> list[str]:
        return sorted(
            {t.session_id for t in self.turns},
            key=lambda s: int(s.split("_")[-1]) if s.split("_")[-1].isdigit() else 0,
        )


@dataclass
class BenchmarkDataset:
    """A loaded dataset ready for benchmarking."""

    name: str
    conversations: list[Conversation]
    description: str = ""

    @property
    def total_qa_pairs(self) -> int:
        return sum(len(c.qa_pairs) for c in self.conversations)

    @property
    def total_turns(self) -> int:
        return sum(len(c.turns) for c in self.conversations)


# ---------------------------------------------------------------------------
# Retrieval result types
# ---------------------------------------------------------------------------


@dataclass
class RetrievedItem:
    """One item returned by a memory system search."""

    dia_id: str
    session_id: str
    text: str
    score: float = 0.0


@dataclass
class QueryResult:
    """Full result of evaluating one QA pair against a memory system."""

    query: str
    ground_truth_answer: str
    category: str
    question_id: str
    retrieved: list[RetrievedItem]
    latency_seconds: float
    token_count: int

    recall_at_k: float = 0.0
    precision_at_k: float = 0.0
    has_stale: bool = False
    stale_count: int = 0

    evidence_session_ids: set[str] = field(default_factory=set)
    evidence_turn_ids: set[str] = field(default_factory=set)

    # additional dataset-specific fields
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemResults:
    """Aggregated results for one memory system on one dataset."""

    system_name: str
    dataset_name: str
    queries: list[QueryResult] = field(default_factory=list)

    # k values to report recall at
    k_curve: tuple[int, ...] = (5, 10, 20, 30, 40, 50)
    configured_k: int = 50

    @property
    def total_queries(self) -> int:
        return len(self.queries)

    @property
    def total_tokens_retrieved(self) -> int:
        return sum(q.token_count for q in self.queries)

    def recall_curve(self) -> dict[int, float]:
        """Compute recall at each k value up to configured_k."""
        result = {}
        for k in self.k_curve:
            if k > self.configured_k:
                continue
            hits = 0
            for q in self.queries:
                retrieved_ids = {r.dia_id for r in q.retrieved[:k]}
                evidence = q.evidence_turn_ids
                if evidence and retrieved_ids & evidence:
                    hits += 1
            result[k] = hits / max(len(self.queries), 1)
        return result

    @property
    def avg_recall_at_k(self) -> float:
        return sum(q.recall_at_k for q in self.queries) / max(len(self.queries), 1)

    @property
    def avg_precision_at_k(self) -> float:
        return sum(q.precision_at_k for q in self.queries) / max(len(self.queries), 1)

    @property
    def stale_query_ratio(self) -> float:
        return sum(1 for q in self.queries if q.has_stale) / max(len(self.queries), 1)

    @property
    def p95_latency(self) -> float:
        lats = sorted(q.latency_seconds for q in self.queries)
        return lats[min(int(len(lats) * 0.95), max(len(lats) - 1, 0))] if lats else 0.0

    @property
    def p50_latency(self) -> float:
        return median(q.latency_seconds for q in self.queries) if self.queries else 0.0

    def by_category(self) -> dict[str, list[QueryResult]]:
        cats: dict[str, list[QueryResult]] = {}
        for q in self.queries:
            cats.setdefault(q.category, []).append(q)
        return cats


# ---------------------------------------------------------------------------
# MemorySystem Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class MemorySystem(Protocol):
    """Interface every memory adapter must implement."""

    def name(self) -> str: ...

    def setup(self) -> None: ...

    def store_turns(self, turns: list[DialogueTurn], namespace: str) -> None: ...

    def search(
        self,
        query: str,
        namespace: str,
        k: int = 10,
    ) -> list[RetrievedItem]: ...

    def teardown(self) -> None: ...

    def dry_run(self) -> bool:
        """End-to-end smoke test: setup → store → search → teardown.

        Must store at least one turn, search for it, and verify the
        result contains the expected content.  Returns True iff every
        step succeeds.
        """
        ...

    def cleanup(self) -> None:
        """Delete all local / remote resources created by this adapter
        (leftover databases, agents, users, namespaces, etc.).
        """
        ...


# ---------------------------------------------------------------------------
# Dataset Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Dataset(Protocol):
    """Interface every dataset must implement."""

    name: str
    description: str

    def load(self, limit: int | None = None, **kwargs) -> BenchmarkDataset: ...

    def compute_metrics(
        self,
        retrieved: list[RetrievedItem],
        qa: QAPair,
        k: int = 10,
        judge_fn: callable | None = None,
    ) -> tuple[float, float, bool, int, dict[str, Any]]:
        """Compute (recall@k, precision@k, has_stale, stale_count, extra).

        Each dataset implements its own scoring logic:
        - LoCoMo: turn-level evidence matching
        - MemoryAgentBench: text-based answer matching via judge
        """
        ...

    def dry_run(self) -> bool:
        """Validate data loading + metric computation on a small subset."""
        ...


# ---------------------------------------------------------------------------
# Scoring helpers (used by datasets that have turn-level evidence)
# ---------------------------------------------------------------------------


def _default_compute_scores(
    retrieved: list[RetrievedItem],
    qa: QAPair,
    k: int = 10,
) -> tuple[float, float, bool, int]:
    """Turn-level or session-level evidence scoring — used by LoCoMo & LongMemEval."""
    top_k = retrieved[:k]

    evidence_turn_ids: set[str] = set()
    for ev in qa.evidence:
        evidence_turn_ids.update(ev.turn_ids)

    retrieved_turn_ids: set[str] = {r.dia_id for r in top_k}

    if not evidence_turn_ids:
        # Session-level evidence fallback
        evidence_session_ids: set[str] = {ev.session_id for ev in qa.evidence}
        retrieved_session_ids: set[str] = {r.session_id for r in top_k}
        if evidence_session_ids:
            recall = len(retrieved_session_ids & evidence_session_ids) / len(
                evidence_session_ids
            )
            precision = (
                len(retrieved_session_ids & evidence_session_ids)
                / len(retrieved_session_ids)
                if retrieved_session_ids
                else 0.0
            )
        else:
            recall = precision = 0.0
    else:
        # Turn-level evidence
        recall = (
            len(retrieved_turn_ids & evidence_turn_ids) / len(evidence_turn_ids)
            if evidence_turn_ids
            else 0.0
        )
        precision = (
            len(retrieved_turn_ids & evidence_turn_ids) / len(retrieved_turn_ids)
            if retrieved_turn_ids
            else 0.0
        )

    has_stale = False
    stale_count = 0
    if qa.category in ("knowledge-update", "temporal", "multi-session"):
        evidence_session_ids = {ev.session_id for ev in qa.evidence}
        if evidence_turn_ids:
            stale_count = sum(1 for r in top_k if r.dia_id not in evidence_turn_ids)
        else:
            stale_count = sum(
                1 for r in top_k if r.session_id not in evidence_session_ids
            )
        has_stale = stale_count > 0

    return recall, precision, has_stale, stale_count


# ---------------------------------------------------------------------------
# Query evaluation glue
# ---------------------------------------------------------------------------


def evaluate_query(
    memory: MemorySystem,
    qa: QAPair,
    dataset: Dataset,
    namespace: str,
    k: int = 10,
    judge_fn: callable | None = None,
) -> QueryResult:
    """Run one QA pair through a memory system, score via the dataset's metric."""
    start = time.perf_counter()
    retrieved = memory.search(qa.question, namespace, k=k)
    elapsed = time.perf_counter() - start

    recall, precision, has_stale, stale_count, extra = dataset.compute_metrics(
        retrieved,
        qa,
        k=k,
        judge_fn=judge_fn,
    )

    evidence_turn_ids: set[str] = set()
    evidence_session_ids: set[str] = set()
    for ev in qa.evidence:
        evidence_turn_ids.update(ev.turn_ids)
        evidence_session_ids.add(ev.session_id)

    return QueryResult(
        query=qa.question,
        ground_truth_answer=qa.answer,
        category=qa.category,
        question_id=qa.question_id,
        retrieved=retrieved,
        latency_seconds=elapsed,
        token_count=sum(len(r.text.split()) for r in retrieved),
        recall_at_k=recall,
        precision_at_k=precision,
        has_stale=has_stale,
        stale_count=stale_count,
        evidence_session_ids=evidence_session_ids,
        evidence_turn_ids=evidence_turn_ids,
        extra=extra,
    )


# ---------------------------------------------------------------------------
# Table formatting
# ---------------------------------------------------------------------------


def format_results_table(results: list[SystemResults]) -> str:
    """Format a comparison table with recall curves."""
    # Header
    k_values = results[0].k_curve if results else (10, 20, 50)
    k_cols = " | ".join(f"Recall@{k}" for k in k_values)
    lines = [
        f"| System | Dataset | Queries | {k_cols} | Stale% | Tokens | p95 Lat |",
        "|--------|---------|--------:"
        + "|".join(":------:" for _ in k_values)
        + "|-------:|-------:|--------:|",
    ]
    for r in results:
        rc = r.recall_curve()
        k_vals = " | ".join(f"{rc[k]:.1%}" for k in k_values)
        lines.append(
            f"| {r.system_name} | {r.dataset_name} | {r.total_queries} | "
            f"{k_vals} | "
            f"{r.stale_query_ratio:.1%} | "
            f"{r.total_tokens_retrieved} | "
            f"{r.p95_latency:.3f}s |"
        )
    return "\n".join(lines)


def format_category_breakdown(results: list[SystemResults]) -> str:
    """Per-category breakdown with recall@20 across all systems."""
    lines = []
    k_report = 20
    for r in results:
        lines.append(f"\n### {r.system_name} — Per-Category (Recall@{k_report})")
        lines.append(
            "| Category | Queries | Recall@20 | Precision@20 | Stale% | "
            "Tokens | p50 Latency |"
        )
        lines.append(
            "|----------|--------:|----------:|-------------:|-------:|"
            "------:|------------:|"
        )
        for cat, qs in sorted(r.by_category().items()):
            n = len(qs)
            recall = sum(q.recall_at_k for q in qs) / n
            prec = sum(q.precision_at_k for q in qs) / n
            stale = sum(1 for q in qs if q.has_stale) / n
            tokens = sum(q.token_count for q in qs)
            lat = median(q.latency_seconds for q in qs)
            lines.append(
                f"| {cat} | {n} | {recall:.1%} | {prec:.1%} | "
                f"{stale:.1%} | {tokens} | {lat:.3f}s |"
            )
    return "\n".join(lines)
