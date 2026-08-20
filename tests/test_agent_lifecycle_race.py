"""Regression tests for agent deletion racing with session activation."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Any

import pytest

from memanto.app.models.session import AgentCreate, AgentPattern
from memanto.app.services.agent_service import AgentService
from memanto.app.services.session_service import SessionService
from memanto.app.utils.errors import AgentNotFoundError, InvalidSessionTokenError
from memanto.cli.client.direct_client import DirectClient
from memanto.cli.client.sdk_client import SdkClient

CLIENT_CLASSES = [DirectClient, SdkClient]
Client = DirectClient | SdkClient


def _wired_clients(
    tmp_path: Path, client_class: type[DirectClient] | type[SdkClient]
) -> tuple[Client, Client, AgentService, SessionService]:
    """Build two clients that share isolated agent and session services."""
    agent_service = AgentService(agents_dir=tmp_path / "agents")
    session_service = SessionService(
        secret_key="test-secret-key-min-32-bytes-1234",
        sessions_dir=tmp_path / "sessions",
    )
    agent_service.create_agent(
        AgentCreate(
            agent_id="race-agent",
            pattern=AgentPattern.TOOL,
            description="lifecycle race regression fixture",
        ),
        moorcheh_api_key="test-key",
    )

    activating_client = client_class(api_key="test-key")
    deleting_client = client_class(api_key="test-key")
    for client in (activating_client, deleting_client):
        client._agent_service = agent_service  # type: ignore[assignment]
        client._session_service = session_service  # type: ignore[assignment]

    return activating_client, deleting_client, agent_service, session_service


@pytest.mark.parametrize("client_class", CLIENT_CLASSES)
def test_delete_revokes_session_from_inflight_activation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    client_class: type[DirectClient] | type[SdkClient],
) -> None:
    """Deletion that follows activation must leave no usable bearer token."""
    activating, deleting, agent_service, session_service = _wired_clients(
        tmp_path, client_class
    )
    activation_persisted = threading.Event()
    release_activation = threading.Event()
    deletion_started = threading.Event()
    original_save = session_service._save_session

    def pause_after_session_persist(session) -> None:
        original_save(session)
        activation_persisted.set()
        assert release_activation.wait(timeout=3)

    def delete_agent() -> dict[str, Any]:
        deletion_started.set()
        return deleting.delete_agent("race-agent")

    monkeypatch.setattr(session_service, "_save_session", pause_after_session_persist)

    with ThreadPoolExecutor(max_workers=2) as pool:
        activation = pool.submit(activating.activate_agent, "race-agent", 1)
        assert activation_persisted.wait(timeout=3)
        deletion = pool.submit(delete_agent)
        assert deletion_started.wait(timeout=3)
        with pytest.raises(FutureTimeoutError):
            deletion.result(timeout=0.5)
        release_activation.set()
        activation_result = activation.result(timeout=3)
        deletion_result = deletion.result(timeout=3)

    assert deletion_result == {"status": "deleted", "agent_id": "race-agent"}
    assert agent_service.get_agent("race-agent") is None
    assert session_service.get_session("race-agent") is None
    with pytest.raises(InvalidSessionTokenError):
        session_service.validate_session(activation_result["session_token"])


@pytest.mark.parametrize("client_class", CLIENT_CLASSES)
def test_activation_rechecks_agent_after_concurrent_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    client_class: type[DirectClient] | type[SdkClient],
) -> None:
    """Activation must not recreate session state after deletion wins the lock."""
    activating, deleting, agent_service, session_service = _wired_clients(
        tmp_path, client_class
    )
    deletion_entered = threading.Event()
    release_deletion = threading.Event()
    activation_started = threading.Event()
    original_delete = agent_service.delete_agent

    def pause_before_agent_delete(agent_id: str) -> None:
        deletion_entered.set()
        assert release_deletion.wait(timeout=3)
        original_delete(agent_id)

    def activate_agent() -> dict[str, Any]:
        activation_started.set()
        return activating.activate_agent("race-agent", 1)

    monkeypatch.setattr(agent_service, "delete_agent", pause_before_agent_delete)

    with ThreadPoolExecutor(max_workers=2) as pool:
        deletion = pool.submit(deleting.delete_agent, "race-agent")
        assert deletion_entered.wait(timeout=3)
        activation = pool.submit(activate_agent)
        assert activation_started.wait(timeout=3)
        with pytest.raises(FutureTimeoutError):
            activation.result(timeout=0.5)
        release_deletion.set()
        assert deletion.result(timeout=3) == {
            "status": "deleted",
            "agent_id": "race-agent",
        }
        with pytest.raises(AgentNotFoundError):
            activation.result(timeout=3)

    assert agent_service.get_agent("race-agent") is None
    assert session_service.get_session("race-agent") is None
