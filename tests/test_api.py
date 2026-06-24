import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from memanto.app.config import settings
from memanto.app.main import app

# Set test environment
os.environ["MOORCHEH_API_KEY"] = "test-api-key"


@pytest.fixture(autouse=True, scope="function")
def test_env_setup():
    """Setup an isolated environment for agent and session metadata for each test"""
    # Create temp dir
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir)

    # Patch all services/routes that use Path.home()
    with (
        patch("memanto.app.services.agent_service.Path.home", return_value=temp_path),
        patch("memanto.app.services.session_service.Path.home", return_value=temp_path),
    ):
        from memanto.app.routes.sessions import agent_service
        from memanto.app.services import session_service as session_service_mod

        # Force a fresh SessionService bound to the patched Path.home so the
        # singleton's sessions_dir always points inside this test's temp dir.
        session_service_mod._session_service = None
        session_service = session_service_mod.get_session_service()

        orig_agent_dir = agent_service.agents_dir
        agent_service.agents_dir = temp_path / ".memanto" / "agents"

        agent_service.agents_dir.mkdir(parents=True, exist_ok=True)
        session_service.sessions_dir.mkdir(parents=True, exist_ok=True)

        try:
            yield temp_path
        finally:
            agent_service.agents_dir = orig_agent_dir
            # Drop the temp-bound singleton so later tests rebuild it against
            # the real Path.home() instead of inheriting a deleted temp dir.
            session_service_mod._session_service = None
            shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
