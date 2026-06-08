from typing import Generic, TypeVar, Any, Dict, Optional
from pydantic import BaseModel, Field

T = TypeVar("T")

class MemantoMemoryItem(BaseModel, Generic[T]):
    """Type-safe container for Memanto memory entries."""
    namespace: str
    key: str
    value: T
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    version: int = 1

class MemantoStoreConfig(BaseModel):
    """Configuration for the MemantoStore provider."""
    api_key: str
    base_url: str
    default_namespace: str = "default"
