"""
Context Summarization Routes

Endpoints for compressing and summarizing agent memory context
using Moorcheh's AI capabilities.
"""

from fastapi import APIRouter, Depends
from memanto.app.services.context_summarization_service import (
    ContextSummarizationService,
)
from moorcheh_sdk import MoorchehClient

from memanto.app.clients.moorcheh import get_moorcheh_client
from memanto.app.models import (
    CompressionResponse,
    ContextSummarizationRequest,
    ConversationCompressionRequest,
    CustomSummarizationRequest,
    SummarizationResponse,
)
from memanto.app.utils.errors import map_error_to_http_exception

router = APIRouter()


@router.post("/summarize", response_model=SummarizationResponse)
async def summarize_scope_context(
    request: ContextSummarizationRequest,
    client: MoorchehClient = Depends(get_moorcheh_client),
):
    """
    Summarize all memories in a scope into a compressed context summary

    This endpoint uses Moorcheh's AI to generate a concise summary of
    multiple memories, which is stored as a new 'context' type memory.

    Use cases:
    - Compress long conversation histories
    - Create executive summaries of project decisions
    - Reduce context window usage for agents
    - Maintain key information while reducing token count

    The summary memory includes links to all original memories for reference.
    """
    try:
        service = ContextSummarizationService(client)

        result = service.summarize_scope_context(
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            actor_id=request.actor_id,
            summary_title=request.summary_title,
            memory_types=list(request.memory_types) if request.memory_types else None,
            max_memories=request.max_memories,
            link_to_originals=request.link_to_originals,
        )

        return SummarizationResponse(**result)

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.post("/summarize/custom", response_model=SummarizationResponse)
async def summarize_by_memory_ids(
    request: CustomSummarizationRequest,
    client: MoorchehClient = Depends(get_moorcheh_client),
):
    """
    Summarize specific memories by their IDs

    Use this when you want to create a summary of a specific set of
    related memories, rather than all memories in a scope.

    Examples:
    - Summarize all memories about a specific topic
    - Compress memories from a particular time period
    - Create a summary of memories with specific tags
    """
    try:
        service = ContextSummarizationService(client)

        result = service.summarize_by_memory_ids(
            memory_ids=request.memory_ids,
            namespace=request.namespace,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            actor_id=request.actor_id,
            summary_title=request.summary_title,
        )

        return SummarizationResponse(
            summary_id=result["summary_id"],
            namespace=result["namespace"],
            status=result["status"],
            summarized_count=result["summarized_count"],
            original_memory_ids=result["original_memory_ids"],
            summary_preview=result["summary_text"][:200] + "..."
            if len(result["summary_text"]) > 200
            else result["summary_text"],
        )

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.post("/compress", response_model=CompressionResponse)
async def compress_conversation_history(
    request: ConversationCompressionRequest,
    client: MoorchehClient = Depends(get_moorcheh_client),
):
    """
    Compress old conversation history while keeping recent memories intact

    This is ideal for long-running agent sessions where old context
    accumulates and needs to be compressed to reduce token usage.

    The service will:
    1. Find memories older than the specified threshold
    2. Generate an AI summary of those memories
    3. Store the summary as a new 'context' memory
    4. Link the summary to all original memories

    Note: Original memories are NOT deleted - they remain accessible
    but the summary provides a compressed alternative for context retrieval.

    Example workflow:
    - Agent runs for 30 days with daily interactions
    - Compress memories older than 7 days
    - Keep last 10 recent memories uncompressed
    - Agent can retrieve compressed summary for old context
    """
    try:
        service = ContextSummarizationService(client)

        result = service.compress_conversation_history(
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            actor_id=request.actor_id,
            days_to_compress=request.days_to_compress,
            keep_recent_count=request.keep_recent_count,
        )

        return CompressionResponse(**result)

    except Exception as e:
        raise map_error_to_http_exception(e)
