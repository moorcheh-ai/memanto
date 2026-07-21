class SdkClient:
    def __init__(self):
        self._active_agent: Optional[str] = None
        self._active_session: Optional[str] = None

    def activate(self, agent_id: str, session_id: str) -> None:
        """Activate the client for the specified agent and session."""
        self._active_agent = agent_id
        self._active_session = session_id

    def close(self) -> None:
        """Close the client and clean up resources."""
        self._active_agent = None
        self._active_session = None

    @property
    def active_agent(self) -> Optional[str]:
        """Get the currently active agent ID."""
        return self._active_agent

    @property
    def active_session(self) -> Optional[str]:
        """Get the currently active session ID."""
        return self._active_session