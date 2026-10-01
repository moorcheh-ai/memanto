"""Regression tests for the DNS-rebinding / missing Host-header validation fix.

Attack recap
------------
MEMANTO binds to 0.0.0.0 and trusts the loopback TCP client for its
session-scoped memory routes (``get_current_session``) and UI management
routes (``_require_local``). A malicious page on ``attacker.example`` that
DNS-rebinding resolves to 127.0.0.1 makes the server see a 127.0.0.1 peer
while the request's Host header names ``attacker.example``. Before the fix
those requests were indistinguishable from a local browser and could read /
write the private memory store, migrate the session cookie onto the attacker
domain (GET /api/ui/config), and enumerate the filesystem (browse).

The fix requires that cookie-transport (browser) session requests and all UI
management requests target a loopback Host header, mirroring the
``require_management_access`` boundary. Header-transport API clients
(``X-Session-Token``, no cookie) must remain callable from remote peers.

These tests pin that boundary: rebinding-origin requests are rejected
(403), legitimate localhost traffic still works (200), and remote header-
transport API clients are unaffected (200).
"""

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from memanto.app.main import app

os.environ["MOORCHEH_API_KEY"] = "test-api-key"

ATTACKER_ORIGIN = "http://attacker.example:8000"
LOCAL_ORIGIN = "http://localhost:8000"


@pytest.fixture(autouse=True, scope="function")
def test_env_setup():
    """Isolated env for agent/session metadata (mirrors test_api.py)."""
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
        orig_agent_dir = agent_service.agents_dir
        agent_service.agents_dir = temp_path / ".memanto" / "agents"
        agent_service.agents_dir.mkdir(parents=True, exist_ok=True)
        session_service.sessions_dir.mkdir(parents=True, exist_ok=True)
        try:
            yield temp_path
        finally:
            agent_service.agents_dir = orig_agent_dir
            session_service_mod._session_service = None
            shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
