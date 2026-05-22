"""
MEMANTO API Models
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from memanto.app.constants import MemoryType, ScopeType, SourceType, StatusType


# Request Models
class MemoryStoreRequest(BaseModel):
    """Request body for storing a single memory."""

    type: MemoryType
    title: str = Field(max_length=100)
    content: str = Field(max_length=10000)
    scope_type: ScopeType
    scope_id: str
    actor_id: str
    source: SourceType
    source_ref: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    tags: list[str] = Field(default_factory=list)
    ttl_seconds: int | None = None
    user_confirmed: bool = False


class MemoryBatchItem(BaseModel):
    """Single memory item for batch write"""

    type: MemoryType
    title: str = Field(max_length=100)
    content: str = Field(max_length=10000)
    source: SourceType
    source_ref: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    tags: list[str] = Field(default_factory=list)
    ttl_seconds: int | None = None
    id: str | None = None  # Optional custom ID


class MemoryBatchWriteRequest(BaseModel):
    """Request to write multiple memories in batch"""

    memories: list[MemoryBatchItem] = Field(
        ..., min_length=1, max_length=100, description="1-100 memories per batch"
    )
    scope_type: ScopeType
    scope_id: str
    actor_id: str
    user_confirmed: bool = False


class BatchRememberItem(BaseModel):
    """Single memory item in a batch-remember request"""

    content: str = Field(..., max_length=10000, description="Memory content")
    type: MemoryType | None = Field(
        None,
        description="Memory type. Omit to auto-parse.",
    )
    title: str | None = Field(
        None, max_length=100, description="Memory title (defaults to truncated content)"
    )
    confidence: float = Field(0.8, ge=0.0, le=1.0, description="Confidence score (0-1)")
    tags: list[str] | None = Field(None, description="Tags for this memory")
    source: str = Field("agent", description="Source of memory")
    provenance: str = Field(
        "explicit_statement",
        description="How memory was obtained (explicit_statement, inferred, observed, etc.)",
    )


class RememberRequest(BatchRememberItem):
    """Request body for remember endpoint"""


class BatchRememberRequest(BaseModel):
    """Request body for batch-remember endpoint"""

    memories: list[BatchRememberItem] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of memories to store (max 100)",
    )


class SupersedeRequest(BaseModel):
    """Request body for supersede endpoint"""

    new_memory_id: str = Field(
        ..., description="ID of new memory that supersedes the old one"
    )


class ConflictResolveRequest(BaseModel):
    """Request body for resolving a conflict"""

    conflict_index: int = Field(..., ge=0, description="Conflict index to resolve")
    action: str = Field(
        ...,
        description="Resolution action: keep_old, keep_new, keep_both, remove_both, manual",
    )
    date: str | None = Field(
        None, description="Conflict report date (YYYY-MM-DD). Defaults to today."
    )
    manual_content: str | None = Field(
        None, description="Required when action is 'manual'"
    )
    manual_type: str | None = Field(
        None, description="Optional memory type for manual action"
    )


class AnswerRequest(BaseModel):
    """Request body for answer endpoint"""

    question: str = Field(..., description="Question to ask")
    limit: int | None = Field(
        None, ge=1, le=100, description="Number of context memories to use"
    )
    threshold: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Confidence threshold (used only in kiosk mode)",
    )
    temperature: float | None = Field(
        None, ge=0.0, le=2.0, description="Temperature for the LLM response"
    )
    ai_model: str | None = Field(
        None, description="AI model to use for generating the answer"
    )
    kiosk_mode: bool = Field(False, description="Kiosk mode setting")


class MemoryUpdateRequest(BaseModel):
    """Request to update an existing memory"""

    namespace: str = Field(..., description="Namespace containing the memory")
    updates: dict[str, Any] = Field(
        ..., description="Fields to update (title, content, confidence, tags, etc.)"
    )
    user_confirmed: bool = False


class MemorySearchRequest(BaseModel):
    query: str
    scope_type: ScopeType | None = None
    scope_id: str | None = None
    memory_types: list[MemoryType] | None = None
    tags: list[str] | None = None
    limit: int = Field(default=10, ge=1, le=100)


class ScopeDefinition(BaseModel):
    """Individual scope for multi-scope search"""

    scope_type: ScopeType
    scope_id: str


class MemoryMultiScopeSearchRequest(BaseModel):
    """Request to search across multiple scopes simultaneously"""

    query: str
    scopes: list[ScopeDefinition] = Field(
        ..., min_length=1, max_length=10, description="1-10 scopes to search across"
    )
    memory_types: list[MemoryType] | None = None
    tags: list[str] | None = None
    min_confidence: float | None = Field(None, ge=0.0, le=1.0)
    status_filter: list[str] | None = None
    min_similarity_score: float | None = Field(
        None, ge=0.0, le=1.0, description="Minimum similarity score threshold"
    )
    limit: int = Field(default=10, ge=1, le=100)


class MemoryAnswerRequest(BaseModel):
    query: str
    scope_type: ScopeType | None = None
    scope_id: str | None = None


class NamespaceCreateRequest(BaseModel):
    scope_type: ScopeType
    scope_id: str


class ContextSummarizationRequest(BaseModel):
    """Request to summarize context in a scope"""

    scope_type: ScopeType
    scope_id: str
    actor_id: str
    summary_title: str = Field(default="Context Summary", max_length=100)
    memory_types: list[MemoryType] | None = None
    max_memories: int = Field(default=50, ge=1, le=100)
    link_to_originals: bool = True


class CustomSummarizationRequest(BaseModel):
    """Request to summarize specific memories by ID"""

    memory_ids: list[str] = Field(..., min_length=1, max_length=100)
    namespace: str
    scope_type: ScopeType
    scope_id: str
    actor_id: str
    summary_title: str = Field(default="Custom Summary", max_length=100)


class ConversationCompressionRequest(BaseModel):
    """Request to compress old conversation history"""

    scope_type: ScopeType
    scope_id: str
    actor_id: str
    days_to_compress: int = Field(default=7, ge=1, le=365)
    keep_recent_count: int = Field(default=10, ge=0, le=50)


# Response Models
class MemoryResponse(BaseModel):
    """Memory record returned by the API."""

    id: str
    type: MemoryType
    title: str
    content: str
    scope_type: ScopeType
    scope_id: str
    actor_id: str
    source: SourceType
    source_ref: str | None
    confidence: float
    status: StatusType
    tags: list[str]
    created_at: datetime
    updated_at: datetime | None
    expires_at: datetime | None


class MemoryStoreResponse(BaseModel):
    id: str
    status: str
    action: str
    reason: str
    namespace: str


class MemoryBatchWriteResult(BaseModel):
    """Result for a single memory in batch operation"""

    id: str
    status: str
    action: str
    reason: str | None = None
    error: str | None = None


class MemoryBatchWriteResponse(BaseModel):
    """Response from batch write operation"""

    total_submitted: int
    successful: int
    failed: int
    namespace: str
    results: list[MemoryBatchWriteResult]


class MemoryUpdateResponse(BaseModel):
    """Response from memory update operation"""

    id: str
    namespace: str
    status: str
    action: str
    reason: str
    updated_fields: list[str]


class MemorySearchResponse(BaseModel):
    results: list[dict[str, Any]]
    total_found: int
    query: str
    execution_time: float


class MemoryAnswerResponse(BaseModel):
    answer: str
    sources: list[str]
    confidence: float
    namespace: str


class NamespaceResponse(BaseModel):
    """Response returned after creating or fetching a namespace."""

    namespace: str
    scope_type: ScopeType
    scope_id: str
    created: bool


class NamespaceListResponse(BaseModel):
    namespaces: list[str]
    total: int


class SummarizationResponse(BaseModel):
    """Response from context summarization"""

    summary_id: str
    namespace: str
    status: str
    summarized_count: int
    original_memory_ids: list[str]
    summary_preview: str


class CompressionResponse(BaseModel):
    """Response from conversation compression"""

    compressed: bool
    reason: str | None = None
    summary_id: str | None = None
    compressed_count: int | None = None
    compression_date: str | None = None
    original_memory_ids: list[str] | None = None


class ErrorResponse(BaseModel):
    """Error response returned by API endpoints."""

    error: str
    message: str
    details: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    moorcheh_connected: bool
