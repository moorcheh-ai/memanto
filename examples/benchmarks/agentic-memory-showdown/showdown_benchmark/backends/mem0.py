"""Real Mem0 backend via mem0ai SDK.

Falls back to AppendLogBackend when MEM0_API_KEY is absent.
"""
from __future__ import annotations

import os
from .base import IngestResult, MemoryBackend, RetrieveResult


class Mem0Backend(MemoryBackend):
    """Real Mem0 API backend using mem0ai.

    Environment variable: MEM0_API_KEY
    Falls back to AppendLogBackend (same append-log architecture Mem0 uses
    under the hood) when key is absent.
    """

    name = "Mem0 (mem0ai)"

    def __init__(self) -> None:
        self._client = None
        self._fallback = None
        self._is_live = False

        api_key = os.getenv("MEM0_API_KEY", "")
        if not api_key:
            self._init_fallback()
            return

        try:
            from mem0 import MemoryClient  # type: ignore[import]
            self._client = MemoryClient(api_key=api_key)
            self._is_live = True
        except ImportError:
            self._init_fallback()
        except Exception:
            self._init_fallback()

    def _init_fallback(self) -> None:
        from .offline import AppendLogBackend
        self._fallback = AppendLogBackend()

    @property
    def is_live(self) -> bool:
        return self._is_live

    def reset(self) -> None:
        if self._fallback is not None:
            self._fallback.reset()
            return
        # Mem0 doesn't have a bulk-delete; best effort per user is done in runner

    def ingest(self, user_id: str, content: str) -> IngestResult:
        if self._fallback is not None:
            return self._fallback.ingest(user_id, content)
        with self._timer() as t:
            try:
                self._client.add(
                    [{"role": "user", "content": content}],
                    user_id=f"benchmark_{user_id}",
                )
                written = len(content.split())
            except Exception:
                written = 0
        return IngestResult(tokens_written=written, latency_ms=t.ms)

    def retrieve(self, user_id: str, query: str) -> RetrieveResult:
        if self._fallback is not None:
            return self._fallback.retrieve(user_id, query)
        with self._timer() as t:
            try:
                results = self._client.search(
                    query, user_id=f"benchmark_{user_id}", limit=5
                )
                parts = [r.get("memory", "") for r in (results or [])]
                ctx = "\n".join(p for p in parts if p)
                tokens = len(ctx.split())
            except Exception as exc:
                ctx = f"[retrieval error: {exc}]"
                tokens = 0
        return RetrieveResult(context=ctx, tokens_retrieved=tokens, latency_ms=t.ms)
