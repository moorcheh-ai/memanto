"""
Memanto Memory Adapter for CrewAI
===================================

This module provides a drop-in memory adapter that integrates Memanto's
persistent, searchable agentic memory layer with CrewAI agents.

Key Features:
    - Persistent cross-session memory storage
    - Semantic search over past memories
    - Agent-specific memory namespacing
    - Automatic context injection for relevant memories
    - Memory summarization for long-running workflows

Architecture:
    ┌─────────────────────────────────────────────────────┐
    │                   CrewAI Crew                        │
    │  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │
    │  │  Researcher  │  │   Analyst    │  │  Writer   │ │
    │  │    Agent     │  │    Agent     │  │   Agent   │ │
    │  └──────┬───────┘  └──────┬───────┘  └─────┬─────┘ │
    │         │                 │                 │        │
    │  ┌──────▼─────────────────▼─────────────────▼─────┐ │
    │  │           MeMantoMemoryAdapter                   │ │
    │  │  - save_memory()   - search_memory()             │ │
    │  │  - get_context()   - summarize_session()         │ │
    │  └──────────────────────┬──────────────────────────┘ │
    └─────────────────────────┼───────────────────────────┘
                              │
    ┌─────────────────────────▼───────────────────────────┐
    │                  Memanto API                         │
    │  - Persistent vector storage                         │
    │  - Semantic similarity search                        │
    │  - Session & agent namespacing                       │
    │  - Timeline visualization                            │
    └─────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import os
import json
import logging
import hashlib
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict

import requests

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class MemoryEntry:
    """Represents a single memory entry stored in Memanto."""

    content: str
    agent_name: str
    session_id: str
    task_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    memory_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class MemorySearchResult:
    """Represents a search result from Memanto."""

    memory_id: str
    content: str
    agent_name: str
    session_id: str
    similarity_score: float
    timestamp: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def age_hours(self) -> float:
        """Returns the age of the memory in hours."""
        try:
            ts = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            return (now - ts).total_seconds() / 3600
        except Exception:
            return 0.0

    def to_context_string(self) -> str:
        """Formats the memory for context injection into agent prompts."""
        age_str = f"{self.age_hours:.1f}h ago" if self.age_hours < 48 else f"{self.age_hours/24:.1f}d ago"
        return (
            f"[Memory from {self.agent_name} | {age_str} | "
            f"relevance: {self.similarity_score:.2f}]\n{self.content}"
        )


# ---------------------------------------------------------------------------
# Memanto Client
# ---------------------------------------------------------------------------

class MeMantoClient:
    """
    Low-level HTTP client for the Memanto API.

    Handles authentication, retries, and error normalisation so the
    higher-level adapter stays clean.
    """

    DEFAULT_BASE_URL = "https://api.memanto.ai/v2"
    DEFAULT_TIMEOUT = 30  # seconds
    MAX_RETRIES = 3
    RETRY_BACKOFF = 1.5  # seconds

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.api_key = api_key or os.getenv("MEMANTO_API_KEY", "")
        self.base_url = (base_url or os.getenv("MEMANTO_BASE_URL", self.DEFAULT_BASE_URL)).rstrip("/")
        self.timeout = timeout

        if not self.api_key:
            raise ValueError(
                "Memanto API key is required. Set MEMANTO_API_KEY environment variable "
                "or pass api_key= to MeMantoClient()."
            )

        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Client": "crewai-memanto-integration/1.0",
        })

    def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Make an authenticated HTTP request with retry logic."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        last_exc: Optional[Exception] = None

        for attempt in range(self.MAX_RETRIES):
            try:
                response = self._session.request(
                    method,
                    url,
                    timeout=self.timeout,
                    **kwargs,
                )
                response.raise_for_status()
                return response.json() if response.content else {}
            except requests.exceptions.HTTPError as exc:
                if exc.response is not None and exc.response.status_code < 500:
                    # Client errors (4xx) — don't retry
                    logger.error(
                        "Memanto API client error %s: %s",
                        exc.response.status_code,
                        exc.response.text,
                    )
                    raise
                last_exc = exc
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                last_exc = exc

            wait = self.RETRY_BACKOFF * (2 ** attempt)
            logger.warning(
                "Memanto API request failed (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1,
                self.MAX_RETRIES,
                wait,
                last_exc,
            )
            time.sleep(wait)

        raise ConnectionError(
            f"Memanto API unavailable after {self.MAX_RETRIES} attempts: {last_exc}"
        )

    # --- Memory CRUD ---------------------------------------------------------

    def store_memory(
        self,
        session_id: str,
        content: str,
        agent_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Store a memory entry in Memanto."""
        payload = {
            "session_id": session_id,
            "content": content,
            "agent_name": agent_name,
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return self._request("POST", "/memories", json=payload)

    def search_memories(
        self,
        query: str,
        session_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        top_k: int = 5,
        min_similarity: float = 0.6,
    ) -> List[Dict[str, Any]]:
        """Search memories using semantic similarity."""
        params: Dict[str, Any] = {
            "query": query,
            "top_k": top_k,
            "min_similarity": min_similarity,
        }
        if session_id:
            params["session_id"] = session_id
        if agent_name:
            params["agent_name"] = agent_name

        result = self._request("GET", "/memories/search", params=params)
        return result.get("memories", [])

    def get_session_memories(
        self,
        session_id: str,
        agent_name: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Retrieve all memories for a session."""
        params: Dict[str, Any] = {"limit": limit}
        if agent_name:
            params["agent_name"] = agent_name

        result = self._request("GET", f"/sessions/{session_id}/memories", params=params)
        return result.get("memories", [])

    def delete_session(self, session_id: str) -> None:
        """Delete all memories for a session."""
        self._request("DELETE", f"/sessions/{session_id}")

    def health_check(self) -> bool:
        """Check if the Memanto API is reachable."""
        try:
            self._request("GET", "/health")
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# High-Level Memory Adapter (CrewAI-focused)
# ---------------------------------------------------------------------------

class MeMantoMemoryAdapter:
    """
    High-level memory adapter that integrates Memanto with CrewAI agents.

    This adapter provides:
    - Automatic memory storage after each agent action
    - Context-aware memory retrieval for enriching agent prompts
    - Cross-session memory sharing between agents
    - Memory summarisation for long-running workflows

    Example:
        >>> memory = MeMantoMemoryAdapter(session_id="research_session_001")
        >>> memory.save("Found key insight: AI adoption growing 40% YoY", agent_name="researcher")
        >>> context = memory.get_relevant_context("What are the AI trends?")
        >>> print(context)
    """

    def __init__(
        self,
        session_id: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        max_context_memories: int = 5,
        min_similarity_threshold: float = 0.65,
        enable_cross_session: bool = False,
        fallback_to_local: bool = True,
    ) -> None:
        """
        Initialize the MeMantoMemoryAdapter.

        Args:
            session_id: Unique identifier for this crew session.
            api_key: Memanto API key (or set MEMANTO_API_KEY env var).
            base_url: Memanto API base URL (or set MEMANTO_BASE_URL env var).
            max_context_memories: Maximum number of memories to inject as context.
            min_similarity_threshold: Minimum similarity score for memory retrieval.
            enable_cross_session: Whether to search across all sessions (not just current).
            fallback_to_local: If True, uses in-memory fallback when API is unavailable.
        """
        self.session_id = session_id
        self.max_context_memories = max_context_memories
        self.min_similarity_threshold = min_similarity_threshold
        self.enable_cross_session = enable_cross_session
        self.fallback_to_local = fallback_to_local

        # Local in-memory store used as fallback
        self._local_store: List[MemoryEntry] = []
        self._api_available = False

        try:
            self._client = MeMantoClient(api_key=api_key, base_url=base_url)
            self._api_available = self._client.health_check()
            if self._api_available:
                logger.info("✅ Memanto API connected for session '%s'", session_id)
            else:
                logger.warning(
                    "⚠️  Memanto API health check failed — using local fallback for session '%s'",
                    session_id,
                )
        except ValueError as exc:
            if fallback_to_local:
                logger.warning(
                    "⚠️  %s — using local in-memory fallback (memories won't persist across restarts)",
                    exc,
                )
                self._client = None  # type: ignore[assignment]
            else:
                raise

    # --- Core Memory Operations ----------------------------------------------

    def save(
        self,
        content: str,
        agent_name: str,
        task_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Save a memory entry.

        Args:
            content: The memory content to store.
            agent_name: Name of the agent creating the memory.
            task_name: Optional name of the task associated with this memory.
            metadata: Optional additional metadata.

        Returns:
            The memory ID if successful, None otherwise.
        """
        extra_metadata = {
            **(metadata or {}),
            "task_name": task_name,
            "crew_session": self.session_id,
        }

        entry = MemoryEntry(
            content=content,
            agent_name=agent_name,
            session_id=self.session_id,
            task_name=task_name,
            metadata=extra_metadata,
        )

        if self._api_available and self._client:
            try:
                result = self._client.store_memory(
                    session_id=self.session_id,
                    content=content,
                    agent_name=agent_name,
                    metadata=extra_metadata,
                )
                memory_id = result.get("memory_id") or result.get("id")
                entry.memory_id = memory_id
                logger.debug(
                    "💾 Memory saved [%s/%s]: %.60s…", agent_name, task_name, content
                )
                return memory_id
            except Exception as exc:
                logger.warning("Failed to save memory to Memanto API: %s", exc)
                if not self.fallback_to_local:
                    raise

        # Local fallback
        entry.memory_id = self._generate_local_id(content)
        self._local_store.append(entry)
        logger.debug(
            "💾 Memory saved locally [%s/%s]: %.60s…", agent_name, task_name, content
        )
        return entry.memory_id

    def search(
        self,
        query: str,
        agent_name: Optional[str] = None,
        top_k: Optional[int] = None,
    ) -> List[MemorySearchResult]:
        """
        Search for relevant memories.

        Args:
            query: The search query (semantic search).
            agent_name: Optional filter by agent name.
            top_k: Maximum number of results (defaults to max_context_memories).

        Returns:
            List of MemorySearchResult objects sorted by relevance.
        """
        k = top_k or self.max_context_memories
        session_id = None if self.enable_cross_session else self.session_id

        if self._api_available and self._client:
            try:
                raw_results = self._client.search_memories(
                    query=query,
                    session_id=session_id,
                    agent_name=agent_name,
                    top_k=k,
                    min_similarity=self.min_similarity_threshold,
                )
                return [
                    MemorySearchResult(
                        memory_id=r.get("id", ""),
                        content=r.get("content", ""),
                        agent_name=r.get("agent_name", "unknown"),
                        session_id=r.get("session_id", self.session_id),
                        similarity_score=r.get("similarity", 0.0),
                        timestamp=r.get("timestamp", datetime.now(timezone.utc).isoformat()),
                        metadata=r.get("metadata", {}),
                    )
                    for r in raw_results
                ]
            except Exception as exc:
                logger.warning("Failed to search Memanto API: %s", exc)

        # Local fallback — simple keyword matching
        return self._local_search(query, agent_name=agent_name, top_k=k)

    def get_relevant_context(
        self,
        query: str,
        agent_name: Optional[str] = None,
        include_header: bool = True,
    ) -> str:
        """
        Get relevant memories formatted as context for injection into agent prompts.

        Args:
            query: The query to find relevant memories for.
            agent_name: Optional filter by agent name.
            include_header: Whether to include a context header.

        Returns:
            Formatted context string ready for prompt injection.
        """
        results = self.search(query, agent_name=agent_name)
        if not results:
            return ""

        parts: List[str] = []
        if include_header:
            parts.append(
                "=== RELEVANT MEMORIES FROM PREVIOUS SESSIONS ===\n"
                "(Use this context to inform your response)\n"
            )

        for i, result in enumerate(results, 1):
            parts.append(f"{i}. {result.to_context_string()}")

        parts.append("=== END OF MEMORIES ===\n")
        return "\n".join(parts)

    def get_session_summary(self) -> str:
        """
        Get a summary of all memories in the current session.

        Returns:
            Formatted summary string.
        """
        if self._api_available and self._client:
            try:
                memories = self._client.get_session_memories(
                    session_id=self.session_id, limit=100
                )
            except Exception:
                memories = []
        else:
            memories = [asdict(e) for e in self._local_store]

        if not memories:
            return f"No memories found for session '{self.session_id}'."

        # Group by agent
        by_agent: Dict[str, List[str]] = {}
        for m in memories:
            agent = m.get("agent_name", "unknown")
            by_agent.setdefault(agent, []).append(m.get("content", ""))

        lines = [f"📋 Session Summary: {self.session_id}", f"Total memories: {len(memories)}\n"]
        for agent, contents in by_agent.items():
            lines.append(f"🤖 {agent} ({len(contents)} memories):")
            for c in contents[:3]:  # show first 3 per agent
                lines.append(f"   • {c[:80]}{'…' if len(c) > 80 else ''}")
            if len(contents) > 3:
                lines.append(f"   … and {len(contents) - 3} more")
            lines.append("")

        return "\n".join(lines)

    def clear_session(self) -> None:
        """Clear all memories for the current session."""
        if self._api_available and self._client:
            try:
                self._client.delete_session(self.session_id)
                logger.info("🗑️  Cleared Memanto session '%s'", self.session_id)
            except Exception as exc:
                logger.warning("Failed to clear Memanto session: %s", exc)

        self._local_store = [
            e for e in self._local_store if e.session_id != self.session_id
        ]

    # --- Helper Methods -------------------------------------------------------

    @staticmethod
    def _generate_local_id(content: str) -> str:
        """Generate a deterministic local memory ID."""
        digest = hashlib.sha256(
            f"{content}{time.time()}".encode()
        ).hexdigest()[:12]
        return f"local_{digest}"

    def _local_search(
        self,
        query: str,
        agent_name: Optional[str] = None,
        top_k: int = 5,
    ) -> List[MemorySearchResult]:
        """Simple keyword-based local search fallback."""
        query_words = set(query.lower().split())
        scored: List[Tuple[float, MemoryEntry]] = []

        for entry in self._local_store:
            if agent_name and entry.agent_name != agent_name:
                continue
            content_words = set(entry.content.lower().split())
            if not query_words or not content_words:
                continue
            overlap = len(query_words & content_words)
            score = overlap / max(len(query_words), len(content_words))
            if score >= self.min_similarity_threshold * 0.5:  # lower bar for local
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            MemorySearchResult(
                memory_id=entry.memory_id or "",
                content=entry.content,
                agent_name=entry.agent_name,
                session_id=entry.session_id,
                similarity_score=score,
                timestamp=entry.timestamp,
                metadata=entry.metadata,
            )
            for score, entry in scored[:top_k]
        ]

    def __repr__(self) -> str:
        backend = "Memanto API" if self._api_available else "local fallback"
        return (
            f"MeMantoMemoryAdapter("
            f"session_id={self.session_id!r}, "
            f"backend={backend!r})"
        )
