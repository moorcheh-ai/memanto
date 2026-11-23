"""
Memanto Cloud as the server's backend.

``memanto serve`` on the ``memanto-cloud`` backend sets ``MEMANTO_SERVE_CLOUD=1``.
The server then answers the same ``/api/v2`` routes, but stores and reads
memories on Memanto Cloud (``mk_`` key) instead of a Moorcheh namespace.
Sessions stay local, exactly as the CLI keeps them on Memanto Cloud: Memanto
Cloud has no sessions, so the session token only proves which agent a caller
activated on this computer.

``memanto ui --local`` does not set the flag, so the local dashboard keeps
reading Memanto local while it moves memories up to Memanto Cloud.
"""

import copy
import os
import threading

from fastapi import HTTPException

from memanto.app.models.session import Session
from memanto.app.utils.errors import (
    AgentAlreadyExistsError,
    AgentNotFoundError,
    AuthenticationError,
    AuthorizationError,
    MemoryOperationError,
    map_error_to_http_exception,
)
from memanto.cli.client.hosted_client import HostedClient, HostedRequestError
from memanto.cli.config.manager import ConfigManager

CLOUD_SERVE_ENV = "MEMANTO_SERVE_CLOUD"

_base: HostedClient | None = None
_base_lock = threading.Lock()


def cloud_serve_enabled() -> bool:
    """True when this server stores memories on Memanto Cloud."""
    return os.environ.get(CLOUD_SERVE_ENV, "").strip() == "1"


def cloud_api_key() -> str | None:
    """The Memanto Cloud key (``MEMANTO_API_KEY``) this server uses."""
    return ConfigManager().get_memanto_api_key()


def _base_client() -> HostedClient:
    """One HostedClient per process, so requests share its HTTP connection pool."""
    global _base
    with _base_lock:
        if _base is None:
            cm = ConfigManager()
            key = cm.get_memanto_api_key()
            if not key:
                raise AuthenticationError(
                    "Not signed in to Memanto Cloud. Run: memanto login"
                )
            _base = HostedClient(key, base_url=cm.get_memanto_api_url())
        return _base


def cloud_reachable(timeout: float = 3.0) -> bool:
    """True when Memanto Cloud answers and accepts this server's key.

    ``GET /me`` is not metered, so health checks cost nothing.
    """
    try:
        response = _base_client()._http.get("/me", timeout=timeout)
    except Exception:
        return False
    return response.is_success


def cloud_client(session: Session | None = None) -> HostedClient:
    """A client for one request, bound to the caller's validated *session*.

    HostedClient keeps the active session on the instance, so each request gets
    its own shallow copy; the copies share the underlying ``httpx.Client``.
    The route has already validated the token, so the copy starts from it.
    """
    client = copy.copy(_base_client())
    client.session_token = session.session_token if session else None
    client.agent_id = session.agent_id if session else None
    client._cached_session = session
    return client


def cloud_http_error(error: Exception) -> HTTPException:
    """Map a Memanto Cloud failure to the status the local server would return.

    A 401 from Memanto Cloud means this server's ``mk_`` key was rejected, not
    the caller's session. Returning 401 would make clients drop their session
    token and activate again in a loop, so it becomes a 502 instead.
    """
    if isinstance(error, HTTPException):
        return error
    if isinstance(error, HostedRequestError):
        return HTTPException(status_code=error.status_code, detail=str(error))
    if isinstance(error, AuthenticationError):
        return HTTPException(status_code=502, detail=error.message)
    if isinstance(error, ConnectionError):
        return HTTPException(status_code=503, detail=str(error))
    if isinstance(
        error,
        (
            AgentAlreadyExistsError,
            AgentNotFoundError,
            AuthorizationError,
            MemoryOperationError,
        ),
    ):
        return map_error_to_http_exception(error)
    if isinstance(error, ValueError):
        return HTTPException(status_code=400, detail=str(error))
    return map_error_to_http_exception(error)
