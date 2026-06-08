"""Real Memanto backend via moorcheh_sdk.

Falls back to offline ActiveMemoryBackend when MOORCHEH_API_KEY is absent
or when the SDK is not installed — so the benchmark always runs.
"""
from __future__ import annotations

import os

from .base import IngestResult, MemoryBackend, RetrieveResult


class MemantoBackend(MemoryBackend):
    """Real Memanto API backend using moorcheh_sdk.

    Environment variable: MOORCHEH_API_KEY
    Falls back to offline ActiveMemoryBackend if key is absent.
    """

    name = "Memanto (moorcheh_sdk)"

    def __init__(self) -> None:
        self._client = None
        self._fallback = None
        self._namespace: str | None = None
        self._is_live = False

        api_key = os.getenv("MOORCHEH_API_KEY", "")
        if not api_key:
            self._init_fallback("[no MOORCHEH_API_KEY — offline fallback]")
            return

        try:
            from moorcheh_sdk import MoorchehClient  # type: ignore[import]
            self._client = MoorchehClient(api_key=api_key)
            self._is_live = True
        except ImportError:
            self._init_fallback("[moorcheh_sdk not installed — offline fallback]")
        except Exception as exc:
            self._init_fallback(f"[SDK init error: {exc} — offline fallback]")

    def _init_fallback(self, reason: str) -> None:
        from .offline import ActiveMemoryBackend
        self._fallback = ActiveMemoryBackend()
        self._fallback_reason = reason

    @property
    def is_live(self) -> bool:
        return self._is_live

    def _ensure_namespace(self) -> None:
        if self._namespace is None and self._client is not None:
            ns_name = "benchmark-showdown"
            try:
                # Try to get existing namespace
                namespaces = self._client.namespaces.list()
                existing = [n for n in namespaces if n.get("name") == ns_name]
                if existing:
                    self._namespace = existing[0]["id"]
                else:
                    ns = self._client.namespaces.create(name=ns_name)
                    self._namespace = ns["id"]
            except Exception:
                # Older SDK may use different interface
                try:
                    ns = self._client.namespaces.create(name=ns_name)
                    self._namespace = ns.get("id") or ns.get("namespace_id")
                except Exception:
                    pass

    def reset(self) -> None:
        if self._fallback is not None:
            self._fallback.reset()
            return
        # For real API: delete namespace and recreate
        try:
            if self._namespace and self._client:
                self._client.namespaces.delete(self._namespace)
            self._namespace = None
        except Exception:
            pass

    def ingest(self, user_id: str, content: str) -> IngestResult:
        if self._fallback is not None:
            return self._fallback.ingest(user_id, content)

        self._ensure_namespace()
        with self._timer() as t:
            try:
                self._client.documents.create(
                    namespace_id=self._namespace,
                    content=content,
                    metadata={"user_id": user_id, "source": "benchmark"},
                )
                written = len(content.split())
            except Exception as exc:
                # Degrade gracefully
                written = 0
        return IngestResult(tokens_written=written, latency_ms=t.ms)

    def retrieve(self, user_id: str, query: str) -> RetrieveResult:
        if self._fallback is not None:
            return self._fallback.retrieve(user_id, query)

        self._ensure_namespace()
        with self._timer() as t:
            try:
                result = self._client.answer.ask(
                    namespace_id=self._namespace,
                    query=query,
                    metadata_filter={"user_id": user_id},
                )
                ctx = result.get("answer") or result.get("text") or str(result)
                tokens = len(ctx.split())
            except Exception as exc:
                ctx = f"[retrieval error: {exc}]"
                tokens = 0
        return RetrieveResult(context=ctx, tokens_retrieved=tokens, latency_ms=t.ms)
