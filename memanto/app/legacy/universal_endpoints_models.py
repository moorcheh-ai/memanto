"""
Universal Adoption Endpoint Models
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# Universal memory explain models
class MemoryExplainRequest(BaseModel):
    scope: dict[str, str] = Field(..., description="Memory scope to explain")
    query: str = Field(..., description="Query that was executed")
    memory_ids: list[str] | None = Field(
        None, description="Specific memory IDs to explain"
    )
    filters: dict[str, Any] | None = Field(
        None, description="Filters that were applied"
    )


class MemoryExplanation(BaseModel):
    memory_id: str
    text: str
    memory_type: str
    confidence: float
    score: float
    match_reason: str = Field(..., description="Why this memory matched the query")
    filter_status: str = Field(..., description="How filters affected this memory")
    routing_path: str = Field(..., description="Which namespace/routing was used")


class MemoryExplainResponse(BaseModel):
    query: str
    namespace_used: str
    total_candidates: int
    filtered_count: int
    returned_count: int
    explanations: list[MemoryExplanation]
    routing_decision: str = Field(..., description="How namespace was computed")
    filter_summary: dict[str, Any] = Field(
        ..., description="Summary of applied filters"
    )


# Universal memory supersede models
class MemorySupersedeRequest(BaseModel):
    memory_id: str = Field(..., description="Memory ID to supersede (mark inactive)")
    superseding_memory: dict[str, Any] = Field(
        ..., description="New memory data that replaces the old one"
    )
    reason: str | None = Field(None, description="Reason for superseding")


class MemorySupersedeResponse(BaseModel):
    superseded_memory_id: str
    new_memory_id: str
    supersede_timestamp: datetime
    reason: str | None
    status: str = "superseded"


# Universal memory export models
class MemoryExportRequest(BaseModel):
    scope: dict[str, str] = Field(..., description="Scope to export")
    format: str = Field("json", description="Export format: json, csv, jsonl")
    include_inactive: bool = Field(
        False, description="Include superseded/inactive memories"
    )
    date_range: dict[str, str] | None = Field(None, description="Date range filter")
    memory_types: list[str] | None = Field(None, description="Filter by memory types")


class ExportedMemory(BaseModel):
    memory_id: str
    text: str
    memory_type: str
    confidence: float
    provisional: bool
    created_at: datetime
    updated_at: datetime | None
    source: str
    status: str  # active, superseded, expired
    superseded_by: str | None = None
    supersedes: list[str] | None = None
    metadata: dict[str, Any] | None = None


class MemoryExportResponse(BaseModel):
    scope: dict[str, str]
    export_timestamp: datetime
    total_memories: int
    exported_count: int
    format: str
    memories: list[ExportedMemory]
    export_metadata: dict[str, Any] = Field(
        ..., description="Export statistics and filters applied"
    )
