from typing import List
from memanto.cli.client.sdk_client import SdkClient
from integrations.langgraph.schema import LangGraphMemantoState, MemantoMemoryEntry

class MemantoCoordinator:
    def __init__(self, sdk_client: SdkClient):
        self.sdk = sdk_client

    def synchronize_memory(self, state: LangGraphMemantoState, query: str) -> LangGraphMemantoState:
        # Recall phase
        memories = self.sdk.recall(
            agent_id=state.agent_id, 
            query=query
        )
        
        state.long_term_recall = [
            MemantoMemoryEntry(
                content=m.get("content", ""),
                memory_type=m.get("type", "fact"),
                agent_id=state.agent_id,
                metadata=m.get("metadata", {})
            ) for m in memories
        ]
        return state

    def commit_persistence(self, state: LangGraphMemantoState) -> LangGraphMemantoState:
        for entry in state.pending_persistence:
            self.sdk.persist(
                agent_id=entry.agent_id,
                content=entry.content,
                memory_type=entry.memory_type,
                metadata=entry.metadata
            )
        state.pending_persistence = []
        return state
