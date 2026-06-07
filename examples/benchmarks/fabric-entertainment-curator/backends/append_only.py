"""Append-Only Baseline — naive memory store.

This is the simplest possible memory implementation: every message is appended
to a list.  ``recall()`` returns the entire history — no conflict resolution,
no deduplication, no recency filtering.

This baseline demonstrates the worst-case context-window bloat: as sessions
grow, the injected context grows proportionally and includes stale facts
that were superseded by later preferences.
"""

from __future__ import annotations

import tiktoken

from backends.base import MemoryBackend

_ENC = tiktoken.encoding_for_model("gpt-4o-mini")


class AppendOnlyBackend(MemoryBackend):
    """Naive append-only memory baseline.

    Stores all memories chronologically.  Returns the complete history on
    every ``recall()`` call — intentionally demonstrating the token-overhead
    and stale-contamination problems that motivated Memanto's design.
    """

    def __init__(self) -> None:
        self._store: list[str] = []

    # ------------------------------------------------------------------
    # MemoryBackend interface
    # ------------------------------------------------------------------

    def reset(self) -> None:
        self._store.clear()

    def remember(self, user_id: str, text: str, memory_type: str = "preference") -> None:  # noqa: ARG002
        self._store.append(f"[{memory_type}] {text}")

    def recall(
        self,
        user_id: str,  # noqa: ARG002
        query: str,  # noqa: ARG002
        limit: int = 10,  # noqa: ARG002
    ) -> tuple[list[str], int]:
        # Return the complete history — no filtering.
        token_count = sum(len(_ENC.encode(m)) for m in self._store)
        return list(self._store), token_count
