import pytest
from typer.testing import CliRunner
from memanto.cli.main import app
from unittest.mock import patch, MagicMock

runner = CliRunner()

@patch("memanto.cli.commands.memory.get_client")
@patch("memanto.cli.commands.memory.config_manager")
def test_multi_agent_recall(mock_config_manager, mock_get_client):
    # Mock active session
    mock_config_manager.get_active_session.return_value = ("default_agent", "token")
    
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    
    # Mock recall results
    def mock_recall(agent_id, **kwargs):
        if agent_id == "agent1":
            return {"memories": [{"id": "m1", "title": "Memory 1", "content": "test 1", "score": 0.9, "_queried_agent": "agent1"}]}
        elif agent_id == "agent2":
            return {"memories": [{"id": "m2", "title": "Memory 2", "content": "test 2", "score": 0.8, "_queried_agent": "agent2"}]}
        return {"memories": []}
        
    mock_client.recall.side_effect = mock_recall
    
    result = runner.invoke(app, ["recall", "test", "--agent", "agent1", "--agent", "agent2"])
    
    assert result.exit_code == 0
    assert "agent1" in result.stdout
    assert "agent2" in result.stdout
    assert "Memory 1" in result.stdout
    assert "Memory 2" in result.stdout
    
    # Ensure client was called for both agents
    assert mock_client.recall.call_count == 2
