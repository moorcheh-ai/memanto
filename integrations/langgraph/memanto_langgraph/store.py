from typing import Any, Generic, TypeVar, Sequence
from pydantic import BaseModel
from langgraph.store.base import BaseStore
from memanto.cli.client.sdk_client import SdkClient

T_schema = TypeVar("T_schema", bound=BaseModel)

class MemantoStore(BaseStore, Generic[T_schema]):
    """
    Memanto implementation of LangGraph BaseStore.
    Maps LangGraph namespaces to Memanto AGENT_ID for semantic persistence.
    """
    def __init__(self, client: SdkClient, schema: type[T_schema]):
        super().__init__()
        self.client = client
        self.schema = schema

    def get(self, namespace: Sequence[str], key: str) -> T_schema | None:
        agent_id = namespace[0]
        result = self.client.get_memory(agent_id=agent_id, memory_id=key)
        if not result:
            return None
        return self.schema.model_validate(result)

    def put(self, namespace: Sequence[str], key: str, value: T_schema) -> None:
        agent_id = namespace[0]
        payload = value.model_dump()
        self.client.store_memory(agent_id=agent_id, memory_id=key, content=payload)

    def search(self, namespace: Sequence[str], query: str) -> Sequence[T_schema]:
        agent_id = namespace[0]
        results = self.client.search_memory(agent_id=agent_id, query=query)
        return [self.schema.model_validate(item) for item in results]

    def delete(self, namespace: Sequence[str], key: str) -> None:
        agent_id = namespace[0]
        self.client.delete_memory(agent_id=agent_id, memory_id=key)
