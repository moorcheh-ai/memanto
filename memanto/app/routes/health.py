"""
Health Check Routes
"""

from fastapi import APIRouter
from moorcheh_sdk import MoorchehClient

from memanto.app import __version__
from memanto.app.config import settings
from memanto.app.models import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""

    # Test Moorcheh connection
    moorcheh_connected = False
    api_key = settings.MOORCHEH_API_KEY.strip()
    if api_key:
        try:
            from moorcheh_sdk.exceptions import AuthenticationError, NamespaceNotFound

            client = MoorchehClient(api_key=api_key)
            try:
                # Dummy fetch to test connection
                client.documents.get(namespace_name="__memanto_auth_ping__", ids=["1"])
                moorcheh_connected = True
            except NamespaceNotFound:
                moorcheh_connected = True
            except AuthenticationError:
                moorcheh_connected = False
        except Exception:
            moorcheh_connected = False

    return HealthResponse(
        status="healthy" if moorcheh_connected else "unhealthy",
        service="MEMANTO",
        version=__version__,
        moorcheh_connected=moorcheh_connected,
    )


@router.get("/ready")
async def readiness_check():
    """Readiness check for Kubernetes"""
    return {"status": "ready"}


@router.get("/live")
async def liveness_check():
    """Liveness check for Kubernetes"""
    return {"status": "alive"}
