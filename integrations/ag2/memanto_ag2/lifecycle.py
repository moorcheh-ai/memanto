"""Bind a shared SdkClient to one Memanto agent_id (thread-safe)."""

from __future__ import annotations

import logging
import threading

from memanto.app.utils.errors import AgentAlreadyExistsError, SessionError
from memanto.cli.client.sdk_client import SdkClient

logger = logging.getLogger(__name__)


class AgentSessionBinder:
    """Create agent once and re-activate when the SDK session is bound elsewhere."""

    def __init__(
        self, client: SdkClient, agent_id: str, *, duration_hours: int = 6
    ) -> None:
        self._client = client
        self._agent_id = agent_id
        self._duration_hours = duration_hours
        self._lock = threading.Lock()
        self._agent_created = False

    def _bind_unlocked(self) -> None:
        if not self._agent_created:
            try:
                self._client.create_agent(agent_id=self._agent_id, pattern="tool")
            except AgentAlreadyExistsError:
                logger.debug(
                    "Memanto agent '%s' already exists, reusing", self._agent_id
                )
                self._agent_created = True
            except Exception:
                raise
            else:
                self._agent_created = True

        if self._client.agent_id != self._agent_id:
            self._client.activate_agent(
                self._agent_id,
                duration_hours=self._duration_hours,
            )

        if self._client.agent_id != self._agent_id:
            raise SessionError(
                f"Failed to bind SdkClient to agent '{self._agent_id}' "
                f"(active session is '{self._client.agent_id}')"
            )

    def bind(self) -> None:
        with self._lock:
            self._bind_unlocked()

    def call(self, operation):
        with self._lock:
            self._bind_unlocked()
            return operation()
