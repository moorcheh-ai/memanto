"""Agent + session lifecycle management for the MCP server.

MCP tool calls are stateless from the model's perspective — the agent decides
to call ``recall`` and expects it to "just work". This module owns:

* Resolving which Memanto agent_id a given tool call targets (explicit arg
  wins; otherwise the configured default).
* Lazily creating the default agent on first use (if enabled).
* Lazily creating one independently activated ``SdkClient`` per agent. The
  underlying ``SdkClient._get_validated_session_for_agent`` already auto-renews
  tokens nearing expiry, so each client only has to be activated once.

The client registry is guarded by a short-lived global lock, while per-agent
locks serialize setup for the same agent without blocking unrelated agents on
network calls.
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

# A long-running MCP server may receive caller-controlled agent IDs. Keep the
# registry bounded rather than retaining a new SDK client and lock forever for
# every unique value. Existing entries are never evicted because callers keep
# using the returned clients after ``client_for`` releases its setup lock.
MAX_SESSION_CLIENTS = 128


class NoAgentConfiguredError(ValueError):
    """Raised when a tool call omits agent_id and no default is configured."""


class MemantoLifecycle:
    """Owns an administrative client and isolated per-agent session clients."""

    _MAX_SESSION_CLIENTS = MAX_SESSION_CLIENTS

    def __init__(self, settings: MCPServerSettings) -> None:
        """Initialize administrative and per-agent client state."""

        self._settings = settings
        self._admin_client = SdkClient(api_key=settings.api_key_value())
        self._session_clients: dict[str, SdkClient] = {}
        self._agent_locks: dict[str, threading.Lock] = {}
        self._ensured_agents: set[str] = set()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Public API used by tools
    # ------------------------------------------------------------------ #

    @property
    def client(self) -> SdkClient:
        """The shared administrative client for agent CRUD operations."""
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
        return self.client_for(agent_id)

    def client_for(self, agent_id: str) -> SdkClient:
        """Return a ready client whose session is isolated to ``agent_id``.

        ``SdkClient`` stores the active agent as mutable instance state. Keeping
        one client per agent prevents a concurrent call for another agent from
        replacing that state between readiness checks and the actual operation.
        """
        with self._lock:
            client = self._session_clients.get(agent_id)
            is_new_client = client is None
            if client is None:
                if len(self._session_clients) >= self._MAX_SESSION_CLIENTS:
                    raise SessionError(
                        "Memanto MCP session-client capacity reached "
                        f"({self._MAX_SESSION_CLIENTS}); reuse an existing agent_id "
                        "or restart the server to clear idle session clients."
                    )
                client = SdkClient(api_key=self._settings.api_key_value())
                self._session_clients[agent_id] = client
                self._agent_locks[agent_id] = threading.Lock()
            agent_lock = self._agent_locks[agent_id]

        with agent_lock:
            try:
                with self._lock:
                    agent_is_ensured = agent_id in self._ensured_agents

                if not agent_is_ensured:
                    self._ensure_agent_exists_locked(client, agent_id)
                    with self._lock:
                        self._ensured_agents.add(agent_id)

                if client.agent_id != agent_id:
                    self._activate_locked(client, agent_id)
            except Exception:
                if is_new_client:
                    with self._lock:
                        if self._session_clients.get(agent_id) is client:
                            self._session_clients.pop(agent_id, None)
                            self._agent_locks.pop(agent_id, None)
                raise

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

        if agent_id != self._settings.default_agent_id:
            raise AgentNotFoundError(
                f"Agent '{agent_id}' does not exist. Only the configured default agent "
                "may be auto-created; create other agents explicitly with "
                f"`memanto agent create {agent_id}` or the gated create_agent tool."
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
