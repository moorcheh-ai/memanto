"""
MEMANTO Core Architecture - Namespace Strategy & Memory Records
"""

import uuid
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from memanto.app.constants import (
    MemoryType,
    ProvenanceType,
    SourceType,
    StatusType,
)


def agent_namespace(agent_id: str) -> str:
    """Map an agent_id to its Moorcheh namespace: memanto_agent_{agent_id}."""
    return f"memanto_agent_{agent_id}"


class MemoryRecord(BaseModel):
    """Structured memory record with standardized format"""

    # Core fields
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: MemoryType | None = None
    title: str = Field(max_length=100)
    content: str = Field(max_length=10000)

    # Metadata fields
    agent_id: str
    actor_id: str
    source: SourceType
    source_ref: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    status: StatusType = "active"
    tags: list[str] = Field(default_factory=list)

    # Provenance
    provenance: ProvenanceType = "explicit_statement"

    # Set when this memory has been superseded by a newer, conflicting one.
    superseded_by: str | None = None

    # Timestamps (auto-populated by server)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None
    ttl_seconds: int | None = None

    def to_moorcheh_document(self) -> dict[str, Any]:
        """
        Convert to Moorcheh document format with flat metadata fields.

        Moorcheh stores metadata as flat fields on the document, which enables
        powerful filtering using the # syntax (e.g., #memory_type:fact #confidence>0.8)
        """
        memory_type = self.type or "fact"

        # Format text as standardized card for semantic search
        text = f"[{memory_type.upper()}] {self.title}\n\n{self.content}"
        if self.tags:
            text += f"\n\nTags: {', '.join(self.tags)}"

        # Build document with flat metadata fields (not nested!)
        document = {
            "id": self.id,
            "text": text,
            # Metadata fields (flat structure for Moorcheh filtering)
            "memory_type": memory_type,
            "agent_id": self.agent_id,
            "actor_id": self.actor_id,
            "source": self.source,
            "confidence": self.confidence,
            "status": self.status,
            # Provenance
            "provenance": self.provenance,
            # Timestamps
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

        # Add optional fields only if present
        if self.source_ref:
            document["source_ref"] = self.source_ref
        if self.tags:
            document["tags"] = ",".join(self.tags)  # Comma-separated for filtering
        if self.expires_at:
            document["expires_at"] = self.expires_at.isoformat()
        if self.ttl_seconds:
            document["ttl_seconds"] = self.ttl_seconds
        if self.superseded_by:
            document["superseded_by"] = self.superseded_by

        return document

    def namespace(self) -> str:
        """The Moorcheh namespace this memory belongs to."""
        return agent_namespace(self.agent_id)

    def set_ttl(self, seconds: int):
        """Set TTL and expiration"""
        self.ttl_seconds = seconds
        self.expires_at = datetime.utcnow() + timedelta(seconds=seconds)


class ValidationPolicy:
    """
    Decides what happens to a new memory before it's persisted.

    Memory types listed in settings.REQUIRE_VALIDATION_FOR ("fact",
    "preference" by default) are treated as consequential enough that
    they shouldn't be trusted at full confidence on a single, unconfirmed
    mention. Everything else is stored as-is. This intentionally stays
    simple (no LLM call) so it doesn't add latency/cost to every write.
    """

    def validate_memory(self, memory: "MemoryRecord", context: dict[str, Any]) -> dict[str, Any]:
        from memanto.app.config import settings

        if memory.type not in settings.REQUIRE_VALIDATION_FOR:
            return {"action": "store", "reason": "Non-critical memory type; stored directly"}

        repetition_count = context.get("repetition_count", 0)
        trusted_source = memory.source in {"tool", "system"} and memory.confidence >= 0.85
        corroborated = repetition_count >= 2 or memory.provenance in {"validated", "corrected"}

        if trusted_source or corroborated:
            return {
                "action": "store",
                "reason": (
                    f"Critical memory type '{memory.type}' met validation "
                    f"requirements (repetition={repetition_count}, source={memory.source})"
                ),
            }

        return {
            "action": "store_provisional",
            "reason": (
                f"Critical memory type '{memory.type}' has not been corroborated "
                "(no repeated mention, not from a trusted source) - stored provisionally"
            ),
        }

    def make_provisional(self, memory: "MemoryRecord") -> "MemoryRecord":
        from memanto.app.config import settings

        memory.status = "provisional"
        memory.confidence = min(memory.confidence, settings.PROVISIONAL_MAX_CONFIDENCE)
        memory.set_ttl(settings.PROVISIONAL_TTL_SECONDS)
        return memory
