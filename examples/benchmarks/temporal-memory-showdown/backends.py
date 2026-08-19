"""Live adapters for Memanto On-Prem and Mem0 OSS."""

from __future__ import annotations

import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from dataset import MemoryRecord


@dataclass(frozen=True)
class SearchHit:
    text: str
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class MemoryBackend(Protocol):
    name: str

    def ingest(self, record: MemoryRecord) -> None: ...

    def search(self, query: str, top_k: int) -> list[SearchHit]: ...

    def usage(self) -> dict[str, int]: ...

    def close(self) -> None: ...


class MemantoBackend:
    name = "memanto-on-prem"

    def __init__(self, base_url: str, run_id: str) -> None:
        from memanto.app.clients.moorcheh import moorcheh_client
        from memanto.app.config import settings
        from memanto.cli.client.sdk_client import SdkClient

        settings.MEMANTO_BACKEND = "on-prem"
        settings.MOORCHEH_ONPREM_URL = base_url
        moorcheh_client.reset_client()

        self.agent_id = f"bench-{run_id}-memanto"
        self.client = SdkClient(api_key="on-prem-local")
        create_memanto_agent(
            self.client,
            agent_id=self.agent_id,
            pattern="tool",
            description="Temporal memory benchmark",
        )
        self.client.activate_agent(self.agent_id, duration_hours=2)

    def ingest(self, record: MemoryRecord) -> None:
        self.client.remember(
            agent_id=self.agent_id,
            memory_type=record.memory_type,
            title=record.record_id,
            content=f"[{record.record_id}] {record.text}",
            confidence=1.0,
            tags=[f"session-{record.session:02d}", record.record_id],
            source="benchmark",
            provenance="explicit_statement",
        )

    def search(self, query: str, top_k: int) -> list[SearchHit]:
        response = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=top_k,
            min_similarity=0.0,
        )
        hits = []
        for item in response.get("memories", []):
            text = item.get("content") or item.get("text") or ""
            hits.append(
                SearchHit(
                    text=text,
                    score=item.get("score"),
                    metadata={
                        "id": item.get("id"),
                        "type": item.get("type"),
                        "tags": item.get("tags", []),
                    },
                )
            )
        return hits

    def usage(self) -> dict[str, int]:
        return {"llm_calls": 0, "llm_input_tokens": 0, "llm_output_tokens": 0}

    def close(self) -> None:
        try:
            self.client.deactivate_agent(self.agent_id)
        except Exception:
            pass


def create_memanto_agent(
    client: Any,
    *,
    agent_id: str,
    pattern: str,
    description: str,
    attempts: int = 5,
    delay_s: float = 1.0,
) -> None:
    """Retry idempotent bootstrap when On-Prem commits before returning 500."""

    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            client.create_agent(
                agent_id=agent_id,
                pattern=pattern,
                description=description,
            )
            return
        except Exception as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(delay_s)
    assert last_error is not None
    raise last_error


class MeteredOllamaClient:
    """Proxy an Ollama client while retaining native token counters."""

    def __init__(self, wrapped: Any) -> None:
        self.wrapped = wrapped
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self.wrapped, name)

    def chat(self, *args: Any, **kwargs: Any) -> Any:
        response = self.wrapped.chat(*args, **kwargs)
        self.calls += 1
        self.input_tokens += _response_int(response, "prompt_eval_count")
        self.output_tokens += _response_int(response, "eval_count")
        return response


def _response_int(response: Any, key: str) -> int:
    if isinstance(response, dict):
        value = response.get(key, 0)
    else:
        value = getattr(response, key, 0)
    return int(value or 0)


class Mem0Backend:
    def __init__(
        self,
        *,
        ollama_url: str,
        llm_model: str,
        run_id: str,
        infer: bool,
        work_dir: Path,
    ) -> None:
        from mem0 import Memory

        self.infer = infer
        self.name = "mem0-agentic" if infer else "mem0-direct"
        self.user_id = f"bench-{run_id}-{self.name}"
        self.work_dir = work_dir / self.name
        if self.work_dir.exists():
            shutil.rmtree(self.work_dir)
        self.work_dir.mkdir(parents=True)

        config = build_mem0_config(
            ollama_url=ollama_url,
            llm_model=llm_model,
            run_id=run_id,
            backend_name=self.name,
            work_dir=self.work_dir,
        )
        os.environ.setdefault("MEM0_TELEMETRY", "false")
        self.memory = Memory.from_config(config)
        self.meter: MeteredOllamaClient | None = None
        if infer:
            self.meter = MeteredOllamaClient(self.memory.llm.client)
            self.memory.llm.client = self.meter

    def ingest(self, record: MemoryRecord) -> None:
        self.memory.add(
            [{"role": "user", "content": f"[{record.record_id}] {record.text}"}],
            user_id=self.user_id,
            metadata={
                "record_id": record.record_id,
                "session": record.session,
                "memory_type": record.memory_type,
            },
            infer=self.infer,
        )

    def search(self, query: str, top_k: int) -> list[SearchHit]:
        response = self.memory.search(
            query,
            top_k=top_k,
            filters={"user_id": self.user_id},
            threshold=0.0,
        )
        hits = []
        for item in response.get("results", []):
            hits.append(
                SearchHit(
                    text=item.get("memory") or item.get("text") or "",
                    score=item.get("score"),
                    metadata=item.get("metadata") or {},
                )
            )
        return hits

    def usage(self) -> dict[str, int]:
        if self.meter is None:
            return {"llm_calls": 0, "llm_input_tokens": 0, "llm_output_tokens": 0}
        return {
            "llm_calls": self.meter.calls,
            "llm_input_tokens": self.meter.input_tokens,
            "llm_output_tokens": self.meter.output_tokens,
        }

    def close(self) -> None:
        close = getattr(self.memory.vector_store.client, "close", None)
        if callable(close):
            close()


def build_mem0_config(
    *,
    ollama_url: str,
    llm_model: str,
    run_id: str,
    backend_name: str,
    work_dir: Path,
) -> dict[str, Any]:
    return {
        "version": "v1.1",
        "llm": {
            "provider": "ollama",
            "config": {
                "model": llm_model,
                "ollama_base_url": ollama_url,
                "temperature": 0.0,
                "max_tokens": 1200,
                "top_p": 0.1,
            },
        },
        "embedder": {
            "provider": "ollama",
            "config": {
                "model": "nomic-embed-text",
                "ollama_base_url": ollama_url,
                "embedding_dims": 768,
            },
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": f"temporal_{run_id}_{backend_name}",
                "path": str(work_dir / "qdrant"),
                "on_disk": True,
                "embedding_model_dims": 768,
            },
        },
        "history_db_path": str(work_dir / "history.db"),
    }


def wait_until_searchable(
    backend: MemoryBackend,
    *,
    query: str,
    expected: str,
    top_k: int,
    timeout_s: float,
) -> float:
    started = time.perf_counter()
    deadline = started + timeout_s
    expected_lower = expected.casefold()
    while time.perf_counter() < deadline:
        hits = backend.search(query, top_k)
        if expected_lower in "\n".join(hit.text for hit in hits).casefold():
            return time.perf_counter() - started
        time.sleep(1.0)
    raise TimeoutError(
        f"{backend.name} did not surface {expected!r} within {timeout_s:.0f}s"
    )


def new_run_id() -> str:
    return uuid.uuid4().hex[:10]
