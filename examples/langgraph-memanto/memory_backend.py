"""
Memory Backend Abstraction for Memanto + LangGraph Integration.

Provides a Protocol-based backend with two implementations:
- LocalBackend: credential-free JSONL storage for testing and review
- MemantoBackend: production backend using the Moorcheh SDK client
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


def _tokenize(text: str) -> set[str]:
    """Split text into lowercase word tokens, stripping punctuation."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


@runtime_checkable
class MemoryBackend(Protocol):
    """Protocol defining the memory backend interface."""

    def store(self, entry: dict[str, Any]) -> str: ...
    def recall(self, query: str, limit: int = 5, tags: list[str] | None = None) -> list[dict[str, Any]]: ...
    def recall_by_type(self, memory_type: str, limit: int = 10) -> list[dict[str, Any]]: ...


def _get_local_dir() -> Path:
    """Return the local data directory, evaluated at access time (not import time)."""
    return Path(os.environ.get("MEMANTO_LANGGRAPH_DATA", str(Path.home() / ".memanto" / "langgraph-memory")))


NEWLINE = chr(10)  # \n


class LocalBackend:
    """Credential-free local JSONL backend for testing and review."""

    def __init__(self, data_dir: Path | str | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir else _get_local_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._store_path = self.data_dir / "memories.jsonl"

    def _read_all(self) -> list[dict[str, Any]]:
        entries = []
        if self._store_path.exists():
            with open(self._store_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        return entries

    def _append(self, entry: dict[str, Any]) -> None:
        with open(self._store_path, "a", encoding="utf-8") as fh:
            line = json.dumps(entry, default=str) + NEWLINE
            fh.write(line)

    def store(self, entry: dict[str, Any]) -> str:
        memory_id = entry.get("id") or str(uuid.uuid4())
        entry["id"] = memory_id
        entry.setdefault("stored_at", datetime.now(timezone.utc).isoformat())
        if "status" not in entry:
            entry["status"] = "active"
        self._append(entry)
        return memory_id

    def recall(self, query: str, limit: int = 5, tags: list[str] | None = None) -> list[dict[str, Any]]:
        query_words = _tokenize(query)
        entries = self._read_all()
        scored = []
        for e in entries:
            if e.get("status") == "superseded":
                continue
            score = 0.0
            text = (e.get("content", "") + " " + e.get("title", "")).lower()
            # Also include tags text for matching
            tag_text = " ".join(e.get("tags", []))
            full_text = text + " " + tag_text
            entry_words = _tokenize(full_text)
            overlap = query_words.intersection(entry_words)
            score += len(overlap) * 1.0
            for w in query_words:
                if len(w) > 3 and w in full_text:
                    score += 0.5
            if tags:
                entry_tags = set(e.get("tags", []))
                tag_overlap = set(tags).intersection(entry_tags)
                score += len(tag_overlap) * 2.0
            # Type boost only applies when there's already a relevance signal
            if score > 0 and e.get("type") in ("decision", "instruction", "preference"):
                score += 0.3
            if score > 0:
                scored.append((score, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:limit]]

    def recall_by_type(self, memory_type: str, limit: int = 10) -> list[dict[str, Any]]:
        entries = self._read_all()
        return [e for e in entries if e.get("type") == memory_type and e.get("status") != "superseded"][:limit]


class MemantoBackend:
    """Production backend using Moorcheh SdkClient."""

    def __init__(self, agent_id: str, api_key: str | None = None) -> None:
        from memanto.cli.client.sdk_client import SdkClient
        self.agent_id = agent_id
        self.api_key = api_key or os.environ["MOORCHEH_API_KEY"]
        self._client = SdkClient(api_key=self.api_key)
        self._activated = False

    def _ensure_activated(self) -> None:
        if not self._activated:
            try:
                self._client.activate_agent(self.agent_id)
            except Exception:
                self._client.create_agent(
                    self.agent_id,
                    pattern="tool",
                    description="LangGraph Memory Companion",
                )
                self._client.activate_agent(self.agent_id)
            self._activated = True

    def store(self, entry: dict[str, Any]) -> str:
        self._ensure_activated()
        result = self._client.remember(
            agent_id=self.agent_id,
            memory_type=entry.get("type"),
            title=entry.get("title", "")[:100],
            content=entry.get("content", ""),
            confidence=entry.get("confidence", 0.8),
            tags=entry.get("tags", []),
            source=entry.get("source", "langgraph-hook"),
            provenance=entry.get("provenance", "observed"),
        )
        return result.get("memory_id", str(uuid.uuid4()))

    def recall(self, query: str, limit: int = 5, tags: list[str] | None = None) -> list[dict[str, Any]]:
        self._ensure_activated()
        result = self._client.recall(agent_id=self.agent_id, query=query, limit=limit, tags=tags)
        return result.get("memories", [])

    def recall_by_type(self, memory_type: str, limit: int = 10) -> list[dict[str, Any]]:
        self._ensure_activated()
        result = self._client.recall(agent_id=self.agent_id, query="*", limit=limit, type=[memory_type])
        return result.get("memories", [])


def get_backend(agent_id: str | None = None, force_local: bool = False) -> MemoryBackend:
    """Return the appropriate backend based on environment configuration.

    Uses LocalBackend when no MOORCHEH_API_KEY is set or when force_local is True.
    Uses MemantoBackend when MOORCHEH_API_KEY is available.
    """
    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not force_local and api_key:
        aid = agent_id or os.environ.get("MEMANTO_AGENT_ID", "langgraph-memory-companion")
        return MemantoBackend(agent_id=aid, api_key=api_key)
    return LocalBackend()
