"""Benchmark Memanto against other agent memory frameworks.

The default run is fully offline and deterministic so contributors can smoke-test
changes without API keys. For real comparisons, select ``memanto-rest`` and
``mem0`` adapters and provide the environment variables documented below.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any

DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "benchmarks"
    / "agent_memory_showdown"
    / "dataset.json"
)

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "by",
    "does",
    "for",
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
    "which",
    "who",
}
CURRENT_HINTS = {"current", "latest", "now", "prefer", "prefers", "preference"}
TYPE_HINTS = {
    "incident": "event",
    "caused": "event",
    "deploy": "fact",
    "deploying": "fact",
    "latency": "instruction",
    "p95": "instruction",
    "prefer": "preference",
    "prefers": "preference",
    "preference": "preference",
    "review": "relationship",
    "security": "relationship",
    "sign": "relationship",
}


@dataclass(frozen=True)
class MemoryEvent:
    id: str
    timestamp: str
    type: str
    title: str
    content: str
    tags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BenchmarkQuestion:
    id: str
    query: str
    expected_terms: tuple[str, ...]
    forbidden_terms: tuple[str, ...] = field(default_factory=tuple)
    top_k: int = 3


@dataclass(frozen=True)
class BenchmarkDataset:
    name: str
    description: str
    memories: tuple[MemoryEvent, ...]
    questions: tuple[BenchmarkQuestion, ...]


@dataclass(frozen=True)
class RecalledMemory:
    content: str
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def normalize_text(text: str) -> str:
    """Lower-case and collapse punctuation for phrase/token matching."""

    normalized = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return re.sub(r"\s+", " ", normalized).strip()


def token_set(text: str) -> set[str]:
    return {token for token in normalize_text(text).split() if token not in STOPWORDS}


def lexical_score(query: str, content: str) -> float:
    query_tokens = token_set(query)
    if not query_tokens:
        return 0.0
    content_tokens = token_set(content)
    overlap = len(query_tokens & content_tokens)
    return overlap / len(query_tokens)


def contains_phrase(text: str, phrase: str) -> bool:
    return normalize_text(phrase) in normalize_text(text)


def estimate_tokens(text: str) -> int:
    """Fast deterministic token estimate used when tokenizer deps are absent."""

    stripped = text.strip()
    if not stripped:
        return 0
    return max(1, math.ceil(len(stripped) / 4))


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = math.ceil((percentile_value / 100.0) * len(sorted_values)) - 1
    index = min(max(index, 0), len(sorted_values) - 1)
    return sorted_values[index]


def load_dataset(path: Path | str = DEFAULT_DATASET_PATH) -> BenchmarkDataset:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    memories = tuple(
        MemoryEvent(
            id=item["id"],
            timestamp=item["timestamp"],
            type=item["type"],
            title=item.get("title", item["id"]),
            content=item["content"],
            tags=tuple(item.get("tags", [])),
        )
        for item in data["memories"]
    )
    questions = tuple(
        BenchmarkQuestion(
            id=item["id"],
            query=item["query"],
            expected_terms=tuple(item["expected_terms"]),
            forbidden_terms=tuple(item.get("forbidden_terms", [])),
            top_k=int(item.get("top_k", 3)),
        )
        for item in data["questions"]
    )
    return BenchmarkDataset(
        name=data["name"],
        description=data.get("description", ""),
        memories=memories,
        questions=questions,
    )


class MemoryAdapter:
    name = "adapter"

    def reset(self) -> None:
        """Clear benchmark state when the backing framework supports it."""

    def remember(self, memory: MemoryEvent) -> None:
        raise NotImplementedError

    def recall(self, query: str, top_k: int) -> list[RecalledMemory]:
        raise NotImplementedError


class LexicalMemoryAdapter(MemoryAdapter):
    """Append-only lexical baseline, similar to a naive passive memory store."""

    name = "lexical-baseline"

    def __init__(self) -> None:
        self._memories: list[MemoryEvent] = []

    def reset(self) -> None:
        self._memories.clear()

    def remember(self, memory: MemoryEvent) -> None:
        self._memories.append(memory)

    def recall(self, query: str, top_k: int) -> list[RecalledMemory]:
        scored = [
            (lexical_score(query, memory.content), index, memory)
            for index, memory in enumerate(self._memories)
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [
            RecalledMemory(
                content=memory.content,
                score=score,
                metadata={"id": memory.id, "type": memory.type},
            )
            for score, _, memory in scored[:top_k]
            if score > 0
        ]


class MemantoOfflineAdapter(MemoryAdapter):
    """Deterministic adapter that mirrors Memanto's typed/temporal contract.

    It is not a substitute for the live service, but it gives CI a stable way to
    exercise the benchmark math and demonstrates why typed, recency-aware memory
    should be compared against append-only baselines.
    """

    name = "memanto-offline"

    def __init__(self) -> None:
        self._memories: list[MemoryEvent] = []

    def reset(self) -> None:
        self._memories.clear()

    def remember(self, memory: MemoryEvent) -> None:
        self._memories.append(memory)

    def recall(self, query: str, top_k: int) -> list[RecalledMemory]:
        query_tokens = token_set(query)
        preferred_type = next(
            (memory_type for hint, memory_type in TYPE_HINTS.items() if hint in query_tokens),
            None,
        )
        newest_by_tag = self._newest_ids_by_tag()
        wants_current = bool(query_tokens & CURRENT_HINTS)
        scored: list[tuple[float, str, MemoryEvent]] = []
        for memory in self._memories:
            score = lexical_score(query, memory.content)
            if preferred_type and memory.type == preferred_type:
                score += 0.30
            if wants_current and any(newest_by_tag.get(tag) == memory.id for tag in memory.tags):
                score += 0.45
            # Tiny ISO timestamp tie-breaker keeps newer memories ahead while
            # preserving the main lexical/type signals.
            score += self._recency_rank(memory) * 0.001
            if score > 0:
                scored.append((score, memory.timestamp, memory))
        scored.sort(key=lambda item: (-item[0], item[1]), reverse=False)
        return [
            RecalledMemory(
                content=memory.content,
                score=score,
                metadata={"id": memory.id, "type": memory.type, "tags": list(memory.tags)},
            )
            for score, _, memory in scored[:top_k]
        ]

    def _newest_ids_by_tag(self) -> dict[str, str]:
        newest: dict[str, MemoryEvent] = {}
        for memory in self._memories:
            for tag in memory.tags:
                current = newest.get(tag)
                if current is None or memory.timestamp > current.timestamp:
                    newest[tag] = memory
        return {tag: memory.id for tag, memory in newest.items()}

    def _recency_rank(self, target: MemoryEvent) -> int:
        timestamps = sorted({memory.timestamp for memory in self._memories})
        return timestamps.index(target.timestamp) if target.timestamp in timestamps else 0


class MemantoRestAdapter(MemoryAdapter):
    """Adapter for a running Memanto REST server.

    Required environment variables:
    - MEMANTO_BASE_URL, for example http://localhost:8000
    - MEMANTO_AGENT_ID
    - MEMANTO_SESSION_TOKEN from `memanto agent activate` or the API
    """

    name = "memanto-rest"

    def __init__(self) -> None:
        self.base_url = os.environ.get("MEMANTO_BASE_URL", "http://localhost:8000").rstrip(
            "/"
        )
        self.agent_id = os.environ.get("MEMANTO_AGENT_ID")
        self.session_token = os.environ.get("MEMANTO_SESSION_TOKEN")
        if not self.agent_id or not self.session_token:
            raise RuntimeError(
                "memanto-rest requires MEMANTO_AGENT_ID and MEMANTO_SESSION_TOKEN"
            )

    def remember(self, memory: MemoryEvent) -> None:
        payload = {
            "content": memory.content,
            "type": memory.type,
            "title": memory.title,
            "confidence": 0.9,
            "tags": list(memory.tags),
            "source": "benchmark",
            "provenance": "explicit_statement",
        }
        self._post(f"/api/v2/agents/{self.agent_id}/remember", payload)

    def recall(self, query: str, top_k: int) -> list[RecalledMemory]:
        response = self._post(
            f"/api/v2/agents/{self.agent_id}/recall",
            {"query": query, "limit": top_k},
        )
        memories = response.get("memories", []) if isinstance(response, dict) else []
        return [self._coerce_recalled_memory(item) for item in memories]

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Session-Token": self.session_token or "",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Memanto REST {exc.code} for {path}: {body}") from exc

    @staticmethod
    def _coerce_recalled_memory(item: Any) -> RecalledMemory:
        if isinstance(item, str):
            return RecalledMemory(content=item)
        if not isinstance(item, dict):
            return RecalledMemory(content=str(item))
        content = str(
            item.get("content")
            or item.get("memory")
            or item.get("text")
            or item.get("document")
            or item
        )
        score = item.get("score") or item.get("similarity")
        return RecalledMemory(
            content=content,
            score=float(score) if isinstance(score, int | float) else None,
            metadata={key: value for key, value in item.items() if key != "content"},
        )


class Mem0Adapter(MemoryAdapter):
    """Best-effort adapter for the real Mem0 package (`pip install mem0ai`)."""

    name = "mem0"

    def __init__(self) -> None:
        try:
            from mem0 import Memory  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover - optional dependency path
            raise RuntimeError("mem0 adapter requires: python -m pip install mem0ai") from exc

        config = self._load_config()
        if config:
            self.client = Memory.from_config(config)  # pragma: no cover
        else:
            self.client = Memory()  # pragma: no cover
        self.user_id = os.environ.get("MEM0_USER_ID", f"memanto-benchmark-{time.time_ns()}")

    def remember(self, memory: MemoryEvent) -> None:  # pragma: no cover
        metadata = {
            "benchmark_id": memory.id,
            "timestamp": memory.timestamp,
            "type": memory.type,
            "tags": list(memory.tags),
        }
        self.client.add(memory.content, user_id=self.user_id, metadata=metadata)

    def recall(self, query: str, top_k: int) -> list[RecalledMemory]:  # pragma: no cover
        try:
            response = self.client.search(query, user_id=self.user_id, limit=top_k)
        except TypeError:
            response = self.client.search(query, user_id=self.user_id)
        items = response.get("results", response) if isinstance(response, dict) else response
        if not isinstance(items, list):
            items = [items]
        return [self._coerce_recalled_memory(item) for item in items[:top_k]]

    @staticmethod
    def _load_config() -> dict[str, Any] | None:
        raw = os.environ.get("MEM0_CONFIG_JSON")
        if not raw:
            return None
        possible_path = Path(raw)
        if possible_path.exists():
            return json.loads(possible_path.read_text(encoding="utf-8"))
        return json.loads(raw)

    @staticmethod
    def _coerce_recalled_memory(item: Any) -> RecalledMemory:
        if isinstance(item, str):
            return RecalledMemory(content=item)
        if not isinstance(item, dict):
            return RecalledMemory(content=str(item))
        content = str(item.get("memory") or item.get("text") or item.get("content") or item)
        score = item.get("score") or item.get("relevance")
        return RecalledMemory(
            content=content,
            score=float(score) if isinstance(score, int | float) else None,
            metadata={key: value for key, value in item.items() if key not in {"memory", "text"}},
        )


def score_question(question: BenchmarkQuestion, memories: list[RecalledMemory]) -> dict[str, Any]:
    joined = "\n".join(memory.content for memory in memories)
    expected_hits = [
        term for term in question.expected_terms if contains_phrase(joined, term)
    ]
    forbidden_hits = [
        term for term in question.forbidden_terms if contains_phrase(joined, term)
    ]
    recall = len(expected_hits) / max(1, len(question.expected_terms))
    penalty = len(forbidden_hits) / max(1, len(question.forbidden_terms)) if forbidden_hits else 0.0
    score = max(0.0, recall - penalty)
    return {
        "question_id": question.id,
        "query": question.query,
        "score": round(score, 4),
        "expected_hits": expected_hits,
        "missing_expected_terms": [
            term for term in question.expected_terms if term not in expected_hits
        ],
        "forbidden_hits": forbidden_hits,
        "retrieved_count": len(memories),
        "retrieved_tokens": sum(estimate_tokens(memory.content) for memory in memories),
    }


def run_adapter(adapter: MemoryAdapter, dataset: BenchmarkDataset) -> dict[str, Any]:
    adapter.reset()
    ingest_latencies: list[float] = []
    recall_latencies: list[float] = []
    ingest_tokens = 0

    for memory in dataset.memories:
        start = time.perf_counter()
        adapter.remember(memory)
        ingest_latencies.append(time.perf_counter() - start)
        ingest_tokens += estimate_tokens(memory.content)

    question_results = []
    retrieved_tokens = 0
    for question in dataset.questions:
        start = time.perf_counter()
        recalled = adapter.recall(question.query, question.top_k)
        recall_latencies.append(time.perf_counter() - start)
        scored = score_question(question, recalled)
        retrieved_tokens += int(scored["retrieved_tokens"])
        question_results.append(scored)

    accuracy = mean(result["score"] for result in question_results) if question_results else 0.0
    return {
        "framework": adapter.name,
        "accuracy": round(accuracy, 4),
        "resource_footprint": {
            "estimated_tokens_ingested": ingest_tokens,
            "estimated_tokens_retrieved": retrieved_tokens,
            "avg_retrieved_tokens_per_query": round(
                retrieved_tokens / max(1, len(dataset.questions)), 2
            ),
            "p95_ingest_latency_ms": round(percentile(ingest_latencies, 95) * 1000, 3),
            "p95_recall_latency_ms": round(percentile(recall_latencies, 95) * 1000, 3),
        },
        "questions": question_results,
    }


def make_adapter(name: str) -> MemoryAdapter:
    normalized = name.strip().lower()
    if normalized in {"lexical", "lexical-baseline", "baseline"}:
        return LexicalMemoryAdapter()
    if normalized in {"memanto-offline", "memanto-local", "offline"}:
        return MemantoOfflineAdapter()
    if normalized in {"memanto", "memanto-rest", "rest"}:
        return MemantoRestAdapter()
    if normalized == "mem0":
        return Mem0Adapter()
    raise ValueError(f"Unknown framework adapter: {name}")


def run_benchmark(dataset: BenchmarkDataset, framework_names: list[str]) -> dict[str, Any]:
    results = [run_adapter(make_adapter(name), dataset) for name in framework_names]
    return {
        "dataset": {
            "name": dataset.name,
            "description": dataset.description,
            "memory_count": len(dataset.memories),
            "question_count": len(dataset.questions),
        },
        "results": results,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Memanto Memory Benchmark: {report['dataset']['name']}",
        "",
        report["dataset"].get("description", ""),
        "",
        "| Framework | Accuracy | Tokens Ingested | Tokens Retrieved | p95 Recall (ms) |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for result in report["results"]:
        footprint = result["resource_footprint"]
        lines.append(
            "| {framework} | {accuracy:.4f} | {ingest} | {retrieved} | {latency:.3f} |".format(
                framework=result["framework"],
                accuracy=result["accuracy"],
                ingest=footprint["estimated_tokens_ingested"],
                retrieved=footprint["estimated_tokens_retrieved"],
                latency=footprint["p95_recall_latency_ms"],
            )
        )
    lines.append("")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare Memanto against another agent memory framework."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET_PATH,
        help="Path to benchmark dataset JSON.",
    )
    parser.add_argument(
        "--frameworks",
        default="memanto-offline,lexical-baseline",
        help="Comma-separated adapters: memanto-offline, lexical-baseline, memanto-rest, mem0.",
    )
    parser.add_argument("--output", type=Path, help="Write benchmark report to this path.")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format for stdout and --output.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    dataset = load_dataset(args.dataset)
    framework_names = [name.strip() for name in args.frameworks.split(",") if name.strip()]
    report = run_benchmark(dataset, framework_names)
    rendered = (
        json.dumps(report, indent=2, sort_keys=True)
        if args.format == "json"
        else render_markdown(report)
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
