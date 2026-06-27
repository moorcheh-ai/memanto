"""Unit tests for shared CLI helpers."""

from unittest.mock import MagicMock, patch

from memanto.app.clients.backend import Backend
from memanto.cli.commands import _shared


def test_existing_session_client_does_not_auto_renew():
    """The deactivate path must not create a fresh session before ending one."""
    config = MagicMock()
    config.get_backend.return_value = Backend.CLOUD
    config.get_api_key.return_value = "test-api-key"
    config.get_active_session.return_value = ("test-agent", "expired-token")
    client = MagicMock()

    with (
        patch.object(_shared, "config_manager", config),
        patch.object(_shared, "SdkClient", return_value=client),
        patch.object(_shared, "get_session_service") as get_session_service,
    ):
        returned = _shared.get_existing_session_client()

    assert returned is client
    assert client.session_token == "expired-token"
    assert client.agent_id == "test-agent"
    config.get_session_config.assert_not_called()
    get_session_service.assert_not_called()
    client.activate_agent.assert_not_called()
