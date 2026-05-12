"""Memanto client lifecycle manager for LangGraph."""

from __future__ import annotations

import logging

from memanto.cli.client.sdk_client import SdkClient

logger = logging.getLogger(__name__)


class MemantoSetup:
    """Manages Memanto agent lifecycle for LangGraph integration."""

    def __init__(self, api_key: str) -> None:
        self._client = SdkClient(api_key=api_key)

    @property
    def client(self) -> SdkClient:
        return self._client

    def setup(
        self,
        agent_id: str,
        pattern: str = "tool",
        description: str | None = None,
        duration_hours: int = 6,
    ) -> SdkClient:
        """Create agent (if needed) and activate a session."""
        try:
            self._client.create_agent(
                agent_id=agent_id,
                pattern=pattern,
                description=description,
            )
            logger.info("Created Memanto agent '%s'", agent_id)
        except Exception:
            logger.info("Memanto agent '%s' already exists, reusing", agent_id)

        self._client.activate_agent(agent_id, duration_hours=duration_hours)
        logger.info("Activated session for agent '%s'", agent_id)
        return self._client

    def teardown(self, agent_id: str) -> None:
        """Deactivate the agent session."""
        try:
            self._client.deactivate_agent(agent_id)
            logger.info("Deactivated session for agent '%s'", agent_id)
        except Exception as e:
            logger.warning("Failed to deactivate agent '%s': %s", agent_id, e)
