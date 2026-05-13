"""Memanto REST API client for LangGraph integration.

A lightweight HTTP client that communicates with the Memanto server
to store and retrieve long-term memories.

API Reference:
  POST /api/v2/agents/{agent_id}/remember  — Store a memory
  POST /api/v2/agents/{agent_id}/recall    — Search memories
  POST /api/v2/agents/{agent_id}/answer    — Get LLM-grounded response
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()


class MemantoClient:
    """Client for the Memanto REST API."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        agent_id: str | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = (base_url or os.getenv("MEMANTO_URL", "http://localhost:8000")).rstrip("/")
        self.api_key = api_key or os.getenv("MEMANTO_API_KEY", "")
        self.agent_id = agent_id or os.getenv("AGENT_ID", "langgraph-agent")
        self.timeout = timeout

    @property
    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def ensure_agent(self) -> dict[str, Any]:
        """Create the agent if it doesn't exist.

        POST /api/v2/agents
        """
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    self._url("/api/v2/agents"),
                    headers=self._headers,
                    json={"agent_id": self.agent_id},
                )
                if resp.status_code == 201:
                    return resp.json()
                if resp.status_code == 409:
                    return {"agent_id": self.agent_id, "status": "already_exists"}
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                return {"agent_id": self.agent_id, "status": "already_exists"}
            raise
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            return {"error": f"Could not connect to Memanto server: {e}"}

    def remember(
        self,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
        confidence: float = 0.9,
    ) -> dict[str, Any]:
        """Store a memory in Memanto.

        POST /api/v2/agents/{agent_id}/remember

        Args:
            memory_type: One of fact, preference, goal, decision, event,
                        observation, learning, instruction, etc.
            title: Short title for the memory (max 100 chars).
            content: The memory content.
            tags: Optional tags for categorization.
            confidence: Confidence score (0.0 to 1.0).
        """
        payload = {
            "type": memory_type,
            "title": title[:100],
            "content": content,
            "confidence": confidence,
        }
        if tags:
            payload["tags"] = tags

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    self._url(f"/api/v2/agents/{self.agent_id}/remember"),
                    headers=self._headers,
                    json=payload,
                )
                resp.raise_for_status()
                return resp.json()
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            return {"error": f"Could not connect: {e}"}

    def recall(
        self,
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search memories by semantic relevance.

        POST /api/v2/agents/{agent_id}/recall

        Args:
            query: Natural language query to search for.
            limit: Maximum number of results (default: 5).
            memory_types: Optional filter by memory types.

        Returns:
            List of matching memory records.
        """
        payload: dict[str, Any] = {"query": query, "limit": limit}
        if memory_types:
            payload["memory_types"] = memory_types

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    self._url(f"/api/v2/agents/{self.agent_id}/recall"),
                    headers=self._headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("memories", data.get("results", []))
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            return []

    def answer(
        self,
        query: str,
        limit: int = 10,
    ) -> str:
        """Ask a question and get an LLM-grounded answer from stored memories.

        POST /api/v2/agents/{agent_id}/answer

        Args:
            query: The question to answer.
            limit: Number of context memories to retrieve.

        Returns:
            The LLM-generated answer grounded in stored memories.
        """
        payload: dict[str, Any] = {"query": query, "limit": limit}

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    self._url(f"/api/v2/agents/{self.agent_id}/answer"),
                    headers=self._headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("answer", data.get("response", str(data)))
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            return f"[Memanto offline: {e}]"

    def activate_session(self) -> dict[str, Any]:
        """Activate a session for the agent.

        POST /api/v2/agents/{agent_id}/activate
        """
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    self._url(f"/api/v2/agents/{self.agent_id}/activate"),
                    headers=self._headers,
                )
                resp.raise_for_status()
                return resp.json()
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            return {"error": f"Could not connect: {e}"}

    def health_check(self) -> bool:
        """Check if the Memanto server is reachable.

        GET /health
        """
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(self._url("/health"))
                return resp.status_code == 200
        except Exception:
            return False
