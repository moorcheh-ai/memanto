import logging
from typing import Optional

from memanto.db.session import SessionDB

logger = logging.getLogger(__name__)

class SessionService:
    def __init__(self):
        self.session_db = SessionDB()

    def delete_session(self, agent_id: str) -> bool:
        """Delete the session for the given agent and revoke it."""
        try:
            # Delete the session record
            success = self.session_db.delete_session(agent_id)

            if success:
                logger.info(f"Session deleted for agent {agent_id}")

            return success
        except Exception as e:
            logger.error(f"Error deleting session for agent {agent_id}: {e}")
            return False