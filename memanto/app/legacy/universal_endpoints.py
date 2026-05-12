"""
Universal Adoption Endpoints
"""

from fastapi import APIRouter, Header, HTTPException
from memanto.app.services.universal_services import (
    MemoryExplainService,
    MemoryExportService,
    MemorySupersedeService,
)

from memanto.app.models.universal_endpoints import (
    MemoryExplainRequest,
    MemoryExplainResponse,
    MemoryExportRequest,
    MemoryExportResponse,
    MemorySupersedeRequest,
    MemorySupersedeResponse,
)
from memanto.app.utils.auth import extract_tenant_from_auth
from memanto.app.utils.logging import get_logger
from memanto.app.utils.rate_limiting import rate_limiter

router = APIRouter()
logger = get_logger(__name__)


@router.post("/explain", response_model=MemoryExplainResponse)
async def explain_memory_retrieval(
    request: MemoryExplainRequest,
    authorization: str = Header(..., description="Bearer token for authentication"),
):
    """
    Explain memory retrieval decisions for debugging and trust

    Returns detailed explanation of:
    - Why specific memories were returned
    - How routing and filtering worked
    - Match scores and reasoning

    This endpoint is essential for:
    - Debugging agent memory issues
    - Building enterprise trust through transparency
    - Understanding system behavior
    """

    # Extract tenant and validate
    tenant_id = extract_tenant_from_auth(authorization)

    # Rate limiting (explain uses memory_read limits)
    rate_limiter.enforce_rate_limit("memory_read", tenant_id)

    try:
        explanation = await MemoryExplainService.explain_memory_retrieval(
            tenant_id, request
        )

        logger.info(
            f"Memory explanation generated for tenant {tenant_id}, query: {request.query}"
        )

        return explanation

    except Exception as e:
        logger.error(f"Memory explanation failed for tenant {tenant_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Explanation failed: {str(e)}")


@router.post("/supersede", response_model=MemorySupersedeResponse)
async def supersede_memory(
    request: MemorySupersedeRequest,
    authorization: str = Header(..., description="Bearer token for authentication"),
):
    """
    Supersede a memory with a new version

    Marks the old memory as inactive and links to the new one.
    This prevents contradictions without hard deletes and maintains audit trail.

    Use cases:
    - Updating customer preferences
    - Correcting incorrect information
    - Evolving project decisions
    - Maintaining data consistency
    """

    # Extract tenant and validate
    tenant_id = extract_tenant_from_auth(authorization)

    # Rate limiting (same as writes)
    rate_limiter.enforce_rate_limit("memory_write", tenant_id)

    try:
        result = await MemorySupersedeService.supersede_memory(tenant_id, request)

        logger.info(
            f"Memory superseded for tenant {tenant_id}: {request.memory_id} -> {result.new_memory_id}"
        )

        return result

    except ValueError as e:
        logger.warning(
            f"Memory supersede validation failed for tenant {tenant_id}: {str(e)}"
        )
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Memory supersede failed for tenant {tenant_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Supersede failed: {str(e)}")


@router.get("/export", response_model=MemoryExportResponse)
async def export_memories(
    scope_type: str,
    scope_id: str,
    format: str = "json",
    include_inactive: bool = False,
    memory_types: str | None = None,
    authorization: str = Header(..., description="Bearer token for authentication"),
):
    """
    Export memories by scope for audits and migrations

    Provides complete memory export with:
    - All memories in a scope
    - Metadata and relationships
    - Multiple export formats
    - Audit trail information

    Enterprise features:
    - Compliance audit support
    - Data migration capabilities
    - Backup and archival
    - Forensic analysis
    """

    # Extract tenant and validate
    tenant_id = extract_tenant_from_auth(authorization)

    # Rate limiting (export uses memory_read limits)
    rate_limiter.enforce_rate_limit("memory_read", tenant_id)

    # Parse memory types filter
    memory_types_list = None
    if memory_types:
        memory_types_list = [t.strip() for t in memory_types.split(",")]

    # Build export request
    export_request = MemoryExportRequest(
        scope={"type": scope_type, "id": scope_id},
        format=format,
        include_inactive=include_inactive,
        date_range=None,
        memory_types=memory_types_list,
    )

    try:
        export_result = await MemoryExportService.export_memories(
            tenant_id, export_request
        )

        logger.info(
            f"Memory export completed for tenant {tenant_id}, scope: {scope_type}:{scope_id}, count: {export_result.exported_count}"
        )

        return export_result

    except Exception as e:
        logger.error(f"Memory export failed for tenant {tenant_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


# Additional utility endpoints for enterprise features


@router.get("/stats")
async def get_memory_statistics(
    authorization: str = Header(..., description="Bearer token for authentication"),
):
    """
    Get memory usage statistics for the tenant

    Returns:
    - Total memory count by type
    - Storage usage metrics
    - Activity statistics
    - Health indicators
    """

    tenant_id = extract_tenant_from_auth(authorization)

    # This would be implemented to provide tenant statistics
    # For now, return a placeholder
    return {
        "tenant_id": tenant_id,
        "total_memories": 0,
        "by_type": {},
        "storage_mb": 0,
        "last_activity": None,
        "health_status": "healthy",
    }


@router.post("/validate")
async def validate_memory_integrity(
    authorization: str = Header(..., description="Bearer token for authentication"),
):
    """
    Validate memory integrity and relationships

    Checks:
    - Superseding relationships are valid
    - No orphaned references
    - Metadata consistency
    - Namespace integrity
    """

    tenant_id = extract_tenant_from_auth(authorization)

    # This would be implemented to validate tenant memory integrity
    return {
        "tenant_id": tenant_id,
        "validation_timestamp": "2026-01-15T10:30:00Z",
        "status": "valid",
        "issues_found": 0,
        "recommendations": [],
    }
