"""Agent deletion must revoke every persisted bearer session."""

from unittest.mock import MagicMock

import pytest

from memanto.app.models.session import AgentPattern
from memanto.app.services.session_service import SessionService
from memanto.app.utils.errors import InvalidSessionTokenError
from memanto.cli.client.direct_client import DirectClient
from memanto.cli.client.sdk_client import SdkClient


@pytest.mark.parametrize("client_cls", [DirectClient, SdkClient])
def test_delete_agent_revokes_session_before_metadata(client_cls, tmp_path):
    session_service = SessionService(
        secret_key="test-session-secret-at-least-32-bytes",
        sessions_dir=tmp_path / "sessions",
    )
    session = session_service.create_session(
        agent_id="doomed-agent",
        pattern=AgentPattern.PROJECT,
        duration_hours=1,
    )
    original_delete_session = session_service.delete_session
    events: list[str] = []
    session_service.delete_session = MagicMock(
        side_effect=lambda agent_id: (
            events.append("session"),
            original_delete_session(agent_id),
        )[1]
    )

    agent_service = MagicMock()
    agent_service.delete_agent.side_effect = lambda _agent_id: events.append("agent")

    client = client_cls(api_key="test-api-key")
    client._session_service = session_service
    client._agent_service = agent_service
    client.agent_id = "doomed-agent"
    client.session_token = session.session_token
    client._cached_session = session

    result = client.delete_agent("doomed-agent")

    assert result == {"status": "deleted", "agent_id": "doomed-agent"}
    assert events == ["session", "agent"]
    session_service.delete_session.assert_called_once_with("doomed-agent")
    agent_service.delete_agent.assert_called_once_with("doomed-agent")
    assert session_service.get_session("doomed-agent") is None
    with pytest.raises(InvalidSessionTokenError, match="no longer active"):
        session_service.validate_session(session.session_token)
    assert client.agent_id is None
    assert client.session_token is None
    assert client._cached_session is None
