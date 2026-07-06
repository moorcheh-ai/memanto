import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import patch
from memanto.app.main import app

@pytest.fixture
async def client():
    # Use ASGITransport to test the FastAPI app directly
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_remember_with_invalid_provenance(client):
    # Setup test headers & mock session dependency
    auth_headers = {"Authorization": "Bearer test-api-key"}
    
    from datetime import datetime, timezone
    from memanto.app.models.session import Session
    
    mock_session = Session(
        session_id="mock-session-id",
        session_token="mock-token",
        agent_id="test_agent",
        actor_id="test_actor",
        moorcheh_api_key="test-api-key",
        namespace="memanto_agent_test_agent",
        started_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc)
    )
    
    from memanto.app.routes.auth_deps import get_current_session
    app.dependency_overrides[get_current_session] = lambda: mock_session
    
    with patch("memanto.app.routes.memory.get_moorcheh_client") as mock_moorcheh:
        # Send an invalid provenance
        response = await client.post(
            "/api/v2/agents/test_agent/remember",
            headers={"X-Session-Token": "mock-token"},
            json={
                "content": "This is a test memory",
                "type": "fact",
                "provenance": "invalid_provenance_value_123"
            }
        )
        
        # Before fix, this returns 500 (Internal Server Error)
        # After fix, this should return 422 (Unprocessable Entity)
        assert response.status_code == 422
        
        # Verify it has a validation error detail
        data = response.json()
        assert "detail" in data

@pytest.mark.asyncio
async def test_batch_remember_with_invalid_provenance(client):
    # Setup test headers & mock session dependency
    from datetime import datetime, timezone
    from memanto.app.models.session import Session
    from memanto.app.routes.auth_deps import get_current_session
    
    mock_session = Session(
        session_id="mock-session-id",
        session_token="mock-token",
        agent_id="test_agent",
        actor_id="test_actor",
        moorcheh_api_key="test-api-key",
        namespace="memanto_agent_test_agent",
        started_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc)
    )
    
    app.dependency_overrides[get_current_session] = lambda: mock_session
    
    with patch("memanto.app.routes.memory.get_moorcheh_client") as mock_moorcheh:
        # Send an invalid provenance in a batch item
        response = await client.post(
            "/api/v2/agents/test_agent/batch-remember",
            headers={"X-Session-Token": "mock-token"},
            json={
                "memories": [
                    {
                        "content": "This is valid memory 1",
                        "type": "fact",
                        "provenance": "explicit_statement"
                    },
                    {
                        "content": "This is invalid memory 2",
                        "type": "fact",
                        "provenance": "invalid_provenance_value_123"
                    }
                ]
            }
        )
        
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

@pytest.mark.asyncio
async def test_daily_summary_output_path_rejected(client):
    from datetime import datetime, timezone
    from memanto.app.models.session import Session
    from memanto.app.routes.auth_deps import get_current_session
    
    mock_session = Session(
        session_id="mock-session-id",
        session_token="mock-token",
        agent_id="test_agent",
        actor_id="test_actor",
        moorcheh_api_key="test-api-key",
        namespace="memanto_agent_test_agent",
        started_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc)
    )
    
    app.dependency_overrides[get_current_session] = lambda: mock_session
    
    response = await client.post(
        "/api/v2/agents/test_agent/daily-summary",
        headers={"X-Session-Token": "mock-token"},
        json={
            "output_path": "/etc/cron.d/malicious_cron"
        }
    )
    
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "output_path" in data["detail"]
