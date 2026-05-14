from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from memanto.cli.client.direct_client import DirectClient

load_dotenv()


class MemantoCommandError(RuntimeError):
    """Raised when the example cannot complete a Memanto operation."""


@dataclass
class RememberRequest:
    content: str
    memory_type: str
    tags: str | None = None
    source: str | None = None
    confidence: float = 0.85
    provenance: str = "explicit_statement"


class MemantoCLI:
    """Stable wrapper around Memanto's direct Python client."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        api_key = os.getenv("MOORCHEH_API_KEY", "").strip()
        if not api_key:
            raise MemantoCommandError(
                "MOORCHEH_API_KEY is missing. Add it to .env before running the demo."
            )
        self.client = DirectClient(api_key=api_key)

    def ensure_agent(self) -> None:
        try:
            self.client.create_agent(self.agent_id)
        except Exception as exc:
            if "already exists" not in str(exc).lower():
                raise MemantoCommandError(
                    f"Unable to create agent '{self.agent_id}': {exc}"
                ) from exc

        try:
            self.client.activate_agent(self.agent_id)
        except Exception as exc:
            raise MemantoCommandError(
                f"Unable to activate agent '{self.agent_id}': {exc}"
            ) from exc

    def remember_many(self, requests: Iterable[RememberRequest]) -> int:
        persisted = 0
        for request in requests:
            try:
                self.client.remember(
                    agent_id=self.agent_id,
                    memory_type=request.memory_type,
                    title=self._build_title(request.content),
                    content=request.content,
                    confidence=request.confidence,
                    tags=self._split_tags(request.tags),
                    source=request.source or self.agent_id,
                    provenance=request.provenance,
                )
            except Exception as exc:
                raise MemantoCommandError(
                    f"Failed to store memory for agent '{self.agent_id}': {exc}"
                ) from exc
            persisted += 1
        return persisted

    def recall(self, query: str, limit: int = 5, memory_type: str | None = None) -> str:
        try:
            result = self.client.recall(
                agent_id=self.agent_id,
                query=query,
                limit=limit,
                type=[memory_type] if memory_type else None,
            )
        except Exception as exc:
            raise MemantoCommandError(
                f"Failed to recall memory for agent '{self.agent_id}': {exc}"
            ) from exc

        memories = result.get("memories", [])
        if not memories:
            return ""

        lines = []
        for memory in memories:
            memory_type_label = memory.get("type", "memory")
            content = memory.get("content") or memory.get("title") or ""
            if content:
                lines.append(f"- [{memory_type_label}] {content}")
        return "\n".join(lines)

    @staticmethod
    def _build_title(content: str) -> str:
        compact = " ".join(content.split())
        if len(compact) <= 60:
            return compact
        return f"{compact[:57]}..."

    @staticmethod
    def _split_tags(tags: str | None) -> list[str] | None:
        if not tags:
            return None
        values = [value.strip() for value in tags.split(",") if value.strip()]
        return values or None
