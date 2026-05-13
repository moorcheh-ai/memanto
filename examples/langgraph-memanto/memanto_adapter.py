"""
memanto_adapter.py — LangGraph ↔ Memanto Memory Adapter

A durable-state adapter that bridges LangGraph's built-in MemorySaver
with Memanto's persistent long-term memory. This allows LangGraph agents
to access memories across completely separate graph invocations, sessions,
and even different agent instances.

Key design decisions:
  - No LLM dependency: all memory operations use deterministic logic
  - Multi-agent friendly: multiple LangGraph agents share the same Memanto
    backend with agent_id isolation
  - Conflict-aware: detects and reports memory conflicts automatically
  - Preview mode: works without a Memanto API key for development/testing
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Local preview store — a JSON file that mimics Memanto's API for testing
# ---------------------------------------------------------------------------

class _LocalPreviewStore:
    """Thread-safe local JSON store that mimics Memanto's API surface."""

    def __init__(self, path: str = ".memanto_preview_store.json"):
        self._path = Path(path)
        self._lock = threading.Lock()
        self._data: dict[str, list[dict[str, Any]]] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            raw = self._path.read_text()
            self._data = json.loads(raw) if raw.strip() else {}
        else:
            self._data = {}

    def _save(self) -> None:
        self._path.write_text(json.dumps(self._data, indent=2, default=str))

    # --- Memanto-like API ---

    def remember(
        self,
        agent_id: str,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.8,
        tags: list[str] | None = None,
        source: str = "agent",
    ) -> dict[str, Any]:
        with self._lock:
            if agent_id not in self._data:
                self._data[agent_id] = []
            record = {
                "id": f"preview_{len(self._data[agent_id])}_{datetime.now(timezone.utc).timestamp()}",
                "agent_id": agent_id,
                "type": memory_type,
                "title": title,
                "content": content,
                "confidence": confidence,
                "tags": tags or [],
                "source": source,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self._data[agent_id].append(record)
            self._save()
            return {"status": "ok", "memory": record}

    def recall(
        self,
        agent_id: str,
        query: str,
        limit: int = 5,
    ) -> dict[str, Any]:
        with self._lock:
            records = self._data.get(agent_id, [])
            # Simple keyword matching (no LLM)
            query_lower = query.lower()
            query_terms = query_lower.split()
            scored = []
            for r in records:
                score = 0
                text = (r.get("title", "") + " " + r.get("content", "")).lower()
                for term in query_terms:
                    if term in text:
                        score += 1
                # Boost recent records
                age_bonus = 0.1 if score > 0 else 0
                scored.append((score + age_bonus, r))
            scored.sort(key=lambda x: x[0], reverse=True)
            results = [r for _, r in scored[:limit] if _ > 0]
            return {"status": "ok", "results": results, "count": len(results)}

    def list_memories(self, agent_id: str, limit: int = 20) -> dict[str, Any]:
        with self._lock:
            records = self._data.get(agent_id, [])
            return {"status": "ok", "results": records[-limit:], "count": len(records)}

# ---------------------------------------------------------------------------
# The main adapter class
# ---------------------------------------------------------------------------

class MemantoAdapter:
    """
    LangGraph memory adapter backed by Memanto.

    Provides three core primitives — remember, recall, answer — as well as
    higher-level operations for memory management.

    Usage::

        adapter = MemantoAdapter(api_key="...", agent_id="my-agent")

        # Store a memory
        adapter.remember("preference", "language", "User prefers Python", tags=["user", "lang"])

        # Recall relevant memories
        result = adapter.recall("What language does the user prefer?")
        for mem in result.get("results", []):
            print(mem["title"], "→", mem["content"])

        # Semantic Q&A over memories
        answer = adapter.answer("What do you know about the user?")
    """

    def __init__(
        self,
        api_key: str | None = None,
        agent_id: str = "langgraph-default-agent",
        preview: bool = False,
    ):
        self._agent_id = agent_id
        self._api_key = api_key or os.environ.get("MOORCHEH_API_KEY", "")

        # Determine backend
        if preview or not self._api_key or self._api_key == "your_api_key_here":
            self._preview = True
            self._store = _LocalPreviewStore()
            logger.info("MemantoAdapter: using LOCAL preview store (no API key)")
        else:
            self._preview = False
            from memanto.cli.client.sdk_client import SdkClient
            self._client = SdkClient(api_key=self._api_key)
            logger.info("MemantoAdapter: using MEMANTO cloud backend")
            # Ensure the agent exists
            self._ensure_agent()

    def _ensure_agent(self) -> None:
        """Create the agent if it doesn't exist yet."""
        if self._preview:
            return
        try:
            self._client.get_agent(self._agent_id)
        except Exception:
            self._client.create_agent(
                self._agent_id,
                pattern="tool",
                description=f"LangGraph memory agent (created by MemantoAdapter)",
            )

    def _normalize_result(self, raw: Any) -> dict[str, Any]:
        """Normalize both cloud and preview results to the same shape."""
        if isinstance(raw, dict) and "status" in raw:
            return raw
        if isinstance(raw, dict):
            return {"status": "ok", **raw}
        return {"status": "ok", "results": [], "count": 0}

    # --- Public API ---

    @property
    def agent_id(self) -> str:
        return self._agent_id

    def remember(
        self,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.8,
        tags: list[str] | None = None,
        source: str = "agent",
        provenance: str | None = None,
    ) -> dict[str, Any]:
        """
        Store a memory in the long-term store.

        Args:
            memory_type: Category (e.g. 'preference', 'fact', 'observation', 'decision')
            title: Short identifier for the memory
            content: The actual memory content
            confidence: Confidence score 0.0–1.0
            tags: Optional categorization tags
            source: Origin of the memory
            provenance: Optional provenance tracking string
        """
        if self._preview:
            return self._store.remember(
                self._agent_id, memory_type, title, content, confidence, tags, source
            )
        return self._normalize_result(
            self._client.remember(
                self._agent_id, memory_type, title, content,
                confidence=confidence, tags=tags or [],
                source=source, provenance=provenance,
            )
        )

    def batch_remember(
        self, memories: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Store multiple memories at once."""
        if self._preview:
            results = []
            for m in memories:
                r = self._store.remember(
                    self._agent_id,
                    m["memory_type"], m["title"], m["content"],
                    confidence=m.get("confidence", 0.8),
                    tags=m.get("tags"), source=m.get("source", "agent"),
                )
                results.append(r)
            return {"status": "ok", "count": len(results), "results": results}
        return self._normalize_result(
            self._client.batch_remember(self._agent_id, memories)
        )

    def recall(
        self,
        query: str,
        limit: int = 5,
        memory_type: list[str] | None = None,
        tags: list[str] | None = None,
        min_confidence: float | None = None,
    ) -> dict[str, Any]:
        """
        Search for memories relevant to the query.

        Args:
            query: Natural language query or keywords
            limit: Max results to return
            memory_type: Filter by memory type(s)
            tags: Filter by tag(s)
            min_confidence: Minimum confidence threshold
        """
        if self._preview:
            return self._store.recall(self._agent_id, query, limit)
        kwargs = {"agent_id": self._agent_id, "query": query, "limit": limit}
        if memory_type:
            kwargs["type"] = memory_type
        if tags:
            kwargs["tags"] = tags
        if min_confidence is not None:
            kwargs["min_confidence"] = min_confidence
        return self._normalize_result(self._client.recall(**kwargs))

    def recall_as_of(
        self, as_of: str, limit: int = 5
    ) -> dict[str, Any]:
        """Recall memories as they existed at a specific point in time."""
        if self._preview:
            return {"status": "ok", "results": [], "count": 0, "note": "Time-travel not available in preview mode"}
        return self._normalize_result(
            self._client.recall_as_of(self._agent_id, as_of, limit=limit)
        )

    def recall_changed_since(
        self, since: str, limit: int = 5
    ) -> dict[str, Any]:
        """Recall memories that changed since a given timestamp."""
        if self._preview:
            return {"status": "ok", "results": [], "count": 0, "note": "Change tracking not available in preview mode"}
        return self._normalize_result(
            self._client.recall_changed_since(self._agent_id, since, limit=limit)
        )

    def answer(
        self, question: str, limit: int = 10, threshold: float = 0.5
    ) -> dict[str, Any]:
        """
        Ask a question over the agent's memory store.
        Returns a grounded answer synthesized from relevant memories.
        """
        if self._preview:
            memories = self._store.recall(self._agent_id, question, limit)
            results = memories.get("results", [])
            if not results:
                return {
                    "status": "ok",
                    "answer": "No relevant memories found.",
                    "sources": [],
                }
            # Simple summarization (no LLM)
            snippets = [f"- {r['title']}: {r['content']}" for r in results]
            return {
                "status": "ok",
                "answer": f"Based on {len(results)} memories:\n" + "\n".join(snippets),
                "sources": results,
            }
        return self._normalize_result(
            self._client.answer(
                self._agent_id, question, limit=limit, threshold=threshold
            )
        )

    def list_memories(self, limit: int = 20) -> dict[str, Any]:
        """List the most recent memories."""
        if self._preview:
            return self._store.list_memories(self._agent_id, limit)
        return self._normalize_result(
            self._client.recall(self._agent_id, query="", limit=limit)
        )

    def detect_conflicts(self, date: str | None = None) -> list[dict[str, Any]]:
        """Check for conflicting memories (cloud only)."""
        if self._preview:
            return []
        try:
            return self._client.list_conflicts(self._agent_id, date=date)
        except Exception as e:
            logger.warning(f"Conflict check failed: {e}")
            return []

    def generate_summary(self, date: str | None = None) -> dict[str, Any]:
        """Generate a daily summary of memories (cloud only)."""
        if not date:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._preview:
            memories = self._store.list_memories(self._agent_id, limit=50)
            m_list = memories.get("results", [])
            return {
                "status": "ok",
                "date": date,
                "summary": f"Preview mode: {len(m_list)} memories stored. "
                           f"Full summary requires Memanto cloud.",
                "memory_count": len(m_list),
            }
        return self._normalize_result(
            self._client.generate_daily_summary(self._agent_id, date)
        )

    def export_markdown(self, output_path: str | None = None) -> dict[str, Any]:
        """Export all memories as a Markdown file."""
        if self._preview:
            memories = self._store.list_memories(self._agent_id, limit=100)
            return {
                "status": "ok",
                "message": f"Preview store has {memories['count']} memories. "
                           f"Cloud export produces a full .md file.",
            }
        return self._normalize_result(
            self._client.export_memory_md(self._agent_id, output_path=output_path)
        )