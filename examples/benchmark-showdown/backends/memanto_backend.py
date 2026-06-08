"""Memanto 后端适配器"""
from __future__ import annotations

import os
import time
from typing import Any

from .base import BaseMemoryBackend, BenchmarkResult, MemoryEntry


class MemantoBackend(BaseMemoryBackend):
    """通过 Memanto Python SDK 接入的记忆后端"""

    def __init__(self):
        super().__init__("Memanto")
        self._client = None
        self._agent_id: str = ""
        self._session_id: str = ""
        self._total_tokens = 0

    def setup(self) -> None:
        api_key = os.environ.get("MEMANTO_API_KEY") or os.environ.get("MOORCHEH_API_KEY", "")
        if not api_key:
            raise RuntimeError("需要设置 MEMANTO_API_KEY 或 MOORCHEH_API_KEY 环境变量")
        self._agent_id = os.environ.get("MEMANTO_AGENT_ID", "benchmark-agent")
        # 使用 CLI SDK 客户端
        from memanto.cli.client.sdk_client import SdkClient
        self._client = SdkClient(api_key=api_key)

    def ingest(self, entry: MemoryEntry) -> BenchmarkResult:
        start = time.perf_counter()
        try:
            response = self._client.remember(
                agent_id=self._agent_id,
                content=entry.content,
                memory_type=entry.memory_type,
            )
            latency = (time.perf_counter() - start) * 1000
            tokens = getattr(response, "tokens_consumed", 0) or 0
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
            response = self._client.recall(
                agent_id=self._agent_id,
                query=query,
                top_k=top_k,
            )
            latency = (time.perf_counter() - start) * 1000
            tokens = getattr(response, "tokens_consumed", 0) or 0
            self._total_tokens += tokens
            memories = getattr(response, "memories", []) or []
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
