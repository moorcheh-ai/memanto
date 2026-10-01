"""Optional global defaults for Memanto AG2 tools."""

from __future__ import annotations

import os
from dataclasses import dataclass

_config: MemantoAg2Config | None = None


@dataclass
class MemantoAg2Config:
    api_key: str | None = None
    source: str = "ag2-agent"
    recall_limit: int = 10


def configure(
    *,
    api_key: str | None = None,
    source: str = "ag2-agent",
    recall_limit: int = 10,
) -> None:
    """Set module-level defaults used when ``register_memanto_tools`` omits explicit values."""
    global _config
    _config = MemantoAg2Config(
        api_key=api_key,
        source=source,
        recall_limit=recall_limit,
    )


def get_config() -> MemantoAg2Config:
    if _config is not None:
        return _config
    return MemantoAg2Config(api_key=os.environ.get("MOORCHEH_API_KEY"))


def reset_config() -> None:
    global _config
    _config = None
