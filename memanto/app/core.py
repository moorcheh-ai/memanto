"""
MEMANTO Core Architecture - Namespace Strategy & Memory Records
"""

import re
import uuid
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from memanto.app.constants import (
    MemoryType,
    ProvenanceType,
    ScopeType,
    SourceType,
    StatusType,
)


class MemoryScope(BaseModel):
    """Defines the scope for memory isolation"""

    scope_type: ScopeType
    scope_id: str

    def to_namespace(self) -> str:
        """Convert scope to Moorcheh namespace using deterministic mapping"""
        # memanto_{scope_type}_{scope_id}
        return f"memanto_{self.scope_type}_{self.scope_id}"

    @classmethod
    def from_namespace(cls, namespace: str) -> "MemoryScope":
        """Parse namespace back to scope"""
        from typing import cast

        parts = namespace.split("_")
        if len(parts) != 3 or parts[0] != "memanto":
            raise ValueError(f"Invalid MEMANTO namespace format: {namespace}")
        return cls(scope_type=cast(ScopeType, parts[1]), scope_id=parts[2])


class MemoryRecord(BaseModel):
    """Structured memory record with standardized format"""

    # Core fields
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: MemoryType | None = None
    title: str = Field(max_length=100)
    content: str = Field(max_length=10000)

    # Metadata fields
    scope_type: ScopeType
    scope_id: str
    actor_id: str
    source: SourceType
    source_ref: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    status: StatusType = "active"
    tags: list[str] = Field(default_factory=list)

    # Provenance & Trust fields
    provenance: ProvenanceType = "explicit_statement"
    superseded_by: str | None = None  # Memory ID that supersedes this one
    supersedes: str | None = None  # Memory ID that this supersedes
    validated_at: datetime | None = None  # Last validation timestamp
    validation_count: int = 0  # Number of times validated/confirmed
    contradiction_detected: bool = False  # Flag for contradictions

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
            "scope_type": self.scope_type,
            "scope_id": self.scope_id,
            "actor_id": self.actor_id,
            "source": self.source,
            "confidence": self.confidence,
            "status": self.status,
            # Provenance & Trust fields
            "provenance": self.provenance,
            "validation_count": self.validation_count,
            "contradiction_detected": self.contradiction_detected,
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
        if self.supersedes:
            document["supersedes"] = self.supersedes
        if self.validated_at:
            document["validated_at"] = self.validated_at.isoformat()

        return document

    def get_scope(self) -> MemoryScope:
        """Get the memory scope"""
        return MemoryScope(scope_type=self.scope_type, scope_id=self.scope_id)

    def set_ttl(self, seconds: int):
        """Set TTL and expiration"""
        self.ttl_seconds = seconds
        self.expires_at = datetime.utcnow() + timedelta(seconds=seconds)

    def compute_confidence(self) -> float:
        """
        Compute confidence based on provenance, validation count, and age.

        Returns adjusted confidence score considering:
        - Provenance type (explicit > validated > observed > inferred)
        - Validation count (more validations = higher confidence)
        - Age decay for preferences (fresher = more trustworthy)
        - Contradiction detection (contradicted = low confidence)
        """
        if self.contradiction_detected:
            return max(
                0.1, self.confidence * 0.3
            )  # Contradicted memories get very low confidence

        if self.status == "superseded":
            return 0.0  # Superseded memories have zero confidence

        # Base confidence from provenance
        provenance_weights = {
            "explicit_statement": 1.0,
            "validated": 0.95,
            "observed": 0.85,
            "corrected": 0.9,
            "inferred": 0.7,
            "imported": 0.8,
        }
        base = self.confidence * provenance_weights.get(self.provenance, 0.8)

        # Validation boost (each validation adds confidence)
        validation_boost = min(0.15, self.validation_count * 0.03)

        # Age decay for preferences and observations (fresher = more trustworthy)
        if self.type in ["preference", "observation"]:
            age_days = (datetime.utcnow() - self.created_at).days
            if age_days > 90:  # 3 months
                age_penalty = 0.2
            elif age_days > 30:  # 1 month
                age_penalty = 0.1
            else:
                age_penalty = 0.0
        else:
            age_penalty = 0.0

        # Compute final confidence
        final = min(1.0, base + validation_boost - age_penalty)
        return round(final, 2)

    def validate(self):
        """Mark memory as validated (increases trust)"""
        self.validation_count += 1
        self.validated_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

        # Upgrade provenance if inferred
        if self.provenance == "inferred":
            self.provenance = "validated"

    def mark_superseded(self, superseded_by_id: str):
        """Mark this memory as superseded by a newer one"""
        self.superseded_by = superseded_by_id
        self.status = "superseded"
        self.updated_at = datetime.utcnow()

    def detect_contradiction(self):
        """Flag memory as contradicted (lowers trust)"""
        self.contradiction_detected = True
        self.updated_at = datetime.utcnow()

    def trust_score(self) -> dict[str, Any]:
        """
        Calculate comprehensive trust score with explanation.

        Returns dict with:
        - computed_confidence: float
        - provenance: str
        - validation_count: int
        - age_days: int
        - is_superseded: bool
        - contradiction_detected: bool
        - trust_level: str (high/medium/low)
        - recommendation: str
        """
        computed_conf = self.compute_confidence()
        age_days = (datetime.utcnow() - self.created_at).days

        # Determine trust level
        if computed_conf >= 0.8 and not self.contradiction_detected:
            trust_level = "high"
            recommendation = "Safe to use"
        elif computed_conf >= 0.5:
            trust_level = "medium"
            recommendation = "Use with caution"
        else:
            trust_level = "low"
            recommendation = "Verify before using"

        return {
            "computed_confidence": computed_conf,
            "original_confidence": self.confidence,
            "provenance": self.provenance,
            "validation_count": self.validation_count,
            "age_days": age_days,
            "is_superseded": self.status == "superseded",
            "contradiction_detected": self.contradiction_detected,
            "trust_level": trust_level,
            "recommendation": recommendation,
            "last_validated": self.validated_at.isoformat()
            if self.validated_at
            else None,
        }


