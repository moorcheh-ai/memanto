"""Mem0 passive-graph baseline.

Uses the mem0ai Python package in local mode when OPENAI_API_KEY is set.
Falls back to a passive accumulation store (returns ALL stored memories)
when the API key is absent — this faithfully simulates the passive-graph
problem: facts accumulate without conflict resolution.

Passive accumulation is the documented failure mode that Memanto was designed
to solve (arXiv:2604.22085, Section 3.2).
"""

from __future__ import annotations

import os

import tiktoken

from backends.base import MemoryBackend

_ENC = tiktoken.encoding_for_model("gpt-4o-mini")


class Mem0Backend(MemoryBackend):
    """Mem0 local-mode backend with passive-accumulation fallback.

    When ``OPENAI_API_KEY`` is set, uses mem0ai with OpenAI embeddings for
    semantic retrieval.  Otherwise uses a simple list that accumulates ALL
    stored memories — simulating the passive-graph token-accumulation
    problem that motivates Memanto's design.
    """

    def __init__(self) -> None:
        self._mem = None
        self._passive: list[tuple[str, str]] = []  # (memory_type, text)
        self._has_api_key = bool(os.environ.get("OPENAI_API_KEY"))

        if self._has_api_key:
            try:
                from mem0 import Memory  # noqa: PLC0415
                self._mem = Memory()
            except ImportError:
                self._has_api_key = False

    # ------------------------------------------------------------------
    # MemoryBackend interface
    # ------------------------------------------------------------------

    def reset(self) -> None:
        if self._has_api_key and self._mem is not None:
            try:
                from mem0 import Memory  # noqa: PLC0415
                self._mem = Memory()
            except Exception:  # noqa: BLE001
                pass
        self._passive.clear()

    def remember(self, user_id: str, text: str, memory_type: str = "preference") -> None:
        if self._has_api_key and self._mem is not None:
            self._mem.add(text, user_id=user_id, metadata={"type": memory_type})
        # Always add to passive store (for token count accuracy).
        self._passive.append((memory_type, text))

    def recall(
        self,
        user_id: str,
        query: str,
        limit: int = 10,
    ) -> tuple[list[str], int]:
        if self._has_api_key and self._mem is not None:
            results = self._mem.search(query, user_id=user_id, limit=limit)
            memories = [r["memory"] for r in results.get("results", [])]
            token_count = sum(len(_ENC.encode(m)) for m in memories)
            return memories, token_count

        # Passive fallback: return ALL stored memories (no conflict resolution).
        # This is intentional — it demonstrates the context-bloat problem.
        all_memories = [f"[{mt}] {txt}" for mt, txt in self._passive]
        token_count = sum(len(_ENC.encode(m)) for m in all_memories)
        return all_memories, token_count
