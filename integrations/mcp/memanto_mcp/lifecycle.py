"""Agent + session lifecycle management for the MCP server.

MCP tool calls are stateless from the model's perspective — the agent decides
to call ``recall`` and expects it to "just work". This module owns:

* Resolving which Memanto agent_id a given tool call targets (explicit arg
  wins; otherwise the configured default).
* Lazily creating the default agent on first use (if enabled).
* Lazily creating one independently activated ``SdkClient`` per agent. The
  underlying ``SdkClient._get_validated_session_for_agent`` already auto-renews
  tokens nearing expiry, so each client only has to be activated once.

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
    """Owns an administrative client and isolated per-agent session clients."""

    def __init__(self, settings: MCPServerSettings) -> None:
        self._settings = settings
        self._client = SdkClient(api_key=settings.api_key_value())
        self._session_clients: dict[str, SdkClient] = {}
        self._ensured_agents: set[str] = set()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Public API used by tools
    # ------------------------------------------------------------------ #

    @property
    def client(self) -> SdkClient:
        """The shared administrative client for agent CRUD operations."""
        return self._client

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

    def ensure_ready(self, agent_id: str) -> str:
        """Make sure the agent exists and a session is active for it.

        Returns the resolved agent_id (mostly a convenience so callers can
        chain ``ensure_ready(resolve_agent_id(...))``).
        """
        self.client_for(agent_id)
        return agent_id

    def client_for(self, agent_id: str) -> SdkClient:
        """Return a ready client whose session is isolated to ``agent_id``.

        ``SdkClient`` stores the active agent as mutable instance state. Keeping
        one client per agent prevents a concurrent call for another agent from
        replacing that state between readiness checks and the actual operation.
        """
        with self._lock:
            client = self._session_clients.get(agent_id)
            if client is None:
                client = SdkClient(api_key=self._settings.api_key_value())

            if agent_id not in self._ensured_agents:
                self._ensure_agent_exists_locked(client, agent_id)
                self._ensured_agents.add(agent_id)

            if client.agent_id != agent_id:
                self._activate_locked(client, agent_id)

            self._session_clients[agent_id] = client

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
