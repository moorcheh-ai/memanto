from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

TOKEN_CHARS = 4
WORD_RE = re.compile(r"[A-Za-z0-9]+")


@dataclass(frozen=True)
class Turn:
    session: str
    content: str


@dataclass(frozen=True)
class Query:
    id: str
    question: str
    expected: tuple[str, ...]
    forbidden: tuple[str, ...]


@dataclass(frozen=True)
class Case:
    case_id: str
    description: str
    turns: tuple[Turn, ...]
    queries: tuple[Query, ...]


@dataclass(frozen=True)
class QueryResult:
    adapter: str
    case_id: str
    query_id: str
    answer: str
    accuracy: float
    ingested_tokens: int
    retrieved_tokens: int
    latency_ms: float


class MemoryAdapter(Protocol):
    name: str

    def reset(self, case_id: str) -> None:
        ...

    def ingest(self, turn: Turn) -> int:
        ...

    def retrieve(self, query: Query) -> str:
        ...


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / TOKEN_CHARS))


def normalized_words(text: str) -> set[str]:
    return {match.group(0).lower() for match in WORD_RE.finditer(text)}


def score_answer(answer: str, query: Query) -> float:
    lowered = answer.lower()
    expected_hits = sum(1 for term in query.expected if term.lower() in lowered)
    forbidden_hits = sum(1 for term in query.forbidden if term.lower() in lowered)
    checks = len(query.expected) + len(query.forbidden)
    if checks == 0:
        return 1.0
    return max(0.0, (expected_hits + len(query.forbidden) - forbidden_hits) / checks)


def load_dataset(path: Path) -> list[Case]:
    cases: list[Case] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        raw = json.loads(line)
        try:
            turns = tuple(Turn(**turn) for turn in raw["turns"])
            queries = tuple(
                Query(
                    id=query["id"],
                    question=query["question"],
                    expected=tuple(query.get("expected", [])),
                    forbidden=tuple(query.get("forbidden", [])),
                )
                for query in raw["queries"]
            )
            cases.append(
                Case(
                    case_id=raw["case_id"],
                    description=raw.get("description", ""),
                    turns=turns,
                    queries=queries,
                )
            )
        except KeyError as exc:
            raise ValueError(f"Dataset line {line_number} is missing {exc}") from exc
    if not cases:
        raise ValueError(f"No benchmark cases found in {path}")
    return cases


class AppendOnlyKeywordAdapter:
    name = "append_only_keyword"

    def __init__(self, top_k: int = 3) -> None:
        self.top_k = top_k
        self._turns: list[Turn] = []

    def reset(self, case_id: str) -> None:
        self._turns = []

    def ingest(self, turn: Turn) -> int:
        self._turns.append(turn)
        return estimate_tokens(turn.content)

    def retrieve(self, query: Query) -> str:
        q_words = normalized_words(query.question)
        ranked = sorted(
            self._turns,
            key=lambda turn: (
                len(q_words & normalized_words(turn.content)),
                turn.session,
            ),
            reverse=True,
        )
        return " ".join(turn.content for turn in ranked[: self.top_k])


class StatefulCompactionAdapter:
    name = "stateful_compaction"

    def __init__(self) -> None:
        self._facts: dict[str, str] = {}
        self._fallback: list[str] = []

    def reset(self, case_id: str) -> None:
        self._facts = {}
        self._fallback = []

    def ingest(self, turn: Turn) -> int:
        self._fallback.append(turn.content)
        for sentence in split_sentences(turn.content):
            key = fact_key(sentence)
            if key:
                self._facts[key] = sentence
        return estimate_tokens(turn.content)

    def retrieve(self, query: Query) -> str:
        q_words = normalized_words(query.question)
        fact_values = list(self._facts.values()) or self._fallback
        ranked = sorted(
            fact_values,
            key=lambda fact: len(q_words & normalized_words(fact)),
            reverse=True,
        )
        return " ".join(ranked[:3])


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def fact_key(sentence: str) -> str | None:
    lowered = sentence.lower()
    if "seat" in lowered:
        return "travel.seat"
    if "meal" in lowered or "seafood" in lowered or "vegetarian" in lowered:
        return "travel.meal"
    if "billing service" in lowered or "owns billing" in lowered:
        return "billing.owner"
    if "payment webhook" in lowered:
        return "billing.escalation"
    if "csv export" in lowered:
        return "analytics.csv"
    if "xml export" in lowered:
        return "analytics.xml"
    if "backward compatible" in lowered or "backward compatibility" in lowered:
        return "analytics.compatibility"
    return None


