"""
MemantoTool — LangGraph-compatible tool wrapping Memanto's three primitives.

Provides `remember`, `recall`, and `answer` as callable methods that
integrate with LangGraph's tool interface.
"""

import os
import json
import logging
logger = logging.getLogger(__name__)

from datetime import datetime
from typing import Any

from memanto.app.core import MemoryRecord, MemoryScope
from memanto.app.services.memory_write_service import MemoryWriteService
from memanto.app.services.memory_read_service import MemoryReadService

try:
    from moorcheh_sdk import MoorchehClient
except ImportError:
    MoorchehClient = None


# Valid memory types from Memanto
MEMORY_TYPES = [
    "fact", "preference", "goal", "decision", "artifact",
    "learning", "event", "instruction", "relationship",
    "context", "observation", "commitment", "error",
]


class MemantoTool:
    """
    LangGraph-compatible tool that wraps Memanto's remember/recall/answer primitives.

    Usage:
        tool = MemantoTool(agent_id="research-agent-1", scope_id="research")
        tool.remember("Quantum error correction uses surface codes", memory_type="fact", confidence=0.9)
        results = tool.recall("error correction approaches")
        answer = tool.answer("What did we learn about quantum error correction?")
    """

    def __init__(
        self,
        agent_id: str = "langgraph-agent",
        scope_type: str = "agent",
        scope_id: str = "default",
        moorcheh_api_key: str | None = None,
    ):
        self.agent_id = agent_id
        self.scope_type = scope_type
        self.scope_id = scope_id

        api_key = moorcheh_api_key or os.environ.get("MOORCHEH_API_KEY", "")
        if not api_key:
            raise ValueError(
                "MOORCHEH_API_KEY is required. Set it in .env or pass moorcheh_api_key."
            )

        if MoorchehClient is None:
            raise ImportError(
                "moorcheh-sdk is required. Install with: pip install moorcheh-sdk"
            )

        self.client = MoorchehClient(api_key=api_key)
        self.write_service = MemoryWriteService(self.client)
        self.read_service = MemoryReadService(self.client)

        # Ensure namespace exists
        self._namespace = MemoryScope(
            scope_type=scope_type, scope_id=scope_id
        ).to_namespace()
        self._ensure_namespace()

    def _ensure_namespace(self):
        """Create the Moorcheh namespace if it doesn't exist."""
        try:
            self.client.namespaces.get(namespace_name=self._namespace)
        except Exception:
            try:
                self.client.namespaces.create(
                    namespace_name=self._namespace,
                    source_type="semantic",
                )
            except Exception:
                pass  # Namespace may already exist (race condition)

    def remember(
        self,
        content: str,
        title: str | None = None,
        memory_type: str = "fact",
        confidence: float = 0.8,
        tags: list[str] | None = None,
        source: str = "agent_inference",
    ) -> dict[str, Any]:
        """
        Store a new memory in Memanto.

        Args:
            content: The memory content text
            title: Short title (auto-generated if None)
            memory_type: One of Memanto's 13 typed categories
            confidence: Self-evaluated certainty (0.0 - 1.0)
            tags: Optional tags for categorization
            source: Provenance source type

        Returns:
            Dict with stored memory ID and metadata
        """
        if memory_type not in MEMORY_TYPES:
            raise ValueError(
                f"Invalid memory_type '{memory_type}'. Must be one of: {MEMORY_TYPES}"
            )
        confidence = max(0.0, min(1.0, confidence))
        if title is None:
            title = content[:80] + ("..." if len(content) > 80 else "")

        memory = MemoryRecord(
            type=memory_type,
            title=title,
            content=content,
            scope_type=self.scope_type,
            scope_id=self.scope_id,
            actor_id=self.agent_id,
            source=source,
            confidence=confidence,
            tags=tags or [],
            provenance="explicit_statement",
        )

        result = self.write_service.store_memory(memory)
        return {
            "action": "remembered",
            "memory_id": memory.id,
            "type": memory_type,
            "confidence": confidence,
            "title": title,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def recall(
        self,
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
        min_confidence: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search for relevant memories in Memanto.

        Args:
            query: Search query for semantic retrieval
            limit: Maximum number of memories to return (1-20)
            memory_types: Filter by memory types
            min_confidence: Filter by minimum confidence score

        Returns:
            List of memory dicts with content, type, confidence, and timestamp
        """
        kwargs = {
            "query": query,
            "scope_type": self.scope_type,
            "scope_id": self.scope_id,
            "limit": limit,
        }
        if memory_types:
            kwargs["type"] = memory_types
        if min_confidence is not None:
            kwargs["min_confidence"] = min_confidence

        result = self.read_service.search_memories(**kwargs)

        memories = []
        items = result.get("memories", result.get("items", []))
        for item in items:
            memories.append({
                "memory_id": item.get("id", ""),
                "type": item.get("memory_type", item.get("type", "unknown")),
                "title": item.get("title", ""),
                "content": item.get("content", item.get("text", "")),
                "confidence": item.get("confidence", 0.0),
                "created_at": item.get("created_at", ""),
            })

        return memories

    def answer(self, query: str) -> dict[str, Any]:
        """
        Get an LLM-grounded answer from Memanto's memory.

        This uses Memanto's native `answer` primitive, which generates
        a response directly from stored memories without requiring an
        external LLM call.

        Args:
            query: Question to answer from memory

        Returns:
            Dict with answer text, source memories, and confidence
        """
        try:
            # Use Memanto's answer endpoint
            result = self.client.answer(
                namespace_name=self._namespace,
                question=query,
            )
            return {
                "answer": result.get("answer", ""),
                "sources": result.get("sources", []),
                "confidence": result.get("confidence", 0.0),
            }
        except Exception:
            # Fallback: recall + format manually
            memories = self.recall(query, limit=3)
            if not memories:
                return {
                    "answer": "No relevant memories found.",
                    "sources": [],
                    "confidence": 0.0,
                }
            answer_parts = []
            for m in memories:
                answer_parts.append(
                    f"[{m['type'].upper()}] {m['content']} (confidence: {m['confidence']})"
                )
            return {
                "answer": "\n".join(answer_parts),
                "sources": memories,
                "confidence": max(m["confidence"] for m in memories) if memories else 0.0,
            }

    def get_langchain_tools(self) -> list:
        """
        Return LangChain-compatible tool definitions for use with LangGraph.

        Returns three tools: remember, recall, answer.
        """
        from langchain_core.tools import tool as lc_tool

        memanto_instance = self

        @lc_tool
        def remember_memory(content: str, memory_type: str = "fact", confidence: float = 0.8) -> str:
            """Store a new memory. Use memory_type: fact, observation, decision, goal, preference, instruction."""
            result = memanto_instance.remember(
                content=content, memory_type=memory_type, confidence=confidence
            )
            return json.dumps(result)

        @lc_tool
        def recall_memories(query: str, limit: int = 5) -> str:
            """Search for relevant memories from previous sessions."""
            results = memanto_instance.recall(query=query, limit=limit)
            return json.dumps(results, default=str)

        @lc_tool
        def answer_from_memory(query: str) -> str:
            """Get an answer grounded in the agent's persistent memory."""
            result = memanto_instance.answer(query=query)
            return json.dumps(result, default=str)

        return [remember_memory, recall_memories, answer_from_memory]
