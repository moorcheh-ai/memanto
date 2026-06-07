#!/usr/bin/env python3
"""Benchmark current-state recall after access and retention revocations."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import re
import shutil
import statistics
import sys
import tempfile
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = ROOT / "dataset.json"
DEFAULT_OUTPUT = ROOT / "results" / "fixture-results.json"
TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def token_count(text: str) -> int:
    """Return a deterministic tokenizer-independent token proxy."""
    return len(TOKEN_RE.findall(text))


def percentile(values: list[float], percentile_value: float) -> float:
    """Return an interpolated percentile for a non-empty list."""
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile_value
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def extract_text(value: Any) -> str:
    """Normalize framework-specific search results into readable text."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("text", "memory", "content", "document"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                return candidate
        return json.dumps(value, sort_keys=True)
    return str(value)


def package_version(name: str) -> str | None:
    """Return an installed package version without making it mandatory."""
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


@dataclass
class ProbeResult:
    """Per-probe retrieval and correctness metrics."""

    probe_id: str
    query: str
    retrieved_text: str
    retrieved_tokens: int
    latency_ms: float
    required_hits: int
    required_total: int
    forbidden_hits: int
    forbidden_total: int
    accuracy: float
    stale_leak: bool


class MemoryAdapter(ABC):
    """Minimal interface shared by the benchmark backends."""

    name: str

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id

    @abstractmethod
    def write(self, event: dict[str, Any]) -> None:
        """Persist one event."""

    @abstractmethod
    def search(self, query: str, limit: int) -> list[Any]:
        """Return relevant memories."""

    def close(self) -> None:
        """Release optional backend resources."""


class FixtureAdapter(MemoryAdapter):
    """Deterministic current-state digest used only for smoke testing."""

    name = "fixture"

    def __init__(self, run_id: str) -> None:
        super().__init__(run_id)
        self._state: dict[str, str] = {}

    def write(self, event: dict[str, Any]) -> None:
        self._state[event["fact_key"]] = event["content"]

    def search(self, query: str, limit: int) -> list[str]:
        query_terms = set(TOKEN_RE.findall(query.lower()))
        ranked = sorted(
            self._state.values(),
            key=lambda text: len(query_terms & set(TOKEN_RE.findall(text.lower()))),
            reverse=True,
        )
        return ranked[:limit]


class MemantoAdapter(MemoryAdapter):
    """Real Memanto SDK adapter backed by Moorcheh."""

    name = "memanto"

    def __init__(self, run_id: str) -> None:
        super().__init__(run_id)
        api_key = os.environ.get("MOORCHEH_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("MOORCHEH_API_KEY is required for --backend memanto")

        from memanto.cli.client.sdk_client import SdkClient

        self._sdk = SdkClient(api_key=api_key)
        self._agent_id = f"revocation-benchmark-{run_id}"
        self._sdk.create_agent(
            agent_id=self._agent_id,
            pattern="tool",
            description=(
                "Benchmark: permission revocation and sensitive-memory retention"
            ),
        )
        self._sdk.activate_agent(self._agent_id, duration_hours=2)

    def write(self, event: dict[str, Any]) -> None:
        self._sdk.remember(
            agent_id=self._agent_id,
            memory_type=event["type"],
            title=event["title"],
            content=event["content"],
            confidence=event.get("confidence", 0.95),
            tags=[event["fact_key"], event["session_id"]],
            provenance=event.get("provenance", "explicit_statement"),
        )

    def search(self, query: str, limit: int) -> list[Any]:
        result = self._sdk.recall(
            agent_id=self._agent_id,
            query=query,
            limit=limit,
        )
        return result.get("memories", [])

    def close(self) -> None:
        try:
            self._sdk.deactivate_agent(self._agent_id)
        except Exception:
            pass


class Mem0Adapter(MemoryAdapter):
    """Real Mem0 adapter using a local embedder and in-memory Qdrant."""

    name = "mem0"

    def __init__(self, run_id: str) -> None:
        super().__init__(run_id)
        from mem0 import Memory

        self._qdrant_path = Path(tempfile.gettempdir()) / f"mem0-revocation-{run_id}"
        config = {
            "embedder": {
                "provider": "fastembed",
                "config": {"model": "BAAI/bge-small-en-v1.5"},
            },
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "collection_name": f"revocation_{run_id}",
                    "embedding_model_dims": 384,
                    "path": str(self._qdrant_path),
                    "on_disk": False,
                },
            },
        }
        self._memory = Memory.from_config(config)
        self._user_id = f"revocation-{run_id}"

    def write(self, event: dict[str, Any]) -> None:
        self._memory.add(
            event["content"],
            user_id=self._user_id,
            metadata={
                "fact_key": event["fact_key"],
                "session_id": event["session_id"],
            },
            infer=False,
        )

    def search(self, query: str, limit: int) -> list[Any]:
        result = self._memory.search(
            query,
            user_id=self._user_id,
            limit=limit,
            rerank=False,
        )
        if isinstance(result, dict):
            return result.get("results", [])
        return result

    def close(self) -> None:
        vector_store = getattr(self._memory, "vector_store", None)
        client = getattr(vector_store, "client", None)
        if client and hasattr(client, "close"):
            client.close()
        shutil.rmtree(self._qdrant_path, ignore_errors=True)


ADAPTERS = {
    "fixture": FixtureAdapter,
    "memanto": MemantoAdapter,
    "mem0": Mem0Adapter,
}


def load_dataset(path: Path) -> dict[str, Any]:
    """Load and minimally validate the benchmark dataset."""
    dataset = json.loads(path.read_text(encoding="utf-8"))
    if not dataset.get("sessions") or not dataset.get("probes"):
        raise ValueError("dataset must contain non-empty sessions and probes")
    return dataset


