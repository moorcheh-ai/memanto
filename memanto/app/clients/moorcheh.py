"""
Moorcheh Client Singleton (backend-aware dispatcher).

Returns either a Moorcheh Cloud client (``moorcheh_sdk.MoorchehClient``) or an
on-prem client (``memanto.app.clients.onprem.OnPremClient``), based on
``settings.MEMANTO_BACKEND``.

Service code keeps calling ``get_moorcheh_client()`` and uses the same
``client.namespaces.* / client.documents.* / client.answer.*`` shape - both
backends expose it.

Security: storage clients are always bound to the *server* credential
(``settings.MOORCHEH_API_KEY`` / on-prem URL). Per-request ``X-Api-Key``
headers must never switch the tenant used for memory read/write.
"""

from typing import Any

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

        ``api_key`` is honored only on the cloud backend, and only when it
        matches the configured server key. Alternate keys are ignored so a
        request cannot pivot the storage tenant.
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

        # Cloud path — always bind to the process-configured server key.
        key_to_use = settings.MOORCHEH_API_KEY
        if api_key and api_key.strip() and api_key.strip() != key_to_use:
            # Reject tenant switching via a foreign key. Callers that already
            # verified the management credential pass the server key itself.
            import logging

            logging.getLogger(__name__).warning(
                "Ignoring non-server Moorcheh API key for storage client "
                "(tenant isolation)."
            )
        client_config = (backend, key_to_use)
        if self._client is None or self._client_config != client_config:
            self._client = MoorchehClient(api_key=key_to_use)
            self._client_config = client_config
        return self._client

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

        key_to_use = settings.MOORCHEH_API_KEY
        if api_key and api_key.strip() and api_key.strip() != key_to_use:
            import logging

            logging.getLogger(__name__).warning(
                "Ignoring non-server Moorcheh API key for async storage client "
                "(tenant isolation)."
            )
        client_config = (backend, key_to_use)
        if self._async_client is None or self._async_client_config != client_config:
            self._async_client = AsyncMoorchehClient(api_key=key_to_use)
            self._async_client_config = client_config
        return self._async_client

    def reset_client(self):
        """Reset cached clients (call after backend switch or in tests)."""
        self._client = None
        self._client_config = None
        self._async_client = None
        self._async_client_config = None


# Global client instance
moorcheh_client = MoorchehClientSingleton()


def get_moorcheh_client(api_key: str | None = None) -> Any:
    """Return the server-bound Moorcheh client.

    Intentionally does **not** read ``X-Api-Key`` from the request. FastAPI
    ``Depends(get_moorcheh_client)`` previously injected client headers and
    allowed a valid session to operate against another Moorcheh account's
    namespaces. Tenant identity is the process configuration only.

    ``api_key`` is accepted for call-site compatibility (e.g. agent service)
    but is ignored unless it matches the configured server key.
    """
    return moorcheh_client.get_client(api_key=api_key)


def get_async_moorcheh_client(api_key: str | None = None) -> Any:
    """Async equivalent of :func:`get_moorcheh_client`."""
    return moorcheh_client.get_async_client(api_key=api_key)
