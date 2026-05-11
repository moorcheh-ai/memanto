"""
Memory adapters for the LangGraph + Memanto example.

The default adapter uses Memanto through SdkClient. A tiny local JSON adapter is
also provided so reviewers can run the LangGraph flow without API credentials.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from dotenv import load_dotenv

from memanto.cli.client.sdk_client import SdkClient


DEFAULT_AGENT_ID = "langgraph-support-agent"
LOCAL_STORE_PATH = Path(__file__).with_name(".local_memanto_demo.json")


class MemoryBackend(Protocol):
    """Small memory interface used by the LangGraph nodes."""

    agent_id: str

    def setup(self) -> None:
        """Prepare the memory backend for reads and writes."""

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        confidence: float,
        tags: list[str],
    ) -> dict[str, Any]:
        """Store one durable memory."""

    def recall(
        self,
        *,
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return relevant memories."""

    def close(self) -> None:
        """Release any session resources."""


@dataclass
class MemantoMemory:
    """Memanto-backed implementation of the demo memory interface."""

    api_key: str
    agent_id: str = DEFAULT_AGENT_ID
    description: str = "LangGraph support agent long-term memory demo"

    def __post_init__(self) -> None:
        self.client = SdkClient(api_key=self.api_key)

    def setup(self) -> None:
        try:
            self.client.create_agent(
                agent_id=self.agent_id,
                pattern="support",
                description=self.description,
            )
        except Exception:
            # The demo is intentionally rerunnable; an existing agent is fine.
            pass

        self.client.activate_agent(self.agent_id, duration_hours=6)

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        confidence: float,
        tags: list[str],
    ) -> dict[str, Any]:
        return self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags,
            source="langgraph-agent",
            provenance="explicit_statement",
        )

    def recall(
        self,
        *,
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        result = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            type=memory_types,
        )
        return list(result.get("memories", []))

    def close(self) -> None:
        try:
            self.client.deactivate_agent(self.agent_id)
        except Exception:
            pass


@dataclass
class LocalJsonMemory:
    """
    Local no-key memory backend for dry runs.

    This is not a replacement for Memanto. It exists only so the LangGraph
    example can be smoke-tested without network credentials.
    """

    agent_id: str = DEFAULT_AGENT_ID
    path: Path = LOCAL_STORE_PATH

    def setup(self) -> None:
        if not self.path.exists():
            self.path.write_text("[]\n", encoding="utf-8")

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        confidence: float,
        tags: list[str],
    ) -> dict[str, Any]:
        memories = self._load()
        memory_id = f"local-{len(memories) + 1}"
        record = {
            "id": memory_id,
            "memory_id": memory_id,
            "type": memory_type,
            "title": title,
            "content": content,
            "confidence": confidence,
            "tags": tags,
            "agent_id": self.agent_id,
        }
        memories.append(record)
        self.path.write_text(json.dumps(memories, indent=2) + "\n", encoding="utf-8")
        return {"memory_id": memory_id, "status": "stored", "agent_id": self.agent_id}

    def recall(
        self,
        *,
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        query_terms = {term.lower() for term in query.split() if len(term) > 2}
        memories = [
            memory
            for memory in self._load()
            if not memory_types or memory.get("type") in memory_types
        ]

        def score(memory: dict[str, Any]) -> int:
            text = f"{memory.get('title', '')} {memory.get('content', '')}".lower()
            return sum(1 for term in query_terms if term in text)

        ranked = sorted(memories, key=score, reverse=True)
        return ranked[:limit]

    def close(self) -> None:
        return None

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))


def create_memory_backend() -> MemoryBackend:
    """Create the configured memory backend."""
    load_dotenv()

    agent_id = os.environ.get("MEMANTO_AGENT_ID", DEFAULT_AGENT_ID)
    if os.environ.get("MEMANTO_DEMO_BACKEND") == "local":
        return LocalJsonMemory(agent_id=agent_id)

    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        raise RuntimeError(
            "MOORCHEH_API_KEY is required. Copy .env.example to .env and add "
            "your key, or set MEMANTO_DEMO_BACKEND=local for a no-key dry run."
        )

    return MemantoMemory(api_key=api_key, agent_id=agent_id)
