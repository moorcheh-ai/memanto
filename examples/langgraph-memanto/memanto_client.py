"""
Async HTTP client for the Memanto v2 REST API.

Provides typed, context-managed access to all Memanto agent and memory
operations.  Designed for use inside LangGraph nodes where async I/O
is the natural execution model.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

# ---------------------------------------------------------------------------
# Response dataclasses
# ---------------------------------------------------------------------------

@dataclass
class AgentInfo:
    agent_id: str
    name: str
    pattern: str
    status: str
    raw: dict = field(default_factory=dict, repr=False)

@dataclass
class SessionInfo:
    session_token: str
    agent_id: str
    raw: dict = field(default_factory=dict, repr=False)

@dataclass
class MemoryResult:
    content: str
    memory_type: str
    confidence: float
    similarity: float = 0.0
    title: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict, repr=False)

@dataclass
class RecallResponse:
    memories: list[MemoryResult]
    query: str
    raw: dict = field(default_factory=dict, repr=False)

@dataclass
class AnswerResponse:
    answer: str
    sources: list[dict]
    raw: dict = field(default_factory=dict, repr=False)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class MemantoClientError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code

# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class MemantoClient:
    """Async HTTP client for the Memanto v2 API.

    Usage::

        async with MemantoClient() as client:
            await client.ensure_agent("my-agent")
            await client.activate("my-agent")
            await client.remember("my-agent", "The sky is blue.", memory_type="fact")
            results = await client.recall("my-agent", "What color is the sky?")
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._api = f"{self.base_url}/api/v2"
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._session_token: Optional[str] = None

    # -- context manager ----------------------------------------------------

    async def __aenter__(self) -> "MemantoClient":
        self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # -- helpers ------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self._session_token:
            h["X-Session-Token"] = self._session_token
        return h

    async def _request(
        self, method: str, path: str, **kwargs: Any
    ) -> dict:
        if self._client is None:
            raise MemantoClientError("Client not initialized. Use 'async with' context manager.")
        url = f"{self._api}{path}"
        resp = await self._client.request(method, url, headers=self._headers(), **kwargs)
        if resp.status_code >= 400:
            raise MemantoClientError(
                f"{method} {path} returned {resp.status_code}: {resp.text}",
                status_code=resp.status_code,
            )
        if resp.status_code == 204:
            return {}
        return resp.json()

    # -- agent lifecycle ----------------------------------------------------

    async def create_agent(
        self, name: str, pattern: str = "conversational"
    ) -> AgentInfo:
        data = await self._request("POST", "/agents", json={"name": name, "pattern": pattern})
        return AgentInfo(
            agent_id=data.get("agent_id", data.get("id", "")),
            name=data.get("name", name),
            pattern=data.get("pattern", pattern),
            status=data.get("status", "created"),
            raw=data,
        )

    async def list_agents(self) -> list[AgentInfo]:
        data = await self._request("GET", "/agents")
        agents_list = data if isinstance(data, list) else data.get("agents", [])
        return [
            AgentInfo(
                agent_id=a.get("agent_id", a.get("id", "")),
                name=a.get("name", ""),
                pattern=a.get("pattern", ""),
                status=a.get("status", ""),
                raw=a,
            )
            for a in agents_list
        ]

    async def ensure_agent(
        self, name: str, pattern: str = "conversational"
    ) -> AgentInfo:
        """Create agent if it doesn't exist, otherwise return existing."""
        agents = await self.list_agents()
        for a in agents:
            if a.name == name:
                return a
        return await self.create_agent(name, pattern)

    async def delete_agent(self, agent_id: str) -> None:
        await self._request("DELETE", f"/agents/{agent_id}")

    # -- session management -------------------------------------------------

    async def activate(self, agent_id: str) -> SessionInfo:
        data = await self._request("POST", f"/agents/{agent_id}/activate")
        self._session_token = data.get("session_token", data.get("token", ""))
        return SessionInfo(
            session_token=self._session_token,
            agent_id=agent_id,
            raw=data,
        )

    async def deactivate(self, agent_id: str) -> None:
        await self._request("POST", f"/agents/{agent_id}/deactivate")
        self._session_token = None

    # -- memory operations --------------------------------------------------

    async def remember(
        self,
        agent_id: str,
        content: str,
        *,
        memory_type: str = "fact",
        title: Optional[str] = None,
        confidence: float = 0.8,
        tags: Optional[list[str]] = None,
        source: str = "agent",
        provenance: str = "explicit_statement",
    ) -> dict:
        payload: dict[str, Any] = {
            "content": content,
            "type": memory_type,
            "confidence": confidence,
            "source": source,
            "provenance": provenance,
        }
        if title:
            payload["title"] = title
        if tags:
            payload["tags"] = tags
        return await self._request(
            "POST", f"/agents/{agent_id}/remember", json=payload
        )

    async def batch_remember(
        self,
        agent_id: str,
        memories: list[dict[str, Any]],
    ) -> dict:
        return await self._request(
            "POST", f"/agents/{agent_id}/batch-remember", json={"memories": memories}
        )

    async def recall(
        self,
        agent_id: str,
        query: str,
        *,
        limit: int = 10,
        min_similarity: float = 0.3,
        memory_types: Optional[list[str]] = None,
    ) -> RecallResponse:
        payload: dict[str, Any] = {
            "query": query,
            "limit": limit,
            "min_similarity": min_similarity,
        }
        if memory_types:
            payload["type"] = memory_types
        data = await self._request(
            "POST", f"/agents/{agent_id}/recall", json=payload
        )
        memories_raw = data.get("memories", data.get("results", []))
        memories = [
            MemoryResult(
                content=m.get("content", ""),
                memory_type=m.get("type", m.get("memory_type", "fact")),
                confidence=m.get("confidence", 0.0),
                similarity=m.get("similarity", m.get("score", 0.0)),
                title=m.get("title"),
                tags=m.get("tags", []),
                raw=m,
            )
            for m in memories_raw
        ]
        return RecallResponse(memories=memories, query=query, raw=data)

    async def recall_recent(
        self,
        agent_id: str,
        *,
        limit: int = 10,
    ) -> RecallResponse:
        data = await self._request(
            "POST", f"/agents/{agent_id}/recall/recent", json={"limit": limit}
        )
        memories_raw = data.get("memories", data.get("results", []))
        memories = [
            MemoryResult(
                content=m.get("content", ""),
                memory_type=m.get("type", m.get("memory_type", "fact")),
                confidence=m.get("confidence", 0.0),
                similarity=0.0,
                title=m.get("title"),
                tags=m.get("tags", []),
                raw=m,
            )
            for m in memories_raw
        ]
        return RecallResponse(memories=memories, query="(recent)", raw=data)

    async def answer(
        self,
        agent_id: str,
        question: str,
    ) -> AnswerResponse:
        data = await self._request(
            "POST", f"/agents/{agent_id}/answer", json={"question": question}
        )
        return AnswerResponse(
            answer=data.get("answer", ""),
            sources=data.get("sources", []),
            raw=data,
        )
