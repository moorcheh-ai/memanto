"""
Memory Operations - Session-Based

Memory operations using session tokens (no tenant_id).
Replaces /api/v1/agents/{agent_id}/remember with session-based auth.
"""

import asyncio
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import cast

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile

from memanto.app.clients.moorcheh import get_moorcheh_client
from memanto.app.config import settings
from memanto.app.core import MemoryRecord
from memanto.app.models import BatchRememberRequest
from memanto.app.models.session import Session
from memanto.app.routes.auth_deps import get_current_session, get_session_service
from memanto.app.services.memory_read_service import MemoryReadService
from memanto.app.services.memory_write_service import MemoryWriteService
from memanto.app.utils.errors import map_error_to_http_exception

router = APIRouter()


@router.post("/{agent_id}/remember")
async def remember(
    agent_id: str,
    content: str = Body(..., embed=True, description="Memory content"),
    memory_type: str | None = Query(
        None, description="Type of memory. Omit to auto-parse."
    ),
    title: str | None = Query(
        None, description="Memory title (optional, defaults to truncated content)"
    ),
    confidence: float = Query(0.8, description="Confidence score (0-1)"),
    tags: str | None = Query(None, description="Comma-separated tags"),
    source: str = Query("agent", description="Source of memory"),
    provenance: str = Query(
        "explicit_statement",
        description="How memory was obtained (explicit_statement, inferred, observed, etc.)",
    ),
    session: Session = Depends(get_current_session),
    client=Depends(get_moorcheh_client),
):
    """
    Store a memory (Session-based)

    Requires:
    - Authorization: Bearer {moorcheh_api_key}
    - X-Session-Token: {session_token}

    The session must be for the specified agent_id.

    Provenance types:
    - explicit_statement: Directly stated by user
    - inferred: Derived from behavior/context
    - observed: Seen in action
    - validated: Confirmed/verified
    - corrected: Updated after contradiction
    - imported: From external source
    """
    # Enforce session scope: token must match agent_id
    if session.agent_id != agent_id:
        raise map_error_to_http_exception(
            Exception(
                f"Session is for agent '{session.agent_id}', cannot access '{agent_id}'"
            )
        )

    try:
        # Initialize memory write service
        write_service = MemoryWriteService(client)

        from memanto.app.constants import MemoryType, ProvenanceType

        resolved_title = title or (
            f"{content[:50]}..." if len(content) > 50 else content
        )

        # Create memory record with scope fields and provenance
        memory = MemoryRecord(
            type=cast(MemoryType, memory_type) if memory_type is not None else None,
            title=resolved_title,
            content=content,
            scope_type="agent",
            scope_id=agent_id,
            actor_id=agent_id,
            confidence=confidence,
            tags=tags.split(",") if tags else [],
            source=source,
            provenance=cast(ProvenanceType, provenance),
        )

        # Store memory in agent's namespace.
        result = await asyncio.to_thread(write_service.store_memory, memory)

        # Log to local session Markdown summary
        session_service = get_session_service()
        await asyncio.to_thread(
            session_service.log_memory_to_session_summary,
            agent_id=agent_id,
            session_id=session.session_id,
            memory_record=memory,
        )

        # skip trust_score() computation
        ## Compute trust score for response
        # trust_score = memory.trust_score()

        return {
            "memory_id": result["id"],
            "agent_id": agent_id,
            "session_id": session.session_id,
            "namespace": session.namespace,
            "status": "queued",
            "type": result.get("type"),
            "provenance": provenance,
            "confidence": confidence,
            # "computed_confidence": trust_score["computed_confidence"],
            # "trust_level": trust_score["trust_level"]
        }

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.post("/{agent_id}/batch-remember")
async def batch_remember(
    agent_id: str,
    request: BatchRememberRequest = Body(...),
    session: Session = Depends(get_current_session),
    client=Depends(get_moorcheh_client),
):
    """
    Store multiple memories in batch (Session-based)

    Accepts up to 100 memories per request. Leverages Moorcheh's batch
    upload capability for efficient storage.

    Requires:
    - Authorization: Bearer {moorcheh_api_key}
    - X-Session-Token: {session_token}

    The session must be for the specified agent_id.
    """
    # Enforce session scope: token must match agent_id
    if session.agent_id != agent_id:
        raise map_error_to_http_exception(
            Exception(
                f"Session is for agent '{session.agent_id}', cannot access '{agent_id}'"
            )
        )

    try:
        # Initialize memory write service
        write_service = MemoryWriteService(client)

        # Convert each item to a MemoryRecord
        from memanto.app.constants import MemoryType

        memory_records = []
        for item in request.memories:
            title = item.title or (
                item.content[:47] + "..." if len(item.content) > 50 else item.content
            )
            memory = MemoryRecord(
                type=cast(MemoryType, item.type) if item.type is not None else None,
                title=title,
                content=item.content,
                scope_type="agent",
                scope_id=agent_id,
                actor_id=agent_id,
                confidence=item.confidence,
                tags=item.tags or [],
                source="user",
                provenance="explicit_statement",
            )
            memory_records.append(memory)

        # Store in batch
        result = await asyncio.to_thread(
            write_service.batch_store_memories, memory_records
        )

        # Log each memory to local MD summary
        session_service = get_session_service()

        for record in memory_records:
            await asyncio.to_thread(
                session_service.log_memory_to_session_summary,
                agent_id=agent_id,
                session_id=session.session_id,
                memory_record=record,
            )

        return {
            "agent_id": agent_id,
            "session_id": session.session_id,
            "namespace": session.namespace,
            "total_submitted": result["total_submitted"],
            "successful": result["successful"],
            "failed": result["failed"],
            "results": result["results"],
        }

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.post("/{agent_id}/upload-file")
async def upload_file(
    agent_id: str,
    file: UploadFile = File(
        ..., description="File to upload (.pdf, .docx, .xlsx, .json, .txt, .csv, .md)"
    ),
    session: Session = Depends(get_current_session),
    client=Depends(get_moorcheh_client),
):
    """
    Upload a file directly to the agent's memory namespace (Session-based)

    Supported formats: .pdf, .docx, .xlsx, .json, .txt, .csv, .md
    Maximum file size: 5GB

    The file is processed by Moorcheh to extract text and generate embeddings,
    making its content searchable via recall.

    Requires:
    - Authorization: Bearer {moorcheh_api_key}
    - X-Session-Token: {session_token}
    - Content-Type: multipart/form-data
    """
    if session.agent_id != agent_id:
        raise map_error_to_http_exception(
            Exception(
                f"Session is for agent '{session.agent_id}', cannot access '{agent_id}'"
            )
        )

    # Validate file extension before reading
    ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".json", ".txt", ".csv", ".md"}
    original_name = file.filename or "upload"
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        allowed_str = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"File type '{suffix}' is not supported. Allowed types: {allowed_str}",
        )

    try:
        namespace = session.namespace

        # Write upload to a temp file so moorcheh SDK can read it
        # Use original filename so the SDK records it as the source
        file_bytes = await file.read()
        tmp_dir = tempfile.mkdtemp()
        tmp_path = os.path.join(tmp_dir, original_name)
        try:
            with open(tmp_path, "wb") as tmp:
                tmp.write(file_bytes)
            result = await asyncio.to_thread(
                client.documents.upload_file, namespace, tmp_path
            )
        finally:
            import shutil

            shutil.rmtree(tmp_dir, ignore_errors=True)

        return {
            "agent_id": agent_id,
            "session_id": session.session_id,
            "namespace": namespace,
            "file_name": original_name,
            "file_size": result.get("fileSize"),
            "status": "uploaded" if result.get("success") else "failed",
            "message": result.get("message", ""),
        }

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.get("/{agent_id}/recall")
async def recall(
    agent_id: str,
    query: str = Query(..., description="Search query"),
    limit: int = Query(None, description="Max results"),
    min_similarity: float | None = Query(
        None, description="Minimum similarity score (0-1)"
    ),
    created_after: datetime | None = Query(None, description="Filter by creation date"),
    created_before: datetime | None = Query(
        None, description="Filter by creation date"
    ),
    memory_types: str | None = Query(None, description="Comma-separated memory types"),
    session: Session = Depends(get_current_session),
    client=Depends(get_moorcheh_client),
):
    """
    Recall memories (Session-based)

    Requires:
    - Authorization: Bearer {moorcheh_api_key}
    - X-Session-Token: {session_token}

    The session must be for the specified agent_id.
    """
    # Enforce session scope
    if session.agent_id != agent_id:
        raise map_error_to_http_exception(
            Exception(
                f"Session is for agent '{session.agent_id}', cannot access '{agent_id}'"
            )
        )

    if limit is None:
        limit = settings.RECALL_LIMIT

    try:
        # Initialize memory read service
        read_service = MemoryReadService(client)

        # Search in agent's namespace using scope.
        result = await asyncio.to_thread(
            read_service.search_memories,
            query=query,
            scope_type="agent",
            scope_id=agent_id,
            memory_types=memory_types.split(",") if memory_types else None,
            min_similarity_score=min_similarity,
            created_after=created_after.isoformat() if created_after else None,
            created_before=created_before.isoformat() if created_before else None,
            limit=limit,
        )

        memories = result.get("results", [])

        return {
            "agent_id": agent_id,
            "session_id": session.session_id,
            "query": query,
            "memories": memories,
            "count": len(memories),
        }

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.post("/{agent_id}/answer")
async def answer(
    agent_id: str,
    question: str = Body(..., embed=True, description="Question to ask"),
    limit: int = Query(None, description="Number of context memories to use"),
    threshold: float = Query(
        None, description="Confidence threshold for memory relevance"
    ),
    temperature: float = Query(None, description="Temperature for the LLM response"),
    aiModel: str = Query(
        None,
        description="AI model to use for generating the answer",
    ),
    kiosk_mode: bool = Query(False, description="Kiosk mode setting"),
    header_prompt: str | None = Body(
        None, embed=True, description="Header prompt for the LLM"
    ),
    footer_prompt: str | None = Body(
        None, embed=True, description="Footer prompt for the LLM"
    ),
    session: Session = Depends(get_current_session),
    client=Depends(get_moorcheh_client),
):
    """
    Answer a question using RAG (Session-based)

    Requires:
    - Authorization: Bearer {moorcheh_api_key}
    - X-Session-Token: {session_token}

    Uses Moorcheh's answer.generate endpoint to produce LLM-generated answers
    based on the agent's stored memories.
    """
    # Enforce session scope
    if session.agent_id != agent_id:
        raise map_error_to_http_exception(
            Exception(
                f"Session is for agent '{session.agent_id}', cannot access '{agent_id}'"
            )
        )

    # Resolve defaults from settings
    if limit is None:
        limit = settings.ANSWER_LIMIT
    if threshold is None:
        threshold = settings.ANSWER_THRESHOLD
    if temperature is None:
        temperature = settings.ANSWER_TEMPERATURE
    if aiModel is None:
        aiModel = settings.ANSWER_MODEL

    try:
        # Use namespace from session
        namespace = session.namespace

        # Define default prompts for RAG
        header_prompt = header_prompt or (
            "You are a helpful AI assistant with access to the agent's persistent memory. "
            "Use the provided context from the agent's memories to answer the user's question accurately. "
            "If the memories don't contain relevant information, say so clearly."
        )

        footer_prompt = footer_prompt or (
            "Answer the question based on the memory context above. "
            "Be concise and cite specific memories when relevant. "
            "If no relevant memories exist, acknowledge that."
        )

        # Use Moorcheh's answer.generate endpoint.
        response = await asyncio.to_thread(
            client.answer.generate,
            namespace=namespace,
            query=question,
            top_k=limit,
            threshold=threshold,
            temperature=temperature,
            ai_model=aiModel,
            kiosk_mode=kiosk_mode,
            header_prompt=header_prompt,
            footer_prompt=footer_prompt,
        )

        # Extract the generated answer and sources
        answer = response.get("answer", "No answer generated.")
        sources = response.get("sources", [])

        return {
            "agent_id": agent_id,
            "session_id": session.session_id,
            "question": question,
            "answer": answer,
            "sources": sources,
            "namespace": namespace,
        }

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.post("/{agent_id}/validate/{memory_id}")
async def validate_memory(
    agent_id: str,
    memory_id: str,
    session: Session = Depends(get_current_session),
    client=Depends(get_moorcheh_client),
):
    """
    Mark a memory as validated (Session-based)

    Increases validation_count and updates validated_at timestamp.
    This increases the computed confidence of the memory.

    Requires:
    - Authorization: Bearer {moorcheh_api_key}
    - X-Session-Token: {session_token}

    The session must be for the specified agent_id.
    """
    # Enforce session scope
    if session.agent_id != agent_id:
        raise map_error_to_http_exception(
            Exception(
                f"Session is for agent '{session.agent_id}', cannot access '{agent_id}'"
            )
        )

    try:
        # Initialize services
        read_service = MemoryReadService(client)
        write_service = MemoryWriteService(client)

        # Use namespace from session
        namespace = session.namespace

        # Retrieve existing memory (blocking SDK call → thread pool)
        existing = await asyncio.to_thread(
            read_service.get_memory, memory_id, namespace
        )
        if not existing:
            raise map_error_to_http_exception(
                Exception(f"Memory {memory_id} not found")
            )

        # Update with validation
        updates = {
            "validation_count": existing.get("validation_count", 0) + 1,
            "validated_at": datetime.utcnow().isoformat(),
        }

        # If provenance was inferred, upgrade to validated
        if existing.get("provenance") == "inferred":
            updates["provenance"] = "validated"

        await asyncio.to_thread(
            write_service.update_memory, memory_id, namespace, updates
        )

        return {
            "memory_id": memory_id,
            "agent_id": agent_id,
            "session_id": session.session_id,
            "status": "validated",
            "validation_count": updates["validation_count"],
            "validated_at": updates["validated_at"],
        }

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.post("/{agent_id}/supersede/{old_memory_id}")
async def supersede_memory(
    agent_id: str,
    old_memory_id: str,
    new_memory_id: str = Query(
        ..., description="ID of new memory that supersedes the old one"
    ),
    session: Session = Depends(get_current_session),
    client=Depends(get_moorcheh_client),
):
    """
    Mark a memory as superseded by a newer one (Session-based)

    This creates a chain: old_memory -> superseded_by -> new_memory
    The old memory's status becomes 'superseded' and computed_confidence becomes 0.

    Requires:
    - Authorization: Bearer {moorcheh_api_key}
    - X-Session-Token: {session_token}

    The session must be for the specified agent_id.
    """
    # Enforce session scope
    if session.agent_id != agent_id:
        raise map_error_to_http_exception(
            Exception(
                f"Session is for agent '{session.agent_id}', cannot access '{agent_id}'"
            )
        )

    try:
        # Initialize services
        write_service = MemoryWriteService(client)

        # Use namespace from session
        namespace = session.namespace

        # Update old memory to mark as superseded
        updates = {"status": "superseded", "superseded_by": new_memory_id}

        await asyncio.to_thread(
            write_service.update_memory, old_memory_id, namespace, updates
        )

        # Update new memory to record what it supersedes
        new_updates = {"supersedes": old_memory_id}
        await asyncio.to_thread(
            write_service.update_memory, new_memory_id, namespace, new_updates
        )

        return {
            "old_memory_id": old_memory_id,
            "new_memory_id": new_memory_id,
            "agent_id": agent_id,
            "session_id": session.session_id,
            "status": "superseded",
            "message": f"Memory {old_memory_id} superseded by {new_memory_id}",
        }

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.post("/{agent_id}/contradict/{memory_id}")
async def mark_contradiction(
    agent_id: str,
    memory_id: str,
    session: Session = Depends(get_current_session),
    client=Depends(get_moorcheh_client),
):
    """
    Flag a memory as contradicted (Session-based)

    Marks contradiction_detected=true, which significantly lowers computed confidence.
    Use this when you discover a memory conflicts with newer information.

    Requires:
    - Authorization: Bearer {moorcheh_api_key}
    - X-Session-Token: {session_token}

    The session must be for the specified agent_id.
    """
    # Enforce session scope
    if session.agent_id != agent_id:
        raise map_error_to_http_exception(
            Exception(
                f"Session is for agent '{session.agent_id}', cannot access '{agent_id}'"
            )
        )

    try:
        # Initialize services
        write_service = MemoryWriteService(client)

        # Use namespace from session
        namespace = session.namespace

        # Update memory to flag contradiction
        updates = {"contradiction_detected": True}

        await asyncio.to_thread(
            write_service.update_memory, memory_id, namespace, updates
        )

        return {
            "memory_id": memory_id,
            "agent_id": agent_id,
            "session_id": session.session_id,
            "status": "contradicted",
            "message": f"Memory {memory_id} marked as contradicted",
        }

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.get("/{agent_id}/recall/as-of")
async def recall_as_of(
    agent_id: str,
    query: str = Query(..., description="Search query"),
    as_of: str = Query(..., description="Point-in-time timestamp (ISO format)"),
    limit: int = Query(None, description="Max results"),
    memory_types: str | None = Query(None, description="Comma-separated memory types"),
    session: Session = Depends(get_current_session),
    client=Depends(get_moorcheh_client),
):
    """
    Point-in-time recall: "What was true at this point in time?"

    Returns memories that were valid at the specified date, excluding:
    - Memories created after as_of date
    - Memories superseded before as_of date
    - Memories expired before as_of date

    Example: "What database did we use on 2025-11-01?"

    Requires:
    - Authorization: Bearer {moorcheh_api_key}
    - X-Session-Token: {session_token}
    """
    if session.agent_id != agent_id:
        raise map_error_to_http_exception(
            Exception(
                f"Session is for agent '{session.agent_id}', cannot access '{agent_id}'"
            )
        )

    if limit is None:
        limit = settings.RECALL_LIMIT

    try:
        read_service = MemoryReadService(client)

        result = await asyncio.to_thread(
            read_service.search_as_of,
            query=query,
            as_of_date=as_of,
            scope_type="agent",
            scope_id=agent_id,
            memory_types=memory_types.split(",") if memory_types else None,
            limit=limit,
        )

        return {
            "agent_id": agent_id,
            "session_id": session.session_id,
            "query": query,
            "as_of_date": as_of,
            "memories": result["results"],
            "count": result["total_found"],
            "temporal_mode": "as_of",
            "note": "Showing memories valid at the specified point in time",
        }

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.get("/{agent_id}/recall/changed-since")
async def recall_changed_since(
    agent_id: str,
    since: str = Query(..., description="Start date for changes (ISO format)"),
    limit: int = Query(None, description="Max results"),
    memory_types: str | None = Query(None, description="Comma-separated memory types"),
    session: Session = Depends(get_current_session),
    client=Depends(get_moorcheh_client),
):
    """
    Differential retrieval: "What changed recently?"

    Returns memories that were created or updated after the specified date.
    Each result includes a change_type field: "created" or "updated".

    Example: "What changed since last week?"

    Requires:
    - Authorization: Bearer {moorcheh_api_key}
    - X-Session-Token: {session_token}
    """
    if session.agent_id != agent_id:
        raise map_error_to_http_exception(
            Exception(
                f"Session is for agent '{session.agent_id}', cannot access '{agent_id}'"
            )
        )

    if limit is None:
        limit = settings.RECALL_LIMIT

    try:
        read_service = MemoryReadService(client)

        result = await asyncio.to_thread(
            read_service.search_changed_since,
            since_date=since,
            scope_type="agent",
            scope_id=agent_id,
            memory_types=memory_types.split(",") if memory_types else None,
            limit=limit,
        )

        return {
            "agent_id": agent_id,
            "session_id": session.session_id,
            "since_date": since,
            "memories": result["results"],
            "count": result["total_found"],
            "temporal_mode": "changed_since",
            "note": "Showing memories created or updated since the specified date",
        }

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.get("/{agent_id}/recall/current")
async def recall_current(
    agent_id: str,
    query: str = Query(..., description="Search query"),
    limit: int = Query(None, description="Max results"),
    memory_types: str | None = Query(None, description="Comma-separated memory types"),
    session: Session = Depends(get_current_session),
    client=Depends(get_moorcheh_client),
):
    """
    Current state recall: "What's the current state?" with supersession awareness

    Returns only currently valid memories, excluding:
    - Superseded memories
    - Expired memories
    - Deleted memories

    Results sorted by computed_confidence (most trusted first).

    Example: "What is the current database preference?"

    Requires:
    - Authorization: Bearer {moorcheh_api_key}
    - X-Session-Token: {session_token}
    """
    if session.agent_id != agent_id:
        raise map_error_to_http_exception(
            Exception(
                f"Session is for agent '{session.agent_id}', cannot access '{agent_id}'"
            )
        )

    if limit is None:
        limit = settings.RECALL_LIMIT

    try:
        read_service = MemoryReadService(client)

        result = await asyncio.to_thread(
            read_service.search_current_only,
            query=query,
            scope_type="agent",
            scope_id=agent_id,
            memory_types=memory_types.split(",") if memory_types else None,
            limit=limit,
        )

        return {
            "agent_id": agent_id,
            "session_id": session.session_id,
            "query": query,
            "memories": result["results"],
            "count": result["total_found"],
            "temporal_mode": "current_only",
            "note": result.get("note", "Showing only current, non-superseded memories"),
        }

    except Exception as e:
        raise map_error_to_http_exception(e)
