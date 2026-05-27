from enum import Enum
from typing import Annotated, List, Optional, Union
from pydantic import BaseModel, Field

class MemoryType(str, Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    EVENT = "event"
    GOAL = "goal"
    BELIEF = "belief"
    ENTITY = "entity"
    RELATIONSHIP = "relationship"
    PROCEDURAL = "procedural"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    USER_PROFILE = "user_profile"
    CONTEXT = "context"
    METADATA = "metadata"

class MemantoMemoryEntry(BaseModel):
    content: str
    memory_type: MemoryType
    agent_id: str
    timestamp: Optional[float] = None
    metadata: dict = Field(default_factory=dict)

class LangGraphMemantoState(BaseModel):
    agent_id: str
    short_term_context: List[str] = Field(default_factory=list)
    long_term_recall: List[MemantoMemoryEntry] = Field(default_factory=list)
    pending_persistence: List[MemantoMemoryEntry] = Field(default_factory=list)
