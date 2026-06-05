"""Multi-agent codebase handoff benchmark.

The harness is intentionally dependency-free so reviewers can run it before
configuring hosted memory services. Backends are small adapters with a shared
interface, which keeps the dataset and scoring reusable for real Memanto or
competitor integrations.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import re
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = ROOT / "dataset" / "codebase_handoff.json"
TOKEN_RE = re.compile(r"[A-Za-z0-9_:/.-]+")
STOPWORDS = {
    "a",
    "and",
    "around",
    "be",
    "for",
    "if",
    "in",
    "is",
    "it",
    "now",
    "of",
    "on",
    "or",
    "should",
    "the",
    "to",
    "use",
    "what",
    "which",
    "who",
}


@dataclass(frozen=True)
class Event:
    turn: int
    timestamp: str
    agent: str
    memory_type: str
    key: str
    value: str
    content: str
    tags: tuple[str, ...]

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "Event":
        return cls(
            turn=int(raw["turn"]),
            timestamp=str(raw["timestamp"]),
            agent=str(raw["agent"]),
            memory_type=str(raw["memory_type"]),
            key=str(raw["key"]),
            value=str(raw["value"]),
            content=str(raw["content"]),
            tags=tuple(str(tag) for tag in raw.get("tags", [])),
        )


@dataclass(frozen=True)
class Question:
    id: str
    asker: str
    query: str
    expected_key: str
    expected_value: str
    requires_cross_agent_memory: bool

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "Question":
        return cls(
            id=str(raw["id"]),
            asker=str(raw["asker"]),
            query=str(raw["query"]),
            expected_key=str(raw["expected_key"]),
            expected_value=str(raw["expected_value"]),
            requires_cross_agent_memory=bool(raw["requires_cross_agent_memory"]),
        )


def tokenize(text: str) -> list[str]:
    return [
        token.lower()
        for token in TOKEN_RE.findall(text)
        if token.lower() not in STOPWORDS
    ]


def token_count(text: str) -> int:
    return len(TOKEN_RE.findall(text))


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[index]


def load_dataset(path: Path) -> tuple[dict[str, Any], list[Event], list[Question]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    events = [Event.from_raw(event) for event in data["events"]]
    questions = [Question.from_raw(question) for question in data["questions"]]
    return data, events, questions


def record_text(record: dict[str, Any]) -> str:
    return " ".join(
        [
            str(record.get("key", "")),
            str(record.get("value", "")),
            str(record.get("content", "")),
            " ".join(str(tag) for tag in record.get("tags", [])),
            str(record.get("memory_type", "")),
        ]
    )


def keyword_score(query: str, record: dict[str, Any]) -> float:
    query_terms = set(tokenize(query))
    record_terms = set(tokenize(record_text(record)))
    if not query_terms:
        return 0.0
    overlap = len(query_terms & record_terms)
    normalized = overlap / math.sqrt(max(len(record_terms), 1))
    recency = float(record.get("turn", 0)) / 1000.0
    return normalized + recency


class SharedActiveDigestBackend:
    name = "shared_active_digest"

    def __init__(self, max_retrieved_facts: int = 1) -> None:
        self.max_retrieved_facts = max_retrieved_facts
        self.active_by_key: dict[str, dict[str, Any]] = {}
        self.ingested_tokens = 0

    def ingest(self, event: Event) -> None:
        self.ingested_tokens += token_count(event.content)
        self.active_by_key[event.key] = {
            "agent": event.agent,
            "content": event.content,
            "key": event.key,
            "memory_type": event.memory_type,
            "tags": list(event.tags),
            "turn": event.turn,
            "value": event.value,
        }

    def retrieve(self, question: Question) -> tuple[list[dict[str, Any]], float]:
        start = time.perf_counter()
        scored = [
            (keyword_score(question.query, record), record)
            for record in self.active_by_key.values()
        ]
        ranked = [
            record
            for score, record in sorted(scored, key=lambda item: item[0], reverse=True)
            if score > 0
        ]
        records = ranked[: self.max_retrieved_facts]
        elapsed = time.perf_counter() - start
        return records, elapsed


class PerAgentAppendLogBackend:
    name = "per_agent_append_log"

    def __init__(self, max_retrieved_events: int = 6) -> None:
        self.max_retrieved_events = max_retrieved_events
        self.logs_by_agent: dict[str, list[dict[str, Any]]] = {}
        self.ingested_tokens = 0

    def ingest(self, event: Event) -> None:
        self.ingested_tokens += token_count(event.content)
        self.logs_by_agent.setdefault(event.agent, []).append(
            {
                "agent": event.agent,
                "content": event.content,
                "key": event.key,
                "memory_type": event.memory_type,
                "tags": list(event.tags),
                "turn": event.turn,
                "value": event.value,
            }
        )

    def retrieve(self, question: Question) -> tuple[list[dict[str, Any]], float]:
        start = time.perf_counter()
        local_log = self.logs_by_agent.get(question.asker, [])
        scored = [
            (keyword_score(question.query, record), record)
            for record in local_log
        ]
        ranked = [
            record
            for score, record in sorted(scored, key=lambda item: item[0], reverse=True)
            if score > 0
        ]
        records = ranked[: self.max_retrieved_events]
        elapsed = time.perf_counter() - start
        return records, elapsed


class SharedAppendLogBackend:
    name = "shared_append_log"

    def __init__(self, max_retrieved_events: int = 6) -> None:
        self.max_retrieved_events = max_retrieved_events
        self.log: list[dict[str, Any]] = []
        self.ingested_tokens = 0

    def ingest(self, event: Event) -> None:
        self.ingested_tokens += token_count(event.content)
        self.log.append(
            {
                "agent": event.agent,
                "content": event.content,
                "key": event.key,
                "memory_type": event.memory_type,
                "tags": list(event.tags),
                "turn": event.turn,
                "value": event.value,
            }
        )

    def retrieve(self, question: Question) -> tuple[list[dict[str, Any]], float]:
        start = time.perf_counter()
        scored = [
            (keyword_score(question.query, record), record)
            for record in self.log
        ]
        ranked = [
            record
            for score, record in sorted(scored, key=lambda item: item[0], reverse=True)
            if score > 0
        ]
        records = ranked[: self.max_retrieved_events]
        elapsed = time.perf_counter() - start
        return records, elapsed


def score_retrieval(
    question: Question, records: list[dict[str, Any]]
) -> dict[str, Any]:
    same_key = [
        (index, record)
        for index, record in enumerate(records)
        if record.get("key") == question.expected_key
    ]
    exact_indexes = [
        index
        for index, record in same_key
        if record.get("value") == question.expected_value
    ]
    first_exact_index = exact_indexes[0] if exact_indexes else None
    stale_before_exact = any(
        record.get("value") != question.expected_value
        and (first_exact_index is None or index <= first_exact_index)
        for index, record in same_key
    )
    stale_retrieved = any(
        record.get("value") != question.expected_value
        for _, record in same_key
    )
    correct = first_exact_index is not None and not stale_before_exact
    retrieved_tokens = sum(token_count(record_text(record)) for record in records)
    signal_records = sum(
        1 for record in records if record.get("key") == question.expected_key
    )
    signal_noise_ratio = signal_records / len(records) if records else 0.0
    return {
        "correct": correct,
        "first_exact_rank": (
            first_exact_index + 1 if first_exact_index is not None else None
        ),
        "retrieved_keys": [record.get("key") for record in records],
        "retrieved_tokens": retrieved_tokens,
        "signal_noise_ratio": signal_noise_ratio,
        "stale_conflict": stale_retrieved,
    }


def evaluate_backend(
    backend: SharedActiveDigestBackend | SharedAppendLogBackend | PerAgentAppendLogBackend,
    events: list[Event],
    questions: list[Question],
) -> dict[str, Any]:
    for event in events:
        backend.ingest(event)

    per_question: list[dict[str, Any]] = []
    latencies: list[float] = []
    for question in questions:
        records, latency = backend.retrieve(question)
        latencies.append(latency)
        scored = score_retrieval(question, records)
        per_question.append(
            {
                "id": question.id,
                "asker": question.asker,
                "query": question.query,
                "expected_key": question.expected_key,
                "expected_value": question.expected_value,
                "requires_cross_agent_memory": question.requires_cross_agent_memory,
                "latency_seconds": latency,
                **scored,
            }
        )

    total_questions = len(per_question)
    correct = sum(1 for item in per_question if item["correct"])
    cross_agent = [
        item for item in per_question if item["requires_cross_agent_memory"]
    ]
    cross_agent_correct = sum(1 for item in cross_agent if item["correct"])
    retrieved_tokens = sum(int(item["retrieved_tokens"]) for item in per_question)
    stale_conflicts = sum(1 for item in per_question if item["stale_conflict"])
    signal_noise_values = [
        float(item["signal_noise_ratio"]) for item in per_question
    ]
    return {
        "backend": backend.name,
        "accuracy": correct / total_questions if total_questions else 0.0,
        "correct": correct,
        "cross_agent_accuracy": (
            cross_agent_correct / len(cross_agent) if cross_agent else 0.0
        ),
        "cross_agent_correct": cross_agent_correct,
        "ingested_tokens": backend.ingested_tokens,
        "p95_latency_seconds": p95(latencies),
        "questions": per_question,
        "retrieved_tokens": retrieved_tokens,
        "signal_noise_ratio": (
            statistics.fmean(signal_noise_values) if signal_noise_values else 0.0
        ),
        "stale_conflict_rate": (
            stale_conflicts / total_questions if total_questions else 0.0
        ),
        "total_questions": total_questions,
    }


def run(dataset_path: Path) -> dict[str, Any]:
    data, events, questions = load_dataset(dataset_path)
    backend_results = [
        evaluate_backend(SharedActiveDigestBackend(), events, questions),
        evaluate_backend(SharedAppendLogBackend(), events, questions),
        evaluate_backend(PerAgentAppendLogBackend(), events, questions),
    ]
    return {
        "benchmark": data["name"],
        "description": data["description"],
        "controls": data["controls"],
        "host_environment": {
            "platform": platform.platform(),
            "python": sys.version,
            "implementation": platform.python_implementation(),
        },
        "results": backend_results,
    }


def format_percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def markdown_report(result: dict[str, Any]) -> str:
    lines = [
        f"# {result['benchmark']}",
        "",
        result["description"],
        "",
        "## Summary",
        "",
        (
            "| Backend | Accuracy | Cross-Agent Accuracy | Ingested Tokens | "
            "Retrieved Tokens | p95 Latency (s) | Stale Conflict Rate | "
            "Signal/Noise |"
        ),
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for backend in result["results"]:
        lines.append(
            "| {backend} | {accuracy} | {cross_accuracy} | {ingested} | "
            "{retrieved} | {latency:.6f} | {stale} | {snr:.2f} |".format(
                backend=backend["backend"],
                accuracy=format_percent(float(backend["accuracy"])),
                cross_accuracy=format_percent(
                    float(backend["cross_agent_accuracy"])
                ),
                ingested=backend["ingested_tokens"],
                retrieved=backend["retrieved_tokens"],
                latency=float(backend["p95_latency_seconds"]),
                stale=format_percent(float(backend["stale_conflict_rate"])),
                snr=float(backend["signal_noise_ratio"]),
            )
        )

    lines.extend(["", "## Per-Question Accuracy", ""])
    lines.append("| Question | Backend | Correct | Retrieved Tokens | Retrieved Keys |")
    lines.append("| --- | --- | ---: | ---: | --- |")
    for backend in result["results"]:
        for item in backend["questions"]:
            lines.append(
                "| {qid} | {backend} | {correct} | {tokens} | {keys} |".format(
                    qid=item["id"],
                    backend=backend["backend"],
                    correct="yes" if item["correct"] else "no",
                    tokens=item["retrieved_tokens"],
                    keys=", ".join(str(key) for key in item["retrieved_keys"]),
                )
            )

    lines.extend(
        [
            "",
            "## Controls",
            "",
            f"- Backend LLM: {result['controls']['backend_llm']}",
            f"- Judge: {result['controls']['judge']}",
            (
                "- Prompt/system instructions: "
                f"{result['controls']['prompt_system_instructions']}"
            ),
            (
                "- Host: "
                f"{result['host_environment']['platform']} / "
                f"{result['host_environment']['implementation']}"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run(args.dataset)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    report = markdown_report(result)
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(report, encoding="utf-8")
    else:
        print(report)


if __name__ == "__main__":
    main()
