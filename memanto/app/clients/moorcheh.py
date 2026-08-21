"""
Moorcheh Client Singleton (backend-aware dispatcher).

Returns either a Moorcheh Cloud client (``moorcheh_sdk.MoorchehClient``) or an
on-prem client (``memanto.app.clients.onprem.OnPremClient``), based on
``settings.MEMANTO_BACKEND``.

Service code keeps calling ``get_moorcheh_client()`` and uses the same
``client.namespaces.* / client.documents.* / client.answer.*`` shape - both
backends expose it.
"""

from typing import Annotated, Any

from moorcheh_sdk import AsyncMoorchehClient, MoorchehClient

from memanto.app.clients.backend import Backend, parse_backend
from memanto.app.config import settings

# Re-export the cloud class name for callers that still import it directly.
# New code should use get_moorcheh_client() so the on-prem backend is honored.
__all__ = [
    "MoorchehClient",
    "AsyncMoorchehClient",
    "MoorchehClientSingleton",
    "moorcheh_client",
    "get_moorcheh_client",
    "get_async_moorcheh_client",
]


class MoorchehClientSingleton:
    """Singleton pattern for the active Moorcheh client (cloud or on-prem)."""

    _instance = None
    _client: Any = None
    _client_config: tuple[Any, ...] | None = None
    _async_client: Any = None
    _async_client_config: tuple[Any, ...] | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _backend(self) -> Backend:
        return parse_backend(settings.MEMANTO_BACKEND)

    def get_client(self, api_key: str | None = None) -> Any:
        """Get or create the active Moorcheh client.

        ``api_key`` is honored only on the cloud backend; ignored on on-prem.
        """
        backend = self._backend()
        if backend == Backend.ON_PREM:
            client_config: tuple[Any, ...] = (
                backend,
                settings.MOORCHEH_ONPREM_URL,
                settings.MOORCHEH_ONPREM_TIMEOUT,
            )
            if self._client is None or self._client_config != client_config:
                from memanto.app.clients.onprem import OnPremClient

                self._client = OnPremClient(
                    base_url=settings.MOORCHEH_ONPREM_URL,
                    timeout=settings.MOORCHEH_ONPREM_TIMEOUT,
                )
                self._client_config = client_config
            return self._client

        # Cloud path
        key_to_use = api_key or settings.MOORCHEH_API_KEY
        if key_to_use == settings.MOORCHEH_API_KEY:
            client_config = (backend, key_to_use)
            if self._client is None or self._client_config != client_config:
                self._client = MoorchehClient(api_key=key_to_use)
                self._client_config = client_config
            return self._client
        return MoorchehClient(api_key=key_to_use)

    def get_async_client(self, api_key: str | None = None) -> Any:
        """Get or create the active async Moorcheh client."""
        backend = self._backend()
        if backend == Backend.ON_PREM:
            client_config: tuple[Any, ...] = (
                backend,
                settings.MOORCHEH_ONPREM_URL,
                settings.MOORCHEH_ONPREM_TIMEOUT,
            )
            if self._async_client is None or self._async_client_config != client_config:
                from memanto.app.clients.onprem import AsyncOnPremClient

                self._async_client = AsyncOnPremClient(
                    base_url=settings.MOORCHEH_ONPREM_URL,
                    timeout=settings.MOORCHEH_ONPREM_TIMEOUT,
                )
                self._async_client_config = client_config
            return self._async_client

        key_to_use = api_key or settings.MOORCHEH_API_KEY
        if key_to_use == settings.MOORCHEH_API_KEY:
            client_config = (backend, key_to_use)
            if self._async_client is None or self._async_client_config != client_config:
                self._async_client = AsyncMoorchehClient(api_key=key_to_use)
                self._async_client_config = client_config
            return self._async_client
        return AsyncMoorchehClient(api_key=key_to_use)

    def reset_client(self):
        """Reset cached clients (call after backend switch or in tests)."""
        self._client = None
        self._client_config = None
        self._async_client = None
        self._async_client_config = None


# Global client instance
moorcheh_client = MoorchehClientSingleton()


def get_moorcheh_client() -> Any:
    """Dependency injection function (cloud or on-prem).

    The backend credential is ALWAYS the server-configured key
    (settings.MOORCHEH_API_KEY). Previously this dependency read the
    ``X-Api-Key`` request header and built a client with the caller-chosen key
    (MEM-02, confused deputy): any holder of a valid session token could run
    server-side memory/LLM operations under their own Moorcheh credentials,
    bypassing the server key's quotas, billing and audit, and potentially
    reaching other tenants' namespaces. Server-to-backend credentials must
    never be decided by the request. The ``api_key`` parameter was removed
    entirely — FastAPI would otherwise expose it as a query parameter
    (``?api_key=...``), re-opening the same bypass (CodeRabbit review).
    """
    return moorcheh_client.get_client()

def get_async_moorcheh_client() -> Any:
    """Dependency injection function for async client (cloud or on-prem).

    Credentials are always the server-configured key (see get_moorcheh_client,
    MEM-02); the request header and query parameter are never used.
    """
    return moorcheh_client.get_async_client()
