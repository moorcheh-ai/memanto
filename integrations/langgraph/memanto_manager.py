from typing import TypeVar, Generic, Optional, Dict, Any
from memanto.cli.client.sdk_client import SdkClient
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

class MemantoManager(Generic[T]):
    def __init__(self, agent_id: str, sdk_client: Optional[SdkClient] = None):
        self.agent_id = agent_id
        self.client = sdk_client or SdkClient()
        self._initialized = False

    def ensure_namespace(self) -> None:
        """Ensures the AGENT_ID namespace is established for the current session."""
        if not self._initialized:
            # Use sdk_client to verify or create the namespace
            self.client.create_namespace(self.agent_id)
            self._initialized = True

    def store_state(self, key: str, state: T) -> None:
        self.ensure_namespace()
        self.client.write_memory(
            namespace=self.agent_id,
            key=key,
            value=state.model_dump_json()
        )

    def retrieve_state(self, key: str, model: type[T]) -> Optional[T]:
        self.ensure_namespace()
        result = self.client.read_memory(namespace=self.agent_id, key=key)
        if not result:
            return None
        return model.model_validate_json(result)
