import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

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
        # Manually update singletons/global instances
        from memanto.app.routes.sessions import agent_service
        from memanto.app.services.session_service import get_session_service

        session_service = get_session_service()

        # Save original dirs
        orig_agent_dir = agent_service.agents_dir
        orig_session_dir = session_service.sessions_dir

        # Set to temp
        agent_service.agents_dir = temp_path / ".memanto" / "agents"
        session_service.sessions_dir = temp_path / ".memanto" / "sessions"

        agent_service.agents_dir.mkdir(parents=True, exist_ok=True)
        session_service.sessions_dir.mkdir(parents=True, exist_ok=True)

        yield temp_path

        # Cleanup
        agent_service.agents_dir = orig_agent_dir
        session_service.sessions_dir = orig_session_dir
        shutil.rmtree(temp_dir)


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
        patch("memanto.app.services.agent_service.MoorchehClient") as mock_agent_client,
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

    @pytest.mark.asyncio
    async def test_list_agents(self, client, auth_headers):
        """Test listing agents"""
        response = await client.get("/api/v2/agents", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data

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
        params = {"query": "test query", "limit": 1}
        response = await client.get(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/recall",
            headers=headers,
            params=params,
        )

        assert response.status_code == 200
        assert len(response.json()["memories"]) == 1

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
        assert response.json()["agent_id"] == self.TEST_AGENT_ID

    @pytest.mark.asyncio
    async def test_delete_agent(self, client, auth_headers):
        """Test deleting agent"""
        await client.post(
            "/api/v2/agents", headers=auth_headers, json={"agent_id": "to-delete"}
        )
        response = await client.delete("/api/v2/agents/to-delete", headers=auth_headers)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_deactivate_agent(self, client, auth_headers):
        """Test deactivating session"""
        await client.post(
            "/api/v2/agents",
            headers=auth_headers,
            json={"agent_id": self.TEST_AGENT_ID},
        )
        await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate", headers=auth_headers
        )

        response = await client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/deactivate", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "ended_at" in data

    @pytest.mark.asyncio
    async def test_current_session_info(self, client, auth_headers):
        """Test getting current session info"""
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
        response = await client.get("/api/v2/session/current", headers=headers)
        assert response.status_code == 200
        assert response.json()["agent_id"] == self.TEST_AGENT_ID

    @pytest.mark.asyncio
    async def test_extend_session_api(self, client, auth_headers):
        """Test extending session"""
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
            "/api/v2/session/extend", headers=headers, params={"additional_hours": 4}
        )
        assert response.status_code == 200
        assert "expires_at" in response.json()

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
        assert response.json()["type"] == "fact"

    @pytest.mark.asyncio
    async def test_list_sessions_api(self, client, auth_headers):
        """Test listing all sessions"""
        response = await client.get("/api/v2/sessions", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

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
    async def test_recall_temporal_api(self, client, auth_headers, mock_moorcheh):
        """Test temporal recall modes"""
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

        # 1. As-of recall
        mock_moorcheh.similarity_search.query.return_value = {
            "results": [],
            "total_found": 0,
        }
        response = await client.get(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/recall/as-of",
            headers=headers,
            params={"query": "test", "as_of": "2025-01-01T00:00:00Z"},
        )
        assert response.status_code == 200
        assert response.json()["temporal_mode"] == "as_of"

        # 2. Changed-since recall
        mock_moorcheh.similarity_search.query.return_value = {
            "results": [],
            "total_found": 0,
        }
        response = await client.get(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/recall/changed-since",
            headers=headers,
            params={"since": "2025-01-01T00:00:00Z"},
        )
        assert response.status_code == 200
        assert response.json()["temporal_mode"] == "changed_since"

        # 3. Current-only recall
        mock_moorcheh.similarity_search.query.return_value = {
            "results": [],
            "total_found": 0,
        }
        response = await client.get(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/recall/current",
            headers=headers,
            params={"query": "test"},
        )
        assert response.status_code == 200
        assert response.json()["temporal_mode"] == "current_only"

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
