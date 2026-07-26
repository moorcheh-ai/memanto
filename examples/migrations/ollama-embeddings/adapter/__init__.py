"""Ollama Embeddings Migration Adapter — Path B: New Migration Adapter.

This package provides the adapter, exporter, and OKF builder for migrating
memory from Ollama embeddings infrastructure into Memanto.

Modules:
    ollama_adapter — Core adapter: model discovery, verification, export,
                      mapping, OKF building, CLI entry point.
"""

from adapter.ollama_adapter import (
    DEFAULT_OLLAMA_BASE,
    build_okf_bundle,
    discover_models,
    export_ollama_memories,
    map_ollama,
    run_full_migration,
    verify_embedding_compatibility,
)

__all__ = [
    "DEFAULT_OLLAMA_BASE",
    "build_okf_bundle",
    "discover_models",
    "export_ollama_memories",
    "map_ollama",
    "run_full_migration",
    "verify_embedding_compatibility",
]
