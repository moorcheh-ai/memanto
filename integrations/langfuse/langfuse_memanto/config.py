"""
Settings for the live Langfuse -> Memanto handler.

Capture rules (which signals, which thresholds, which score rules) are
deliberately *not* duplicated here: they live in
``~/.memanto/migrate/langfuse/config.json``, written by
``memanto migrate langfuse --save`` or the UI tile, and are loaded per Langfuse
project. That way an app and the CLI sync agree on what counts as a failure,
and there is one place to change it.

What belongs here is only what is specific to running inside an application:
which agent to write to, how often to flush, and how much to buffer.
"""

from __future__ import annotations

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class HandlerSettings(BaseSettings):
    """Environment-driven settings for :class:`MemantoLangfuseHandler`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    api_key: SecretStr | None = Field(
        default=None,
        validation_alias="MOORCHEH_API_KEY",
        description="Memanto/Moorcheh API key. Never logged.",
    )
    agent_id: str | None = Field(
        default=None,
        validation_alias="MEMANTO_LANGFUSE_AGENT_ID",
        description="Agent that receives the memories.",
    )
    project_key: str | None = Field(
        default=None,
        validation_alias="MEMANTO_LANGFUSE_PROJECT",
        description=(
            "Which stored capture profile to use. Defaults to the shared "
            "'default' profile; set it when one app spans several Langfuse "
            "projects."
        ),
    )
    flush_interval_seconds: float = Field(
        default=30.0,
        validation_alias="MEMANTO_LANGFUSE_FLUSH_INTERVAL",
        description="How often the background thread writes buffered signatures.",
    )
    max_buffer: int = Field(
        default=100,
        validation_alias="MEMANTO_LANGFUSE_MAX_BUFFER",
        description="Flush early once this many distinct signatures are pending.",
    )
    max_cache: int = Field(
        default=2000,
        validation_alias="MEMANTO_LANGFUSE_MAX_CACHE",
        description=(
            "Signatures remembered in-process so a retry storm writes one "
            "memory rather than thousands. Bounded so a long-running app "
            "cannot grow it without limit."
        ),
    )
    auto_create_agent: bool = Field(
        default=True,
        validation_alias="MEMANTO_LANGFUSE_AUTO_CREATE_AGENT",
        description=(
            "Create and activate the agent on first write if it does not "
            "exist, so an app needs no CLI setup. Turn off to require the "
            "agent to have been provisioned already."
        ),
    )
    session_hours: int = Field(
        default=24,
        validation_alias="MEMANTO_LANGFUSE_SESSION_HOURS",
        description="Lifetime of the agent session the handler opens.",
    )

    @field_validator("flush_interval_seconds")
    @classmethod
    def _positive_interval(cls, value: float) -> float:
        if value <= 0:
            raise ValueError(
                "MEMANTO_LANGFUSE_FLUSH_INTERVAL must be greater than 0 seconds."
            )
        return value

    @field_validator("max_buffer", "max_cache")
    @classmethod
    def _positive_size(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Buffer and cache sizes must be greater than 0.")
        return value

    def api_key_value(self) -> str | None:
        """The raw key, read only when constructing the Memanto client."""
        return self.api_key.get_secret_value() if self.api_key else None
