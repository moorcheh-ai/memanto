"""Regression tests for browser-origin checks on management API access."""

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from memanto.app.config import settings
from memanto.app.main import app

os.environ["MOORCHEH_API_KEY"] = "test-api-key"


@pytest.fixture(autouse=True)
def isolated_agent_state():
    """Run each management API test with an isolated on-disk agent state."""
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir)

    with (
        patch("memanto.app.services.agent_service.Path.home", return_value=temp_path),
        patch("memanto.app.services.session_service.Path.home", return_value=temp_path),
    ):
        from memanto.app.routes.sessions import agent_service
        from memanto.app.services import session_service as session_service_mod

        session_service_mod._session_service = None
        session_service = session_service_mod.get_session_service()

        original_agents_dir = agent_service.agents_dir
        agent_service.agents_dir = temp_path / ".memanto" / "agents"
        agent_service.agents_dir.mkdir(parents=True, exist_ok=True)
        session_service.sessions_dir.mkdir(parents=True, exist_ok=True)

        try:
            yield
        finally:
            agent_service.agents_dir = original_agents_dir
            session_service_mod._session_service = None
            shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(autouse=True)
def mock_moorcheh_client():
    """Replace networked Moorcheh clients with deterministic in-process mocks."""
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
        mock_instance = MagicMock()
        mock_async_instance = MagicMock()
        mock_agent_client.return_value = mock_instance
        mock_moorcheh_cls.return_value = mock_instance
        mock_async_moorcheh_cls.return_value = mock_async_instance
        mock_instance.namespaces.create.return_value = {"status": "created"}
        mock_async_instance.namespaces.create = AsyncMock(
            return_value={"status": "created"}
        )

        yield

        moorcheh_client.reset_client()


@pytest.mark.asyncio
async def test_loopback_management_rejects_cross_site_origin():
    """Reject unauthenticated loopback requests sent from non-local pages."""
    transport = ASGITransport(app=app, client=("127.0.0.1", 54321))
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.post(
            "/api/v2/agents",
            headers={"Origin": "https://evil.example"},
            json={"agent_id": "csrf-agent", "pattern": "support"},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_loopback_management_accepts_localhost_origin_without_credential():
    """Allow local browser origins to keep normal developer workflows working."""
    transport = ASGITransport(app=app, client=("127.0.0.1", 54321))
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.post(
            "/api/v2/agents",
            headers={"Origin": "http://localhost:8000"},
            json={"agent_id": "localhost-origin-agent", "pattern": "support"},
        )

    assert response.status_code == 201
    assert response.json()["agent_id"] == "localhost-origin-agent"


@pytest.mark.asyncio
async def test_valid_management_credential_allows_nonlocal_origin():
    """Allow credentialed automation even when its browser origin is external."""
    transport = ASGITransport(app=app, client=("127.0.0.1", 54321))
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        response = await client.post(
            "/api/v2/agents",
            headers={
                "Authorization": f"Bearer {settings.MOORCHEH_API_KEY}",
                "Origin": "https://automation.example",
            },
            json={"agent_id": "credential-origin-agent", "pattern": "support"},
        )

    assert response.status_code == 201
    assert response.json()["agent_id"] == "credential-origin-agent"