class ValidationPolicy:
    """Memory validation policy to prevent poisoning"""

    @staticmethod
    def validate_memory(
        memory: MemoryRecord, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Validate memory before storage
        Returns: {"valid": bool, "action": str, "reason": str}
        """
        context = context or {}

        # High-confidence types require validation
        if memory.type in ["fact", "preference"]:
            return ValidationPolicy._validate_critical_memory(memory, context)

        # Other types are generally safe
        return {"valid": True, "action": "store", "reason": "Non-critical memory type"}

    @staticmethod
    def _validate_critical_memory(
        memory: MemoryRecord, context: dict[str, Any]
    ) -> dict[str, Any]:
        """Validate critical memory types (fact, preference)"""

        # Check for explicit user confirmation
        if context.get("user_confirmed"):
            return {"valid": True, "action": "store", "reason": "User confirmed"}

        # Check for repetition (same content seen before)
        if context.get("repetition_count", 0) >= 2:
            return {"valid": True, "action": "store", "reason": "Repeated content"}

        # Check for tool-grounded source
        if memory.source == "tool" and memory.source_ref:
            return {"valid": True, "action": "store", "reason": "Tool-grounded"}

        # Check for high confidence from reliable source
        if memory.confidence >= 0.9 and memory.source in ["system", "tool"]:
            return {
                "valid": True,
                "action": "store",
                "reason": "High confidence system source",
            }

        # Default: store as provisional
        return {
            "valid": True,
            "action": "store_provisional",
            "reason": "Requires validation - storing as provisional",
        }

    @staticmethod
    def make_provisional(memory: MemoryRecord) -> MemoryRecord:
        """Convert memory to provisional status with short TTL"""
        memory.status = "provisional"
        memory.confidence = min(memory.confidence, 0.5)  # Cap confidence
        memory.set_ttl(3600)  # 1 hour TTL
        return memory


# Utility functions
def create_memory_scope(scope_type: ScopeType, scope_id: str) -> MemoryScope:
    """Helper to create memory scope"""
    return MemoryScope(scope_type=scope_type, scope_id=scope_id)


def parse_namespace(namespace: str) -> MemoryScope:
    """Helper to parse namespace"""
    return MemoryScope.from_namespace(namespace)


def validate_namespace_format(namespace: str) -> bool:
    """Validate namespace follows MEMANTO convention"""
    pattern = r"^memanto_(user|workspace|agent|session)_[a-zA-Z0-9_-]+$"
    return bool(re.match(pattern, namespace))
