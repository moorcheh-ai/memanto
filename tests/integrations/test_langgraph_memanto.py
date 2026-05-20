import pytest
from unittest.mock import AsyncMock, MagicMock
from integrations.langgraph.memanto_manager import MemantoMemoryManager, MemoryEntry

@pytest.fixture
def mock_sdk():
    mock = MagicMock()
    mock.remember = AsyncMock(return_value=True)
    mock.recall = AsyncMock(return_value=None)
    return mock

@pytest.mark.asyncio
async def test_versioned_append_strategy(mock_sdk):
    # Inject mock SDK into manager
    manager = MemantoMemoryManager(agent_id="test_agent", api_key="fake_key")
    manager.client = mock_sdk
    
    # First write
    await manager.remember("user_pref", "Likes Coffee")
    
    # Mock recall to simulate existing memory
    first_entry = MemoryEntry(timestamp="2023-01-01T00:00:00", content="Likes Coffee", metadata={}).model_dump_json()
    mock_sdk.recall.return_value = first_entry
    
    # Second write (should append)
    await manager.remember("user_pref", "Actually likes Tea")
    
    # Verify that the last call to remember contained both entries (the log)
    args, _ = mock_sdk.remember.call_args
    assert "Likes Coffee" in args[2]
    assert "Actually likes Tea" in args[2]
    assert args[2].count("\n") == 1

@pytest.mark.asyncio
async def test_cross_session_recall(mock_sdk):
    manager = MemantoMemoryManager(agent_id="test_agent", api_key="fake_key")
    manager.client = mock_sdk
    
    # Setup mocked log
    entry = MemoryEntry(timestamp="2023-01-01T00:00:00", content="The secret code is 1234", metadata={}).model_dump_json()
    mock_sdk.recall.return_value = entry
    
    result = await manager.recall("secret")
    assert result == "The secret code is 1234"
