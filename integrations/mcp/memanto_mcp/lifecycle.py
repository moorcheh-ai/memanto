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
from typing import TYPE_CHECKING, Any

from memanto.app.utils.errors import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    SessionError,
)
from memanto.cli.client.sdk_client import SdkClient

from memanto_mcp.cloud_client import (
     DEFAULT_PUBLIC_API_URL,
    CloudPublicApiClient,
    PublicApiUnauthorizedError,
)

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
        initial_key = settings.api_key_value()
        self._active_api_key: str = initial_key
        self._admin_client: Any = (
            self._build_backend_client(initial_key) if initial_key else None
        )
        self._session_clients: dict[str, Any] = {}
        self._agent_locks: dict[str, threading.Lock] = {}
        self._ensured_agents: set[str] = set()
        self._auto_creatable_agents: set[str] = (
            {settings.default_agent_id} if settings.default_agent_id else set()
        )
        self._lock = threading.Lock()

    def _build_backend_client(self, api_key: str) -> Any:
        """Create CloudPublicApiClient for mk_... keys (memanto-cloud), or SdkClient for legacy keys."""
        if api_key.startswith("mk_"):
            base_url = (
                getattr(self._settings, "public_api_url", None)
                or DEFAULT_PUBLIC_API_URL
            )
            return CloudPublicApiClient(api_key=api_key, base_url=base_url)
        return SdkClient(api_key=api_key)

    def _require_api_key(self) -> str:
        key = self._settings.api_key_value()
        if not key:
            raise PublicApiUnauthorizedError()
        with self._lock:
            if key != self._active_api_key:
                self._active_api_key = key
                self._admin_client = self._build_backend_client(key)
                self._session_clients.clear()
                self._agent_locks.clear()
                self._ensured_agents.clear()
        return key

    # ------------------------------------------------------------------ #
    # Public API used by tools
    # ------------------------------------------------------------------ #

    @property
    def client(self) -> Any:
        """The shared administrative client for agent CRUD operations."""
        if self._admin_client is None:
            key = self._require_api_key()
            with self._lock:
                if self._admin_client is None:
                    self._admin_client = self._build_backend_client(key)
        return self._admin_client

    @property
    def settings(self) -> MCPServerSettings:
        """The server settings driving this lifecycle."""
        return self._settings

    def resolve_agent_id(
        self,
        agent_id: str | None,
        *,
        client_agent_id: str | None = None,
    ) -> str:
        """Pick the explicit ``agent_id`` if given, else fall back to default or IDE handshake.

        Raises:
            NoAgentConfiguredError: If none was provided.
        """
        connection_default = self._settings.default_agent_id or (
            client_agent_id.strip()
            if client_agent_id and client_agent_id.strip()
            else None
        )
        if connection_default:
            with self._lock:
                if len(self._auto_creatable_agents) < self._MAX_SESSION_CLIENTS:
                    self._auto_creatable_agents.add(connection_default)

        if agent_id and agent_id.strip():
            return agent_id.strip()
        if connection_default:
            return connection_default
        raise NoAgentConfiguredError(
            "No agent_id was supplied and no MEMANTO_DEFAULT_AGENT_ID is "
            "configured. Either pass agent_id explicitly or set the env var."
        )

    def ensure_ready(self, agent_id: str) -> Any:
        """Make sure the agent exists and a session is active for it.

        Returns an agent-scoped SDK client. ``SdkClient`` stores the active
        session token on the instance, so sharing one client across multiple
        concurrent MCP tool calls can make agents overwrite each other's
        session state.
        """
        return self.client_for(agent_id)

    def client_for(self, agent_id: str) -> Any:
        """Return a ready client whose session is isolated to ``agent_id``.

        ``SdkClient`` stores the active agent as mutable instance state. Keeping
        one client per agent prevents a concurrent call for another agent from
        replacing that state between readiness checks and the actual operation.
        """
        effective_key = self._require_api_key()
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
                client = self._build_backend_client(effective_key)
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

        with self._lock:
            is_auto_creatable = (
                agent_id == self._settings.default_agent_id
                or agent_id in self._auto_creatable_agents
            )

        if not is_auto_creatable:
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