async def client():
    """Create an async client for testing the FastAPI app"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers():
    """Return standard auth headers"""
    return {"Authorization": "Bearer test-api-key"}


@pytest.fixture(autouse=True)
def mock_moorcheh():
    """Mock the Moorcheh SDK client globally across services"""
    # Reset the singleton to ensure it picks up the patched class
    from memanto.app.clients.moorcheh import moorcheh_client

    moorcheh_client.reset_client()

    with (
        patch(
            "memanto.app.services.agent_service.get_moorcheh_client"
        ) as mock_agent_client,
        patch("memanto.app.clients.moorcheh.MoorchehClient") as mock_moorcheh_cls,
        patch(
            "memanto.app.clients.moorcheh.AsyncMoorchehClient"
        ) as mock_async_moorcheh_cls,
    ):
        # Setup mock instances
        mock_instance = MagicMock()
        mock_async_instance = MagicMock()

        mock_agent_client.return_value = mock_instance
        mock_moorcheh_cls.return_value = mock_instance
        mock_async_moorcheh_cls.return_value = mock_async_instance

        # Sync mock returns
        mock_instance.namespaces.create.return_value = {"status": "created"}
        mock_instance.namespaces.list.return_value = {"namespaces": []}
        mock_instance.documents.get.return_value = {"documents": []}
        mock_instance.documents.upload.return_value = {
            "status": "success",
            "id": "mem-1",
        }
        mock_instance.documents.upload_file.return_value = {
            "success": True,
            "fileSize": 1024,
        }
        mock_instance.similarity_search.query.return_value = {
            "results": [],
            "total_found": 0,
        }
        mock_instance.answer.generate.return_value = {
            "answer": "Mocked answer",
            "sources": [],
        }

        # Async mock returns
        mock_async_instance.namespaces.create = AsyncMock(
            return_value={"status": "created"}
        )
        mock_async_instance.namespaces.list = AsyncMock(return_value={"namespaces": []})
        mock_async_instance.documents.get = AsyncMock(return_value={"documents": []})
        mock_async_instance.documents.upload = AsyncMock(
            return_value={"status": "success", "id": "mem-1"}
        )
        mock_async_instance.documents.upload_file = AsyncMock(
            return_value={"success": True, "fileSize": 1024}
        )
        mock_async_instance.similarity_search.query = AsyncMock(
            return_value={"results": [], "total_found": 0}
        )
        mock_async_instance.answer.generate = AsyncMock(
            return_value={"answer": "Mocked answer", "sources": []}
        )

        yield mock_instance

        # Reset again after test
        moorcheh_client.reset_client()


class TestMEMANTOAPI:
    """Contract tests for MEMANTO session-based API"""

    TEST_AGENT_ID = "test-api-agent"

    @pytest.mark.asyncio
    async def test_create_agent(self, client, auth_headers):
        """Test creating a new agent"""
        payload = {
            "agent_id": self.TEST_AGENT_ID,
            "pattern": "support",
            "description": "Test Agent for API tests",
        }
        response = await client.post(
            "/api/v2/agents", headers=auth_headers, json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["agent_id"] == self.TEST_AGENT_ID
        assert "namespace" in data
        assert "metadata" not in data

    @pytest.mark.asyncio
    async def test_create_agent_without_authorization_header(self, client):
        """Test creating a new agent using server-configured API key"""
        payload = {
            "agent_id": "server-key-agent",
            "pattern": "support",
        }
        response = await client.post("/api/v2/agents", json=payload)
        assert response.status_code == 201
        assert response.json()["agent_id"] == "server-key-agent"

    @pytest.mark.asyncio
    async def test_create_agent_fails_when_server_key_missing(self, client):
        """Test failure when server API key is not configured"""
        payload = {
            "agent_id": "missing-key-agent",
            "pattern": "support",
        }
        with patch.object(settings, "MOORCHEH_API_KEY", ""):
            response = await client.post("/api/v2/agents", json=payload)
        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_list_agents(self, client, auth_headers):
        """Test listing agents"""
        response = await client.get("/api/v2/agents", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
        if data["agents"]:
            assert "metadata" not in data["agents"][0]

    @pytest.mark.asyncio
    async def test_activate_session(self, client, auth_headers):
        """Test activating an agent session"""
        # Ensure agent exists (will be created in memory by AgentService for this test session)
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID, "pattern": "support"},
        )

        url = f"/api/v2/agents/{self.TEST_AGENT_ID}/activate"
        response = await client.post(url, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "session_token" in data
        assert "session_id" in data
        assert data["agent_id"] == self.TEST_AGENT_ID

    @pytest.mark.asyncio
    async def test_remember_with_session(self, client, auth_headers, mock_moorcheh):
        """Test storing memory with session token"""
        # Setup session
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        activate_url = f"/api/v2/agents/{self.TEST_AGENT_ID}/activate"
        activate_response = await client.post(activate_url, headers=auth_headers)
        session_token = activate_response.json()["session_token"]

        # Mock the store_memory result
        mock_moorcheh.documents.upload.return_value = {
            "status": "success",
            "ids": ["mem-1"],
        }

        # Store memory
        remember_url = f"/api/v2/agents/{self.TEST_AGENT_ID}/remember"
        headers = {**auth_headers, "X-Session-Token": session_token}
        params = {
            "memory_type": "fact",
            "title": "API Test",
            "confidence": 0.9,
        }
        json_body = {
            "content": "Testing the API with mocks",
        }
        response = await client.post(
            remember_url, headers=headers, params=params, json=json_body
        )

        assert response.status_code == 200
        assert response.json()["status"] == "queued"

    @pytest.mark.asyncio
    async def test_answer_with_session(self, client, auth_headers, mock_moorcheh):
        """Test RAG answer with session token"""
        # Setup session
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        activate_resp = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate", headers=auth_headers
        )
        token = activate_resp.json()["session_token"]

        # Mock RAG answer
        mock_moorcheh.answer.generate.return_value = {
            "answer": "This is a mocked answer",
            "sources": ["source-1"],
        }

        # Ask question
        headers = {**auth_headers, "X-Session-Token": token}
        payload = {"question": "What is being tested?"}
        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/answer", headers=headers, json=payload
        )

        assert response.status_code == 200
        assert "mocked answer" in response.json()["answer"]
        call_kwargs = mock_moorcheh.answer.generate.call_args.kwargs
        assert "threshold" not in call_kwargs

    @pytest.mark.asyncio
    async def test_answer_with_kiosk_mode_uses_default_threshold(
        self, client, auth_headers, mock_moorcheh
    ):
        """Kiosk mode without an explicit threshold falls back to 0.15."""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        activate_resp = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate", headers=auth_headers
        )
        token = activate_resp.json()["session_token"]

        headers = {**auth_headers, "X-Session-Token": token}
        payload = {"question": "What is being tested?", "kiosk_mode": True}
        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/answer", headers=headers, json=payload
        )

        assert response.status_code == 200
        call_kwargs = mock_moorcheh.answer.generate.call_args.kwargs
        assert call_kwargs["kiosk_mode"] is True
        assert call_kwargs["threshold"] == 0.15

    @pytest.mark.asyncio
    async def test_answer_with_kiosk_mode_forwards_explicit_threshold(
        self, client, auth_headers, mock_moorcheh
    ):
        """Kiosk mode + explicit threshold: REST forwards it unchanged."""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        activate_resp = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate", headers=auth_headers
        )
        token = activate_resp.json()["session_token"]

        headers = {**auth_headers, "X-Session-Token": token}
        payload = {
            "question": "What is being tested?",
            "kiosk_mode": True,
            "threshold": 0.42,
        }
        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/answer", headers=headers, json=payload
        )

        assert response.status_code == 200
        call_kwargs = mock_moorcheh.answer.generate.call_args.kwargs
        assert call_kwargs["threshold"] == 0.42

    @pytest.mark.asyncio
    async def test_answer_accepts_ai_model_field(
        self, client, auth_headers, mock_moorcheh
    ):
        """Test ai_model request field maps to answer.generate ai_model."""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        activate_resp = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate", headers=auth_headers
        )
        token = activate_resp.json()["session_token"]

        headers = {**auth_headers, "X-Session-Token": token}
        payload = {
            "question": "What is being tested?",
            "ai_model": "anthropic.claude-sonnet-4-6",
        }
        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/answer", headers=headers, json=payload
        )

        assert response.status_code == 200
        call_kwargs = mock_moorcheh.answer.generate.call_args.kwargs
        assert call_kwargs["ai_model"] == "anthropic.claude-sonnet-4-6"

    @pytest.mark.asyncio
    async def test_recall_with_session(self, client, auth_headers, mock_moorcheh):
        """Test semantic recall with session token"""
        # Setup session
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        activate_resp = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate", headers=auth_headers
        )
        token = activate_resp.json()["session_token"]

        # Mock recall
        mock_moorcheh.similarity_search.query.return_value = {
            "results": [{"content": "Result 1", "score": 0.95}],
            "total_found": 1,
        }

        # Query
        headers = {**auth_headers, "X-Session-Token": token}
        payload = {"query": "test query", "limit": 1}
        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/recall",
            headers=headers,
            json=payload,
        )

        assert response.status_code == 200
        assert len(response.json()["memories"]) == 1

    @pytest.mark.asyncio
    async def test_recall_accepts_type_filter(
        self, client, auth_headers, mock_moorcheh
    ):
        """Test recall request uses 'type' field for memory filters."""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        activate_resp = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate", headers=auth_headers
        )
        token = activate_resp.json()["session_token"]

        headers = {**auth_headers, "X-Session-Token": token}
        payload = {"query": "test query", "type": ["fact"]}
        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/recall",
            headers=headers,
            json=payload,
        )

        assert response.status_code == 200
        call_kwargs = mock_moorcheh.similarity_search.query.call_args.kwargs
        assert "memory_type:fact" in call_kwargs["query"]

    @pytest.mark.asyncio
    async def test_get_agent(self, client, auth_headers):
        """Test getting agent details"""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        response = await client.get(
            f"/api/v2/agents/{self.TEST_AGENT_ID}", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == self.TEST_AGENT_ID
        assert "metadata" not in data

    @pytest.mark.asyncio
    async def test_delete_agent(self, client, auth_headers, mock_moorcheh):
        """Test deleting agent"""
        await client.post(
            "/api/v2/agents", headers=auth_headers, json={"agent_id": "to-delete"}
        )
        response = await client.delete("/api/v2/agents/to-delete", headers=auth_headers)
        assert response.status_code == 200
        mock_moorcheh.namespaces.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_agent_with_backup_delete(
        self, client, auth_headers, mock_moorcheh
    ):
        """Test deleting agent including Moorcheh backup deletion."""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": "to-delete-remote"},
        )
        response = await client.delete(
            "/api/v2/agents/to-delete-remote?delete-backup-too=true",
            headers=auth_headers,
        )
        assert response.status_code == 200
        mock_moorcheh.namespaces.delete.assert_called_once_with(
            namespace_name="memanto_agent_to-delete-remote"
        )

    @pytest.mark.asyncio
    async def test_deactivate_agent(self, client, auth_headers):
        """Test deactivating session"""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        activate_resp = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate", headers=auth_headers
        )
        token = activate_resp.json()["session_token"]
        headers = {**auth_headers, "X-Session-Token": token}

        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/deactivate", headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "ended_at" in data

    @pytest.mark.asyncio
    async def test_global_status(self, client, auth_headers):
        """Test GET /api/v2/status returns active session info without auth params"""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate", headers=auth_headers
        )

        response = await client.get("/api/v2/status")
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == self.TEST_AGENT_ID
        assert "session_id" in data
        assert "time_remaining_seconds" in data

    @pytest.mark.asyncio
    async def test_remember_body_type_is_respected(
        self, client, auth_headers, mock_moorcheh
    ):
        """Test single remember accepts explicit type from JSON body"""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        activate_resp = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate", headers=auth_headers
        )
        token = activate_resp.json()["session_token"]

        mock_moorcheh.documents.upload.return_value = {"status": "success"}

        headers = {**auth_headers, "X-Session-Token": token}
        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/remember",
            headers=headers,
            json={
                "content": "my favourite hobby is to listen music. I am musicaholic",
                "type": "fact",
            },
        )

        assert response.status_code == 200
        # Explicit type is respected and echoed back in the response.
        assert response.json()["type"] == "fact"
        uploaded_doc = mock_moorcheh.documents.upload.call_args.kwargs["documents"][0]
        assert uploaded_doc["memory_type"] == "fact"

    @pytest.mark.asyncio
    async def test_remember_auto_parses_type_when_omitted(
        self, client, auth_headers, mock_moorcheh
    ):
        """Test single remember auto-detects the type when none is provided"""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        activate_resp = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate", headers=auth_headers
        )
        token = activate_resp.json()["session_token"]

        mock_moorcheh.documents.upload.return_value = {"status": "success"}

        headers = {**auth_headers, "X-Session-Token": token}
        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/remember",
            headers=headers,
            json={"content": "I really love using Python for data work"},
        )

        assert response.status_code == 200
        assert response.json()["type"] == "preference"
        uploaded_doc = mock_moorcheh.documents.upload.call_args.kwargs["documents"][0]
        assert uploaded_doc["memory_type"] == "preference"

    @pytest.mark.asyncio
    async def test_global_status_no_active_session(self, client):
        """Test GET /api/v2/status returns 404 when no session is active"""
        response = await client.get("/api/v2/status")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_batch_remember_api(self, client, auth_headers, mock_moorcheh):
        """Test batch storage via API"""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        activate_resp = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate", headers=auth_headers
        )
        token = activate_resp.json()["session_token"]

        # Backend uses self.client.documents.upload for batch too
        mock_moorcheh.documents.upload.return_value = {"status": "success"}

        headers = {**auth_headers, "X-Session-Token": token}
        payload = {
            "memories": [
                {"content": "Batch 1", "type": "fact", "confidence": 0.9},
                {"content": "Batch 2", "type": "fact", "confidence": 0.8},
            ]
        }
        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/batch-remember",
            headers=headers,
            json=payload,
        )
        assert response.status_code == 200
        assert response.json()["successful"] == 2

    @pytest.mark.asyncio
    async def test_delete_memory_with_session(
        self, client, auth_headers, mock_moorcheh
    ):
        """Test deleting one memory from the active agent namespace."""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        activate_resp = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate", headers=auth_headers
        )
        token = activate_resp.json()["session_token"]
        headers = {**auth_headers, "X-Session-Token": token}
        mock_moorcheh.documents.delete.return_value = {"actual_deletions": 1}

        response = await client.delete(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/memories/mem-123",
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"
        assert data["memory_id"] == "mem-123"
        mock_moorcheh.documents.delete.assert_called_once_with(
            namespace_name="memanto_agent_test-api-agent", ids=["mem-123"]
        )

    @pytest.mark.asyncio
    async def test_delete_memory_not_found(self, client, auth_headers, mock_moorcheh):
        """Deleting a missing memory returns a clear 404."""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        activate_resp = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate", headers=auth_headers
        )
        token = activate_resp.json()["session_token"]
        headers = {**auth_headers, "X-Session-Token": token}
        mock_moorcheh.documents.delete.return_value = {"actual_deletions": 0}

        response = await client.delete(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/memories/missing-memory",
            headers=headers,
        )

        assert response.status_code == 404
        assert "missing-memory" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_memory_rejects_session_agent_mismatch(
        self, client, auth_headers, mock_moorcheh
    ):
        """Deleting through another agent's session is forbidden."""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        activate_resp = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate", headers=auth_headers
        )
        token = activate_resp.json()["session_token"]
        headers = {**auth_headers, "X-Session-Token": token}

        response = await client.delete(
            "/api/v2/agents/other-agent/memories/mem-123",
            headers=headers,
        )

        assert response.status_code == 403
        assert response.json()["detail"]["error"] == "AuthorizationError"
        mock_moorcheh.documents.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_extract_memories_from_conversation_dry_run(
        self, client, auth_headers, mock_moorcheh
    ):
        """Conversation extraction can preview candidates without writing."""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        activate_resp = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate", headers=auth_headers
        )
        assert activate_resp.status_code == 200, activate_resp.text
        token = activate_resp.json()["session_token"]
        headers = {**auth_headers, "X-Session-Token": token}

        mock_moorcheh.answer.generate.return_value = {
            "answer": json.dumps(
                [
                    {
                        "type": "preference",
                        "title": "Summary style",
                        "content": "The user prefers concise summaries.",
                        "confidence": 0.9,
                    }
                ]
            ),
            "sources": [],
        }

        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/remember/extract",
            headers=headers,
            json={
                "dry_run": True,
                "messages": [
                    {"role": "user", "content": "Please keep summaries concise."}
                ],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["dry_run"] is True
        assert data["count"] == 1
        assert data["candidates"][0]["type"] == "preference"
        mock_moorcheh.documents.upload.assert_not_called()

    @pytest.mark.asyncio
    async def test_extract_memories_from_conversation_stores_batch(
        self, client, auth_headers, mock_moorcheh
    ):
        """Conversation extraction stores candidates through batch memory writes."""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        activate_resp = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate", headers=auth_headers
        )
        assert activate_resp.status_code == 200, activate_resp.text
        token = activate_resp.json()["session_token"]
        headers = {**auth_headers, "X-Session-Token": token}

        mock_moorcheh.answer.generate.return_value = {
            "answer": json.dumps(
                [
                    {
                        "type": "fact",
                        "title": "Test stack",
                        "content": "The project uses pytest for tests.",
                        "confidence": 0.88,
                    }
                ]
            ),
            "sources": [],
        }
        mock_moorcheh.documents.upload.return_value = {"status": "success"}

        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/remember/extract",
            headers=headers,
            json={
                "messages": [
                    {"role": "user", "content": "The project uses pytest for tests."}
                ],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["dry_run"] is False
        assert data["successful"] == 1
        uploaded_doc = mock_moorcheh.documents.upload.call_args.kwargs["documents"][0]
        assert uploaded_doc["memory_type"] == "fact"
        assert uploaded_doc["provenance"] == "inferred"

    @pytest.mark.asyncio
    async def test_recall_temporal_api(self, client, auth_headers, mock_moorcheh):
        """Test temporal recall modes (POST + JSON body)"""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        activate_resp = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate", headers=auth_headers
        )
        token = activate_resp.json()["session_token"]
        headers = {**auth_headers, "X-Session-Token": token}

        mock_moorcheh.similarity_search.query.return_value = {
            "results": [],
            "total_found": 0,
        }
        mock_moorcheh.documents.fetch_text_data.return_value = {
            "status": "ok",
            "items": [],
        }

        # 1. As-of recall — date-only input defaults to end of day
        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/recall/as-of",
            headers=headers,
            json={"as_of": "2025-01-01"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["temporal_mode"] == "as_of"
        assert "2025-01-01T23:59:59" in data["as_of_date"]

        # 2. As-of recall — full ISO datetime
        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/recall/as-of",
            headers=headers,
            json={"as_of": "2025-06-15T12:00:00Z"},
        )
        assert response.status_code == 200
        assert response.json()["temporal_mode"] == "as_of"

        # 3. Changed-since recall — date-only input defaults to start of day
        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/recall/changed-since",
            headers=headers,
            json={"since": "2025-01-01"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["temporal_mode"] == "changed_since"
        assert "2025-01-01T00:00:00" in data["since_date"]

        # 4. Changed-since recall — full ISO datetime, no query
        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/recall/changed-since",
            headers=headers,
            json={"since": "2025-01-01T00:00:00Z"},
        )
        assert response.status_code == 200
        assert response.json()["temporal_mode"] == "changed_since"

    @pytest.mark.asyncio
    async def test_recall_recent_api(self, client, auth_headers, mock_moorcheh):
        """Test recall/recent returns newest memories sorted by created_at"""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        activate_resp = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate", headers=auth_headers
        )
        token = activate_resp.json()["session_token"]
        headers = {**auth_headers, "X-Session-Token": token}

        mock_moorcheh.similarity_search.query.return_value = {
            "results": [
                {
                    "id": "m1",
                    "metadata": {
                        "created_at": "2025-06-01T10:00:00",
                        "memory_type": "fact",
                    },
                    "text": "fact one",
                },
                {
                    "id": "m2",
                    "metadata": {
                        "created_at": "2025-05-01T08:00:00",
                        "memory_type": "fact",
                    },
                    "text": "fact two",
                },
            ],
            "total_found": 2,
        }

        # No body required — all fields optional
        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/recall/recent",
            headers=headers,
            json={},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["temporal_mode"] == "recent"
        assert "memories" in data
        assert "count" in data

        # With limit and type filter
        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/recall/recent",
            headers=headers,
            json={"limit": 5, "type": ["fact"]},
        )
        assert response.status_code == 200
        assert response.json()["temporal_mode"] == "recent"

    @pytest.mark.asyncio
    async def test_conflicts_list_api(self, client, auth_headers):
        """Test listing conflicts via API."""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        activate_resp = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate", headers=auth_headers
        )
        token = activate_resp.json()["session_token"]
        headers = {**auth_headers, "X-Session-Token": token}

        with patch("memanto.app.routes.memory.DirectClient") as mock_client_cls:
            mock_client = mock_client_cls.return_value
            mock_client.list_conflicts.return_value = [
                {"type": "conflict", "id": "c-1"}
            ]

            response = await client.get(
                f"/api/v2/agents/{self.TEST_AGENT_ID}/conflicts",
                headers=headers,
                params={"date": "2026-05-08"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["conflicts"][0]["id"] == "c-1"

    @pytest.mark.asyncio
    async def test_conflicts_resolve_api(self, client, auth_headers):
        """Test resolving conflicts via API."""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        activate_resp = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate", headers=auth_headers
        )
        token = activate_resp.json()["session_token"]
        headers = {**auth_headers, "X-Session-Token": token}

        with patch("memanto.app.routes.memory.DirectClient") as mock_client_cls:
            mock_client = mock_client_cls.return_value
            mock_client.resolve_conflict.return_value = {
                "status": "resolved",
                "action": "keep_new",
            }

            response = await client.post(
                f"/api/v2/agents/{self.TEST_AGENT_ID}/conflicts/resolve",
                headers=headers,
                json={"date": "2026-05-08", "conflict_index": 0, "action": "keep_new"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "resolved"
        assert data["action"] == "keep_new"

    @pytest.mark.asyncio
    async def test_upload_file_with_session(self, client, auth_headers, mock_moorcheh):
        """Test file upload to agent's memory namespace"""
        # Setup agent and session
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        activate_resp = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate", headers=auth_headers
        )
        token = activate_resp.json()["session_token"]

        # Mock documents.upload_file result
        mock_moorcheh.documents.upload_file.return_value = {
            "success": True,
            "message": "File uploaded successfully",
            "fileName": "notes.txt",
            "fileSize": 1024,
        }

        # Upload a small text file
        headers = {**auth_headers, "X-Session-Token": token}
        file_content = b"This is a test memory document."
        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/upload-file",
            headers=headers,
            files={"file": ("notes.txt", file_content, "text/plain")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == self.TEST_AGENT_ID
        assert data["file_name"] == "notes.txt"
        assert data["status"] == "uploaded"

    @pytest.mark.asyncio
    async def test_upload_file_unsupported_extension(self, client, auth_headers):
        """Test that unsupported file types are rejected"""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        activate_resp = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate", headers=auth_headers
        )
        token = activate_resp.json()["session_token"]

        headers = {**auth_headers, "X-Session-Token": token}
        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/upload-file",
            headers=headers,
            files={
                "file": ("script.exe", b"binary content", "application/octet-stream")
            },
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_file_requires_session(self, client, auth_headers):
        """Test that upload requires a valid session token"""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )

        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/upload-file",
            headers=auth_headers,  # no X-Session-Token
            files={"file": ("notes.txt", b"content", "text/plain")},
        )

        assert response.status_code in (401, 403, 422)

    @pytest.mark.asyncio
    async def test_traversal_filename_is_sanitized(
        self, client, auth_headers, mock_moorcheh
    ):
        """A filename with ../../ should be stripped to its basename."""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        activate_resp = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate", headers=auth_headers
        )
        token = activate_resp.json()["session_token"]

        mock_moorcheh.documents.upload_file.return_value = {
            "success": True,
            "message": "File uploaded",
            "fileName": "notes.txt",
            "fileSize": 100,
        }

        headers = {**auth_headers, "X-Session-Token": token}
        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/upload-file",
            headers=headers,
            files={
                "file": (
                    "../../../etc/passwd.txt",
                    b"test content",
                    "text/plain",
                )
            },
        )

        assert response.status_code == 200
        data = response.json()
        # The returned file_name should be the sanitized basename
        assert data["file_name"] == "passwd.txt"
        assert "/" not in data["file_name"]
        assert ".." not in data["file_name"]

    @pytest.mark.asyncio
    async def test_absolute_path_filename_is_sanitized(
        self, client, auth_headers, mock_moorcheh
    ):
        """An absolute path filename should be stripped to its basename."""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        activate_resp = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate", headers=auth_headers
        )
        token = activate_resp.json()["session_token"]

        mock_moorcheh.documents.upload_file.return_value = {
            "success": True,
            "message": "File uploaded",
            "fileName": "secret.json",
            "fileSize": 50,
        }

        headers = {**auth_headers, "X-Session-Token": token}
        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/upload-file",
            headers=headers,
            files={
                "file": (
                    "/etc/secret.json",
                    b'{"key": "value"}',
                    "application/json",
                )
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["file_name"] == "secret.json"


class TestFilenameSanitizationLogic:
    """Direct tests on the sanitization logic used in the fix."""

    @staticmethod
    def sanitize(raw: str | None) -> str:
        """Reproduce the exact sanitization logic from the fix."""
        original_name = Path(raw or "upload").name
        if not original_name or original_name in (".", ".."):
            original_name = "upload"
        return original_name

    def test_normal_filename(self):
        assert self.sanitize("notes.txt") == "notes.txt"

    def test_normal_filename_with_spaces(self):
        assert self.sanitize("my notes.pdf") == "my notes.pdf"

    def test_normal_filename_uppercase(self):
        assert self.sanitize("REPORT.DOCX") == "REPORT.DOCX"

    def test_simple_traversal(self):
        result = self.sanitize("../../../etc/passwd")
        assert result == "passwd"
        assert "/" not in result
        assert ".." not in result

    def test_deep_traversal(self):
        result = self.sanitize("../../../../../../../../etc/shadow")
        assert result == "shadow"

    def test_traversal_to_txt(self):
        result = self.sanitize("../../sensitive.txt")
        assert result == "sensitive.txt"
        assert ".." not in result

    def test_windows_traversal(self):
        result = self.sanitize("..\\..\\..\\windows\\win.ini")
        assert "/" not in result

    def test_mixed_traversal(self):
        result = self.sanitize("../../../etc/passwd.txt")
        assert result == "passwd.txt"

    def test_absolute_path_linux(self):
        result = self.sanitize("/etc/passwd")
        assert result == "passwd"

    def test_absolute_path_deep(self):
        result = self.sanitize("/var/www/html/config.php")
        assert result == "config.php"

    def test_none_filename(self):
        assert self.sanitize(None) == "upload"

    def test_empty_filename(self):
        assert self.sanitize("") == "upload"

    def test_dot_filename(self):
        assert self.sanitize(".") == "upload"

    def test_dotdot_filename(self):
        assert self.sanitize("..") == "upload"

    def test_only_slashes(self):
        assert self.sanitize("/") == "upload"

    def test_dotfile(self):
        result = self.sanitize(".env")
        assert result == ".env"


class TestRealpathGuard:
    """Verify the defense-in-depth realpath check prevents escape."""

    def test_safe_path_passes(self):
        tmp_dir = tempfile.mkdtemp()
        safe_name = "report.pdf"
        tmp_path = os.path.join(tmp_dir, safe_name)
        assert os.path.realpath(tmp_path).startswith(os.path.realpath(tmp_dir) + os.sep)

    def test_traversal_path_fails(self):
        tmp_dir = tempfile.mkdtemp()
        malicious_path = os.path.join(tmp_dir, "..", "..", "etc", "passwd")
        assert not os.path.realpath(malicious_path).startswith(
            os.path.realpath(tmp_dir) + os.sep
        )
