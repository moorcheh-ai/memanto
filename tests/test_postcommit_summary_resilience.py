"""Committed memory operations must not fail on auxiliary summary logging."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from memanto.app.services.session_service import SessionService
from memanto.cli.client.direct_client import DirectClient
from memanto.cli.client.sdk_client import SdkClient


@pytest.mark.parametrize("client_cls", [DirectClient, SdkClient])
def test_remember_returns_committed_result_when_summary_logging_fails(client_cls):
    """A committed single write remains successful when its summary fails."""
    write_service = MagicMock()
    write_service.store_memory.return_value = {
        "id": "mem-committed",
        "namespace": "memanto_agent_test-agent",
        "status": "queued",
        "type": "fact",
    }
    session_service = SessionService.__new__(SessionService)
    session_service.log_memory_to_session_summary = MagicMock(
        side_effect=OSError("summary disk is full")
    )
    session = SimpleNamespace(
        namespace="memanto_agent_test-agent", session_id="session-1"
    )

    with (
        patch.object(
            client_cls, "_get_validated_session_for_agent", return_value=session
        ),
        patch.object(client_cls, "_get_write_service", return_value=write_service),
        patch.object(client_cls, "_get_session_service", return_value=session_service),
    ):
        client = client_cls.__new__(client_cls)
        client.api_key = "test-api-key"
        client.session_token = "session-token"
        result = client.remember(
            agent_id="test-agent",
            memory_type="fact",
            title="Committed fact",
            content="The remote write already succeeded.",
        )

    assert result["memory_id"] == "mem-committed"
    write_service.store_memory.assert_called_once()
    session_service.log_memory_to_session_summary.assert_called_once()


@pytest.mark.parametrize("client_cls", [DirectClient, SdkClient])
def test_batch_remember_returns_committed_result_when_summary_logging_fails(
    client_cls,
):
    """A committed batch remains successful when its summary fails."""
    write_service = MagicMock()
    committed = {
        "total_submitted": 1,
        "successful": 1,
        "failed": 0,
        "results": [{"id": "mem-batch", "status": "success"}],
    }
    write_service.batch_store_memories.return_value = committed
    session_service = SessionService.__new__(SessionService)
    session_service.log_memory_to_session_summary = MagicMock(
        side_effect=OSError("summary directory is read-only")
    )
    session = SimpleNamespace(namespace="memanto_agent_test-agent")

    with (
        patch.object(
            client_cls, "_get_validated_session_for_agent", return_value=session
        ),
        patch.object(client_cls, "_get_write_service", return_value=write_service),
        patch.object(client_cls, "_get_session_service", return_value=session_service),
    ):
        client = client_cls.__new__(client_cls)
        client.api_key = "test-api-key"
        client.session_token = "session-token"
        result = client.batch_remember(
            agent_id="test-agent", memories=[{"content": "Committed batch item"}]
        )

    assert result == committed
    write_service.batch_store_memories.assert_called_once()
    session_service.log_memory_to_session_summary.assert_called_once()


@pytest.mark.parametrize("client_cls", [DirectClient, SdkClient])
def test_delete_returns_committed_result_when_summary_logging_fails(client_cls):
    """A committed deletion remains successful when its summary fails."""
    write_service = MagicMock()
    write_service.delete_memory.return_value = True
    session_service = SessionService.__new__(SessionService)
    session_service.log_memory_deletion_to_session_summary = MagicMock(
        side_effect=OSError("summary file cannot be updated")
    )
    session = SimpleNamespace(
        namespace="memanto_agent_test-agent", session_id="session-1"
    )

    with (
        patch.object(
            client_cls, "_get_validated_session_for_agent", return_value=session
        ),
        patch.object(client_cls, "_get_write_service", return_value=write_service),
        patch.object(client_cls, "_get_session_service", return_value=session_service),
    ):
        client = client_cls.__new__(client_cls)
        client.api_key = "test-api-key"
        client.session_token = "session-token"
        result = client.delete_memory(agent_id="test-agent", memory_id="mem-delete")

    assert result["status"] == "deleted"
    assert result["memory_id"] == "mem-delete"
    write_service.delete_memory.assert_called_once()
    session_service.log_memory_deletion_to_session_summary.assert_called_once()
