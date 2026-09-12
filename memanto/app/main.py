"""
MEMANTO FastAPI Application
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from moorcheh_sdk import MoorchehClient
from moorcheh_sdk.exceptions import AuthenticationError, NamespaceNotFound

from memanto.app import __version__
from memanto.app.clients.backend import Backend, parse_backend
from memanto.app.config import check_secure_deployment, settings
from memanto.app.routes import health, sessions
from memanto.app.ui.routes.ui_router import mount_ui_static
from memanto.app.ui.routes.ui_router import router as ui_router
from memanto.app.utils.client_identity import (
    UNKNOWN_CLIENT,
    ClientIdentity,
    normalize_tool,
    reset_client,
    set_client,
)


def _validate_startup_dependencies() -> None:
    """Fail fast when mandatory external dependencies are misconfigured."""
    backend = parse_backend(settings.MEMANTO_BACKEND)

    if backend == Backend.ON_PREM:
        import httpx

        url = f"{settings.MOORCHEH_ONPREM_URL.rstrip('/')}/health"
        try:
            resp = httpx.get(url, timeout=5.0)
            resp.raise_for_status()
        except Exception as exc:
            raise RuntimeError(
                f"Moorcheh on-prem server not reachable at {url}. "
                f"Start it with: moorcheh up"
            ) from exc
        return

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


# Create FastAPI app. The interactive docs and the OpenAPI schema are disabled
# by default (MEMANTO_ENABLE_DOCS=true re-enables them): the server binds
# 0.0.0.0 by default, so an unauthenticated schema would enumerate every route
# to any network peer.
app = FastAPI(
    title="Memanto - Memory that AI Agents Love!",
    description="A memory layer service for agentic AI systems using Moorcheh SDK",
    version=__version__,
    docs_url="/docs" if settings.MEMANTO_ENABLE_DOCS else None,
    redoc_url="/redoc" if settings.MEMANTO_ENABLE_DOCS else None,
    openapi_url="/openapi.json" if settings.MEMANTO_ENABLE_DOCS else None,
    lifespan=lifespan,
)


def _validate_cors_settings(
    allowed_origins: list[str], allow_credentials: bool
) -> None:
    """Raise ValueError when wildcard origins and allow_credentials are combined.

    Starlette reflects the request Origin (instead of returning '*') when both
    allow_all_origins=True and allow_credentials=True, which lets any website make
    credentialed cross-origin requests — a CORS misconfiguration.
    """
    if "*" in allowed_origins and allow_credentials:
        raise ValueError(
            "CORS misconfiguration: CORS_ALLOW_CREDENTIALS=true is incompatible with "
            "ALLOWED_ORIGINS=['*']. Specify explicit trusted origins when enabling credentials."
        )


# Add CORS middleware
_validate_cors_settings(settings.ALLOWED_ORIGINS, settings.CORS_ALLOW_CREDENTIALS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
    # Header-authenticated API clients must be able to read an auto-renewed
    # token from the response. Custom response headers are not CORS-safelisted.
    expose_headers=["X-Session-Token"],
)


@app.middleware("http")
async def attribute_calling_tool(request, call_next):
    """Bind the calling tool to this request so activity logging can name it.

    Over HTTP the server's own environment says nothing about the caller, so
    the tool identifies itself with ``X-Memanto-Client`` (optionally
    ``X-Memanto-Project``). The session comes from the session token, not from
    a header.
    """
    tool = (request.headers.get("X-Memanto-Client") or "").strip()
    if tool:
        identity = ClientIdentity(
            tool=normalize_tool(tool),
            display=tool,
            project_dir=(request.headers.get("X-Memanto-Project") or "").strip()
            or None,
        )
    else:
        # Bind UNKNOWN rather than leaving the context empty. Falling through to
        # environment detection here would attribute every anonymous HTTP call
        # to whatever launched the *server* - an editor that started `memanto
        # server` would be credited with requests it never made.
        identity = UNKNOWN_CLIENT

    token = set_client(identity)
    try:
        return await call_next(request)
    finally:
        reset_client(token)


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
        "description": "A companion memory agent that lets your agents focus and improve while you keep ownership of everything they learn.",
        "version": __version__,
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    try:
        check_secure_deployment(host="0.0.0.0")
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    uvicorn.run(app, host="0.0.0.0", port=8000)
