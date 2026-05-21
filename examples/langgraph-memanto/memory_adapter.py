"""
Memory adapter used by the LangGraph + Memanto example.

The live adapter writes to Memanto. The local adapter gives contributors a
no-key dry run path and keeps the example testable in CI.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Protocol


class MemoryClient(Protocol):
    """Small memory interface consumed by the LangGraph workflow."""

    agent_id: str

    def setup(self) -> None:
        """Prepare the memory backend for reads and writes."""

    def teardown(self) -> None:
        """Release any active session resources."""

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
        confidence: float = 0.9,
    ) -> dict[str, Any]:
        """Persist one memory."""

    def recall(self, *, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Retrieve memories relevant to a natural-language query."""


class LiveMemantoMemory:
    """Memanto-backed memory client for the real integration demo."""

    def __init__(
        self,
        *,
        api_key: str,
        agent_id: str,
        description: str = "LangGraph support-agent memory demo",
        duration_hours: int = 6,
    ) -> None:
        from memanto.cli.client.sdk_client import SdkClient

        self.agent_id = agent_id
        self.description = description
        self.duration_hours = duration_hours
        self.client = SdkClient(api_key=api_key)

    def setup(self) -> None:
        try:
            self.client.create_agent(
                agent_id=self.agent_id,
                pattern="support",
                description=self.description,
            )
        except Exception:
            # Reusing an existing demo agent is expected across separate runs.
            pass

        self.client.activate_agent(
            self.agent_id,
            duration_hours=self.duration_hours,
        )

    def teardown(self) -> None:
        try:
            self.client.deactivate_agent(self.agent_id)
        except Exception:
            pass

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
        confidence: float = 0.9,
    ) -> dict[str, Any]:
        return self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags or [],
            source="langgraph-demo",
            provenance="explicit_statement",
        )

    def recall(self, *, query: str, limit: int = 5) -> list[dict[str, Any]]:
        result = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
        )
        return list(result.get("memories", []))


class LocalJsonMemory:
    """Tiny persistent memory backend for tests and no-key dry runs."""

    def __init__(self, *, path: str | Path, agent_id: str) -> None:
        self.path = Path(path)
        self.agent_id = agent_id

    def setup(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]\n", encoding="utf-8")

    def teardown(self) -> None:
        return None

    def remember(
        self,
        *,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
        confidence: float = 0.9,
    ) -> dict[str, Any]:
        memories = self._load()
        memory_id = f"local-{uuid.uuid4().hex[:10]}"
        record = {
            "memory_id": memory_id,
            "agent_id": self.agent_id,
            "type": memory_type,
            "title": title,
            "content": content,
            "tags": tags or [],
            "confidence": confidence,
        }
        memories.append(record)
        self.path.write_text(
            json.dumps(memories, indent=2) + "\n",
            encoding="utf-8",
        )
        return record

    def recall(self, *, query: str, limit: int = 5) -> list[dict[str, Any]]:
        query_terms = set(_tokenize(query))
        scored: list[tuple[int, dict[str, Any]]] = []

        for memory in self._load():
            haystack = " ".join(
                [
                    str(memory.get("title", "")),
                    str(memory.get("content", "")),
                    " ".join(memory.get("tags", [])),
                ]
            )
            score = len(query_terms.intersection(_tokenize(haystack)))
            if score:
                scored.append((score, memory))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [memory for _, memory in scored[:limit]]

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return []
        return loaded if isinstance(loaded, list) else []


def create_memory_client() -> MemoryClient:
    """Create the memory client configured by environment variables."""
    agent_id = os.environ.get("MEMANTO_AGENT_ID", "langgraph-support-memory-demo")
    dry_run = os.environ.get("MEMANTO_DRY_RUN", "").lower() in {"1", "true", "yes"}

    if dry_run:
        return LocalJsonMemory(
            path=os.environ.get(
                "MEMANTO_LOCAL_STORE",
                ".memanto-langgraph-demo.json",
            ),
            agent_id=agent_id,
        )

    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        raise RuntimeError(
            "MOORCHEH_API_KEY is required. Set MEMANTO_DRY_RUN=true for a "
            "local no-key demo."
        )

    return LiveMemantoMemory(api_key=api_key, agent_id=agent_id)


def _tokenize(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())
