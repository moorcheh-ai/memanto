"""抽象后端接口 - 所有记忆后端必须实现此接口"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryEntry:
    """单条记忆记录"""
    content: str
    memory_type: str = "fact"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkResult:
    """单次操作的基准测试结果"""
    backend: str
    operation: str  # "ingest" | "retrieve" | "full_cycle"
    tokens_consumed: int = 0
    latency_ms: float = 0.0
    accuracy_score: float = 0.0
    raw_response: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseMemoryBackend(ABC):
    """记忆后端抽象基类"""

    def __init__(self, name: str):
        self.name = name
        self._total_tokens = 0

    @abstractmethod
    def setup(self) -> None:
        """初始化后端连接"""

    @abstractmethod
    def ingest(self, entry: MemoryEntry) -> BenchmarkResult:
        """存储一条记忆"""

    @abstractmethod
    def retrieve(self, query: str, top_k: int = 5) -> BenchmarkResult:
        """根据查询检索记忆"""

    @abstractmethod
    def get_conversation_tokens(self) -> int:
        """获取当前会话消耗的总token数"""

    @abstractmethod
    def reset(self) -> None:
        """重置后端状态"""

    def full_cycle(self, entries: list[MemoryEntry], query: str) -> list[BenchmarkResult]:
        """完整的存储-检索周期"""
        results = []
        # 存储阶段
        for entry in entries:
            r = self.ingest(entry)
            results.append(r)
        # 检索阶段
        r = self.retrieve(query)
        results.append(r)
        return results
