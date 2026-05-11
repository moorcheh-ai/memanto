"""
Memanto memory layer for the LangGraph example.

A thin facade around ``memanto.cli.client.sdk_client.SdkClient`` that:

* Creates / activates a single shared agent namespace.
* Exposes ``remember`` / ``recall`` / ``answer`` with the small surface this
  example actually uses.
* Renders recalled memories as a compact context block ready to drop into a
  LangGraph state's prompt.

The point of this module is to keep ``graph.py`` focused on the LangGraph
wiring -- all the Memanto bookkeeping lives here.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from memanto.cli.client.sdk_client import SdkClient

logger = logging.getLogger(__name__)

DEFAULT_AGENT_ID = "langgraph-support-concierge"
DEFAULT_SESSION_HOURS = 6


@dataclass(frozen=True)
class Memory:
    """A retrieved memory rendered for prompt consumption."""

    title: str
    content: str
    type: str
    confidence: float
    tags: tuple[str, ...]

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "Memory":
        return cls(
            title=raw.get("title", "Untitled"),
            content=raw.get("content", ""),
            type=raw.get("type", "unknown"),
            confidence=float(raw.get("confidence", 0.0) or 0.0),
            tags=tuple(raw.get("tags", []) or []),
        )

    def render(self) -> str:
        tag_str = f" [{', '.join(self.tags)}]" if self.tags else ""
        return f"- ({self.type}, c={self.confidence:.2f}){tag_str} {self.title}: {self.content}"


class MemantoMemory:
    """High-level memory operations bound to a single agent namespace."""

    def __init__(
        self,
        client: SdkClient,
        agent_id: str = DEFAULT_AGENT_ID,
    ) -> None:
        self._client = client
        self.agent_id = agent_id

    @property
    def client(self) -> SdkClient:
        return self._client

    def remember(
        self,
        memory_type: str,
        title: str,
        content: str,
        *,
        confidence: float = 0.85,
        tags: list[str] | None = None,
    ) -> str:
        """Store a single memory; returns the new memory id."""
        result = self._client.remember(
            agent_id=self.agent_id,
            memory_type=memory_type,
            title=title[:100],
            content=content[:500],
            confidence=confidence,
            tags=tags or [],
            source="langgraph-agent",
            provenance="explicit_statement",
        )
        memory_id = result.get("memory_id", "")
        logger.info(
            "Stored memory %s (type=%s, title=%r)", memory_id, memory_type, title
        )
        return memory_id

    def recall(
        self,
        query: str,
        *,
        limit: int = 6,
        memory_types: list[str] | None = None,
    ) -> list[Memory]:
        """Semantic search; returns rendered memories sorted by relevance."""
        result = self._client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            type=memory_types,
        )
        return [Memory.from_raw(m) for m in result.get("memories", [])]

    def answer(self, question: str) -> str:
        """RAG-grounded answer over the agent's memories."""
        result = self._client.answer(
            agent_id=self.agent_id,
            question=question,
        )
        return result.get("answer", "")

    @staticmethod
    def render_memories(memories: list[Memory]) -> str:
        if not memories:
            return "(no relevant memories)"
        return "\n".join(m.render() for m in memories)


@contextmanager
def memanto_session(
    api_key: str | None = None,
    agent_id: str = DEFAULT_AGENT_ID,
    description: str = "LangGraph + Memanto cross-session memory example",
    duration_hours: int = DEFAULT_SESSION_HOURS,
) -> Iterator[MemantoMemory]:
    """
    Context manager that creates (idempotently), activates, and tears down a
    Memanto agent session.

    Reads ``MOORCHEH_API_KEY`` from the environment if *api_key* is not given.
    """
    resolved_key = api_key or os.environ.get("MOORCHEH_API_KEY")
    if not resolved_key:
        raise RuntimeError(
            "MOORCHEH_API_KEY is not set. Copy .env.example to .env and fill it in."
        )

    client = SdkClient(api_key=resolved_key)

    try:
        client.create_agent(
            agent_id=agent_id,
            pattern="tool",
            description=description,
        )
        logger.info("Created Memanto agent %r", agent_id)
    except Exception:
        logger.info("Memanto agent %r already exists; reusing", agent_id)

    client.activate_agent(agent_id, duration_hours=duration_hours)
    logger.info("Activated session for agent %r", agent_id)

    try:
        yield MemantoMemory(client=client, agent_id=agent_id)
    finally:
        try:
            client.deactivate_agent(agent_id)
            logger.info("Deactivated session for agent %r", agent_id)
        except Exception as exc:
            logger.warning("Failed to deactivate agent %r: %s", agent_id, exc)