def score_probe(probe: dict[str, Any], retrieved_text: str) -> tuple[int, int, float]:
    """Score required current facts and forbidden stale facts."""
    normalized = retrieved_text.lower()
    required = [term.lower() for term in probe["required_terms"]]
    forbidden = [term.lower() for term in probe["forbidden_terms"]]
    required_hits = sum(term in normalized for term in required)
    forbidden_hits = sum(term in normalized for term in forbidden)
    accuracy = required_hits / len(required) if required else 1.0
    return required_hits, forbidden_hits, accuracy


def run_backend(
    backend_name: str,
    dataset: dict[str, Any],
    limit: int,
    settle_seconds: float,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Execute one backend and return a fully serializable report."""
    run_id = run_id or uuid.uuid4().hex[:12]
    adapter = ADAPTERS[backend_name](run_id)
    write_latencies: list[float] = []
    ingested_tokens = 0
    probe_results: list[ProbeResult] = []

    try:
        for session in dataset["sessions"]:
            for raw_event in session["events"]:
                event = {**raw_event, "session_id": session["id"]}
                started = time.perf_counter()
                adapter.write(event)
                latency_ms = (time.perf_counter() - started) * 1000
                write_latencies.append(
                    0.0 if backend_name == "fixture" else latency_ms
                )
                ingested_tokens += token_count(event["content"])
                if settle_seconds:
                    time.sleep(settle_seconds)

        for probe in dataset["probes"]:
            started = time.perf_counter()
            hits = adapter.search(probe["query"], limit)
            latency_ms = (time.perf_counter() - started) * 1000
            if backend_name == "fixture":
                latency_ms = 0.0
            retrieved_text = "\n".join(extract_text(hit) for hit in hits)
            required_hits, forbidden_hits, accuracy = score_probe(
                probe, retrieved_text
            )
            probe_results.append(
                ProbeResult(
                    probe_id=probe["id"],
                    query=probe["query"],
                    retrieved_text=retrieved_text,
                    retrieved_tokens=token_count(retrieved_text),
                    latency_ms=latency_ms,
                    required_hits=required_hits,
                    required_total=len(probe["required_terms"]),
                    forbidden_hits=forbidden_hits,
                    forbidden_total=len(probe["forbidden_terms"]),
                    accuracy=accuracy,
                    stale_leak=forbidden_hits > 0,
                )
            )
    finally:
        adapter.close()

    total_probes = len(probe_results)
    return {
        "schema_version": 1,
        "backend": backend_name,
        "run_id": run_id,
        "mode": "smoke_fixture" if backend_name == "fixture" else "live_framework",
        "dataset": dataset["name"],
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine(),
            "retrieval_limit": limit,
            "settle_seconds": settle_seconds,
            "tokenizer": "regex word-and-punctuation proxy",
            "package_versions": {
                "memanto": package_version("memanto"),
                "mem0ai": package_version("mem0ai"),
                "fastembed": package_version("fastembed"),
                "qdrant-client": package_version("qdrant-client"),
            },
        },
        "summary": {
            "retrieval_accuracy": statistics.fmean(
                result.accuracy for result in probe_results
            ),
            "stale_leak_rate": (
                sum(result.stale_leak for result in probe_results) / total_probes
            ),
            "ingested_tokens": ingested_tokens,
            "retrieved_tokens_total": sum(
                result.retrieved_tokens for result in probe_results
            ),
            "retrieved_tokens_mean": statistics.fmean(
                result.retrieved_tokens for result in probe_results
            ),
            "write_latency_p95_ms": percentile(write_latencies, 0.95),
            "read_latency_p95_ms": percentile(
                [result.latency_ms for result in probe_results], 0.95
            ),
        },
        "probes": [asdict(result) for result in probe_results],
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render a concise human-readable report."""
    summary = report["summary"]
    write_p95_seconds = summary["write_latency_p95_ms"] / 1000
    read_p95_seconds = summary["read_latency_p95_ms"] / 1000
    lines = [
        f"# Revocation Memory Benchmark: {report['backend']}",
        "",
        f"- Mode: `{report['mode']}`",
        f"- Dataset: `{report['dataset']}`",
        f"- Retrieval accuracy: {summary['retrieval_accuracy']:.1%}",
        f"- Stale leak rate: {summary['stale_leak_rate']:.1%}",
        f"- Ingested tokens: {summary['ingested_tokens']}",
        f"- Retrieved tokens (mean): {summary['retrieved_tokens_mean']:.1f}",
        f"- Write p95: {write_p95_seconds:.4f} seconds",
        f"- Read p95: {read_p95_seconds:.4f} seconds",
        "",
        "| Probe | Accuracy | Stale leak | Retrieved tokens | Latency ms |",
        "|---|---:|---:|---:|---:|",
    ]
    for probe in report["probes"]:
        lines.append(
            f"| {probe['probe_id']} | {probe['accuracy']:.1%} | "
            f"{'yes' if probe['stale_leak'] else 'no'} | "
            f"{probe['retrieved_tokens']} | {probe['latency_ms']:.2f} |"
        )
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=sorted(ADAPTERS), default="fixture")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--settle-seconds", type=float, default=0.0)
    return parser.parse_args()


def main() -> int:
    """Run the selected backend and persist JSON plus optional Markdown."""
    args = parse_args()
    if args.limit < 1:
        raise SystemExit("--limit must be at least 1")
    dataset = load_dataset(args.dataset)
    report = run_backend(
        args.backend,
        dataset,
        limit=args.limit,
        settle_seconds=args.settle_seconds,
        run_id="fixture" if args.backend == "fixture" else None,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    markdown_path = args.markdown or args.output.with_suffix(".md")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
