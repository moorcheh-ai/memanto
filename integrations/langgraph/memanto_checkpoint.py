from pydantic import BaseModel, Field
from typing import Any, Dict, Optional

class CheckpointState(BaseModel):
    thread_id: str
    checkpoint_id: str
    checkpoint: Dict[str, Any]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    version: int = 0

class MemantoOCCError(Exception):
    """Raised when a concurrent modification is detected."""
    pass
