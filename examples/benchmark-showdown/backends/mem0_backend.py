"""Mem0 后端适配器 - 作为对比基线"""
from __future__ import annotations

import os
import time
from typing import Any

from .base import BaseMemoryBackend, BenchmarkResult, MemoryEntry


class Mem0Backend(BaseMemoryBackend):
    """通过 Mem0 SDK 接入的记忆后端 (对比组)"""

    def __init__(self):
        super().__init__("Mem0")
        self._client = None
        self._user_id: str = "benchmark-user"
        self._total_tokens = 0

    def setup(self) -> None:
        api_key = os.environ.get("MEM0_API_KEY", "")
        if not api_key:
            raise RuntimeError("需要设置 MEM0_API_KEY 环境变量")
        from mem0 import MemoryClient
        self._client = MemoryClient(api_key=api_key)

    def ingest(self, entry: MemoryEntry) -> BenchmarkResult:
        start = time.perf_counter()
        try:
            response = self._client.add(
                entry.content,
                user_id=self._user_id,
                metadata={"memory_type": entry.memory_type, **entry.metadata},
            )
            latency = (time.perf_counter() - start) * 1000
            # Mem0 API 不直接返回 token 用量，估算
            tokens = len(entry.content.split()) * 2  # 粗略估算
            self._total_tokens += tokens
            return BenchmarkResult(
                backend=self.name,
                operation="ingest",
                tokens_consumed=tokens,
                latency_ms=latency,
                raw_response=str(response),
            )
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            return BenchmarkResult(
                backend=self.name,
                operation="ingest",
                latency_ms=latency,
                raw_response=str(e),
                metadata={"error": True},
            )

    def retrieve(self, query: str, top_k: int = 5) -> BenchmarkResult:
        start = time.perf_counter()
        try:
            response = self._client.search(
                query,
                user_id=self._user_id,
                limit=top_k,
            )
            latency = (time.perf_counter() - start) * 1000
            memories = response.get("results", []) if isinstance(response, dict) else []
            tokens = len(query.split()) * 2 + sum(
                len(m.get("memory", "").split()) * 2 for m in memories
            )
            self._total_tokens += tokens
            return BenchmarkResult(
                backend=self.name,
                operation="retrieve",
                tokens_consumed=tokens,
                latency_ms=latency,
                accuracy_score=len(memories) / max(top_k, 1),
                raw_response=str(memories),
                metadata={"retrieved_count": len(memories)},
            )
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            return BenchmarkResult(
                backend=self.name,
                operation="retrieve",
                latency_ms=latency,
                raw_response=str(e),
                metadata={"error": True},
            )

    def get_conversation_tokens(self) -> int:
        return self._total_tokens

    def reset(self) -> None:
        self._total_tokens = 0
