"""Deleting an agent's Moorcheh memories together with the agent."""

from unittest.mock import MagicMock, patch

import pytest
from moorcheh_sdk.exceptions import ConflictError, NamespaceNotFound

from memanto.app.models.session import AgentCreate
from memanto.app.services.agent_service import AgentService
from memanto.app.utils.errors import AgentNotFoundError, NamespaceError
from memanto.cli.client.direct_client import DirectClient
from memanto.cli.client.sdk_client import SdkClient


@pytest.fixture
def moorcheh():
    client = MagicMock()
    with patch(
        "memanto.app.services.agent_service.get_moorcheh_client", return_value=client
    ) as factory:
        client.factory = factory
        yield client


def test_delete_agent_memories_deletes_namespace(tmp_path, moorcheh):
    AgentService(agents_dir=tmp_path).delete_agent_memories("bot", "key")

    moorcheh.factory.assert_called_once_with()
    moorcheh.namespaces.delete.assert_called_once_with(
        namespace_name="memanto_agent_bot"
    )


@pytest.mark.parametrize(
    "error",
    [NamespaceNotFound("gone"), Exception("Namespace 'x' not found")],
)
def test_delete_agent_memories_already_gone_is_success(tmp_path, moorcheh, error):
    moorcheh.namespaces.delete.side_effect = error
    AgentService(agents_dir=tmp_path).delete_agent_memories("bot")


def test_delete_agent_memories_failure_raises(tmp_path, moorcheh):
    moorcheh.namespaces.delete.side_effect = Exception("Forbidden")
    with pytest.raises(NamespaceError, match="Forbidden"):
        AgentService(agents_dir=tmp_path).delete_agent_memories("bot")


def test_delete_agent_memories_rejects_unsafe_id(tmp_path, moorcheh):
    with pytest.raises(ValueError):
        AgentService(agents_dir=tmp_path).delete_agent_memories("../x")
    moorcheh.namespaces.delete.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        ConflictError("exists"),
        Exception("Namespace 'memanto_agent_bot' already exists"),
    ],
)
def test_create_agent_reuses_kept_namespace(tmp_path, moorcheh, error):
    moorcheh.namespaces.create.side_effect = error
    service = AgentService(agents_dir=tmp_path)

    agent = service.create_agent(AgentCreate(agent_id="bot"))

    assert agent.namespace == "memanto_agent_bot"
    assert service.get_agent("bot") is not None
    moorcheh.namespaces.delete.assert_not_called()


def test_create_agent_save_failure_keeps_reused_namespace(tmp_path, moorcheh):
    moorcheh.namespaces.create.side_effect = ConflictError("exists")
    service = AgentService(agents_dir=tmp_path)
    with patch.object(service, "_save_agent", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            service.create_agent(AgentCreate(agent_id="bot"))
    moorcheh.namespaces.delete.assert_not_called()


def test_create_agent_save_failure_rolls_back_new_namespace(tmp_path, moorcheh):
    service = AgentService(agents_dir=tmp_path)
    with patch.object(service, "_save_agent", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            service.create_agent(AgentCreate(agent_id="bot"))
    moorcheh.namespaces.delete.assert_called_once_with(
        namespace_name="memanto_agent_bot"
    )


@pytest.fixture(params=[SdkClient, DirectClient])
def client(request):
    c = request.param(api_key="key")
    c._agent_service = MagicMock()
    c._session_service = MagicMock()
    return c


def test_client_delete_agent_keeps_memories_by_default(client):
    result = client.delete_agent("bot")

    client._agent_service.delete_agent_memories.assert_not_called()
    client._agent_service.delete_agent.assert_called_once_with("bot")
    assert result == {"status": "deleted", "agent_id": "bot", "memories_deleted": False}


def test_client_delete_agent_with_memories_deletes_memories_first(client):
    calls = MagicMock()
    client._agent_service.delete_agent_memories = calls.memories
    client._agent_service.delete_agent = calls.agent

    result = client.delete_agent("bot", delete_memories=True)

    assert [c[0] for c in calls.mock_calls] == ["memories", "agent"]
    calls.memories.assert_called_once_with("bot", "key")
    assert result["memories_deleted"] is True


def test_client_delete_agent_memory_failure_leaves_agent(client):
    client._agent_service.delete_agent_memories.side_effect = NamespaceError("boom")

    with pytest.raises(NamespaceError):
        client.delete_agent("bot", delete_memories=True)
    client._agent_service.delete_agent.assert_not_called()
    client._session_service.delete_session.assert_not_called()


def test_client_delete_missing_agent_touches_nothing(client):
    client._agent_service.get_agent.return_value = None

    with pytest.raises(AgentNotFoundError):
        client.delete_agent("ghost", delete_memories=True)
    client._agent_service.delete_agent_memories.assert_not_called()
