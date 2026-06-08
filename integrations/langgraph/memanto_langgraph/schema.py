from typing import TypeVar, Generic, Optional
from pydantic import BaseModel, Field

T = TypeVar("T")

class MemantoStoreConfig(BaseModel):
    """Configuration for Memanto Store connectivity and scoping."""
    api_key: str
    base_url: str = "http://localhost:8000"
    default_namespace: str = "langgraph_default"

class MemantoMemoryItem(BaseModel, Generic[T]):
    """Type-safe wrapper for memories stored in Memanto."""
    namespace: str
    key: str
    value: T
    metadata: Optional[dict] = Field(default_factory=dict)