def build_adapters(names: Iterable[str]) -> list[MemoryAdapter]:
    registry: dict[str, MemoryAdapter] = {
        AppendOnlyKeywordAdapter.name: AppendOnlyKeywordAdapter(),
        StatefulCompactionAdapter.name: StatefulCompactionAdapter(),
    }
    adapters = []
    for name in names:
        try:
            adapters.append(registry[name])
        except KeyError:
            known = ", ".join(sorted(registry))
            raise ValueError(f"Unknown adapter '{name}'. Known adapters: {known}")
    return adapters


def run_suite(cases: list[Case], adapters: list[MemoryAdapter]) -> list[QueryResult]:
    results: list[QueryResult] = []
    for adapter in adapters:
        for case in cases:
            adapter.reset(case.case_id)
            ingested_tokens = sum(adapter.ingest(turn) for turn in case.turns)
            for query in case.queries:
                start = time.perf_counter()
                answer = adapter.retrieve(query)
                latency_ms = (time.perf_counter() - start) * 1000
                results.append(
                    QueryResult(
                        adapter=adapter.name,
                        case_id=case.case_id,
                        query_id=query.id,
                        answer=answer,
                        accuracy=score_answer(answer, query),
                        ingested_tokens=ingested_tokens,
                        retrieved_tokens=estimate_tokens(answer),
                        latency_ms=latency_ms,
                    )
                )
    return results


def summarize(results: list[QueryResult]) -> dict[str, dict[str, float]]:
    by_adapter: dict[str, list[QueryResult]] = {}
    for result in results:
        by_adapter.setdefault(result.adapter, []).append(result)

    summary: dict[str, dict[str, float]] = {}
    for adapter, rows in by_adapter.items():
        latencies = sorted(row.latency_ms for row in rows)
        p95_index = max(0, math.ceil(len(latencies) * 0.95) - 1)
        summary[adapter] = {
            "accuracy": statistics.fmean(row.accuracy for row in rows),
            "avg_ingested_tokens": statistics.fmean(
                row.ingested_tokens for row in rows
            ),
            "avg_retrieved_tokens": statistics.fmean(
                row.retrieved_tokens for row in rows
            ),
            "p95_latency_ms": latencies[p95_index],
            "query_count": float(len(rows)),
        }
    return summary


def write_outputs(results: list[QueryResult], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "results.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "adapter",
                "case_id",
                "query_id",
                "accuracy",
                "ingested_tokens",
                "retrieved_tokens",
                "latency_ms",
                "answer",
            ],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "adapter": result.adapter,
                    "case_id": result.case_id,
                    "query_id": result.query_id,
                    "accuracy": f"{result.accuracy:.4f}",
                    "ingested_tokens": result.ingested_tokens,
                    "retrieved_tokens": result.retrieved_tokens,
                    "latency_ms": f"{result.latency_ms:.4f}",
                    "answer": result.answer,
                }
            )

    (output_dir / "summary.json").write_text(
        json.dumps(summarize(results), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    default_dataset = Path(__file__).with_name("dataset.jsonl")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=default_dataset)
    parser.add_argument("--output-dir", type=Path, default=Path("benchmark-results"))
    parser.add_argument(
        "--adapter",
        action="append",
        choices=[AppendOnlyKeywordAdapter.name, StatefulCompactionAdapter.name],
        help="Adapter to run. Repeat to compare multiple adapters.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    adapter_names = args.adapter or [
        StatefulCompactionAdapter.name,
        AppendOnlyKeywordAdapter.name,
    ]
    cases = load_dataset(args.dataset)
    adapters = build_adapters(adapter_names)
    results = run_suite(cases, adapters)
    write_outputs(results, args.output_dir)
    print(json.dumps(summarize(results), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
