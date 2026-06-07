"""Live adapters for Memanto and Mem0."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol, TypeVar

import certifi

from .dataset import Event, Probe
from .scoring import RetrievedItem

T = TypeVar("T")
_TRANSIENT_MARKERS = (
    "connection reset",
    "network or request error",
    "remote protocol error",
    "server disconnected",
    "temporarily unavailable",
    "timed out",
    "timeout",
    "502",
    "503",
    "504",
)
_PERMANENT_MARKERS = (
    "certificate verify failed",
    "invalid api key",
    "unauthorized",
)


class MemoryAdapter(Protocol):
    """Common interface implemented by live benchmark backends."""

    name: str

    def add(self, event: Event) -> None:
        """Store one benchmark event."""
        ...

    def search(self, probe: Probe, *, limit: int) -> Sequence[RetrievedItem]:
        """Retrieve ranked context for one benchmark probe."""
        ...

    def close(self) -> None:
        """Release resources and remove isolated benchmark state."""
        ...


def _safe_id(value: str, limit: int = 48) -> str:
    """Normalize and, when needed, hash an external-resource identifier."""

    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-")
    if len(normalized) <= limit:
        return normalized
    digest = hashlib.sha256(normalized.encode()).hexdigest()[:8]
    return f"{normalized[: limit - len(digest) - 1]}-{digest}"


def _is_transient_error(exc: BaseException) -> bool:
    """Return whether an exception chain represents a retryable failure."""

    current: BaseException | None = exc
    while current is not None:
        name = current.__class__.__name__.lower()
        message = str(current).lower()
        if any(marker in name or marker in message for marker in _PERMANENT_MARKERS):
            return False
        if any(marker in name or marker in message for marker in _TRANSIENT_MARKERS):
            return True
        current = current.__cause__ or current.__context__
    return False


def _retry_transient(
    operation: Callable[[], T],
    *,
    attempts: int = 5,
    initial_delay: float = 1.0,
) -> T:
    """Retry transient failures with bounded exponential backoff."""

    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:
            if attempt == attempts or not _is_transient_error(exc):
                raise
            time.sleep(initial_delay * 2 ** (attempt - 1))
    raise AssertionError("retry loop exhausted")


def _result_text(result: Any) -> str:
    """Extract textual memory content from supported SDK result shapes."""

    if isinstance(result, str):
        return result
    if not isinstance(result, dict):
        return str(result)
    for key in ("content", "memory", "text", "document"):
        value = result.get(key)
        if isinstance(value, str) and value:
            return value
    return str(result)


def _result_score(result: Any) -> float | None:
    """Extract an optional similarity score from an SDK result."""

    if not isinstance(result, dict):
        return None
    for key in ("score", "similarity", "similarity_score"):
        value = result.get(key)
        if isinstance(value, int | float):
            return float(value)
    return None


class MemantoAdapter:
    """Live Memanto adapter backed by an isolated Moorcheh namespace."""

    name = "memanto"

    def __init__(self, *, run_id: str, cleanup: bool = True) -> None:
        """Create and activate one isolated benchmark agent."""

        os.environ.setdefault("SSL_CERT_FILE", certifi.where())

        from moorcheh_sdk import MoorchehClient

        from memanto.cli.client.sdk_client import SdkClient

        api_key = os.environ.get("MOORCHEH_API_KEY", "")
        if not api_key:
            raise RuntimeError("MOORCHEH_API_KEY is required for Memanto")
        self._client = SdkClient(api_key=api_key)
        self._moorcheh = MoorchehClient(api_key=api_key)
        self._run_id = run_id
        self._agent_id = _safe_id(f"long-horizon-{run_id}")
        self._cleanup = cleanup
        agent = self._client.create_agent(
            agent_id=self._agent_id,
            pattern="tool",
            description="Long-horizon agent memory benchmark",
        )
        self._namespace = str(agent["namespace"])
        try:
            session = self._client.activate_agent(self._agent_id, duration_hours=4)
            if session["namespace"] != self._namespace:
                raise RuntimeError("Memanto activated an unexpected namespace")
        except Exception:
            if self._cleanup:
                self._moorcheh.namespaces.delete(self._namespace)
                self._client.delete_agent(self._agent_id)
            raise

    def add(self, event: Event) -> None:
        """Store an event with a deterministic ID for retry idempotency."""

        from memanto.app.core import MemoryRecord

        digest = hashlib.sha256(f"{self._run_id}:{event.event_id}".encode()).hexdigest()
        memory = MemoryRecord(
            id=digest,
            type="context",
            title=event.title,
            content=event.content,
            scope_type="agent",
            scope_id=self._agent_id,
            actor_id=self._agent_id,
            confidence=1.0,
            tags=list(event.tags),
            source="benchmark",
            provenance="explicit_statement",
        )
        # The public remember() API does not accept caller-supplied IDs. Use the
        # write service so an ambiguous retried request cannot create duplicates.
        _retry_transient(lambda: self._client._get_write_service().store_memory(memory))

    def search(self, probe: Probe, *, limit: int) -> Sequence[RetrievedItem]:
        """Recall and normalize ranked Memanto memories."""

        response = _retry_transient(
            lambda: self._client.recall(
                agent_id=self._agent_id,
                query=probe.query,
                limit=limit,
            )
        )
        memories = response.get("memories", [])
        return [
            RetrievedItem(
                text=_result_text(memory),
                rank=index,
                score=_result_score(memory),
            )
            for index, memory in enumerate(memories, start=1)
        ]

    def close(self) -> None:
        """Deactivate the agent and remove benchmark-created state."""

        errors: list[str] = []
        try:
            self._client.deactivate_agent(self._agent_id)
        except Exception as exc:
            errors.append(f"deactivate agent: {exc}")
        if self._cleanup:
            try:
                _retry_transient(
                    lambda: self._moorcheh.namespaces.delete(self._namespace)
                )
            except Exception as exc:
                errors.append(f"delete namespace: {exc}")
            try:
                self._client.delete_agent(self._agent_id)
            except Exception as exc:
                errors.append(f"delete local agent metadata: {exc}")
        if errors:
            raise RuntimeError("; ".join(errors))


class Mem0Adapter:
    """Local Mem0 adapter using isolated Qdrant and FastEmbed state."""

    name = "mem0"

    def __init__(
        self,
        *,
        run_id: str,
        work_dir: Path,
        cleanup: bool = True,
    ) -> None:
        """Configure one isolated local Mem0 collection."""

        benchmark_work = Path(__file__).resolve().parents[1] / "work"
        os.environ.setdefault("MEM0_TELEMETRY", "false")
        os.environ.setdefault("MEM0_DIR", str(benchmark_work / "mem0-runtime"))

        from fastembed import TextEmbedding
        from fastembed.common.model_description import ModelSource, PoolingType
        from mem0 import Memory

        self._user_id = _safe_id(f"long-horizon-{run_id}")
        self._cleanup = cleanup
        self._storage_path = work_dir / f"mem0-{self._user_id}"
        self._storage_path.mkdir(parents=True, exist_ok=True)
        model_cache = benchmark_work / "fastembed-cache"
        os.environ.setdefault("FASTEMBED_CACHE_PATH", str(model_cache))
        direct_model = "benchmark/all-MiniLM-L6-v2"
        if not any(
            model["model"] == direct_model
            for model in TextEmbedding.list_supported_models()
        ):
            TextEmbedding.add_custom_model(
                model=direct_model,
                pooling=PoolingType.MEAN,
                normalization=True,
                sources=ModelSource(
                    url=(
                        "https://storage.googleapis.com/qdrant-fastembed/"
                        "sentence-transformers-all-MiniLM-L6-v2.tar.gz"
                    ),
                    _deprecated_tar_struct=True,
                ),
                dim=384,
                model_file="model.onnx",
                description=(
                    "sentence-transformers/all-MiniLM-L6-v2 via "
                    "FastEmbed's official mirror"
                ),
                license="apache-2.0",
                size_in_gb=0.09,
            )
        embedding_model = os.environ.get(
            "MEM0_EMBEDDING_MODEL",
            direct_model,
        )
        embedding_dims = int(os.environ.get("MEM0_EMBEDDING_DIMS", "384"))
        config = {
            "history_db_path": str(self._storage_path / "history.db"),
            # Mem0 constructs an LLM client even with infer=False. A sentinel
            # key keeps that unused client local and prevents credential use.
            "llm": {
                "provider": "openai",
                "config": {
                    "api_key": "unused-infer-false",
                    "model": "unused-infer-false",
                },
            },
            "embedder": {
                "provider": "fastembed",
                "config": {
                    "model": embedding_model,
                    "embedding_dims": embedding_dims,
                },
            },
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "collection_name": _safe_id(
                        f"long_horizon_{run_id}",
                        limit=63,
                    ),
                    "path": str(self._storage_path),
                    "embedding_model_dims": embedding_dims,
                },
            },
        }
        try:
            self._memory = Memory.from_config(config)
        except Exception:
            if self._cleanup:
                shutil.rmtree(self._storage_path)
            raise

    def add(self, event: Event) -> None:
        """Store an event without LLM inference."""

        self._memory.add(
            messages=event.content,
            user_id=self._user_id,
            infer=False,
            metadata={
                "event_id": event.event_id,
                "session": event.session,
                "fact_key": event.fact_key,
            },
        )

    def search(self, probe: Probe, *, limit: int) -> Sequence[RetrievedItem]:
        """Search and normalize ranked Mem0 memories."""

        response = self._memory.search(
            probe.query,
            user_id=self._user_id,
            limit=limit,
        )
        results = (
            response.get("results", response)
            if isinstance(response, dict)
            else response
        )
        return [
            RetrievedItem(
                text=_result_text(result),
                rank=index,
                score=_result_score(result),
            )
            for index, result in enumerate(results, start=1)
        ]

    def close(self) -> None:
        """Close Mem0 and remove its isolated local state."""

        self._memory.close()
        if self._cleanup:
            shutil.rmtree(self._storage_path)


def create_adapter(
    name: str,
    *,
    run_id: str,
    work_dir: Path,
    cleanup: bool,
) -> MemoryAdapter:
    """Construct the requested live backend adapter."""

    if name == "memanto":
        return MemantoAdapter(run_id=run_id, cleanup=cleanup)
    if name == "mem0":
        return Mem0Adapter(
            run_id=run_id,
            work_dir=work_dir,
            cleanup=cleanup,
        )
    raise ValueError(f"Unsupported backend: {name}")
