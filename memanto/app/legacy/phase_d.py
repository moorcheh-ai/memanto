"""MEMANTO API Models - Phase D Specification"""

from datetime import datetime
from typing import Any, Literal, cast

from pydantic import BaseModel, Field

from memanto.app.constants import (
    ActorType,
    MemoryType,
    ProvenanceSource,
    ScopeType,
    ValidationMode,
)

# ===== COMMON TYPES =====


class Scope(BaseModel):
    """Scope definition for memory isolation"""

    scope_type: ScopeType
    scope_id: str


class Actor(BaseModel):
    """Actor information"""

    actor_id: str | None = None
    actor_type: ActorType


class Provenance(BaseModel):
    """Provenance tracking"""

    source: ProvenanceSource
    source_ref: str | None = None
    observed_at: datetime | None = None


# ===== MEMORY WRITE =====


class ValidationConfig(BaseModel):
    """Validation configuration"""

    mode: ValidationMode = "strict"
    require_provenance: bool = False


class MemoryWriteRequest(BaseModel):
    """Request to write/store a memory"""

    scope: Scope
    actor: Actor
    memory_type: MemoryType
    text: str = Field(description="Final text card OR raw content to be normalized")
    metadata: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    ttl_seconds: int | None = None
    provisional: bool = False
    validation: ValidationConfig | None = None
    idempotency_key: str | None = None


class MemoryWriteResponse(BaseModel):
    """Response from memory write operation"""

    status: Literal["queued", "success"]
    namespace: str
    memory_id: str
    stored_confidence: float
    stored_status: Literal["active", "provisional"]
    warnings: list[str] = Field(default_factory=list)


# ===== MEMORY READ =====


class ReadFilters(BaseModel):
    """Filters for memory search"""

    types: list[str] | None = None
    status: list[Literal["active", "provisional", "superseded"]] | None = Field(
        default_factory=lambda: cast(
            list[Literal["active", "provisional", "superseded"]], ["active"]
        )
    )
    min_confidence: float | None = Field(None, ge=0.0, le=1.0)
    tags: list[str] | None = None


class ReadBudget(BaseModel):
    """Budget constraints for read operations"""

    max_items: int | None = None
    max_chars: int | None = None


class ReadInclude(BaseModel):
    """What to include in response"""

    raw_text: bool = True
    metadata: bool = True
    explanation: bool = False


class MemoryReadRequest(BaseModel):
    """Request to read/search memories"""

    scope: Scope
    query: str
    k: int = Field(default=10, ge=1, le=100)
    filters: ReadFilters | None = None
    budget: ReadBudget | None = None
    include: ReadInclude | None = None


class MemoryItem(BaseModel):
    """Individual memory item in search results"""

    id: str
    text: str | None = None  # Optional if raw_text=False
    score: float | None = None  # From similarity search
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReadExplanation(BaseModel):
    """Explanation of read operation"""

    routing: dict[str, Any] | None = None
    filters_applied: dict[str, Any] | None = None


class MemoryReadResponse(BaseModel):
    """Response from memory read operation"""

    namespace: str
    query: str
    results: list[MemoryItem]
    explanation: ReadExplanation | None = None


# ===== MEMORY DELETE =====


class MemoryDeleteRequest(BaseModel):
    """Request to delete memories"""

    scope: Scope
    ids: list[str]


class MemoryDeleteResponse(BaseModel):
    """Response from memory delete operation"""

    status: Literal["success"]
    deleted_count: int


# ===== MEMORY ANSWER =====


class MemoryAnswerRequest(BaseModel):
    """Request to generate AI answer from memories"""

    scope: Scope
    question: str


class MemoryAnswerResponse(BaseModel):
    """Response from memory answer generation"""

    answer: str
    used_namespace: str
    note: str | None = None  # e.g., "may be incomplete if indexing catches up"


# ===== ADDITIONAL MODELS =====


class NamespaceResponse(BaseModel):
    """Namespace operation response"""

    namespace: str
    scope_type: str
    scope_id: str
    created: bool = True


class NamespaceListResponse(BaseModel):
    """List of namespaces response"""

    namespaces: list[str]
    total: int


class HealthResponse(BaseModel):
    """Health check response"""

    status: str
    service: str
    version: str
    moorcheh_connected: bool


class ErrorResponse(BaseModel):
    """Standardized error response"""

    error: str
    message: str
    details: dict[str, Any] | None = None
