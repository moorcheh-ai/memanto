"""
Memory Management Routes
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from moorcheh_sdk import MoorchehClient

from memanto.app.clients.moorcheh import get_moorcheh_client
from memanto.app.core import MemoryRecord
from memanto.app.models import (
    MemoryAnswerRequest,
    MemoryAnswerResponse,
    MemoryBatchWriteRequest,
    MemoryBatchWriteResponse,
    MemoryMultiScopeSearchRequest,
    MemoryResponse,
    MemorySearchResponse,
    MemoryStoreRequest,
    MemoryStoreResponse,
    MemoryUpdateRequest,
    MemoryUpdateResponse,
)
from memanto.app.services.memory_read_service import MemoryReadService
from memanto.app.services.memory_write_service import MemoryWriteService
from memanto.app.utils.errors import map_error_to_http_exception

router = APIRouter()


@router.post("/store", response_model=MemoryStoreResponse)
async def store_memory(
    request: MemoryStoreRequest, client: MoorchehClient = Depends(get_moorcheh_client)
):
    """Store a new memory"""
    try:
        # Create memory record
        memory = MemoryRecord(
            type=request.type,
            title=request.title,
            content=request.content,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            actor_id=request.actor_id,
            source=request.source,
            source_ref=request.source_ref,
            confidence=request.confidence,
            tags=request.tags,
        )

        # Set TTL if provided
        if request.ttl_seconds:
            memory.set_ttl(request.ttl_seconds)

        # Store memory
        service = MemoryWriteService(client)
        context = {"user_confirmed": request.user_confirmed}
        result = service.store_memory(memory, context)

        return MemoryStoreResponse(
            id=result["id"],
            status=result["status"],
            action=result["action"],
            reason=result["reason"],
            namespace=result["namespace"],
        )

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.post("/batch/write", response_model=MemoryBatchWriteResponse)
async def batch_write_memories(
    request: MemoryBatchWriteRequest,
    client: MoorchehClient = Depends(get_moorcheh_client),
):
    """
    Store multiple memories in batch (up to 100 per request)

    Leverages Moorcheh's batch upload capability for efficient storage.
    All memories must belong to the same tenant/scope.
    """
    try:
        # Create memory records from batch items
        memory_records = []
        for item in request.memories:
            memory = MemoryRecord(
                type=item.type,
                title=item.title,
                content=item.content,
                scope_type=request.scope_type,
                scope_id=request.scope_id,
                actor_id=request.actor_id,
                source=item.source,
                source_ref=item.source_ref,
                confidence=item.confidence,
                tags=item.tags,
            )
            if item.id is not None:
                memory.id = item.id

            # Set TTL if provided
            if item.ttl_seconds:
                memory.set_ttl(item.ttl_seconds)

            memory_records.append(memory)

        # Store in batch
        service = MemoryWriteService(client)
        context = {"user_confirmed": request.user_confirmed}
        result = service.batch_store_memories(memory_records, context)

        return MemoryBatchWriteResponse(**result)

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.patch("/{memory_id}", response_model=MemoryUpdateResponse)
async def update_memory(
    memory_id: str,
    request: MemoryUpdateRequest,
    client: MoorchehClient = Depends(get_moorcheh_client),
):
    """
    Update an existing memory using delete-and-recreate pattern

    Since Moorcheh doesn't support in-place updates, this endpoint:
    1. Retrieves the existing memory
    2. Applies the requested updates
    3. Deletes the old version
    4. Uploads the updated version with the same ID

    This ensures atomic updates while preserving the memory ID.
    """
    try:
        service = MemoryWriteService(client)
        context = {"user_confirmed": request.user_confirmed}

        result = service.update_memory(
            memory_id=memory_id,
            namespace=request.namespace,
            updates=request.updates,
            context=context,
        )

        return MemoryUpdateResponse(**result)

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.get("/search", response_model=MemorySearchResponse)
async def search_memories(
    query: str = Query(..., description="Search query"),
    scope_type: str | None = Query(None, description="Scope type filter"),
    scope_id: str | None = Query(None, description="Scope ID filter"),
    memory_types: list[str] | None = Query(
        None, description="Memory type filters (leverages Moorcheh #type:value)"
    ),
    tags: list[str] | None = Query(
        None, description="Tag filters (leverages Moorcheh #keyword)"
    ),
    min_confidence: float | None = Query(
        None, ge=0.0, le=1.0, description="Minimum confidence threshold"
    ),
    status_filter: list[str] | None = Query(
        None, description="Status filters: active, provisional, superseded"
    ),
    min_similarity_score: float | None = Query(
        None,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score (uses Moorcheh kiosk_mode)",
    ),
    created_after: str | None = Query(
        None, description="ISO timestamp - only return memories created after this time"
    ),
    created_before: str | None = Query(
        None,
        description="ISO timestamp - only return memories created before this time",
    ),
    limit: int = Query(
        10, ge=1, le=100, description="Result limit (maps to Moorcheh top_k)"
    ),
    offset: int = Query(
        0, ge=0, description="Pagination offset - number of results to skip"
    ),
    client: MoorchehClient = Depends(get_moorcheh_client),
):
    """
    Search memories with Moorcheh's native metadata filtering

    Leverages Moorcheh's #key:value syntax for server-side filtering
    and kiosk_mode for threshold-based result filtering.

    Temporal filtering (created_after/created_before) allows queries like:
    - "Find memories from last 7 days"
    - "Get memories created before 2025-01-01"

    Pagination: Use limit and offset for paging through results:
    - First page: limit=10, offset=0
    - Second page: limit=10, offset=10
    - Check has_more in response to see if more results available

    Set min_similarity_score to filter out low-relevance results
    (e.g., 0.8 for high relevance, 0.5 for medium relevance).
    """
    try:
        service = MemoryReadService(client)
        result = service.search_memories(
            query=query,
            scope_type=scope_type,
            scope_id=scope_id,
            type=memory_types,
            tags=tags,
            min_confidence=min_confidence,
            status_filter=status_filter,
            min_similarity_score=min_similarity_score,
            created_after=created_after,
            created_before=created_before,
            limit=limit,
            offset=offset,
        )

        return MemorySearchResponse(**result)

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.post("/search/multi", response_model=MemorySearchResponse)
async def search_multi_scope(
    request: MemoryMultiScopeSearchRequest,
    client: MoorchehClient = Depends(get_moorcheh_client),
):
    """
    Search across multiple scopes simultaneously

    Leverages Moorcheh's multi-namespace search to find memories
    across different scopes (e.g., user + project + workspace)
    in a single query.

    Example use case: "Find all mentions of 'budget' across
    user preferences, project decisions, and workspace context"
    """
    try:
        service = MemoryReadService(client)

        # Convert scope definitions to dicts
        scopes = [
            {"scope_type": s.scope_type, "scope_id": s.scope_id} for s in request.scopes
        ]

        result = service.search_multi_scope(
            query=request.query,
            scopes=scopes,
            type=list(request.memory_types) if request.memory_types else None,
            tags=request.tags,
            min_confidence=request.min_confidence,
            status_filter=request.status_filter,
            min_similarity_score=request.min_similarity_score,
            limit=request.limit,
        )

        return MemorySearchResponse(**result)

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.post("/answer", response_model=MemoryAnswerResponse)
async def answer_memories(
    request: MemoryAnswerRequest, client: MoorchehClient = Depends(get_moorcheh_client)
):
    """Generate AI answer from memories"""
    try:
        service = MemoryReadService(client)
        result = service.generate_answer(
            query=request.query,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
        )

        return MemoryAnswerResponse(
            answer=result["answer"],
            sources=[],  # TODO: Extract sources from answer
            confidence=0.8,  # TODO: Calculate confidence
            namespace=result["namespace"],
        )

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: str,
    namespace: str = Query(..., description="Namespace containing the memory"),
    client: MoorchehClient = Depends(get_moorcheh_client),
):
    """Retrieve specific memory by ID"""
    try:
        service = MemoryReadService(client)
        memory = service.get_memory(memory_id, namespace)

        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")

        # Convert to response model (simplified)
        return memory

    except HTTPException:
        raise
    except Exception as e:
        raise map_error_to_http_exception(e)


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    namespace: str = Query(..., description="Namespace containing the memory"),
    client: MoorchehClient = Depends(get_moorcheh_client),
):
    """Delete memory by ID"""
    try:
        service = MemoryWriteService(client)
        success = service.delete_memory(memory_id, namespace)

        if success:
            return {"message": "Memory deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Memory not found")

    except HTTPException:
        raise
    except Exception as e:
        raise map_error_to_http_exception(e)
