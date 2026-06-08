"""
Memanto adapter for the benchmark suite.

Stores messages directly via moorcheh-sdk without LLM extraction —
all token cost comes from the text content itself, not from LLM inference.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from moorcheh_sdk import MoorchehClient

from metrics.token_counter import count, count_results


class MenantoAdapter:
    def __init__(self, namespace: str, api_key: str | None = None) -> None:
        self.namespace = namespace
        self._client = MoorchehClient(api_key=api_key or os.environ["MOORCHEH_API_KEY"])
        self._write_latencies: list[float] = []
        self._read_latencies: list[float] = []
        self.total_tokens_written: int = 0
        self.total_tokens_retrieved: int = 0

    def ingest_session(self, session_id: str, messages: list[str]) -> dict:
        """Store all messages from a session as individual documents."""
        start = time.perf_counter()
        tokens_written = 0

        docs = [
            {
                "text": f"[{session_id}] {msg}",
                "tags": [session_id],
            }
            for msg in messages
        ]

        self._client.documents.upsert(
            namespace=self.namespace,
            documents=docs,
        )

        latency = time.perf_counter() - start
        tokens_written = sum(count(d["text"]) for d in docs)
        self.total_tokens_written += tokens_written
        self._write_latencies.append(latency)

        return {"tokens_written": tokens_written, "write_latency_s": round(latency, 4)}

    def query(self, question: str, top_k: int = 5) -> dict:
        """Retrieve relevant memories for a query."""
        start = time.perf_counter()

        results = self._client.similarity_search(
            namespace=self.namespace,
            query=question,
            top_k=top_k,
        )

        latency = time.perf_counter() - start
        tokens_retrieved = count_results(results if isinstance(results, list) else [])
        self.total_tokens_retrieved += tokens_retrieved
        self._read_latencies.append(latency)

        # Flatten results to a single text block for the judge
        texts = []
        for r in (results if isinstance(results, list) else []):
            if isinstance(r, dict):
                texts.append(r.get("text") or r.get("content") or str(r))
            else:
                texts.append(str(r))

        return {
            "retrieved_text": "\n---\n".join(texts),
            "tokens_retrieved": tokens_retrieved,
            "read_latency_s": round(latency, 4),
            "result_count": len(results) if isinstance(results, list) else 0,
        }

    def p95_write_latency(self) -> float:
        return _p95(self._write_latencies)

    def p95_read_latency(self) -> float:
        return _p95(self._read_latencies)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = max(0, int(len(sorted_vals) * 0.95) - 1)
    return round(sorted_vals[idx], 4)
