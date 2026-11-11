"""Configuration for the Memanto MCP server.

Loaded from environment variables (and optionally a ``.env`` file in the
working directory). Validated via pydantic-settings so misconfiguration
surfaces immediately at startup rather than on the first tool call.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TransportType(str, Enum):
    """MCP transport modes supported by this server."""

    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable-http"


# Patterns recognized by Memanto's agent service. Kept in sync with
# `memanto.app.constants.VALID_PATTERNS`.
_VALID_AGENT_PATTERNS = {"support", "project", "tool"}


class MCPServerSettings(BaseSettings):
    """Server settings loaded from env / ``.env``.

    Required:
        moorcheh_api_key: Memanto Cloud API key (``MEMANTO_API_KEY``) or
            Moorcheh API key (``MOORCHEH_API_KEY``), unless signed in to
            Memanto Cloud via ``memanto login`` (``~/.memanto``).

    Optional:
        default_agent_id: When set, callers may omit ``agent_id`` from tool
            calls and this value is used. Strongly recommended in MCP setups
            since most clients invoke a tool per turn with no shared state.
        agent_pattern: Pattern used when auto-creating the default agent
            (``support``, ``project``, or ``tool``).
        agent_auto_create: If True (default), the default agent is created
            on first use when missing.
        session_duration_hours: Override session lifetime (defaults to the
            value baked into the Memanto core config).
        expose_admin_tools: If True, register ``create_agent``, ``list_agents``,
            ``get_agent``, and ``delete_agent`` tools. Off by default to keep
            the surface focused on memory operations.
        transport / host / port: How the server is reached.
        log_level: Logging verbosity (logs go to stderr).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Memanto credentials & agent ----
    memanto_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="MEMANTO_API_KEY",
        description=(
            "Memanto Cloud API key (recommended). Create one at "
            "https://console.memanto.ai/sign-in or sign in with `memanto login`."
        ),
    )
    moorcheh_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="MOORCHEH_API_KEY",
        description=(
            "Moorcheh API key for Memanto local fallback. Create one at "
            "https://console.moorcheh.ai/api-keys."
        ),
    )
    default_agent_id: str | None = Field(
        default=None,
        validation_alias="MEMANTO_DEFAULT_AGENT_ID",
        description=(
            "Default agent used when a tool call omits agent_id. "
            "Set this to a stable per-project identifier."
        ),
    )
    default_source: str | None = Field(
        default=None,
        validation_alias="MEMANTO_DEFAULT_SOURCE",
        description=(
            "Override the source identity recorded for memories when none is explicitly provided. "
            "If unset, the server infers the source from the MCP client's handshake."
        ),
    )
    agent_pattern: str = Field(
        default="tool",
        validation_alias="MEMANTO_AGENT_PATTERN",
        description="Memanto pattern used when auto-creating the default agent.",
    )
    agent_auto_create: bool = Field(
        default=True,
        validation_alias="MEMANTO_AGENT_AUTO_CREATE",
        description="Auto-create the default agent if it does not exist.",
    )
    session_duration_hours: int | None = Field(
        default=None,
        validation_alias="MEMANTO_SESSION_DURATION_HOURS",
        ge=1,
        le=24 * 30,
        description="Override session lifetime in hours.",
    )
    expose_admin_tools: bool = Field(
        default=False,
        validation_alias="MEMANTO_EXPOSE_ADMIN",
        description="Register agent-management tools (create/list/get/delete).",
    )

    # ---- Transport ----
    transport: TransportType = Field(
        default=TransportType.STDIO,
        validation_alias="MEMANTO_MCP_TRANSPORT",
        description="MCP transport mode.",
    )
    host: str = Field(
        default="127.0.0.1",
        validation_alias="MEMANTO_MCP_HOST",
        description="Bind host for sse / streamable-http.",
    )
    port: int = Field(
        default=8765,
        ge=1,
        le=65535,
        validation_alias="MEMANTO_MCP_PORT",
        description="Bind port for sse / streamable-http.",
    )

    # ---- Logging ----
    log_level: str = Field(
        default="INFO",
        validation_alias="MEMANTO_MCP_LOG_LEVEL",
        description="Log level (DEBUG / INFO / WARNING / ERROR).",
    )

    @field_validator("agent_pattern")
    @classmethod
    def _validate_pattern(cls, v: str) -> str:
        if v not in _VALID_AGENT_PATTERNS:
            allowed = ", ".join(sorted(_VALID_AGENT_PATTERNS))
            raise ValueError(f"agent_pattern must be one of: {allowed} (got {v!r})")
        return v

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        upper = v.upper()
        if upper not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(
                "log_level must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL"
            )
        return upper

    @model_validator(mode="after")
    def _require_credentials(self) -> MCPServerSettings:
        if self.api_key_value().strip():
            return self
        try:
            from memanto.cli.config.manager import ConfigManager

            if getattr(ConfigManager().get_backend(), "value", None) == "memanto-cloud":
                return self
        except Exception:
            pass
        raise ValueError(
            "MEMANTO_API_KEY or MOORCHEH_API_KEY is required. Sign in at "
            "https://console.memanto.ai/sign-in (or https://console.moorcheh.ai/api-keys) "
            "and set it in your environment or MCP client config, or run `memanto login`."
        )

    # Convenience accessor — never logged. Prefers non-empty MEMANTO_API_KEY, then MOORCHEH_API_KEY.
    def api_key_value(self) -> str:
        if self.memanto_api_key is not None:
            val = self.memanto_api_key.get_secret_value().strip()
            if val:
                return val
        if self.moorcheh_api_key is not None:
            val = self.moorcheh_api_key.get_secret_value().strip()
            if val:
                return val
        return ""
