from typing import Dict, Any
from memanto.cli.client.sdk_client import SdkClient
from integrations.langgraph.memanto_checkpointer import MemantoCheckpointer

class MemantoGraphManager:
    """
    Manager to coordinate SdkClient and MemantoCheckpointer initialization.
    """
    def __init__(self, agent_id: str, session_id: str):
        self.client = SdkClient()
        self.agent_id = agent_id
        self.session_id = session_id
        self.checkpointer = MemantoCheckpointer(
            client=self.client, 
            namespace=agent_id
        )

    def get_checkpointer(self) -> MemantoCheckpointer:
        return self.checkpointer

    def get_sdk_client(self) -> SdkClient:
        return self.client
