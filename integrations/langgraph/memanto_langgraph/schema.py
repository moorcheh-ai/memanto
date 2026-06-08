from typing import TypeVar, Generic, Dict, Any, Optional
from pydantic import BaseModel, Field

T = TypeVar("T")

class MemoryPayload(BaseModel, Generic[T]):
    """Generic wrapper for Memanto memory payloads to ensure type safety."""
    content: T
    metadata: Dict[str, Any] = Field(default_factory=dict)
    version: Optional[int] = None

class StoreNamespace(BaseModel):
    """Standardized namespace for LangGraph store keys."""
    agent_id: str
    scope: str = "global"
