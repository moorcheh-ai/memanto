from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from core.models import MemoryEntity


@dataclass
class DataSource:
    """A generalized migration source.

    A migration does not have to come from a local file path. Sources are
    modeled as either a local file export or a live API/agent endpoint, so the
    pipeline is not hard-wired to files (this is the seam that will allow
    agent-to-agent migration in the future).
    """

    kind: str  # "file" | "api"
    path: str | None = None
    endpoint: str | None = None
    credentials: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: str) -> DataSource:
        return cls(kind="file", path=path)

    @classmethod
    def from_api(
        cls, endpoint: str, credentials: dict[str, Any] | None = None
    ) -> DataSource:
        return cls(kind="api", endpoint=endpoint, credentials=credentials or {})


@runtime_checkable
class SourceAdapter(Protocol):
    """File-export adapters (backward compatible with the original design)."""

    @property
    def name(self) -> str: ...

    def load(self, path: str) -> Any: ...

    def extract(self, raw: Any, filters: dict | None = None) -> list[MemoryEntity]: ...

    def get_conversation_list(self, raw: Any) -> list[dict]: ...

    def get_source_stats(self) -> dict: ...


@runtime_checkable
class ApiSourceAdapter(Protocol):
    """Adapters that pull from a live API/agent instead of a file.

    Credentials are injected (DI) via ``DataSource`` — adapters must NOT read
    ``os.getenv`` themselves. Implement this protocol to add agent-to-agent
    migration (e.g. opencode-like agents) without touching the pipeline.
    """

    @property
    def name(self) -> str: ...

    def load_source(self, source: DataSource) -> Any: ...

    def extract(self, raw: Any, filters: dict | None = None) -> list[MemoryEntity]: ...

    def get_conversation_list(self, raw: Any) -> list[dict]: ...

    def get_source_stats(self) -> dict: ...


ADAPTERS: dict[str, type[SourceAdapter | ApiSourceAdapter]] = {}


def register_adapter(
    cls: type[SourceAdapter | ApiSourceAdapter],
) -> type[SourceAdapter | ApiSourceAdapter]:
    ADAPTERS[str(cls.name)] = cls
    return cls


def load_source(adapter: SourceAdapter | ApiSourceAdapter, source: DataSource) -> Any:
    """Dispatch loading to a file or API adapter based on the ``DataSource``."""
    if source.kind == "file":
        if not isinstance(adapter, SourceAdapter) or not hasattr(adapter, "load"):
            raise TypeError(f"Adapter '{adapter.name}' cannot load file sources")
        return adapter.load(source.path)  # type: ignore[arg-type]
    if source.kind == "api":
        if not isinstance(adapter, ApiSourceAdapter) or not hasattr(
            adapter, "load_source"
        ):
            raise TypeError(
                f"Adapter '{adapter.name}' does not support API sources. "
                "Implement ApiSourceAdapter to enable agent-to-agent migration."
            )
        return adapter.load_source(source)
    raise ValueError(f"Unknown source kind: {source.kind!r}")
