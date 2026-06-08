from typing import Generic, TypeVar, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime

T = TypeVar("T")

class MemantoMemoryItem(BaseModel, Generic[T]):
    """Type-safe container for memories stored in Memanto."""
    key: str
    value: T
    namespace: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[dict[str, Any]] = None

    def to_sdk_payload(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "content": self.value if isinstance(self.value, str) else str(self.value),
            "metadata": self.metadata or {}
        }
