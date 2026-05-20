from __future__ import annotations

from pathlib import Path

from graph import build_graph
from memory_store import LocalJsonMemoryStore, MemantoSdkMemoryStore, Memory
from run_demo import TODAY_MESSAGE, YESTERDAY_MESSAGE


def test_cross_session_recall_comes_from_memanto_not_graph_state(tmp_path: Path) -> None:
    store = LocalJsonMemoryStore(tmp_path / "memories.json")
    graph = build_graph(store)

    graph.invoke(
        {
            "agent_id": "test-agent",
            "session_id": "support-yesterday",
            "user_message": YESTERDAY_MESSAGE,
        }
    )
    today = graph.invoke(
        {
            "agent_id": "test-agent",
            "session_id": "support-today",
            "user_message": TODAY_MESSAGE,
        }
    )

    response = today["response"]
    assert "Northstar" in response
    assert "Friday" in response
    assert "May 28" in response
    assert "Ada" in response
    assert all(
        memory["source_session"] == "support-yesterday"
        for memory in today["recalled_memories"]
    )


def test_fresh_agent_has_no_cross_session_memory(tmp_path: Path) -> None:
    store = LocalJsonMemoryStore(tmp_path / "memories.json")
    graph = build_graph(store)

    today = graph.invoke(
        {
            "agent_id": "empty-agent",
            "session_id": "support-today",
            "user_message": TODAY_MESSAGE,
        }
    )

    assert today["recalled_memories"] == []
    assert "do not have durable memory" in today["response"]


def test_sdk_store_activates_agent_and_maps_source_session() -> None:
    class FakeSdkClient:
        def __init__(self) -> None:
            self.activated_agents = []
            self.remember_calls = []
            self.recall_calls = []

        def activate_agent(self, agent_id: str):
            self.activated_agents.append(agent_id)
            return {"agent_id": agent_id}

        def remember(self, **kwargs):
            self.remember_calls.append(kwargs)
            return {"memory_id": "sdk-memory-1"}

        def recall(self, **kwargs):
            self.recall_calls.append(kwargs)
            return {
                "memories": [
                    {
                        "type": "instruction",
                        "title": "Support escalation owner",
                        "content": "Riley wants support escalations routed to Ada.",
                        "confidence": 0.89,
                        "tags": ["support", "escalation", "ada"],
                        "source": "langgraph:support-yesterday",
                    }
                ]
            }

    client = FakeSdkClient()
    store = MemantoSdkMemoryStore(api_key="test-key", client=client)
    memory_id = store.remember(
        "agent-1",
        Memory(
            memory_type="instruction",
            title="Support escalation owner",
            content="Riley wants support escalations routed to Ada.",
            confidence=0.89,
            tags=["support", "escalation", "ada"],
            source_session="support-yesterday",
        ),
    )
    recalled = store.recall("agent-1", "support escalation", limit=1)

    assert memory_id == "sdk-memory-1"
    assert client.activated_agents == ["agent-1"]
    assert client.remember_calls[0]["source"] == "langgraph:support-yesterday"
    assert client.recall_calls[0]["agent_id"] == "agent-1"
    assert recalled[0].source_session == "support-yesterday"
    assert "Ada" in recalled[0].content
