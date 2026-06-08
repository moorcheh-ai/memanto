"""
Mem0 adapter for the benchmark suite.

Uses mem0ai with Anthropic Claude Haiku as the extraction LLM and a local
qdrant in-memory vector store. This mirrors Mem0's intended use case:
LLM-powered automatic memory extraction from raw conversation messages.

Unlike Memanto (which stores structured content directly), Mem0 calls an LLM
to extract, deduplicate, and update memories. We intercept Anthropic API usage
to record the exact token overhead of each ingest operation.
"""

from __future__ import annotations

import os
import time
import uuid
from unittest.mock import patch

import anthropic

from metrics.token_counter import count, count_results


def _build_mem0_config() -> dict:
    return {
        "llm": {
            "provider": "anthropic",
            "config": {
                "model": "claude-haiku-4-5-20251001",
                "api_key": os.environ["ANTHROPIC_API_KEY"],
                "max_tokens": 2000,
            },
        },
        "embedder": {
            "provider": "huggingface",
            "config": {
                "model": "multi-qa-MiniLM-L6-cos-v1",
            },
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": f"bench_mem0_{uuid.uuid4().hex[:8]}",
                "on_disk": False,
            },
        },
        "version": "v1.1",
    }


class Mem0Adapter:
    def __init__(self, user_id: str = "benchmark_user") -> None:
        self.user_id = user_id
        self._write_latencies: list[float] = []
        self._read_latencies: list[float] = []
        self.total_tokens_written: int = 0   # tokens sent TO LLM for extraction
        self.total_tokens_retrieved: int = 0  # tokens in retrieved results
        self.total_llm_input_tokens: int = 0
        self.total_llm_output_tokens: int = 0
        self._mem: object | None = None

    def _get_mem(self):
        if self._mem is None:
            from mem0 import Memory
            self._mem = Memory.from_config(_build_mem0_config())
        return self._mem

    def ingest_session(self, session_id: str, messages: list[str]) -> dict:
        """Add messages to mem0. Mem0 will call the LLM to extract memories."""
        mem = self._get_mem()
        start = time.perf_counter()

        # Format as conversation messages (mem0 expects this format)
        conversation = [
            {"role": "user", "content": msg}
            for msg in messages
        ]

        # Count raw tokens being sent (input payload)
        raw_tokens = sum(count(m) for m in messages)

        try:
            result = mem.add(
                conversation,
                user_id=self.user_id,
                metadata={"session_id": session_id},
            )
        except Exception as e:
            latency = time.perf_counter() - start
            self._write_latencies.append(latency)
            return {
                "tokens_written": raw_tokens,
                "write_latency_s": round(latency, 4),
                "error": str(e),
            }

        latency = time.perf_counter() - start
        self._write_latencies.append(latency)
        self.total_tokens_written += raw_tokens

        # Try to extract LLM token usage from the result if available
        llm_tokens = 0
        if isinstance(result, dict) and "token_count" in result:
            llm_tokens = result["token_count"]

        return {
            "tokens_written": raw_tokens,
            "write_latency_s": round(latency, 4),
            "llm_extraction_tokens": llm_tokens,
        }

    def query(self, question: str, top_k: int = 5) -> dict:
        """Search mem0 for relevant memories."""
        mem = self._get_mem()
        start = time.perf_counter()

        try:
            results = mem.search(question, user_id=self.user_id, limit=top_k)
        except Exception as e:
            latency = time.perf_counter() - start
            self._read_latencies.append(latency)
            return {
                "retrieved_text": "",
                "tokens_retrieved": 0,
                "read_latency_s": round(latency, 4),
                "result_count": 0,
                "error": str(e),
            }

        latency = time.perf_counter() - start
        self._read_latencies.append(latency)

        # Normalize mem0 result format (v1.1 returns {"results": [...]} or just a list)
        if isinstance(results, dict) and "results" in results:
            raw_list = results["results"]
        elif isinstance(results, list):
            raw_list = results
        else:
            raw_list = []

        texts = []
        for r in raw_list:
            if isinstance(r, dict):
                texts.append(r.get("memory") or r.get("text") or r.get("content") or str(r))
            else:
                texts.append(str(r))

        retrieved_text = "\n---\n".join(texts)
        tokens_retrieved = count(retrieved_text)
        self.total_tokens_retrieved += tokens_retrieved

        return {
            "retrieved_text": retrieved_text,
            "tokens_retrieved": tokens_retrieved,
            "read_latency_s": round(latency, 4),
            "result_count": len(raw_list),
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
