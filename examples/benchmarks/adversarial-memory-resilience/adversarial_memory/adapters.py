"""Live backend adapters with tenant-scoped benchmark state."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from pathlib import Path
from typing import Any, Protocol

from .dataset import Event, Probe


class MemoryAdapter(Protocol):
    """Minimal common contract used by the benchmark runner."""

    name: str

    def add(self, event: Event) -> None:
        """Persist one event in its tenant's isolated memory."""
        ...

    def search(self, probe: Probe, *, limit: int) -> list[str]:
        """Return ranked text for one tenant-scoped query."""
        ...

    def close(self) -> None:
        """Release resources and optionally delete benchmark state."""
        ...


def _safe_id(value: str, *, limit: int = 48) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-")
    if len(normalized) <= limit:
        return normalized
    digest = hashlib.sha256(normalized.encode()).hexdigest()[:8]
    return f"{normalized[: limit - 9]}-{digest}"


def _text(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        for key in ("content", "memory", "text", "document"):
            value = result.get(key)
            if isinstance(value, str):
                return value
    return str(result)


class MemantoAdapter:
    """Live Memanto adapter using one agent namespace per tenant."""

    name = "memanto"

    def __init__(self, *, run_id: str, tenants: tuple[str, ...], cleanup: bool) -> None:
        from moorcheh_sdk import MoorchehClient

        from memanto.cli.client.sdk_client import SdkClient

        api_key = os.environ.get("MOORCHEH_API_KEY", "")
        if not api_key:
            raise RuntimeError("MOORCHEH_API_KEY is required for Memanto")
        self._moorcheh = MoorchehClient(api_key=api_key)
        self._cleanup = cleanup
        self._clients: dict[str, Any] = {}
        self._agents: dict[str, str] = {}
        self._namespaces: dict[str, str] = {}
        try:
            for tenant in tenants:
                client = SdkClient(api_key=api_key)
                agent_id = _safe_id(f"adversarial-{run_id}-{tenant}")
                agent = client.create_agent(
                    agent_id=agent_id,
                    pattern="tool",
                    description="Adversarial incident-memory benchmark",
                )
                namespace = str(agent["namespace"])
                self._clients[tenant] = client
                self._agents[tenant] = agent_id
                self._namespaces[tenant] = namespace
                client.activate_agent(agent_id, duration_hours=4)
        except Exception:
            try:
                self.close()
            except RuntimeError:
                pass
            raise

    def add(self, event: Event) -> None:
        agent_id = self._agents[event.tenant]
        self._clients[event.tenant].remember(
            agent_id=agent_id,
            memory_type="context",
            title=f"Incident memory {event.event_id}",
            content=event.content,
            confidence=1.0,
            tags=[event.kind, f"session-{event.session}"],
            source="adversarial-benchmark",
            provenance="explicit_statement",
        )

    def search(self, probe: Probe, *, limit: int) -> list[str]:
        response = self._clients[probe.tenant].recall(
            agent_id=self._agents[probe.tenant], query=probe.query, limit=limit
        )
        return [_text(item) for item in response.get("memories", [])]

    def close(self) -> None:
        errors: list[str] = []
        for tenant, agent_id in self._agents.items():
            client = self._clients[tenant]
            try:
                client.deactivate_agent(agent_id)
            except Exception as exc:
                errors.append(f"deactivate {tenant}: {exc}")
            if self._cleanup:
                try:
                    self._moorcheh.namespaces.delete(self._namespaces[tenant])
                except Exception as exc:
                    errors.append(f"delete namespace {tenant}: {exc}")
                try:
                    client.delete_agent(agent_id)
                except Exception as exc:
                    errors.append(f"delete agent {tenant}: {exc}")
        if errors:
            raise RuntimeError("; ".join(errors))


class Mem0Adapter:
    """Local Mem0 adapter with isolated Qdrant state and no LLM inference."""

    name = "mem0"

    def __init__(self, *, run_id: str, work_dir: Path, cleanup: bool) -> None:
        from fastembed import TextEmbedding
        from fastembed.common.model_description import ModelSource, PoolingType
        from mem0 import Memory

        self._cleanup = cleanup
        self._path = work_dir / f"mem0-{_safe_id(run_id)}"
        self._path.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("MEM0_TELEMETRY", "false")
        model_cache = work_dir / "fastembed-cache"
        os.environ.setdefault("FASTEMBED_CACHE_PATH", str(model_cache))
        embedding_model = "benchmark/all-MiniLM-L6-v2"
        if not any(
            item["model"] == embedding_model
            for item in TextEmbedding.list_supported_models()
        ):
            # FastEmbed's Hugging Face path requires symlink privileges on
            # Windows. Its official mirror is portable and byte-identical.
            TextEmbedding.add_custom_model(
                model=embedding_model,
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
                description="all-MiniLM-L6-v2 from FastEmbed's official mirror",
                license="apache-2.0",
                size_in_gb=0.09,
            )
        config = {
            "history_db_path": str(self._path / "history.db"),
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
                    "embedding_dims": 384,
                },
            },
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "collection_name": _safe_id(f"adversarial_{run_id}", limit=63),
                    "path": str(self._path),
                    "embedding_model_dims": 384,
                },
            },
        }
        self._memory = Memory.from_config(config)

    def add(self, event: Event) -> None:
        self._memory.add(
            messages=event.content,
            user_id=event.tenant,
            infer=False,
            metadata={
                "event_id": event.event_id,
                "session": event.session,
                "kind": event.kind,
            },
        )

    def search(self, probe: Probe, *, limit: int) -> list[str]:
        response = self._memory.search(probe.query, user_id=probe.tenant, limit=limit)
        results = (
            response.get("results", response)
            if isinstance(response, dict)
            else response
        )
        return [_text(item) for item in results]

    def close(self) -> None:
        self._memory.close()
        if self._cleanup:
            shutil.rmtree(self._path, ignore_errors=True)


def create_adapter(
    name: str,
    *,
    run_id: str,
    tenants: tuple[str, ...],
    work_dir: Path,
    cleanup: bool,
) -> MemoryAdapter:
    """Create a configured live backend."""

    if name == "memanto":
        return MemantoAdapter(run_id=run_id, tenants=tenants, cleanup=cleanup)
    if name == "mem0":
        return Mem0Adapter(run_id=run_id, work_dir=work_dir, cleanup=cleanup)
    raise ValueError(f"unsupported backend: {name}")
