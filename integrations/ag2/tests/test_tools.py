from unittest.mock import MagicMock

import pytest
from memanto_ag2.register import register_memanto_tools
from memanto_ag2.tools import create_memanto_tools

from memanto.app.utils.errors import SessionError


def test_create_memanto_tools_returns_selected_tools():
    client = MagicMock()
    client.agent_id = "test-agent"
    tools = create_memanto_tools(
        client,
        "test-agent",
        include_remember=True,
        include_recall=True,
        include_answer=False,
    )
    assert len(tools) == 2
    assert {t.__name__ for t in tools} == {"memanto_remember", "memanto_recall"}


def test_memanto_remember_calls_sdk():
    client = MagicMock()
    client.agent_id = "test-agent"
    client.remember.return_value = {"memory_id": "mem-1"}

    remember = create_memanto_tools(client, "test-agent")[0]
    out = remember(
        memory_type="preference",
        title="Language",
        content="Prefers Python",
        confidence=1.0,
        tags="ag2",
    )

    assert "mem-1" in out
    client.remember.assert_called_once()
    assert client.remember.call_args.kwargs["agent_id"] == "test-agent"
    assert client.remember.call_args.kwargs["tags"] == ["ag2"]


def test_memanto_recall_formats_results():
    client = MagicMock()
    client.agent_id = "team"
    client.recall.return_value = {
        "memories": [
            {
                "title": "T",
                "content": "Body",
                "type": "fact",
                "confidence": 0.9,
                "tags": [],
            },
        ]
    }

    recall = next(
        t
        for t in create_memanto_tools(client, "team")
        if t.__name__ == "memanto_recall"
    )
    text = recall(query="facts", limit=5)
    assert "Body" in text
    client.recall.assert_called_once_with(
        agent_id="team", query="facts", limit=5, type=None
    )


def test_memanto_remember_retries_after_session_error():
    client = MagicMock()
    client.agent_id = None

    def _activate(agent_id: str, duration_hours: int = 6) -> None:
        client.agent_id = agent_id

    client.activate_agent.side_effect = _activate
    client.remember.side_effect = [SessionError("no session"), {"memory_id": "mem-2"}]

    remember = create_memanto_tools(client, "test-agent")[0]
    result = remember(
        memory_type="event",
        title="Hi",
        content="Hello",
        confidence=0.8,
    )
    assert "mem-2" in result
    assert client.remember.call_count == 2
    client.activate_agent.assert_called()


def test_register_memanto_tools_wires_ag2_agents():
    client = MagicMock()
    client.agent_id = "bank-1"
    assistant = MagicMock()
    executor = MagicMock()

    tools = register_memanto_tools(
        assistant, executor=executor, client=client, agent_id="bank-1"
    )

    assert len(tools) == 3
    assert assistant.register_for_llm.call_count == 3
    assert executor.register_for_execution.call_count == 3


def test_register_requires_api_key_without_client(monkeypatch):
    from memanto_ag2.config import reset_config

    monkeypatch.delenv("MOORCHEH_API_KEY", raising=False)
    reset_config()
    with pytest.raises(ValueError, match="MOORCHEH_API_KEY"):
        register_memanto_tools(MagicMock(), executor=MagicMock(), agent_id="x")
