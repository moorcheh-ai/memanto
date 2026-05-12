"""
MEMANTO FastAPI Application
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from moorcheh_sdk import MoorchehClient
from moorcheh_sdk.exceptions import AuthenticationError, NamespaceNotFound

from memanto.app import __version__
from memanto.app.config import settings
from memanto.app.routes import health, sessions
from memanto.app.ui.routes.ui_router import mount_ui_static
from memanto.app.ui.routes.ui_router import router as ui_router


def _validate_startup_dependencies() -> None:
    """Fail fast when mandatory external dependencies are misconfigured."""
    api_key = settings.MOORCHEH_API_KEY.strip()
    if not api_key:
        raise RuntimeError(
            "MOORCHEH_API_KEY is not configured. Set it before starting MEMANTO."
        )

    try:
        client = MoorchehClient(api_key=api_key)
        try:
            client.documents.get(namespace_name="__memanto_auth_ping__", ids=["1"])
        except NamespaceNotFound:
            # Auth succeeded; ping namespace intentionally does not exist.
            pass
    except AuthenticationError as exc:
        raise RuntimeError(
            "MOORCHEH_API_KEY is invalid. Update it and restart MEMANTO."
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"Failed to validate Moorcheh connectivity: {exc}") from exc


@asynccontextmanager
async def lifespan(_: FastAPI):
    _validate_startup_dependencies()
    yield


# Create FastAPI app
app = FastAPI(
    title="Memanto - Memory that AI Agents Love!",
    description="A memory layer service for agentic AI systems using Moorcheh SDK",
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, tags=["Health"])

# Session-Based API (Primary)
app.include_router(sessions.router, prefix="/api/v2", tags=["Sessions & Agents"])


# Web UI Dashboard
app.include_router(ui_router, tags=["Web UI"])
mount_ui_static(app)


@app.get("/")
async def root():
    return {
        "service": "MEMANTO",
        "description": "Memory that AI Agents Love!",
        "version": __version__,
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
