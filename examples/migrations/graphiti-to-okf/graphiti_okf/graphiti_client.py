"""Build a configured Graphiti client from environment variables.

Kept separate from the scripts so ``populate``, ``export`` and ``validate`` all
talk to the same graph with the same settings, and so swapping backend or LLM
provider is one env var rather than three edits.

Graphiti needs three separate model clients: an LLM for entity/edge extraction,
an embedder for vector search, and a cross-encoder for reranking. Anthropic
publishes no embeddings API, so the ``anthropic`` provider borrows an embedder
and reranker from OpenAI and says so loudly rather than failing deep inside an
ingest run.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

DEFAULT_GROUP_ID = "graphiti-okf-demo"
_DEFAULT_MODELS = {
    "openai": "gpt-4.1-mini",
    "anthropic": "claude-sonnet-4-5",
    "gemini": "gemini-2.0-flash",
}


class ConfigError(RuntimeError):
    """Raised when the environment cannot produce a usable Graphiti client."""


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(
            f"{name} is not set. Copy .env.example to .env and fill it in, "
            "then re-run. See the README 'Setup' section."
        )
    return value


def group_id() -> str:
    return os.getenv("GRAPHITI_GROUP_ID", "").strip() or DEFAULT_GROUP_ID


def backend_name() -> str:
    return os.getenv("GRAPHITI_BACKEND", "neo4j").strip().lower()


def llm_provider() -> str:
    return os.getenv("GRAPHITI_LLM_PROVIDER", "openai").strip().lower()


def build_driver() -> Any:
    """Instantiate the graph driver named by ``GRAPHITI_BACKEND``."""
    backend = backend_name()
    if backend == "neo4j":
        from graphiti_core.driver.neo4j_driver import Neo4jDriver

        return Neo4jDriver(
            uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            user=os.getenv("NEO4J_USER", "neo4j"),
            password=_require("NEO4J_PASSWORD"),
        )
    if backend == "falkordb":
        from graphiti_core.driver.falkordb_driver import FalkorDriver

        return FalkorDriver(
            host=os.getenv("FALKORDB_HOST", "localhost"),
            port=int(os.getenv("FALKORDB_PORT", "6379")),
        )
    if backend == "kuzu":
        # Deprecated upstream, but still the only zero-Docker backend Graphiti
        # ships. Prefer neo4j/falkordb when a container runtime is available.
        from graphiti_core.driver.kuzu_driver import KuzuDriver

        db_path = os.getenv("KUZU_DB_PATH", "").strip() or str(
            Path(__file__).resolve().parent.parent / "data" / "graphiti.kuzu"
        )
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        return KuzuDriver(db=db_path)
    raise ConfigError(
        f"GRAPHITI_BACKEND={backend!r} is not supported. "
        "Use 'neo4j', 'falkordb', or 'kuzu'."
    )


def build_model_clients() -> tuple[Any, Any, Any]:
    """Return ``(llm_client, embedder, cross_encoder)`` for the chosen provider."""
    from graphiti_core.llm_client.config import LLMConfig

    provider = llm_provider()
    model = os.getenv("GRAPHITI_LLM_MODEL", "").strip() or _DEFAULT_MODELS.get(provider)

    if provider == "openai":
        from graphiti_core.cross_encoder.openai_reranker_client import (
            OpenAIRerankerClient,
        )
        from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
        from graphiti_core.llm_client.openai_client import OpenAIClient

        api_key = _require("OPENAI_API_KEY")
        config = LLMConfig(api_key=api_key, model=model)
        return (
            OpenAIClient(config=config),
            OpenAIEmbedder(config=OpenAIEmbedderConfig(api_key=api_key)),
            OpenAIRerankerClient(config=config),
        )

    if provider == "gemini":
        from graphiti_core.cross_encoder.gemini_reranker_client import (
            GeminiRerankerClient,
        )
        from graphiti_core.embedder.gemini import GeminiEmbedder, GeminiEmbedderConfig
        from graphiti_core.llm_client.gemini_client import GeminiClient

        api_key = _require("GEMINI_API_KEY")
        config = LLMConfig(api_key=api_key, model=model)
        return (
            GeminiClient(config=config),
            GeminiEmbedder(config=GeminiEmbedderConfig(api_key=api_key)),
            GeminiRerankerClient(config=config),
        )

    if provider == "anthropic":
        from graphiti_core.cross_encoder.openai_reranker_client import (
            OpenAIRerankerClient,
        )
        from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
        from graphiti_core.llm_client.anthropic_client import AnthropicClient

        anthropic_key = _require("ANTHROPIC_API_KEY")
        # Anthropic has no embeddings endpoint; Graphiti cannot index without one.
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not openai_key:
            raise ConfigError(
                "GRAPHITI_LLM_PROVIDER=anthropic still needs OPENAI_API_KEY for "
                "embeddings and reranking — Anthropic publishes no embeddings API. "
                "Either set OPENAI_API_KEY as well, or use "
                "GRAPHITI_LLM_PROVIDER=openai/gemini."
            )
        return (
            AnthropicClient(config=LLMConfig(api_key=anthropic_key, model=model)),
            OpenAIEmbedder(config=OpenAIEmbedderConfig(api_key=openai_key)),
            OpenAIRerankerClient(config=LLMConfig(api_key=openai_key)),
        )

    raise ConfigError(
        f"GRAPHITI_LLM_PROVIDER={provider!r} is not supported. "
        "Use 'openai', 'anthropic' or 'gemini'."
    )


def build_graphiti() -> Any:
    """Construct a ready-to-use Graphiti instance."""
    from graphiti_core import Graphiti

    llm_client, embedder, cross_encoder = build_model_clients()
    return Graphiti(
        graph_driver=build_driver(),
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=cross_encoder,
    )


def describe_config() -> dict[str, str]:
    """Non-secret description of the active configuration, for run manifests."""
    return {
        "backend": backend_name(),
        "llm_provider": llm_provider(),
        "llm_model": os.getenv("GRAPHITI_LLM_MODEL", "").strip()
        or _DEFAULT_MODELS.get(llm_provider(), "unknown"),
        "group_id": group_id(),
    }
