from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class MemoryHit:
    title: str
    content: str
    memory_type: str = "preference"


class MemoryStore(Protocol):
    def setup(self) -> None: ...

    def remember_preference(self, user_id: str, content: str) -> None: ...

    def recall(self, user_id: str, query: str, limit: int = 5) -> list[MemoryHit]: ...

    def close(self) -> None: ...


class MemantoMemoryStore:
    """Memanto-backed memory store used by the real demo path."""

    def __init__(self, api_key: str, agent_id: str) -> None:
        from memanto.cli.client.sdk_client import SdkClient

        self.agent_id = agent_id
        self.client = SdkClient(api_key=api_key)

    def setup(self) -> None:
        try:
            self.client.create_agent(
                self.agent_id,
                pattern="tool",
                description="LangGraph support agent with cross-session Memanto recall",
            )
        except Exception:
            pass
        self.client.activate_agent(self.agent_id, duration_hours=6)

    def remember_preference(self, user_id: str, content: str) -> None:
        self.client.remember(
            agent_id=self.agent_id,
            memory_type="preference",
            title=f"{user_id} support preference",
            content=f"User {user_id}: {content}",
            confidence=0.9,
            tags=["langgraph-demo", "support-agent", user_id],
            source="langgraph-memanto-example",
            provenance="explicit_statement",
        )

    def recall(self, user_id: str, query: str, limit: int = 5) -> list[MemoryHit]:
        result = self.client.recall(
            agent_id=self.agent_id,
            query=f"User {user_id}: {query}",
            limit=limit,
            type=["preference", "fact", "context"],
            tags=[user_id],
        )
        hits: list[MemoryHit] = []
        for item in result.get("memories", []):
            hits.append(
                MemoryHit(
                    title=item.get("title", "Untitled"),
                    content=item.get("content", ""),
                    memory_type=item.get("type", "memory"),
                )
            )
        return hits

    def close(self) -> None:
        try:
            self.client.deactivate_agent(self.agent_id)
        except Exception:
            pass


class LocalJsonMemoryStore:
    """Offline-only fallback for testing the graph without external credentials."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._records: list[dict[str, str]] = []

    def setup(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = []
            self._records = data if isinstance(data, list) else []
        else:
            self._records = []

    def remember_preference(self, user_id: str, content: str) -> None:
        self._records.append(
            {
                "user_id": user_id,
                "type": "preference",
                "title": f"{user_id} support preference",
                "content": f"User {user_id}: {content}",
            }
        )
        self.path.write_text(
            json.dumps(self._records, indent=2) + "\n",
            encoding="utf-8",
        )

    def recall(self, user_id: str, query: str, limit: int = 5) -> list[MemoryHit]:
        query_terms = {part.strip(".,?!").lower() for part in query.split()}
        matches: list[MemoryHit] = []
        for record in reversed(self._records):
            if record.get("user_id") != user_id:
                continue
            content = record.get("content", "")
            content_terms = {part.strip(".,?!").lower() for part in content.split()}
            if query_terms & content_terms or not matches:
                matches.append(
                    MemoryHit(
                        title=record.get("title", "Untitled"),
                        content=content,
                        memory_type=record.get("type", "memory"),
                    )
                )
            if len(matches) >= limit:
                break
        return matches

    def close(self) -> None:
        pass


def build_memory_store(offline: bool = False) -> MemoryStore:
    if offline:
        return LocalJsonMemoryStore(Path(".langgraph_memanto_demo.json"))

    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        raise RuntimeError(
            "MOORCHEH_API_KEY is not set. Add it to .env or run with --offline."
        )
    agent_id = os.environ.get("MEMANTO_AGENT_ID", "langgraph-support-demo")
    return MemantoMemoryStore(api_key=api_key, agent_id=agent_id)
