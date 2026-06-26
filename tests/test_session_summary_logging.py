from unittest.mock import MagicMock

import pytest


@pytest.mark.parametrize(
    "client_cls_path",
    [
        "memanto.cli.client.direct_client.DirectClient",
        "memanto.cli.client.sdk_client.SdkClient",
    ],
)
def test_remember_logs_to_real_session_summary_id(client_cls_path, monkeypatch):
    module_name, class_name = client_cls_path.rsplit(".", 1)
    module = __import__(module_name, fromlist=[class_name])
    client_cls = getattr(module, class_name)

    session = MagicMock()
    session.session_id = "sess-real-123"
    session.namespace = "memanto_agent_test-agent"

    write_service = MagicMock()
    write_service.store_memory.return_value = {
        "id": "mem-1",
        "namespace": session.namespace,
        "status": "queued",
        "type": "learning",
    }

    session_service = MagicMock()

    monkeypatch.setattr(
        client_cls,
        "_get_validated_session_for_agent",
        lambda self, agent_id: session,
    )
    monkeypatch.setattr(client_cls, "_get_write_service", lambda self: write_service)
    monkeypatch.setattr(
        client_cls, "_get_session_service", lambda self: session_service
    )

    client = client_cls.__new__(client_cls)
    client.session_token = "token"

    client.remember(
        agent_id="test-agent",
        content="Remember the release checklist",
        title="Release checklist",
        memory_type="learning",
    )

    session_service.log_memory_to_session_summary.assert_called_once()
    assert (
        session_service.log_memory_to_session_summary.call_args.kwargs["session_id"]
        == "sess-real-123"
    )


@pytest.mark.parametrize(
    "client_cls_path",
    [
        "memanto.cli.client.direct_client.DirectClient",
        "memanto.cli.client.sdk_client.SdkClient",
    ],
)
def test_batch_remember_logs_to_real_session_summary_id(client_cls_path, monkeypatch):
    module_name, class_name = client_cls_path.rsplit(".", 1)
    module = __import__(module_name, fromlist=[class_name])
    client_cls = getattr(module, class_name)

    session = MagicMock()
    session.session_id = "sess-real-456"
    session.namespace = "memanto_agent_test-agent"

    write_service = MagicMock()
    write_service.batch_store_memories.return_value = {
        "total_submitted": 2,
        "successful": 2,
        "failed": 0,
        "results": [{"id": "mem-1"}, {"id": "mem-2"}],
    }

    session_service = MagicMock()

    monkeypatch.setattr(
        client_cls,
        "_get_validated_session_for_agent",
        lambda self, agent_id: session,
    )
    monkeypatch.setattr(client_cls, "_get_write_service", lambda self: write_service)
    monkeypatch.setattr(
        client_cls, "_get_session_service", lambda self: session_service
    )

    client = client_cls.__new__(client_cls)
    client.session_token = "token"

    client.batch_remember(
        agent_id="test-agent",
        memories=[{"content": "First"}, {"content": "Second"}],
    )

    assert session_service.log_memory_to_session_summary.call_count == 2
    assert [
        call.kwargs["session_id"]
        for call in session_service.log_memory_to_session_summary.call_args_list
    ] == ["sess-real-456", "sess-real-456"]
