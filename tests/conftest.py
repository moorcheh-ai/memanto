from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True, scope="function")
def cleanup_test_sessions():
    """Clean up test-agent and test sessions after each test to prevent pollution."""
    yield
    # After test completes, remove test session files from ~/.memanto/sessions/
    sessions_dir = Path.home() / ".memanto" / "sessions"
    if sessions_dir.exists():
        for agent_id in ["test-agent", "test"]:
            session_file = sessions_dir / f"{agent_id}.json"
            if session_file.exists():
                session_file.unlink()
        # If active marker points to a non-existent agent, clear it
        active_marker = sessions_dir / "active"
        if active_marker.exists():
            try:
                content = active_marker.read_text().strip()
                if (
                    content in ["test-agent", "test"]
                    or not (sessions_dir / f"{content}.json").exists()
                ):
                    active_marker.unlink()
            except Exception:
                pass


@pytest.fixture(autouse=True)
def reset_auto_parse(monkeypatch):
    """Ensure tests are not affected by the local smart_parse config setting."""
    from memanto.app.config import settings

    monkeypatch.setattr(settings, "AUTO_PARSE_ENABLED", True)


@pytest.fixture(autouse=True)
def force_cloud_backend(monkeypatch):
    """Force ``settings.MEMANTO_BACKEND='cloud'`` and a placeholder API key so
    the dispatcher never tries to instantiate ``OnPremClient`` during
    cloud-focused tests, regardless of the developer's local
    ``~/.memanto/config.yaml``. Tests that explicitly exercise the on-prem
    branch (see ``tests/test_backend.py``) do their own per-test save/restore
    and override this safely. Tests that explicitly verify the
    ``MOORCHEH_API_KEY``-missing branch (e.g.
    ``test_create_agent_fails_when_server_key_missing``) use
    ``patch.object(settings, "MOORCHEH_API_KEY", "")`` which temporarily
    overrides this fixture's value.
    """
    from memanto.app.clients.moorcheh import moorcheh_client
    from memanto.app.config import settings

    monkeypatch.setattr(settings, "MEMANTO_BACKEND", "cloud")
    if not settings.MOORCHEH_API_KEY:
        monkeypatch.setattr(settings, "MOORCHEH_API_KEY", "test-api-key")
    moorcheh_client.reset_client()


@pytest.fixture(autouse=True)
def mock_moorcheh_for_tests():
    """Prevent tests from calling real Moorcheh APIs.

    Patches the backend-aware dispatcher and the cloud SDK class used inside
    ``moorcheh.py``; everything that goes through ``get_moorcheh_client`` or
    creates a cloud client lands on the same mock.
    """
    mock_instance = MagicMock()
    mock_instance.namespaces.create.return_value = {"status": "created"}
    mock_instance.namespaces.list.return_value = {"namespaces": []}
    mock_instance.documents.upload.return_value = {"status": "queued"}
    mock_instance.documents.upload_file.return_value = {
        "success": True,
        "fileSize": 0,
        "message": "",
    }
    mock_instance.answer.generate.return_value = {"answer": "", "sources": []}

    with (
        patch(
            "memanto.app.services.agent_service.get_moorcheh_client",
            return_value=mock_instance,
        ),
        patch(
            "memanto.app.clients.moorcheh.MoorchehClient",
            return_value=mock_instance,
        ),
    ):
        yield mock_instance
