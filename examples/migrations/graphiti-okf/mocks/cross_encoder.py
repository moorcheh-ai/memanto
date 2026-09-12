"""Deterministic cross-encoder / reranker — no API spend."""

from __future__ import annotations

import hashlib


class MockCrossEncoder:
    """Drop-in for graphiti_core.cross_encoder.client.CrossEncoderClient."""

    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        scored: list[tuple[str, float]] = []
        q = query.lower()
        for p in passages:
            overlap = len(set(q.split()) & set(p.lower().split()))
            # Stable tie-break from hash
            h = int(hashlib.md5(f'{query}|{p}'.encode()).hexdigest()[:8], 16)
            score = float(overlap) + (h % 1000) / 1_000_000.0
            scored.append((p, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored
