from typing import TypeVar, Generic, Annotated, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

T = TypeVar("T")

class MemoryWrapper(BaseModel, Generic[T]):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    content: T
    memory_type: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version_id: int = 1
    metadata: Dict[str, Any] = Field(default_factory=dict)

class GraphState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    agent_id: str
    thread_id: str
    messages: list = Field(default_factory=list)
    semantic_memories: list[MemoryWrapper] = Field(default_factory=list)
    iteration: int = 0
