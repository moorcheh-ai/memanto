"""
Memanto Client — wraps the Memanto REST API for use by LangGraph agents.

Memanto is an active memory agent: it remembers, recalls, and answers
so your LangGraph agents can maintain long-term memory across sessions.

This client talks to the Memanto REST API (served by `memanto serve`)
or directly to the Moorcheh API via the moorcheh_sdk. The default
mode is REST API (local server) which is the most portable option.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx


# ── Memory types (13 built-in categories) ──────────────────────────
MEMORY_TYPES = {
    "instruction",
    "fact",
    "decision",
    "goal",
    "commitment",
    "preference",
    "relationship",
    "context",
    "event",
    "learning",
    "observation",
    "artifact",
    "error",
}


@dataclass
class MemantoConfig:
    """Configuration for connecting to Memanto."""

    api_key: str = field(default_factory=lambda: os.getenv("MOORCHEH_API_KEY", ""))
    base_url: str = "http://127.0.0.1:8000"
    agent_id: str = "langgraph-memanto-agent"
    use_direct_api: bool = False  # True = hit Moorcheh API directly via SDK


class MemantoClient:
    """Lightweight HTTP client for the Memanto REST API.

    Requires `memanto serve` to be running locally (or direct API mode).
    """

    def __init__(self, config: MemantoConfig | None = None):
        self.config = config or MemantoConfig()
        self._http = httpx.Client(timeout=30.0)
        self._session_token: str | None = None

    # ── Agent lifecycle ────────────────────────────────────────────

    def ensure_agent(self) -> str:
        """Create or verify the agent namespace exists. Returns the agent ID."""
        resp = self._http.get(
            f"{self.config.base_url}/api/v2/agents",
            headers=self._headers(),
        )
        if resp.status_code == 200:
            agents = resp.json()
            for agent in agents:
                if agent.get("name") == self.config.agent_id:
                    return self.config.agent_id

        # Create agent
        resp = self._http.post(
            f"{self.config.base_url}/api/v2/agents",
            headers=self._headers(),
            json={"name": self.config.agent_id},
        )
        resp.raise_for_status()
        return self.config.agent_id

    def activate_session(self) -> str:
        """Start a session and return the session token."""
        self.ensure_agent()
        resp = self._http.post(
            f"{self.config.base_url}/api/v2/agents/{self.config.agent_id}/activate",
            headers=self._headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        self._session_token = data.get("session_token", "")
        return self._session_token

    def deactivate_session(self) -> None:
        """End the current session."""
        if not self._session_token:
            return
        self._http.post(
            f"{self.config.base_url}/api/v2/agents/{self.config.agent_id}/deactivate",
            headers=self._headers(),
        )
        self._session_token = None

    # ── Memory operations ──────────────────────────────────────────

    def remember(
        self,
        content: str,
        memory_type: str = "fact",
        confidence: float = 0.9,
    ) -> dict[str, Any]:
        """Store a new memory.

        Args:
            content: The memory content (e.g., "User prefers dark mode").
            memory_type: One of the 13 built-in memory types.
            confidence: Confidence score 0.0–1.0.

        Returns:
            The API response containing the stored memory metadata.
        """
        if memory_type not in MEMORY_TYPES:
            memory_type = "fact"

        payload = {
            "content": content,
            "type": memory_type,
            "confidence": confidence,
        }
        resp = self._http.post(
            f"{self.config.base_url}/api/v2/agents/{self.config.agent_id}/remember",
            headers=self._session_headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    def recall(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Search memory for context relevant to *query*.

        Args:
            query: Natural language query.
            top_k: Maximum number of results.

        Returns:
            List of matching memories with content, type, confidence, and timestamp.
        """
        payload = {"query": query, "top_k": top_k}
        resp = self._http.post(
            f"{self.config.base_url}/api/v2/agents/{self.config.agent_id}/recall",
            headers=self._session_headers(),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", data if isinstance(data, list) else [])

    def answer(self, question: str) -> str:
        """Generate a grounded answer based on stored memories (built-in RAG).

        Args:
            question: The question to answer using memory context.

        Returns:
            The answer text generated from relevant memories.
        """
        payload = {"query": question}
        resp = self._http.post(
            f"{self.config.base_url}/api/v2/agents/{self.config.agent_id}/answer",
            headers=self._session_headers(),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("answer", data.get("response", ""))

    def batch_remember(self, memories: list[dict[str, Any]]) -> dict[str, Any]:
        """Store multiple memories at once.

        Args:
            memories: List of dicts with keys 'content', 'type' (optional), 'confidence' (optional).
        """
        for m in memories:
            if "type" not in m:
                m["type"] = "fact"
            if "confidence" not in m:
                m["confidence"] = 0.9
        resp = self._http.post(
            f"{self.config.base_url}/api/v2/agents/{self.config.agent_id}/batch-remember",
            headers=self._session_headers(),
            json={"memories": memories},
        )
        resp.raise_for_status()
        return resp.json()

    # ── Helpers ────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self.config.api_key,
            "Content-Type": "application/json",
        }

    def _session_headers(self) -> dict[str, str]:
        h = self._headers()
        if self._session_token:
            h["X-Session-Token"] = self._session_token
        return h

    def close(self) -> None:
        self._http.close()
