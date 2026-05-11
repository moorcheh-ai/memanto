"""Memanto memory adapter for the LangGraph example."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

from memanto.cli.client.sdk_client import SdkClient

logger = logging.getLogger(__name__)

DEFAULT_AGENT_ID = "langgraph-support-memory"
VALID_MEMORY_TYPES = {
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
class MemorySearchResult:
    """Small, LangGraph-friendly memory result."""

    title: str
    content: str
    memory_type: str
    confidence: float | str
    tags: list[str]

    @classmethod
    def from_memanto(cls, item: dict[str, Any]) -> "MemorySearchResult":
        return cls(
            title=item.get("title", "Untitled"),
            content=item.get("content", ""),
            memory_type=item.get("type", "unknown"),
            confidence=item.get("confidence", "unknown"),
            tags=item.get("tags", []) or [],
        )

    def as_prompt_line(self) -> str:
        tags = f" tags={','.join(self.tags)}" if self.tags else ""
        return (
            f"- [{self.memory_type}] {self.title}: {self.content} "
            f"(confidence={self.confidence}{tags})"
        )


class MemantoMemory:
    """Thin wrapper that makes Memanto feel like a LangGraph memory store."""

    def __init__(self, api_key: str, agent_id: str = DEFAULT_AGENT_ID) -> None:
        self.agent_id = agent_id
        self.client = SdkClient(api_key=api_key)

    @classmethod
    def from_env(cls) -> "MemantoMemory":
        load_dotenv()
        api_key = os.environ.get("MOORCHEH_API_KEY")
        if not api_key:
            raise RuntimeError(
                "MOORCHEH_API_KEY is not set. Copy .env.example to .env and add "
                "a Moorcheh API key before running this example."
            )

        agent_id = os.environ.get("MEMANTO_LANGGRAPH_AGENT_ID", DEFAULT_AGENT_ID)
        return cls(api_key=api_key, agent_id=agent_id)

    def connect(self, duration_hours: int = 6) -> None:
        """Create the Memanto agent if needed and activate a fresh session."""
        try:
            self.client.create_agent(
                agent_id=self.agent_id,
                pattern="support",
                description=(
                    "LangGraph customer support agent with persistent Memanto "
                    "long-term memory."
                ),
            )
            logger.info("Created Memanto agent %s", self.agent_id)
        except Exception:
            logger.info("Reusing existing Memanto agent %s", self.agent_id)

        self.client.activate_agent(
            agent_id=self.agent_id,
            duration_hours=duration_hours,
        )

    def close(self) -> None:
        """End the current session while keeping memories in Memanto."""
        try:
            self.client.deactivate_agent(self.agent_id)
        except Exception as exc:
            logger.warning("Could not deactivate Memanto session: %s", exc)

    def remember(
        self,
        *,
        title: str,
        content: str,
        memory_type: str = "fact",
        confidence: float = 0.9,
        tags: list[str] | None = None,
    ) -> str:
        """Store one typed memory and return its Memanto memory ID."""
        if memory_type not in VALID_MEMORY_TYPES:
            raise ValueError(
                f"Unknown memory_type '{memory_type}'. Expected one of "
                f"{', '.join(sorted(VALID_MEMORY_TYPES))}."
            )

        result = self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags or [],
            source="langgraph-example",
            provenance="explicit_statement",
        )
        return str(result["memory_id"])

    def recall(
        self,
        query: str,
        *,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[MemorySearchResult]:
        """Search persistent Memanto memory from any future graph run."""
        result = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            type=memory_types,
        )
        return [
            MemorySearchResult.from_memanto(item)
            for item in result.get("memories", [])
        ]
