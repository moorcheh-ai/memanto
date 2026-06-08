from typing import TypedDict, Annotated, List, Optional, Dict, Any
from pydantic import BaseModel, Field

class MemoryItem(BaseModel):
    content: str
    namespace: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    memory_id: Optional[str] = None

class MemantoState(TypedDict):
    messages: Annotated[List[Any], "The conversation history"]
    agent_id: str
    session_id: str
    context_window: List[MemoryItem]
