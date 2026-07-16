"""
MEMANTO API Models
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from memanto.app.constants import (
    VALID_PROVENANCE_TYPES,
    MemoryType,
    SourceType,
    StatusType,
)


def _validate_non_blank_content(value: str) -> str:
    """Reject whitespace-only memory content before it reaches storage."""
    if not value.strip():
        raise ValueError("Memory content must be a non-empty string")
    return value


# Request Models
class MemoryStoreRequest(BaseModel):
    """Request body for storing a single memory."""

    type: MemoryType
    title: str = Field(max_length=100)
    content: str = Field(max_length=10000)
    agent_id: str
    actor_id: str
    source: SourceType
    source_ref: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    tags: list[str] = Field(default_factory=list)
    ttl_seconds: int | None = None
    user_confirmed: bool = False

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        """Ensure stored memories contain useful non-blank content."""
        return _validate_non_blank_content(value)


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

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        """Ensure batch memory items contain useful non-blank content."""
        return _validate_non_blank_content(value)


class MemoryBatchWriteRequest(BaseModel):
    """Request to write multiple memories in batch"""

    memories: list[MemoryBatchItem] = Field(
        ..., min_length=1, max_length=100, description="1-100 memories per batch"
    )
    agent_id: str
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

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        """Ensure session memory writes contain useful non-blank content."""
        return _validate_non_blank_content(value)

    @field_validator("provenance")
    @classmethod
    def provenance_must_be_valid(cls, value: str) -> str:
        if value not in VALID_PROVENANCE_TYPES:
            valid_provenance = ", ".join(sorted(VALID_PROVENANCE_TYPES))
            raise ValueError(
                f"Invalid provenance '{value}'. Must be one of: {valid_provenance}."
            )
        return value


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


class ConversationMessage(BaseModel):
    """Chat-style message used for conversation memory extraction."""

    role: str = Field(..., min_length=1, max_length=50)
    content: str = Field(..., min_length=1, max_length=10000)

    @field_validator("role")
    @classmethod
    def role_must_not_be_blank(cls, value: str) -> str:
        """Reject message roles that contain only whitespace."""
        if not value.strip():
            raise ValueError("role must be a non-empty string")
        return value

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        """Reject message content that contains only whitespace."""
        if not value.strip():
            raise ValueError("content must be a non-empty string")
        return value


class ExtractMemoriesRequest(BaseModel):
    """Request body for extracting typed memories from conversation turns."""

    messages: list[ConversationMessage] = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Conversation turns to extract durable memories from",
    )
    dry_run: bool = Field(
        False,
        description="When true, return candidates without storing them",
    )
    max_memories: int = Field(
        20,
        ge=1,
        le=100,
        description="Maximum candidate memories to extract",
    )
    ai_model: str | None = Field(
        None,
        description="Optional model override for extraction",
    )


class ConflictResolveRequest(BaseModel):
    """Request body for resolving a conflict"""

    conflict_index: int = Field(..., ge=0, description="Conflict index to resolve")
    action: Literal["keep_old", "keep_new", "keep_both", "remove_both", "manual"] = (
        Field(
            ...,
            description=(
                "Resolution action: keep_old, keep_new, keep_both, remove_both, manual"
            ),
        )
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

    @model_validator(mode="after")
    def validate_manual_resolution(self) -> "ConflictResolveRequest":
        if self.action == "manual" and not (
            self.manual_content and self.manual_content.strip()
        ):
            raise ValueError("manual_content is required when action is 'manual'")
        return self


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

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        """Reject questions that contain only whitespace."""
        if not value.strip():
            raise ValueError("question must be a non-empty string")
        return value


class MemoryUpdateRequest(BaseModel):
    """Request to update an existing memory"""

    namespace: str = Field(..., description="Namespace containing the memory")
    updates: dict[str, Any] = Field(
        ..., description="Fields to update (title, content, confidence, tags, etc.)"
    )
    user_confirmed: bool = False


class MemorySearchRequest(BaseModel):
    query: str
    agent_id: str | None = None
    memory_types: list[MemoryType] | None = None
    tags: list[str] | None = None
    limit: int = Field(default=10, ge=1, le=100)


class MemoryAnswerRequest(BaseModel):
    query: str
    agent_id: str | None = None


class ContextSummarizationRequest(BaseModel):
    """Request to summarize context in a scope"""

    agent_id: str
    actor_id: str
    summary_title: str = Field(default="Context Summary", max_length=100)
    memory_types: list[MemoryType] | None = None
    max_memories: int = Field(default=50, ge=1, le=100)
    link_to_originals: bool = True


class CustomSummarizationRequest(BaseModel):
    """Request to summarize specific memories by ID"""

    memory_ids: list[str] = Field(..., min_length=1, max_length=100)
    namespace: str
    agent_id: str
    actor_id: str
    summary_title: str = Field(default="Custom Summary", max_length=100)


class ConversationCompressionRequest(BaseModel):
    """Request to compress old conversation history"""

    agent_id: str
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
    agent_id: str
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


# Session-based v2 endpoint responses (typed for OpenAPI codegen)


class MemoryItem(BaseModel):
    """Single memory record as returned by recall/answer endpoints."""

    id: str | None = None
    title: str = ""
    content: str = ""
    text: str = ""
    type: str | None = None
    confidence: float | None = None
    status: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None
    expires_at: str | None = None
    ttl_seconds: int | None = None
    actor_id: str | None = None
    source: str | None = None
    agent_id: str | None = None
    score: float | None = None
    provenance: str = "explicit_statement"
    change_type: str | None = None


class RememberResponse(BaseModel):
    memory_id: str
    agent_id: str
    session_id: str
    namespace: str
    status: str
    provenance: str
    confidence: float
    type: str | None = None


class BatchRememberResultItem(BaseModel):
    id: str
    status: str
    action: str | None = None
    reason: str | None = None
    error: str | None = None
    type: str | None = None


class BatchRememberResponse(BaseModel):
    agent_id: str
    session_id: str
    namespace: str
    total_submitted: int
    successful: int
    failed: int
    results: list[BatchRememberResultItem]


class UploadFileResponse(BaseModel):
    agent_id: str
    session_id: str
    namespace: str
    file_name: str
    file_size: int | None = None
    status: str
    message: str = ""


class RecallResponse(BaseModel):
    agent_id: str
    session_id: str
    query: str
    memories: list[MemoryItem]
    count: int


class TemporalRecallResponse(BaseModel):
    agent_id: str
    session_id: str
    memories: list[MemoryItem]
    count: int
    temporal_mode: str
    as_of_date: str | None = None
    since_date: str | None = None


class AnswerResponse(BaseModel):
    agent_id: str
    session_id: str
    question: str
    answer: str
    sources: list[Any] = Field(default_factory=list)
    namespace: str
