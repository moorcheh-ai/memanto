"""A locally valid token must authorize the requested client agent only."""

import socket
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from memanto.app.config import settings
from memanto.app.services.session_service import SessionService
from memanto.app.utils.errors import (
    InvalidSessionTokenError,
    SessionError,
    SessionExpiredError,
)
from memanto.cli.client.direct_client import DirectClient
from memanto.cli.client.sdk_client import SdkClient


@pytest.fixture(params=[SdkClient, DirectClient], ids=["sdk", "direct"])
def client(request, tmp_path, monkeypatch):
    """Use real signed sessions and disposable local state, with no network."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(settings, "SESSION_AUTO_RENEW_ENABLED", False)
    monkeypatch.setattr(settings, "SESSION_AUTO_RECREATE_ENABLED", True)
    monkeypatch.setattr(settings, "SESSION_DEFAULT_DURATION_HOURS", 1)
    monkeypatch.setattr(settings, "SESSION_EXTEND_THRESHOLD_MINUTES", 15)
    monkeypatch.setattr(settings, "SESSION_AUTO_RENEW_INTERVAL_HOURS", 1)

    def refuse_network(*args, **kwargs):
        raise AssertionError("This local session regression must not use the network")

    monkeypatch.setattr(socket.socket, "connect", refuse_network)
    monkeypatch.setattr(socket, "getaddrinfo", refuse_network)
    instance = request.param(api_key="isolated-test-key")
    instance.agent_id = "target-agent"
    instance._session_service = SessionService(
        secret_key="isolated-session-scope-test-key-00000000",
        sessions_dir=tmp_path / "sessions",
    )
    instance._read_service = MagicMock()
    instance._read_service.search_memories.return_value = {
        "results": [{"id": "private-marker", "content": "target-agent fixture"}],
        "total_found": 1,
    }
    return instance


def recall(client):
    """Exercise the public client entry point, including session resolution."""
    return client.recall(agent_id="target-agent", query="private marker", limit=1)


def test_recall_rejects_another_agents_valid_token(client):
    other = client._session_service.create_session("other-agent", duration_hours=1)
    client.session_token = other.session_token

    with pytest.raises(SessionError, match="cannot access"):
        recall(client)

    client._read_service.search_memories.assert_not_called()
    assert client._cached_session is None


def test_replaced_token_cannot_reuse_another_tokens_cache(client):
    target = client._session_service.create_session("target-agent", duration_hours=1)
    client.session_token = target.session_token
    assert recall(client)["count"] == 1
    client._read_service.search_memories.reset_mock()

    other = client._session_service.create_session("other-agent", duration_hours=1)
    client.session_token = other.session_token

    with pytest.raises(SessionError, match="cannot access"):
        recall(client)

    client._read_service.search_memories.assert_not_called()
    assert client._cached_session is None


def test_expired_other_agent_token_is_not_recreated(client):
    other = client._session_service.create_session("other-agent", duration_hours=0)
    client.session_token = other.session_token

    with pytest.raises(SessionExpiredError):
        recall(client)

    client._read_service.search_memories.assert_not_called()
    assert client._cached_session is None
    assert (
        client._session_service.get_session("other-agent").session_id
        == other.session_id
    )


def test_matching_expired_token_still_recovers(client):
    expired = client._session_service.create_session("target-agent", duration_hours=0)
    client.session_token = expired.session_token

    assert recall(client)["count"] == 1

    assert client.session_token != expired.session_token
    assert client._cached_session.agent_id == "target-agent"
    assert (
        client._session_service.validate_session(client.session_token).agent_id
        == "target-agent"
    )


def test_matching_cached_token_still_renews(client, monkeypatch):
    monkeypatch.setattr(settings, "SESSION_AUTO_RENEW_ENABLED", True)
    near_expiry = client._session_service.create_session(
        "target-agent", duration_hours=0.01
    )
    client.session_token = near_expiry.session_token
    client._cached_session = near_expiry

    assert recall(client)["count"] == 1

    renewed_token = client.session_token
    assert renewed_token != near_expiry.session_token
    assert (
        client._session_service.validate_session(renewed_token).agent_id
        == "target-agent"
    )
    assert recall(client)["count"] == 1
    assert client.session_token == renewed_token


@pytest.mark.parametrize("revocation", ["logout", "delete", "replace"])
@pytest.mark.parametrize("auto_renew", [False, True])
def test_cached_session_honors_persisted_revocation(
    client, monkeypatch, revocation, auto_renew
):
    target = client._session_service.create_session("target-agent", duration_hours=1)
    client.session_token = target.session_token
    assert recall(client)["count"] == 1
    client._read_service.search_memories.reset_mock()

    # Model an independent CLI/server instance sharing the same session files.
    other_service = SessionService(
        secret_key=client._session_service.secret_key,
        sessions_dir=client._session_service.sessions_dir,
    )
    if revocation == "logout":
        other_service.end_session("target-agent")
    elif revocation == "delete":
        other_service.delete_session("target-agent")
    else:
        # A revoked cache must not renew or take over the replacement session.
        other_service.create_session("target-agent", duration_hours=0.01)
    persisted = other_service.get_session("target-agent")
    monkeypatch.setattr(settings, "SESSION_AUTO_RENEW_ENABLED", auto_renew)

    with pytest.raises(InvalidSessionTokenError):
        other_service.validate_session(target.session_token)
    with pytest.raises(InvalidSessionTokenError):
        recall(client)

    client._read_service.search_memories.assert_not_called()
    assert client._cached_session is None
    assert client.session_token == target.session_token
    assert other_service.get_session("target-agent") == persisted
