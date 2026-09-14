"""Deterministic fixed-dim embedder — no API spend."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from typing import Any


class MockEmbedder:
    """Drop-in for graphiti_core.embedder.client.EmbedderClient."""

    def __init__(self, embedding_dim: int = 64) -> None:
        self.embedding_dim = embedding_dim

    def _vec(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode('utf-8')).digest()
        # Expand digest into embedding_dim floats in [-1, 1]
        vals: list[float] = []
        i = 0
        while len(vals) < self.embedding_dim:
            b = digest[i % len(digest)]
            vals.append((b / 127.5) - 1.0)
            i += 1
        # L2 normalize for stability
        norm = math.sqrt(sum(v * v for v in vals)) or 1.0
        return [v / norm for v in vals]

    async def create(
        self, input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]]
    ) -> list[float]:
        if isinstance(input_data, str):
            return self._vec(input_data)
        if isinstance(input_data, list) and input_data and isinstance(input_data[0], str):
            # Graphiti sometimes passes list[str] to create(); embed concatenation
            return self._vec('\n'.join(input_data))  # type: ignore[arg-type]
        return self._vec(repr(input_data))

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in input_data_list]
