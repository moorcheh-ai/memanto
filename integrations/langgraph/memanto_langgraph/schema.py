from typing import Generic, TypeVar, Any
from pydantic import BaseModel, Field

T = TypeVar("T")

class MemantoStoreConfig(BaseModel):
    api_key: str
    base_url: str
    default_namespace: str = "langgraph_default"

class MemantoMemoryItem(BaseModel, Generic[T]):
    key: str
    value: T
    namespace: str
    metadata: dict[str, Any] = Field(default_factory=dict)
