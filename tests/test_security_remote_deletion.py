"""Regression tests for fail-closed remote memory deletion."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from memanto.app.routes import sessions


@pytest.mark.asyncio
async def test_delete_backup_failure_preserves_local_agent(monkeypatch):
    """A failed cloud delete must not orphan remotely retained memories."""
    agent = SimpleNamespace(namespace="memanto_agent_security-test")
    local_agent_service = Mock()
    local_agent_service.get_agent.return_value = agent

    namespaces = Mock()
    namespaces.delete.side_effect = RuntimeError("backend unavailable")
    remote_client = SimpleNamespace(namespaces=namespaces)

    monkeypatch.setattr(sessions, "agent_service", local_agent_service)
    monkeypatch.setattr(
        sessions.moorcheh_clients, "get_moorcheh_client", lambda: remote_client
    )

    with pytest.raises(HTTPException) as exc_info:
        await sessions.delete_agent(
            "security-test", delete_backup_too=True, moorcheh_api_key="test-key"
        )

    assert exc_info.value.status_code == 502
    assert "preserved" in exc_info.value.detail
    assert "backend unavailable" not in exc_info.value.detail
    local_agent_service.delete_agent.assert_not_called()
