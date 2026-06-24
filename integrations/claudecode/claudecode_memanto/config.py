"""Environment-driven configuration for the Claude Code skills memory layer.

Kept dependency-light on purpose: the hooks run on *every* prompt and must
start fast, so we avoid pulling pydantic into the hot path and read plain
environment variables (optionally seeded from a local ``.env``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

try:  # .env support is convenient but never required.
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is an optional convenience
    pass


DEFAULT_AGENT_ID = "skills-dev-profile"
DEFAULT_RECALL_LIMIT = 8
# No floor by default: Memanto's information-theoretic retrieval already returns
# only relevant results, and its ITS scores live on a small, non-cosine scale
# (top hits are often ~0.1-0.2), so a naive 0-1 floor would discard everything.
# Advanced users can opt in via MEMANTO_MIN_SIMILARITY once they know the scale.
DEFAULT_MIN_SIMILARITY: float | None = None


class ConfigError(RuntimeError):
    """Raised when required configuration (the API key) is missing."""


@dataclass(frozen=True)
class SkillsConfig:
    """Resolved configuration for a memory-backed skill session."""

    api_key: str
    agent_id: str = DEFAULT_AGENT_ID
    recall_limit: int = DEFAULT_RECALL_LIMIT
    min_similarity: float | None = DEFAULT_MIN_SIMILARITY

    @classmethod
    def from_env(cls) -> SkillsConfig:
        """Build config from the environment.

        Raises:
            ConfigError: if ``MOORCHEH_API_KEY`` is absent. We fail loud here
                because a silent no-op would make the memory layer look broken.
        """
        api_key = (os.environ.get("MOORCHEH_API_KEY") or "").strip()
        if not api_key:
            raise ConfigError(
                "MOORCHEH_API_KEY is not set. Create a key at "
                "https://console.moorcheh.ai/api-keys and export it "
                "(or add it to a .env file in this directory)."
            )

        agent_id = (
            os.environ.get("MEMANTO_AGENT_ID") or DEFAULT_AGENT_ID
        ).strip() or DEFAULT_AGENT_ID

        recall_limit = _int_env("MEMANTO_RECALL_LIMIT", DEFAULT_RECALL_LIMIT)
        min_similarity = _float_env("MEMANTO_MIN_SIMILARITY", DEFAULT_MIN_SIMILARITY)

        return cls(
            api_key=api_key,
            agent_id=agent_id,
            recall_limit=recall_limit,
            min_similarity=min_similarity,
        )


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _float_env(name: str, default: float | None) -> float | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    # Clamp into the valid similarity range; treat <=0 as "no floor".
    if value <= 0:
        return None
    return min(value, 1.0)
