"""Agent + session lifecycle management for the MCP server.

MCP tool calls are stateless from the model's perspective — the agent decides
to call ``recall`` and expects it to "just work". This module owns:

* Resolving which Memanto agent_id a given tool call targets (explicit arg
  wins; then the agent active on this computer, shared with the CLI, widget
  and other tools; then the configured default).
* Lazily creating the default agent on first use (if enabled).
* Lazily creating one independently activated ``SdkClient`` per agent. With
  auto-activate on, ``SdkClient._get_validated_session_for_agent`` renews and
  recreates tokens around expiry, so each client only has to be activated once.

The client registry is guarded by a short-lived global lock, while per-agent
locks serialize setup for the same agent without blocking unrelated agents on
network calls.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from memanto.app.services.session_service import get_session_service
from memanto.app.utils.errors import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    SessionError,
)
from memanto.cli.client.factory import build_client
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
        self._admin_client = self._new_client()
        self._session_clients: dict[str, SdkClient] = {}
        self._agent_locks: dict[str, threading.Lock] = {}
        self._ensured_agents: set[str] = set()
        self._lock = threading.Lock()

    def _new_client(self) -> SdkClient:
        """A client for the backend in ``~/.memanto/config.yaml`` (shared CLI factory)."""
        return build_client(moorcheh_api_key=self._settings.api_key_value() or None)

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
        """Pick the explicit ``agent_id``, else the active agent, else the default.

        The active agent is the one the CLI, widget and other tools on this
        computer share, so switching agents anywhere switches it here too.

        Raises:
            NoAgentConfiguredError: If none of the three is available.
        """
        if agent_id and agent_id.strip():
            return agent_id.strip()
        active = get_session_service().get_active_session()
        if active is not None:
            return active.agent_id
        if self._settings.default_agent_id:
            return self._settings.default_agent_id
        raise NoAgentConfiguredError(
            "No agent_id was supplied, no agent is active, and no "
            "MEMANTO_DEFAULT_AGENT_ID is configured. Pass agent_id, run "
            "`memanto agent activate <agent-id>`, or set the env var."
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
                client = self._new_client()
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

                if (
                    not self._adopt_live_session_locked(client, agent_id)
                    and client.agent_id != agent_id
                ):
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

    def _adopt_live_session_locked(self, client: SdkClient, agent_id: str) -> bool:
        """Use the agent's live session from ``~/.memanto/sessions``, if it has one.

        Memanto keeps one session per agent. Joining it instead of activating
        keeps the CLI and other tools signed in, and picking up a session
        another tool replaced (``memanto agent activate``) keeps this server
        working without a restart.
        """
        session = get_session_service().get_session(agent_id)
        if session is None or not session.is_active():
            return False
        if client.agent_id != agent_id or client.session_token != session.session_token:
            client.agent_id = agent_id
            client.session_token = session.session_token
            client._cached_session = None
            logger.info("Joined the live Memanto session for agent '%s'.", agent_id)
        return True

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
