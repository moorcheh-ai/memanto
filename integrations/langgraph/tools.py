from typing import Annotated
from langchain.tools import tool
from memanto.cli.client.sdk_client import SdkClient
from integrations.langgraph.schema import MemoryType

def create_memanto_tools(sdk_client: SdkClient, agent_id: str):
    @tool
    def store_memory(
        content: Annotated[str, "The specific piece of information to remember"],
        memory_type: Annotated[MemoryType, "The category of memory (e.g., preference, fact)"]
    ):
        """Persists information to the long-term brain."""
        return sdk_client.persist(
            agent_id=agent_id,
            content=content,
            memory_type=memory_type.value
        )

    @tool
    def retrieve_memory(
        query: Annotated[str, "The search query to recall previous interactions"]
    ):
        """Recalls associative memories from the long-term brain."""
        return sdk_client.recall(
            agent_id=agent_id,
            query=query
        )

    return [store_memory, retrieve_memory]
