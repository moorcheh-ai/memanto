import logging
from typing import Optional

from memanto.cli.client.base import BaseClient
from memanto.services.session_service import SessionService

logger = logging.getLogger(__name__)

class DirectClient(BaseClient):
    def __init__(self, agent_id: str, config_path: str):
        super().__init__(agent_id, config_path)
        self.session_service = SessionService()

    def delete_agent(self) -> bool:
        """Delete the agent and revoke its session."""
        try:
            # Delete the agent
            success = super().delete_agent()

            if success:
                # Revoke the session
                self.session_service.delete_session(self.agent_id)
                logger.info(f"Session revoked for agent {self.agent_id}")

            return success
        except Exception as e:
            logger.error(f"Error deleting agent {self.agent_id}: {e}")
            return False