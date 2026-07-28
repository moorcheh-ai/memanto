"""
Namespace Management Routes
"""

from fastapi import APIRouter, Depends, HTTPException
from moorcheh_sdk import MoorchehClient

from memanto.app.clients.moorcheh import get_moorcheh_client
from memanto.app.models import (
    NamespaceCreateRequest,
    NamespaceListResponse,
    NamespaceResponse,
)
from memanto.app.services.namespace_service import NamespaceService
from memanto.app.utils.errors import map_error_to_http_exception

router = APIRouter()


@router.post("/", response_model=NamespaceResponse)
async def create_namespace(
    request: NamespaceCreateRequest,
    client: MoorchehClient = Depends(get_moorcheh_client),
):
    """Create a new namespace"""
    try:
        service = NamespaceService(client)
        namespace = service.create_namespace(request.scope_type, request.scope_id)

        return NamespaceResponse(
            namespace=namespace,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            created=True,
        )

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.get("/", response_model=NamespaceListResponse)
async def list_namespaces(client: MoorchehClient = Depends(get_moorcheh_client)):
    """List all MEMANTO namespaces"""
    try:
        service = NamespaceService(client)
        namespaces = service.list_namespaces()

        return NamespaceListResponse(namespaces=namespaces, total=len(namespaces))

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.delete("/{scope_type}/{scope_id}")
async def delete_namespace(
    scope_type: str,
    scope_id: str,
    client: MoorchehClient = Depends(get_moorcheh_client),
):
    """Delete a namespace"""
    try:
        from typing import cast

        from memanto.app.constants import ScopeType

        scope_type_resolved = (
            scope_type
            if scope_type in {"user", "workspace", "agent", "session"}
            else "agent"
        )
        service = NamespaceService(client)
        success = service.delete_namespace(
            cast(ScopeType, scope_type_resolved), scope_id
        )

        if success:
            return {"message": "Namespace deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Namespace not found")

    except Exception as e:
        raise map_error_to_http_exception(e)


@router.get("/{scope_type}/{scope_id}/exists")
async def check_namespace_exists(
    scope_type: str,
    scope_id: str,
    client: MoorchehClient = Depends(get_moorcheh_client),
):
    """Check if namespace exists"""
    try:
        from typing import cast

        from memanto.app.constants import ScopeType

        scope_type_resolved = (
            scope_type
            if scope_type in {"user", "workspace", "agent", "session"}
            else "agent"
        )
        service = NamespaceService(client)
        exists = service.namespace_exists(
            cast(ScopeType, scope_type_resolved), scope_id
        )

        return {"exists": exists}

    except Exception as e:
        raise map_error_to_http_exception(e)
