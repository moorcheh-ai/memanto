from typing import TypeVar, Generic, Optional, Any
from pydantic import BaseModel, Field

T = TypeVar("T")

class MemantoStoreItem(BaseModel, Generic[T]):
    """
    Schema for items stored in Memanto, ensuring type integrity 
    during serialization and deserialization.
    """
    value: T
    metadata: Optional[dict[str, Any]] = Field(default_factory=dict)
