"""
MemantoSetup — Manages Memanto agent lifecycle for LangGraph integration.

Handles agent creation, session activation, and teardown so that
LangGraph scripts can focus on workflow orchestration.
"""

from __future__ import annotations

import logging
from typing import Any

from memanto.app.utils.errors import AgentAlreadyExistsError
from memanto.cli.client.sdk_client import SdkClient

logger = logging.getLogger(__name__)


class MemantoSetup:
    """
    Manages Memanto agent lifecycle for LangGraph integration.

    Usage::

        setup = MemantoSetup(api_key="moorcheh-...")
        client = setup.setup(agent_id="support-agent", pattern="support")
        # ... use client for remember/recall/answer ...
        setup.teardown(agent_id="support-agent")
    """

    def __init__(self, api_key: str) -> None:
        self.client = SdkClient(api_key=api_key)

    def setup(
        self,
        agent_id: str,
        pattern: str = "support",
        description: str | None = None,
        duration_hours: int = 6,
    ) -> SdkClient:
        """
        Create agent (if needed) and activate a session.

        Args:
            agent_id: Unique identifier for the agent.
            pattern: Agent pattern — ``"support"``, ``"project"``, or ``"tool"``.
            description: Optional human-readable description.
            duration_hours: Session lifetime in hours.

        Returns:
            The active SdkClient with a valid session.
        """
        try:
            self.client.create_agent(
                agent_id=agent_id,
                pattern=pattern,
                description=description,
            )
            logger.info("Created Memanto agent '%s'", agent_id)
        except AgentAlreadyExistsError:
            logger.info("Memanto agent '%s' already exists, reusing", agent_id)
        except Exception as e:
            logger.error("Failed to create agent '%s': %s", agent_id, e)
            raise

        self.client.activate_agent(agent_id, duration_hours=duration_hours)
        logger.info("Activated session for agent '%s'", agent_id)
        return self.client

    def teardown(self, agent_id: str) -> None:
        """Deactivate the agent session."""
        try:
            self.client.deactivate_agent(agent_id)
            logger.info("Deactivated session for agent '%s'", agent_id)
        except Exception as e:
            logger.warning("Failed to deactivate agent '%s': %s", agent_id, e)
