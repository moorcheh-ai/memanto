from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


class MemoryBackend(Protocol):
    def remember(
        self,
        *,
        title: str,
        content: str,
        memory_type: str,
        tags: list[str],
        source: str,
        metadata: dict[str, Any],
        confidence: float = 0.82,
    ) -> dict[str, Any]:
        ...

    def recall(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        ...


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def tokenise(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_\-/.]*", value.lower())
        if len(token) > 2
    }


class LocalJsonlBackend:
    def __init__(self, store_path: Path | str) -> None:
        self.store_path = Path(store_path).expanduser()

    def remember(
        self,
        *,
        title: str,
        content: str,
        memory_type: str,
        tags: list[str],
        source: str,
        metadata: dict[str, Any],
        confidence: float = 0.82,
    ) -> dict[str, Any]:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "id": str(uuid.uuid4()),
            "created_at": utc_now(),
            "title": title.strip()[:120],
            "content": content.strip(),
            "memory_type": memory_type,
            "tags": sorted(set(tags)),
            "source": source,
            "confidence": max(0.0, min(1.0, confidence)),
            "metadata": metadata,
        }
        with self.store_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        return record

    def recall(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        if not self.store_path.exists():
            return []

        query_tokens = tokenise(query)
        scored: list[dict[str, Any]] = []
        for record in self._iter_records():
            score = self._score(record, query_tokens)
            if score <= 0:
                continue
            scored_record = dict(record)
            scored_record["score"] = score
            scored.append(scored_record)

        scored.sort(
            key=lambda item: (
                item["score"],
                item.get("confidence", 0.0),
                item.get("created_at", ""),
            ),
            reverse=True,
        )
        return scored[:limit]

    def _iter_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        with self.store_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records

    def _score(self, record: dict[str, Any], query_tokens: set[str]) -> float:
        searchable = " ".join(
            [
                str(record.get("title", "")),
                str(record.get("content", "")),
                " ".join(record.get("tags", [])),
                str(record.get("metadata", {}).get("path", "")),
                str(record.get("metadata", {}).get("skill", "")),
            ]
        )
        record_tokens = tokenise(searchable)
        overlap = len(query_tokens & record_tokens)
        if overlap == 0:
            return 0.0
        type_boost = 0.25 if record.get("memory_type") in {"decision", "instruction"} else 0
        confidence = float(record.get("confidence", 0.0))
        return overlap + type_boost + confidence


class LiveMemantoBackend:
    def __init__(
        self,
        *,
        api_key: str,
        agent_id: str,
        client_factory: Any | None = None,
    ) -> None:
        self.api_key = api_key
        self.agent_id = agent_id
        self._client_factory = client_factory
        self._client: Any | None = None
        self._activated = False

    @property
    def client(self) -> Any:
        if self._client is None:
            factory = self._client_factory
            if factory is None:
                from memanto.cli.client.sdk_client import SdkClient

                factory = SdkClient
            self._client = factory(self.api_key)
        return self._client

    def _ensure_active_session(self) -> None:
        if self._activated:
            return
        activate = getattr(self.client, "activate_agent", None)
        if callable(activate):
            activate(self.agent_id)
        self._activated = True

    def remember(
        self,
        *,
        title: str,
        content: str,
        memory_type: str,
        tags: list[str],
        source: str,
        metadata: dict[str, Any],
        confidence: float = 0.82,
    ) -> dict[str, Any]:
        self._ensure_active_session()
        live_tags = sorted(set(tags + ["developer-skill-memory"]))
        enriched = content
        if metadata:
            enriched = f"{content}\n\nMetadata: {json.dumps(metadata, sort_keys=True)}"
        result = self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory_type,
            title=title,
            content=enriched,
            confidence=confidence,
            tags=live_tags,
            source=source,
            provenance="explicit_statement",
        )
        return dict(result)

    def recall(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        self._ensure_active_session()
        result = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            tags=["developer-skill-memory"],
        )
        memories = result.get("memories", []) if isinstance(result, dict) else []
        normalised: list[dict[str, Any]] = []
        for memory in memories:
            normalised.append(
                {
                    "title": memory.get("title", "Memory"),
                    "content": memory.get("content", ""),
                    "memory_type": memory.get("type", memory.get("memory_type", "context")),
                    "tags": memory.get("tags", []),
                    "confidence": memory.get("confidence", 0.0),
                    "metadata": memory.get("metadata", {}),
                    "score": memory.get("score", 1.0),
                }
            )
        return normalised


def default_store_path() -> Path:
    return Path(
        os.environ.get(
            "SKILL_MEMANTO_STORE",
            "~/.memanto/skill-memory/developer-skills.jsonl",
        )
    ).expanduser()


def build_backend() -> MemoryBackend:
    backend = os.environ.get("SKILL_MEMANTO_BACKEND", "local").strip().lower()
    if backend in {"live", "memanto", "sdk"}:
        api_key = os.environ.get("MOORCHEH_API_KEY") or os.environ.get("MEMANTO_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Live backend requested but MOORCHEH_API_KEY or MEMANTO_API_KEY is missing."
            )
        return LiveMemantoBackend(
            api_key=api_key,
            agent_id=os.environ.get("SKILL_MEMANTO_AGENT_ID", "developer-skills"),
        )
    return LocalJsonlBackend(default_store_path())
