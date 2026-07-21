import pytest
from unittest.mock import patch, MagicMock

from memanto.cli.client.sdk_client import SdkClient

@pytest.fixture
def sdk_client():
    return SdkClient("test-agent", "test-config")

def test_delete_agent(sdk_client):
    # Mock the session service
    with patch.object(sdk_client, 'session_service') as mock_session_service:
        # Mock the base delete_agent method
        with patch.object(sdk_client, 'delete_agent', return_value=True) as mock_base_delete:
            # Call the method
            result = sdk_client.delete_agent()

            # Assertions
            assert result is True
            mock_base_delete.assert_called_once()
            mock_session_service.delete_session.assert_called_once_with("test-agent")

def test_delete_agent_failure(sdk_client):
    # Mock the session service
    with patch.object(sdk_client, 'session_service') as mock_session_service:
        # Mock the base delete_agent method to fail
        with patch.object(sdk_client, 'delete_agent', return_value=False) as mock_base_delete:
            # Call the method
            result = sdk_client.delete_agent()

            # Assertions
            assert result is False
            mock_base_delete.assert_called_once()
            mock_session_service.delete_session.assert_not_called()