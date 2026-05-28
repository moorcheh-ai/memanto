"""Configuration for Claude Code + Memanto integration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class MemantoConfig:
    """Configuration for the cross-skill memory layer."""

    # Moorcheh API key (required)
    api_key: str = field(default_factory=lambda: os.environ.get("MOORCHEH_API_KEY", ""))

    # Agent ID for memory namespace isolation
    agent_id: str = field(
        default_factory=lambda: os.environ.get("MEMANTO_AGENT_ID", "claudecode-default")
    )

    # Minimum confidence threshold for memory injection
    min_confidence: float = 0.6

    # Maximum number of memories to inject per skill
    max_inject_memories: int = 10

    # Memory types to capture
    capture_types: list[str] = field(
        default_factory=lambda: ["decision", "preference", "fact", "pattern"]
    )

    # Skills to exclude from memory capture
    exclude_skills: list[str] = field(default_factory=list)

    def validate(self) -> None:
        """Validate configuration."""
        if not self.api_key:
            raise ValueError(
                "MOORCHEH_API_KEY is required. Get one at https://console.moorcheh.ai/api-keys"
            )
