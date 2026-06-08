"""
PoC test for CWE-200: API key leaked in plaintext via /api/ui/config endpoint.

The GET /api/ui/config endpoint returns the full Moorcheh API key in its
JSON response under the "api_key" field.  There is no authentication on
this endpoint, so any network-reachable caller can steal the key.

This test:
  - FAILS before the fix (response contains "api_key" with plaintext value)
  - PASSES after the fix  (response no longer contains "api_key" field)
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def _mock_config_manager():
    """Patch ConfigManager used by ui_router so we don't touch disk."""
    mock_cm = MagicMock()
    mock_cm.get_api_key.return_value = "mk_test_secret_api_key_12345678"
    mock_cm.get_server_config.return_value = {
        "url": "localhost",
        "port": 8000,
        "auto_start": False,
    }
    mock_cm.get_session_config.return_value = {}
    mock_cm.get_cli_config.return_value = {}
    mock_cm.get_answer_config.return_value = {}
    mock_cm.get_recall_config.return_value = {}
    mock_cm.get_schedule_time.return_value = None
    mock_cm.get_active_session.return_value = ("agent-1", "tok_abc")
    mock_cm.get_backend.return_value = MagicMock(value="cloud")
    mock_cm.get_onprem_config.return_value = {}
    mock_cm.get_data_dir.return_value = "/tmp/memanto"

    with patch(
        "memanto.app.ui.routes.ui_router._config_manager", mock_cm
    ):
        yield mock_cm


@pytest.fixture
def client(_mock_config_manager):
    """TestClient that exercises only the UI router (no startup validation)."""
    from fastapi import FastAPI

    from memanto.app.ui.routes.ui_router import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestApiKeyNotLeaked:
    """Verify that the raw API key is never returned in /api/ui/config."""

    def test_config_endpoint_does_not_return_raw_api_key(self, client):
        resp = client.get("/api/ui/config")
        assert resp.status_code == 200
        data = resp.json()

        # The plaintext api_key field must NOT appear in the response
        assert "api_key" not in data, (
            "The response contains an 'api_key' field that leaks the raw "
            "Moorcheh API key in plaintext. Remove it."
        )

    def test_config_endpoint_still_has_api_key_status_fields(self, client):
        """Ensure the safe metadata fields are still present."""
        resp = client.get("/api/ui/config")
        assert resp.status_code == 200
        data = resp.json()

        # These fields are safe (boolean / masked preview) and should remain
        assert "api_key_configured" in data
        assert data["api_key_configured"] is True
        assert "api_key_preview" in data
        # Preview must NOT contain the full key
        assert data["api_key_preview"] != "mk_test_secret_api_key_12345678"

    def test_config_endpoint_does_not_return_session_token(self, client):
        """Session token should also not leak."""
        resp = client.get("/api/ui/config")
        assert resp.status_code == 200
        data = resp.json()

        assert "session_token" not in data, (
            "The response contains a 'session_token' field that leaks the "
            "session JWT in plaintext. Remove it."
        )
