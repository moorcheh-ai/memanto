from enum import Enum
from typing import Any, Dict, Optional, Union, List
from pydantic import BaseModel, Field, field_validator
from memanto.cli.client.sdk_client import SdkClient

class MemoryType(str, Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    GOAL = "goal"
    USER_PROFILE = "user_profile"
    SESSION_CONTEXT = "session_context"
    PROCEDURAL = "procedural"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    EMOTIONAL = "emotional"
    SOCIAL = "social"
    TEMPORAL = "temporal"
    CULTURAL = "cultural"
    CORE_BELIEF = "core_belief"

class MemorySchema(BaseModel):
    content: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    version: int = Field(default=1)

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))

class MemoryRegistry:
    _schemas = {mt: MemorySchema for mt in MemoryType}

    @classmethod
    def validate(cls, memory_type: str, payload: Dict[str, Any]) -> MemorySchema:
        if memory_type not in cls._schemas:
            raise ValueError(f"Unsupported memory type: {memory_type}")
        return cls._schemas[memory_type](**payload)

class MemantoMemoryManager:
    def __init__(self, agent_id: str, api_key: str):
        self.client = SdkClient(api_key=api_key)
        self.agent_id = agent_id

    def persist_state(self, memory_type: MemoryType, content: str, confidence: float = 1.0, version: int = 1, extra_meta: Optional[Dict] = None):
        payload = {
            "content": content,
            "confidence": confidence,
            "version": version,
            "metadata": extra_meta or {}
        }
        validated = MemoryRegistry.validate(memory_type.value, payload)
        return self.client.put_memory(
            agent_id=self.agent_id,
            memory_type=memory_type.value,
            content=validated.content,
            confidence=validated.confidence,
            metadata=validated.metadata
        )

    def recall_state(self, memory_type: MemoryType) -> List[Dict]:
        return self.client.get_memories(
            agent_id=self.agent_id,
            memory_type=memory_type.value
        )
