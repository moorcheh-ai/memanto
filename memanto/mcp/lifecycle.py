from typing import Dict, Optional
from memanto.sdk.client import SdkClient

class McpLifecycle:
    def __init__(self):
        self._admin_client = SdkClient()
        self._agent_clients: Dict[str, SdkClient] = {}

    def client_for(self, agent_id: str) -> SdkClient:
        """Get or create a client scoped to the specified agent."""
        if agent_id not in self._agent_clients:
            self._agent_clients[agent_id] = SdkClient()
        return self._agent_clients[agent_id]

    @property
    def client(self) -> SdkClient:
        """Get the administrative client for agent management."""
        return self._admin_client

    def cleanup(self):
        """Clean up all agent-scoped clients."""
        for client in self._agent_clients.values():
            client.close()
        self._agent_clients.clear()