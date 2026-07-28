"""Agent + session lifecycle management for the MCP server.

MCP tool calls are stateless from the model's perspective — the agent decides
to call ``recall`` and expects it to "just work". This module owns:

* Resolving which Memanto agent_id a given tool call targets (explicit arg
  wins; otherwise the configured default).
* Lazily creating the default agent on first use (if enabled).
* Lazily activating a session and keeping it valid across calls. The underlying
  ``SdkClient._get_validated_session_for_agent`` already auto-renews tokens
  nearing expiry, so we only have to activate once per agent.

All operations are guarded by a lock so concurrent tool invocations don't race
to create the same agent twice.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from memanto.app.utils.errors import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    SessionError,
)
from memanto.cli.client.sdk_client import SdkClient

if TYPE_CHECKING:
    from memanto_mcp.config import MCPServerSettings

logger = logging.getLogger(__name__)


class NoAgentConfiguredError(ValueError):
    """Raised when a tool call omits agent_id and no default is configured."""


class MemantoLifecycle:
    """Owns the long-lived SdkClient and per-agent session bookkeeping."""

    def __init__(self, settings: MCPServerSettings) -> None:
        """Initialize admin and per-agent client state."""
        self._settings = settings
        self._admin_client = SdkClient(api_key=settings.api_key_value())
        self._clients: dict[str, SdkClient] = {}
        self._activated_agents: set[str] = set()
        self._ensured_agents: set[str] = set()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Public API used by tools
    # ------------------------------------------------------------------ #

    @property
    def client(self) -> SdkClient:
        """An SDK client for agent administration calls."""
        return self._admin_client

    @property
    def settings(self) -> MCPServerSettings:
        """The server settings driving this lifecycle."""
        return self._settings

    def resolve_agent_id(self, agent_id: str | None) -> str:
        """Pick the explicit ``agent_id`` if given, else fall back to default.

        Raises:
            NoAgentConfiguredError: If neither was provided.
        """
        if agent_id and agent_id.strip():
            return agent_id.strip()
        if self._settings.default_agent_id:
            return self._settings.default_agent_id
        raise NoAgentConfiguredError(
            "No agent_id was supplied and no MEMANTO_DEFAULT_AGENT_ID is "
            "configured. Either pass agent_id explicitly or set the env var."
        )

    def ensure_ready(self, agent_id: str) -> SdkClient:
        """Make sure the agent exists and a session is active for it.

        Returns an agent-scoped SDK client. ``SdkClient`` stores the active
        session token on the instance, so sharing one client across multiple
        concurrent MCP tool calls can make agents overwrite each other's
        session state.
        """
        with self._lock:
            client = self._clients.get(agent_id)
            is_new_client = client is None
            if is_new_client:
                client = SdkClient(api_key=self._settings.api_key_value())

            if agent_id not in self._ensured_agents:
                self._ensure_agent_exists_locked(client, agent_id)
                self._ensured_agents.add(agent_id)

            if agent_id not in self._activated_agents or client.agent_id != agent_id:
                self._activate_locked(client, agent_id)
                self._activated_agents.add(agent_id)

            if is_new_client:
                self._clients[agent_id] = client

        return client

    def shutdown(self) -> None:
        """Best-effort cleanup. Sessions can outlive the process safely."""
        # We deliberately do NOT deactivate sessions on shutdown: they are
        # JWT-backed with a TTL and other Memanto clients (CLI, REST) may
        # still want to use them after the MCP server exits.
        logger.debug("MemantoLifecycle shutting down (no-op cleanup).")

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _ensure_agent_exists_locked(self, client: SdkClient, agent_id: str) -> None:
        """Verify an agent exists, auto-creating it when configured."""
        try:
            client.get_agent(agent_id)
            logger.debug("Agent '%s' exists.", agent_id)
            return
        except AgentNotFoundError:
            pass

        if not self._settings.agent_auto_create:
            raise AgentNotFoundError(
                f"Agent '{agent_id}' does not exist and MEMANTO_AGENT_AUTO_CREATE "
                f"is disabled. Create it first with `memanto agent create "
                f"{agent_id}` or via the create_agent tool."
            )

        logger.info(
            "Auto-creating agent '%s' with pattern '%s'.",
            agent_id,
            self._settings.agent_pattern,
        )
        try:
            client.create_agent(
                agent_id=agent_id,
                pattern=self._settings.agent_pattern,
                description="Auto-created by memanto-mcp",
            )
        except AgentAlreadyExistsError:
            # Race: another caller created it between our get_agent and create.
            logger.debug("Agent '%s' was created concurrently.", agent_id)

    def _activate_locked(self, client: SdkClient, agent_id: str) -> None:
        """Activate a Memanto session on the provided agent-scoped client."""
        try:
            client.activate_agent(
                agent_id=agent_id,
                duration_hours=self._settings.session_duration_hours,
            )
            logger.info("Activated Memanto session for agent '%s'.", agent_id)
        except Exception as exc:
            # Wrap so tools surface a uniform error type.
            raise SessionError(
                f"Failed to activate Memanto session for '{agent_id}': {exc}"
            ) from exc