async def local_client():
    """Loopback client whose Host header names localhost (real local UI
    browser / localhost callers)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=LOCAL_ORIGIN) as ac:
        yield ac


@pytest.fixture(autouse=True)
def mock_moorcheh():
    """Mock the Moorcheh SDK (extends the shared conftest mock with the shapes
    the memory read/write services consume)."""
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
        mock_instance.namespaces.list.return_value = {"namespaces": []}
        mock_instance.documents.get.return_value = {"documents": []}
        mock_instance.documents.upload.return_value = {
            "status": "success",
            "id": "mem-1",
        }
        mock_instance.documents.upload_file.return_value = {
            "success": True,
            "file_size": 0,
        }
        mock_instance.documents.delete.return_value = {"deleted": True}
        mock_instance.namespaces.get.return_value = {
            "namespace_name": "memanto_agent_victim",
        }
        mock_instance.documents.fetch_text_data.return_value = {
            "items": [
                {
                    "id": "mem-1",
                    "text": "SECRET data",
                    "content": "SECRET data",
                    "type": "fact",
                    "confidence": 0.9,
                    "source": "user",
                    "provenance": "observation",
                    "tags": ["secret"],
                    "created_at": "2026-08-28T00:00:00+00:00",
                    "updated_at": "2026-08-28T00:00:00+00:00",
                    "title": "vault",
                    "status": "active",
                }
            ],
            "pagination": {},
        }
        yield mock_instance


def _rebinding_headers():
    """Headers a page on the attacker origin sends: same-origin to its own
    (rebinding) origin, carrying no cross-site Origin on GET."""
    return {"Sec-Fetch-Site": "same-origin"}


async def _activate_client_session(client, agent_id: str) -> str:
    """Create + activate an agent through a loopback client; return the
    session token (mirrors what the attacker steals via cookie migration)."""
    await client.post(
        "/api/v2/agents",
        headers={"Authorization": "Bearer test-api-key"},
        json={"agent_id": agent_id},
    )
    activate = await client.post(
        f"/api/v2/agents/{agent_id}/activate",
        headers={"Authorization": "Bearer test-api-key"},
    )
    assert activate.status_code == 200
    return activate.json()["session_token"]


class TestRebindingRejected:
    """Requests whose Host header is not loopback must be rejected even though
    the TCP client is loopback (the DNS-rebinding scenario)."""

    TEST_AGENT_ID = "victim"

    @pytest.mark.asyncio
    async def test_rebinding_ui_config_rejected_and_no_cookie_migration(
        self, local_client, mock_moorcheh
    ):
        """Stage A of the kill chain — GET /api/ui/config on the attacker
        origin — must return 403 and must NOT migrate the session cookie onto
        the attacker domain."""
        await _activate_client_session(local_client, self.TEST_AGENT_ID)

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url=ATTACKER_ORIGIN
        ) as rebind:
            resp = await rebind.get("/api/ui/config", headers=_rebinding_headers())
            assert resp.status_code == 403
            assert "set-cookie" not in resp.headers  # no cookie migration

    @pytest.mark.asyncio
    async def test_rebinding_cannot_read_memories(self, local_client, mock_moorcheh):
        """Even with a valid session cookie attached, a non-loopback Host must
        not read the private memory store."""
        token = await _activate_client_session(local_client, self.TEST_AGENT_ID)

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url=ATTACKER_ORIGIN
        ) as rebind:
            rebind.cookies.set("memanto_session_token", token)
            resp = await rebind.post(
                f"/api/v2/agents/{self.TEST_AGENT_ID}/recall/recent",
                headers=_rebinding_headers(),
                json={"limit": 10},
            )
            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_rebinding_cannot_write_memories(self, local_client, mock_moorcheh):
        """A non-loopback Host must not poison the private memory store."""
        token = await _activate_client_session(local_client, self.TEST_AGENT_ID)

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url=ATTACKER_ORIGIN
        ) as rebind:
            rebind.cookies.set("memanto_session_token", token)
            resp = await rebind.post(
                f"/api/v2/agents/{self.TEST_AGENT_ID}/remember",
                headers=_rebinding_headers(),
                json={
                    "content": "ATTACKER INJECTED",
                    "type": "fact",
                    "confidence": 0.99,
                },
            )
            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_rebinding_cannot_browse_filesystem(self, mock_moorcheh):
        """GET /api/ui/browse on a non-loopback Host must not enumerate the
        local filesystem."""
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url=ATTACKER_ORIGIN
        ) as rebind:
            resp = await rebind.get(
                "/api/ui/browse",
                params={"path": "/home"},
                headers=_rebinding_headers(),
            )
            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_cross_site_cookie_request_rejected(self, local_client, mock_moorcheh):
        """Cross-site origin with a valid cookie is also rejected (defense in
        depth; the Host check already handles the rebinding variant)."""
        token = await _activate_client_session(local_client, self.TEST_AGENT_ID)

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url=ATTACKER_ORIGIN
        ) as rebind:
            rebind.cookies.set("memanto_session_token", token)
            resp = await rebind.post(
                f"/api/v2/agents/{self.TEST_AGENT_ID}/recall/recent",
                headers={"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"},
                json={"limit": 10},
            )
            assert resp.status_code == 403


class TestLoopbackStillWorks:
    """The fix must not break the legitimate local desktop flow."""

    TEST_AGENT_ID = "local-user"

    @pytest.mark.asyncio
    async def test_loopback_memory_read_write_still_work(
        self, local_client, mock_moorcheh
    ):
        """A localhost browser with the session cookie can still read and write
        memories."""
        await local_client.post(
            "/api/v2/agents",
            headers={"Authorization": "Bearer test-api-key"},
            json={"agent_id": self.TEST_AGENT_ID},
        )
        activate = await local_client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/activate",
            headers={"Authorization": "Bearer test-api-key"},
        )
        assert activate.status_code == 200
        token = activate.json()["session_token"]
        local_client.cookies.set("memanto_session_token", token)

        read = await local_client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/recall/recent",
            json={"limit": 10},
        )
        assert read.status_code == 200
        assert read.json()["memories"]
        assert read.json()["memories"][0]["content"] == "SECRET data"

        write = await local_client.post(
            f"/api/v2/agents/{self.TEST_AGENT_ID}/remember",
            json={
                "content": "legitimate memory",
                "type": "fact",
                "confidence": 0.9,
            },
        )
        assert write.status_code == 200

    @pytest.mark.asyncio
    async def test_loopback_ui_config_still_works(self, local_client, mock_moorcheh):
        """GET /api/ui/config from localhost still returns the UI config."""
        await local_client.post(
            "/api/v2/agents",
            headers={"Authorization": "Bearer test-api-key"},
            json={"agent_id": self.TEST_AGENT_ID},
        )
        resp = await local_client.get("/api/ui/config")
        assert resp.status_code == 200
        assert "active_agent_id" in resp.json()

    @pytest.mark.asyncio
    async def test_remote_header_api_client_still_works(
        self, local_client, mock_moorcheh
    ):
        """Header-transport API clients (X-Session-Token, no cookie) may stay
        remote — the cookie-only Host gate must not affect them."""
        token = await _activate_client_session(local_client, self.TEST_AGENT_ID)

        transport = ASGITransport(app=app, client=("203.0.113.10", 54321))
        async with AsyncClient(
            transport=transport, base_url=ATTACKER_ORIGIN
        ) as remote:
            resp = await remote.post(
                f"/api/v2/agents/{self.TEST_AGENT_ID}/recall/recent",
                headers={"X-Session-Token": token},
                json={"limit": 10},
            )
            assert resp.status_code == 200
            assert resp.json()["memories"]