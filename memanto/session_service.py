from memanto.utils import validate_safe_id

class SessionService:
    # ... existing methods ...

    def delete_session(self, agent_id: str) -> None:
        """
        Delete a session by agent ID.
        
        :param agent_id: The ID of the agent whose session is to be deleted.
        """
        validate_safe_id(agent_id, "agent_id")
        # Existing session deletion logic here
        # ...