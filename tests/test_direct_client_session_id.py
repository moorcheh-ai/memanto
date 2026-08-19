"""
Test that DirectClient uses the actual session_id (not "unknown") when
logging memories to session summary MD files.

References #770
"""

from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path
import json


def _make_client():
    """Create a DirectClient with mocked services."""
    from memanto.cli.client.direct_client import DirectClient

    client = DirectClient(api_key="test-key")
    client.session_token = "fake-jwt-token"
    client.agent_id = "test-agent"

    # Mock the moorcheh client
    client._moorcheh = MagicMock()

    # Mock write service
    mock_write = MagicMock()
    mock_write.store_memory.return_value = {
        "id": "mem-123",
        "status": "queued",
        "namespace": "memanto_agent_test-agent",
        "type": "fact",
    }
    mock_write.batch_store_memories.return_value = {
        "total_submitted": 1,
        "successful": 1,
        "failed": 0,
        "rejected": 0,
        "results": [{"id": "mem-123", "status": "queued"}],
        "namespace": "memanto_agent_test-agent",
    }
    client._write_service = mock_write

    # Mock session service
    mock_session_svc = MagicMock()
    client._session_service = mock_session_svc

    # Mock session object
    mock_session = MagicMock()
    mock_session.session_id = "sess_abc123"
    mock_session.agent_id = "test-agent"
    mock_session.namespace = "memanto_agent_test-agent"
    mock_session.is_active.return_value = True
    mock_session.pattern = MagicMock()
    mock_session.pattern.value = "tool"

    # Mock _get_validated_session_for_agent to return our mock session
    client._get_validated_session_for_agent = MagicMock(return_value=mock_session)
    client._cached_session = mock_session

    return client, mock_session_svc, mock_session


def test_remember_uses_actual_session_id():
    """remember() should pass the real session_id to session summary logging."""
    client, mock_session_svc, mock_session = _make_client()

    client.remember(
        agent_id="test-agent",
        memory_type="fact",
        title="Test memory",
        content="This is a test memory",
    )

    # Verify session summary logging was called with the real session_id
    mock_session_svc.try_log_memory_to_session_summary.assert_called_once()
    call_kwargs = mock_session_svc.try_log_memory_to_session_summary.call_args
    assert call_kwargs.kwargs["session_id"] == "sess_abc123", (
        f"Expected session_id='sess_abc123', got '{call_kwargs.kwargs['session_id']}'"
    )


def test_batch_remember_uses_actual_session_id():
    """batch_remember() should pass the real session_id to session summary logging."""
    client, mock_session_svc, mock_session = _make_client()

    memories = [
        {
            "content": "First memory",
            "title": "First",
            "type": "fact",
        }
    ]

    client.batch_remember(agent_id="test-agent", memories=memories)

    # Verify session summary logging was called with the real session_id
    mock_session_svc.try_log_memory_to_session_summary.assert_called_once()
    call_kwargs = mock_session_svc.try_log_memory_to_session_summary.call_args
    assert call_kwargs.kwargs["session_id"] == "sess_abc123", (
        f"Expected session_id='sess_abc123', got '{call_kwargs.kwargs['session_id']}'"
    )


def test_remember_does_not_use_unknown_session_id():
    """remember() must NOT pass 'unknown' as session_id."""
    client, mock_session_svc, mock_session = _make_client()

    client.remember(
        agent_id="test-agent",
        memory_type="fact",
        title="Test memory",
        content="This is a test memory",
    )

    mock_session_svc.try_log_memory_to_session_summary.assert_called_once()
    call_kwargs = mock_session_svc.try_log_memory_to_session_summary.call_args
    assert call_kwargs.kwargs["session_id"] != "unknown", (
        "session_id should not be 'unknown'"
    )


def test_batch_remember_does_not_use_unknown_session_id():
    """batch_remember() must NOT pass 'unknown' as session_id."""
    client, mock_session_svc, mock_session = _make_client()

    memories = [{"content": "Test memory", "type": "fact"}]

    client.batch_remember(agent_id="test-agent", memories=memories)

    mock_session_svc.try_log_memory_to_session_summary.assert_called_once()
    call_kwargs = mock_session_svc.try_log_memory_to_session_summary.call_args
    assert call_kwargs.kwargs["session_id"] != "unknown", (
        "session_id should not be 'unknown'"
    )
