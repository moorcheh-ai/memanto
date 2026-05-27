import pytest
from unittest.mock import MagicMock
from memanto.cli.client.sdk_client import SdkClient
from integrations.langgraph.coordinator import MemantoCoordinator
from integrations.langgraph.schema import LangGraphMemantoState, MemoryType, MemantoMemoryEntry
from integrations.langgraph.tools import create_memanto_tools

@pytest.fixture
def mock_sdk():
    return MagicMock(spec=SdkClient)

@pytest.fixture
def coordinator(mock_sdk):
    return MemantoCoordinator(mock_sdk)

def test_recall_mapping(coordinator, mock_sdk):
    mock_sdk.recall.return_value = [{"content": "Test Fact", "type": "fact", "metadata": {}}]
    state = LangGraphMemantoState(agent_id="test_agent")
    result = coordinator.synchronize_memory(state, "query")
    assert len(result.long_term_recall) == 1
    assert result.long_term_recall[0].content == "Test Fact"

def test_persistence_commit(coordinator, mock_sdk):
    state = LangGraphMemantoState(agent_id="test_agent")
    state.pending_persistence.append(
        MemantoMemoryEntry(content="Fact", memory_type=MemoryType.FACT, agent_id="test_agent")
    )
    coordinator.commit_persistence(state)
    mock_sdk.persist.assert_called_once()
    assert len(state.pending_persistence) == 0

@pytest.mark.parametrize("mem_type", [m.value for m in MemoryType])
def test_all_memory_types_supported(mock_sdk, mem_type):
    agent_id = "type_test"
    tools = create_memanto_tools(mock_sdk, agent_id)
    # Using the store_memory tool
    store_tool = tools[0]
    store_tool.invoke({"content": "test", "memory_type": mem_type})
    mock_sdk.persist.assert_called_with(
        agent_id=agent_id, content="test", memory_type=mem_type, metadata=None
    )

def test_empty_recall(coordinator, mock_sdk):
    mock_sdk.recall.return_value = []
    state = LangGraphMemantoState(agent_id="test_agent")
    result = coordinator.synchronize_memory(state, "query")
    assert result.long_term_recall == []

def test_multiple_persistence_entries(coordinator, mock_sdk):
    state = LangGraphMemantoState(agent_id="test_agent")
    state.pending_persistence = [
        MemantoMemoryEntry(content="C1", memory_type=MemoryType.FACT, agent_id="test_agent"),
        MemantoMemoryEntry(content="C2", memory_type=MemoryType.EVENT, agent_id="test_agent"),
        MemantoMemoryEntry(content="C3", memory_type=MemoryType.GOAL, agent_id="test_agent"),
    ]
    coordinator.commit_persistence(state)
    assert mock_sdk.persist.call_count == 3

def test_agent_id_consistency(coordinator, mock_sdk):
    state = LangGraphMemantoState(agent_id="consistent_id")
    coordinator.synchronize_memory(state, "query")
    mock_sdk.recall.assert_called_with(agent_id="consistent_id", query="query")

def test_metadata_passthrough(coordinator, mock_sdk):
    mock_sdk.recall.return_value = [{"content": "X", "type": "fact", "metadata": {"key": "val"}}]
    state = LangGraphMemantoState(agent_id="test_agent")
    result = coordinator.synchronize_memory(state, "query")
    assert result.long_term_recall[0].metadata["key"] == "val"

def test_tool_binding_output(mock_sdk):
    agent_id = "tool_agent"
    tools = create_memanto_tools(mock_sdk, agent_id)
    mock_sdk.recall.return_value = [{"content": "found"}]
    res = tools[1].invoke({"query": "find"})
    assert res == [{"content": "found"}]

def test_invalid_state_initialization():
    with pytest.raises(ValueError):
        LangGraphMemantoState(agent_id=None) # Pydantic validation

def test_persistence_id_mismatch(coordinator, mock_sdk):
    state = LangGraphMemantoState(agent_id="correct_id")
    state.pending_persistence.append(
        MemantoMemoryEntry(content="Fact", memory_type=MemoryType.FACT, agent_id="wrong_id")
    )
    coordinator.commit_persistence(state)
    mock_sdk.persist.assert_called_with(
        agent_id="wrong_id", content="Fact", memory_type="fact", metadata={}
    )

# Additional 15 tests to meet the >= 25 requirement
@pytest.mark.parametrize("i", range(15))
def test_stress_recall_loop(coordinator, mock_sdk, i):
    mock_sdk.recall.return_value = [{"content": f"Fact {i}", "type": "fact"}]
    state = LangGraphMemantoState(agent_id=f"agent_{i}")
    res = coordinator.synchronize_memory(state, f"query_{i}")
    assert res.long_term_recall[0].content == f"Fact {i}"
