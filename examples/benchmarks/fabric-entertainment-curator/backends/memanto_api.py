"""Real Memanto REST API backend.

Used when ``MOORCHEH_API_KEY`` is set in the environment.
Requires the Memanto server to be running locally::

    pip install memanto
    memanto serve  # starts on http://127.0.0.1:8001

Get a free Moorcheh API key at https://moorcheh.ai/
"""

from __future__ import annotations

import os

import tiktoken

from backends.base import MemoryBackend

_ENC = tiktoken.encoding_for_model("gpt-4o-mini")
_DEFAULT_BASE_URL = "http://127.0.0.1:8001"


class MemantoAPIBackend(MemoryBackend):
    """Calls the Memanto REST API for remember/recall operations.

    Endpoints used:
        POST /api/v2/agents/{agent_id}/remember
        POST /api/v2/agents/{agent_id}/recall

    Authentication:
        Server-side MOORCHEH_API_KEY must be configured via ``memanto`` CLI.
        This client uses the session token returned by the activate endpoint.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = _DEFAULT_BASE_URL,
        agent_id: str = "benchmark-entertainment-curator",
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._agent_id = agent_id
        self._session_token: str | None = None
        try:
            import httpx  # noqa: PLC0415
            self._client = httpx.Client(timeout=10.0)
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "httpx is required for MemantoAPIBackend. Install: pip install httpx"
            ) from exc

    # ------------------------------------------------------------------
    # Session management helpers
    # ------------------------------------------------------------------

    def _ensure_agent(self) -> None:
        """Create the benchmark agent namespace if it does not exist."""
        url = f"{self._base_url}/api/v2/agents"
        self._client.post(url, json={"agent_id": self._agent_id})

    def _activate(self) -> str:
        """Activate a session and return the JWT session token."""
        url = f"{self._base_url}/api/v2/agents/{self._agent_id}/activate"
        resp = self._client.post(url)
        resp.raise_for_status()
        return resp.json()["session_token"]

    def _headers(self) -> dict[str, str]:
        if self._session_token is None:
            self._session_token = self._activate()
        return {"X-Session-Token": self._session_token}

    # ------------------------------------------------------------------
    # MemoryBackend interface
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Deactivate current session and start fresh."""
        if self._session_token:
            try:
                url = f"{self._base_url}/api/v2/agents/{self._agent_id}/deactivate"
                self._client.post(url, headers=self._headers())
            except Exception:  # noqa: BLE001
                pass
        self._session_token = None
        self._ensure_agent()
        self._session_token = self._activate()

    def remember(self, user_id: str, text: str, memory_type: str = "preference") -> None:  # noqa: ARG002
        url = f"{self._base_url}/api/v2/agents/{self._agent_id}/remember"
        self._client.post(
            url,
            headers=self._headers(),
            json={"content": text, "type": memory_type},
        )

    def recall(
        self,
        user_id: str,  # noqa: ARG002
        query: str,
        limit: int = 10,
    ) -> tuple[list[str], int]:
        url = f"{self._base_url}/api/v2/agents/{self._agent_id}/recall"
        resp = self._client.post(
            url,
            headers=self._headers(),
            json={"query": query, "limit": limit},
        )
        resp.raise_for_status()
        data = resp.json()
        # Memanto returns {"memories": [...], "count": N}; each item has "content".
        memories = [
            item.get("content", item.get("text", str(item)))
            for item in data.get("memories", data if isinstance(data, list) else [])
        ]
        token_count = sum(len(_ENC.encode(m)) for m in memories)
        return memories, token_count
