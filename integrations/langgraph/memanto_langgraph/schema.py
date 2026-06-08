from typing import Generic, TypeVar, Optional, Dict, Any
from pydantic import BaseModel, Field

T = TypeVar("T")

class MemantoMemoryItem(BaseModel, Generic[T]):
    key: str
    value: T
    namespace: str
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

class MemantoStoreConfig(BaseModel):
    api_key: str
    default_namespace: str = "default"
    base_url: Optional[str] = None
