"""
Memanto Memory Adapter for CrewAI
===================================

This module provides a drop-in memory adapter that connects CrewAI agents
to Memanto's agentic memory layer, enabling:

- Persistent memory across sessions
- Semantic search over past interactions
- User preference tracking
- Long-term task outcome storage
- Cross-agent memory sharing
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class MemantoMemoryError(Exception):
    """Raised when Memanto API operations fail."""


class MemantoClient:
    """
    Low-level HTTP client for the Memanto API.

    Handles authentication, retries, and error normalisation so that
    higher-level classes can stay focused on business logic.
    """

    DEFAULT_BASE_URL = "https://api.memanto.ai/v2"
    DEFAULT_TIMEOUT = 30  # seconds
    DEFAULT_RETRIES = 3

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
    ) -> None:
        self.api_key = api_key or os.environ.get("MEMANTO_API_KEY", "")
        self.base_url = (base_url or os.environ.get("MEMANTO_BASE_URL", self.DEFAULT_BASE_URL)).rstrip("/")
        self.timeout = timeout
        self.retries = retries

        if not self.api_key:
            raise MemantoMemoryError(
                "No Memanto API key found. "
                "Set the MEMANTO_API_KEY environment variable or pass api_key= explicitly."
            )

        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "crewai-memanto-integration/1.0",
            }
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Dict:
        url = f"{self.base_url}{path}"
        last_exc: Optional[Exception] = None

        for attempt in range(1, self.retries + 1):
            try:
                resp = self._session.request(
                    method,
                    url,
                    json=payload,
                    params=params,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                return resp.json() if resp.content else {}
            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                # Don't retry client errors (4xx)
                if 400 <= status < 500:
                    raise MemantoMemoryError(
                        f"Memanto API client error {status}: {exc.response.text}"
                    ) from exc
                last_exc = exc
            except requests.exceptions.RequestException as exc:
                last_exc = exc

            if attempt < self.retries:
                backoff = 2 ** (attempt - 1)
                logger.warning("Memanto request failed (attempt %d/%d), retrying in %ds…", attempt, self.retries, backoff)
                time.sleep(backoff)

        raise MemantoMemoryError(f"Memanto API request failed after {self.retries} attempts: {last_exc}") from last_exc

    # ------------------------------------------------------------------
    # Public API wrappers
    # ------------------------------------------------------------------

    def store_memory(
        self,
        session_id: str,
        content: str,
        metadata: Optional[Dict] = None,
        memory_type: str = "episodic",
    ) -> Dict:
        """Store a memory entry in Memanto."""
        return self._request(
            "POST",
            "/memories",
            payload={
                "session_id": session_id,
                "content": content,
                "metadata": metadata or {},
                "memory_type": memory_type,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
        )

    def search_memories(
        self,
        session_id: str,
        query: str,
        top_k: int = 5,
        memory_type: Optional[str] = None,
        min_score: float = 0.0,
    ) -> List[Dict]:
        """Semantic search over stored memories."""
        params: Dict[str, Any] = {
            "session_id": session_id,
            "query": query,
            "top_k": top_k,
            "min_score": min_score,
        }
        if memory_type:
            params["memory_type"] = memory_type

        result = self._request("GET", "/memories/search", params=params)
        return result.get("memories", result) if isinstance(result, dict) else result

    def get_session_memories(
        self,
        session_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict]:
        """Retrieve all memories for a session, paginated."""
        result = self._request(
            "GET",
            f"/sessions/{session_id}/memories",
            params={"limit": limit, "offset": offset},
        )
        return result.get("memories", result) if isinstance(result, dict) else result

    def create_session(self, agent_id: str, metadata: Optional[Dict] = None) -> Dict:
        """Create a new Memanto session."""
        return self._request(
            "POST",
            "/sessions",
            payload={
                "agent_id": agent_id,
                "metadata": metadata or {},
                "created_at": datetime.utcnow().isoformat() + "Z",
            },
        )

    def get_or_create_session(self, agent_id: str, session_tag: str) -> str:
        """
        Return an existing session ID for (agent_id, session_tag) or create one.

        The session_tag is stored in metadata so we can look it up on the next run.
        """
        # Try to find an existing session by listing sessions and matching tag
        try:
            result = self._request(
                "GET",
                "/sessions",
                params={"agent_id": agent_id, "tag": session_tag},
            )
            sessions = result.get("sessions", result) if isinstance(result, dict) else result
            if sessions:
                return sessions[0]["id"]
        except MemantoMemoryError:
            pass  # Fall through to creation

        new_session = self.create_session(
            agent_id=agent_id,
            metadata={"tag": session_tag, "agent_id": agent_id},
        )
        return new_session["id"]

    def delete_memory(self, memory_id: str) -> None:
        """Delete a specific memory entry."""
        self._request("DELETE", f"/memories/{memory_id}")

    def update_memory(self, memory_id: str, content: str, metadata: Optional[Dict] = None) -> Dict:
        """Update an existing memory entry."""
        return self._request(
            "PUT",
            f"/memories/{memory_id}",
            payload={"content": content, "metadata": metadata or {}},
        )


class MemantoAgentMemory:
    """
    High-level memory interface designed for individual CrewAI agents.

    Each agent gets its own ``MemantoAgentMemory`` instance which is bound
    to a specific ``agent_id`` and optionally a persistent ``session_tag``
    (e.g. a user ID or project name) so that memories survive process restarts.

    Usage
    -----
    ::

        memory = MemantoAgentMemory(
            api_key="mk-...",
            agent_id="research_agent",
            session_tag="project-alpha",
        )

        # Store a finding
        memory.remember("The market cap of Acme Corp is $4.2B as of Q2 2025.")

        # Later, recall relevant context
        context = memory.recall("Acme Corp valuation")
        for item in context:
            print(item["content"])
    """

    def __init__(
        self,
        agent_id: str,
        session_tag: str = "default",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        max_recall: int = 5,
        min_relevance_score: float = 0.5,
    ) -> None:
        self.agent_id = agent_id
        self.session_tag = session_tag
        self.max_recall = max_recall
        self.min_relevance_score = min_relevance_score

        self._client = MemantoClient(api_key=api_key, base_url=base_url)
        self._session_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    @property
    def session_id(self) -> str:
        if self._session_id is None:
            self._session_id = self._client.get_or_create_session(
                agent_id=self.agent_id,
                session_tag=self.session_tag,
            )
        return self._session_id

    # ------------------------------------------------------------------
    # Core memory operations
    # ------------------------------------------------------------------

    def remember(
        self,
        content: str,
        memory_type: str = "episodic",
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        Persist a memory and return its ID.

        Parameters
        ----------
        content:
            The text to remember. This will be embedded and indexed.
        memory_type:
            One of ``"episodic"`` (default, event-based), ``"semantic"``
            (facts / knowledge), or ``"procedural"`` (how-to steps).
        metadata:
            Arbitrary key-value pairs attached to the memory for filtering.

        Returns
        -------
        str
            The memory ID assigned by Memanto.
        """
        extra_meta = {
            "agent_id": self.agent_id,
            "session_tag": self.session_tag,
            **(metadata or {}),
        }
        result = self._client.store_memory(
            session_id=self.session_id,
            content=content,
            metadata=extra_meta,
            memory_type=memory_type,
        )
        memory_id = result.get("id", result.get("memory_id", str(uuid.uuid4())))
        logger.debug("Stored memory %s for agent %s", memory_id, self.agent_id)
        return memory_id

    def recall(
        self,
        query: str,
        top_k: Optional[int] = None,
        memory_type: Optional[str] = None,
    ) -> List[Dict]:
        """
        Retrieve memories semantically relevant to *query*.

        Returns a list of memory dicts, each containing at minimum:
        ``id``, ``content``, ``score``, ``memory_type``, ``timestamp``.
        """
        memories = self._client.search_memories(
            session_id=self.session_id,
            query=query,
            top_k=top_k or self.max_recall,
            memory_type=memory_type,
            min_score=self.min_relevance_score,
        )
        logger.debug("Recalled %d memories for query %r (agent=%s)", len(memories), query, self.agent_id)
        return memories

    def recall_as_context(self, query: str, top_k: Optional[int] = None) -> str:
        """
        Recall memories and format them as a single context string suitable
        for injection into an LLM prompt.
        """
        memories = self.recall(query, top_k=top_k)
        if not memories:
            return ""

        lines = ["[Relevant memories from past sessions]"]
        for i, mem in enumerate(memories, 1):
            score = mem.get("score", "?")
            ts = mem.get("timestamp", "unknown time")
            lines.append(f"{i}. [{ts}] (relevance={score}) {mem.get('content', '')}")
        return "\n".join(lines)

    def get_all(self, limit: int = 50) -> List[Dict]:
        """Retrieve all memories for the current session."""
        return self._client.get_session_memories(self.session_id, limit=limit)

    def forget(self, memory_id: str) -> None:
        """Delete a specific memory by ID."""
        self._client.delete_memory(memory_id)
        logger.debug("Deleted memory %s (agent=%s)", memory_id, self.agent_id)

    def remember_preference(self, key: str, value: Any) -> str:
        """
        Convenience method for storing structured user/project preferences.
        Preferences are stored as semantic memories with a ``preference_key``
        metadata tag so they can be retrieved precisely.
        """
        content = f"Preference[{key}]: {json.dumps(value)}"
        return self.remember(
            content=content,
            memory_type="semantic",
            metadata={"preference_key": key, "preference_value": str(value)},
        )

    def recall_preference(self, key: str) -> Optional[Any]:
        """
        Retrieve a previously stored preference by its exact key.
        Returns the parsed value or *None* if not found.
        """
        memories = self.recall(f"Preference[{key}]", memory_type="semantic")
        for mem in memories:
            if mem.get("metadata", {}).get("preference_key") == key:
                raw_value = mem["metadata"].get("preference_value")
                try:
                    return json.loads(raw_value)
                except (json.JSONDecodeError, TypeError):
                    return raw_value
        return None
