"""
Build the right client for the configured backend.

The one place that maps ``backend`` in ``~/.memanto/config.yaml`` to a client,
used by the CLI (``get_client``) and memanto-mcp, so switching backend never
requires reconnecting tools.
"""

import os

from memanto.app.clients.backend import Backend
from memanto.app.utils.errors import AuthenticationError
from memanto.cli.client.sdk_client import SdkClient
from memanto.cli.config.manager import ConfigManager

__all__ = ["build_client"]


def build_client(
    config_manager: ConfigManager | None = None,
    moorcheh_api_key: str | None = None,
    backend: Backend | None = None,
) -> SdkClient:
    """Return a client for the active backend.

    Args:
        config_manager: Config to read; defaults to ``~/.memanto``.
        moorcheh_api_key: Moorcheh key to use on the ``cloud`` backend instead
            of the one in ``~/.memanto/.env`` (memanto-mcp passes its own).
        backend: Build for this backend instead of the active one (moving
            memories reads from the old backend after switching).

    Returns:
        ``HostedClient`` on ``memanto-cloud``, otherwise ``SdkClient``.

    Raises:
        AuthenticationError: If the active backend has no credentials.
    """
    cm = config_manager or ConfigManager()
    backend = backend or cm.get_backend()

    if backend == Backend.MEMANTO_CLOUD:
        from memanto.cli.client.hosted_client import HostedClient

        key = cm.get_memanto_api_key()
        if not key:
            raise AuthenticationError(
                "Not signed in to Memanto Cloud. Run: memanto login"
            )
        return HostedClient(key, base_url=cm.get_memanto_api_url())

    if backend == Backend.ON_PREM:
        # On-prem: no API key needed. The underlying OnPremClient ignores it.
        return SdkClient("on-prem")

    key = moorcheh_api_key or cm.get_api_key()
    if not key:
        raise AuthenticationError(
            "MEMANTO not configured. Run 'memanto' to set up your API key."
        )
    # Ensure env is set for app services on the cloud path.
    os.environ["MOORCHEH_API_KEY"] = key
    return SdkClient(key)
