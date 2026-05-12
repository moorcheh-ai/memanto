"""
End-to-end tests — real Moorcheh API, zero mocks.

API key is loaded automatically from ~/.memanto/.env by config.py.
Agent/session metadata is stored in a temporary directory that is
cleaned up after the module finishes.

Tests are intentionally numbered so pytest runs them in definition
order; each test may depend on state set by earlier tests (e.g. the
session token produced by test_05 is used by all memory tests).
"""

import shutil
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from memanto.app.config import settings
from memanto.app.main import app


def _live_moorcheh_api_key_configured() -> bool:
    """E2E hits production Moorcheh; skip when key is missing or the unit-test placeholder."""
    key = (settings.MOORCHEH_API_KEY or "").strip()
    if not key:
        return False
    if key == "test-api-key":
        return False
    return True


# Skip entire module unless a real Moorcheh key is configured (CI uses placeholder).
pytestmark = pytest.mark.skipif(
    not _live_moorcheh_api_key_configured(),
    reason=(
        "Live Moorcheh E2E skipped: MOORCHEH_API_KEY missing or placeholder 'test-api-key'. "
        "Use a real key locally (~/.memanto/.env). In GitHub Actions, set the MOORCHEH_API_KEY "
        "repository secret and pass it to the test job env to run E2E in CI."
    ),
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_AGENT_ID = "e2e-memanto-test"
AUTH = {"Authorization": f"Bearer {settings.MOORCHEH_API_KEY}"}

# Mutable state shared across ordered tests in this module.
state: dict = {}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def isolated_dirs():
    """Redirect agent/session storage to a temp dir for the whole E2E module."""
    from memanto.app.routes.sessions import agent_service
    from memanto.app.services.session_service import get_session_service

    svc = get_session_service()
    tmp = Path(tempfile.mkdtemp())

    orig_agents = agent_service.agents_dir
    orig_sessions = svc.sessions_dir

    agent_service.agents_dir = tmp / ".memanto" / "agents"
    svc.sessions_dir = tmp / ".memanto" / "sessions"
    agent_service.agents_dir.mkdir(parents=True, exist_ok=True)
    svc.sessions_dir.mkdir(parents=True, exist_ok=True)

    yield

    agent_service.agents_dir = orig_agents
    svc.sessions_dir = orig_sessions
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
async def http():
    """Fresh async HTTP client pointing at the real app (no mocks)."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestE2E:
    """Sequential end-to-end coverage of all MEMANTO API v2 endpoints."""

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_01_health_connected(self, http):
        """GET /health confirms Moorcheh connectivity with real API key."""
        resp = await http.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["moorcheh_connected"] is True, (
            f"Moorcheh not connected — check MOORCHEH_API_KEY. Response: {data}"
        )
        assert data["status"] == "healthy"

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_02_create_agent(self, http):
        """POST /api/v2/agents — creates agent and Moorcheh namespace."""
        resp = await http.post(
            "/api/v2/agents",
            headers=AUTH,
            json={
                "agent_id": TEST_AGENT_ID,
                "pattern": "support",
                "description": "Automated E2E test agent — safe to delete",
            },
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["agent_id"] == TEST_AGENT_ID
        assert "namespace" in data
        assert data["namespace"] == f"memanto_agent_{TEST_AGENT_ID}"

    @pytest.mark.asyncio
    async def test_03_list_agents(self, http):
        """GET /api/v2/agents — test agent appears in the list."""
        resp = await http.get("/api/v2/agents", headers=AUTH)
        assert resp.status_code == 200
        ids = [a["agent_id"] for a in resp.json()["agents"]]
        assert TEST_AGENT_ID in ids

    @pytest.mark.asyncio
    async def test_04_get_agent(self, http):
        """GET /api/v2/agents/{id} — returns agent details."""
        resp = await http.get(f"/api/v2/agents/{TEST_AGENT_ID}", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] == TEST_AGENT_ID
        assert data["namespace"] == f"memanto_agent_{TEST_AGENT_ID}"

    @pytest.mark.asyncio
    async def test_04b_get_nonexistent_agent(self, http):
        """GET /api/v2/agents/{id} — returns 404 for unknown agent."""
        resp = await http.get("/api/v2/agents/no-such-agent-xyz", headers=AUTH)
        assert resp.status_code == 404

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_05_activate_session(self, http):
        """POST /api/v2/agents/{id}/activate — returns a real JWT session token."""
        resp = await http.post(f"/api/v2/agents/{TEST_AGENT_ID}/activate", headers=AUTH)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "session_token" in data
        assert "session_id" in data
        assert data["agent_id"] == TEST_AGENT_ID
        # Persist token for all subsequent tests
        state["session_token"] = data["session_token"]
        state["session_id"] = data["session_id"]

    @pytest.mark.asyncio
    async def test_06_global_status(self, http):
        """GET /api/v2/status — returns active session info (no auth required)."""
        resp = await http.get("/api/v2/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] == TEST_AGENT_ID
        assert data["time_remaining_seconds"] > 0
        assert "session_id" in data

    # ------------------------------------------------------------------
    # Memory writes
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_07_remember(self, http):
        """POST /{id}/remember — stores a single memory in Moorcheh."""
        headers = {**AUTH, "X-Session-Token": state["session_token"]}
        resp = await http.post(
            f"/api/v2/agents/{TEST_AGENT_ID}/remember",
            headers=headers,
            json={
                "content": "The E2E test agent uses Python 3.11 and FastAPI.",
                "type": "fact",
                "title": "Tech stack",
                "confidence": 0.95,
                "tags": ["tech", "e2e"],
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "queued"
        assert "memory_id" in data
        assert data["agent_id"] == TEST_AGENT_ID

    @pytest.mark.asyncio
    async def test_08_batch_remember(self, http):
        """POST /{id}/batch-remember — stores three memories in one request."""
        headers = {**AUTH, "X-Session-Token": state["session_token"]}
        resp = await http.post(
            f"/api/v2/agents/{TEST_AGENT_ID}/batch-remember",
            headers=headers,
            json={
                "memories": [
                    {
                        "content": "We deploy to AWS us-east-1.",
                        "type": "fact",
                        "confidence": 0.9,
                    },
                    {
                        "content": "Use PostgreSQL 15 for the production database.",
                        "type": "decision",
                        "confidence": 0.85,
                    },
                    {
                        "content": "Send weekly status updates every Friday morning.",
                        "type": "instruction",
                        "confidence": 0.9,
                    },
                ]
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total_submitted"] == 3
        assert data["failed"] == 0
        # successful count depends on Moorcheh's batch-upload response format;
        # what matters is nothing was rejected (failed == 0)
        assert data["successful"] + data["failed"] <= data["total_submitted"]

    @pytest.mark.asyncio
    async def test_09_upload_file(self, http):
        """POST /{id}/upload-file — uploads a .txt file to agent's namespace."""
        headers = {**AUTH, "X-Session-Token": state["session_token"]}
        file_bytes = (
            b"E2E Test Document\n"
            b"=================\n"
            b"This file was uploaded by the automated end-to-end test suite.\n"
            b"It contains notes about the test agent configuration.\n"
        )
        resp = await http.post(
            f"/api/v2/agents/{TEST_AGENT_ID}/upload-file",
            headers=headers,
            files={"file": ("e2e_notes.txt", file_bytes, "text/plain")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["file_name"] == "e2e_notes.txt"
        assert data["status"] == "uploaded"
        assert data["agent_id"] == TEST_AGENT_ID

    @pytest.mark.asyncio
    async def test_09b_upload_file_rejects_bad_extension(self, http):
        """POST /{id}/upload-file — rejects unsupported file types with 400."""
        headers = {**AUTH, "X-Session-Token": state["session_token"]}
        resp = await http.post(
            f"/api/v2/agents/{TEST_AGENT_ID}/upload-file",
            headers=headers,
            files={"file": ("script.exe", b"binary", "application/octet-stream")},
        )
        assert resp.status_code == 400

    # ------------------------------------------------------------------
    # Memory reads / recall
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_10_recall(self, http):
        """POST /{id}/recall — semantic search returns valid response shape."""
        headers = {**AUTH, "X-Session-Token": state["session_token"]}
        resp = await http.post(
            f"/api/v2/agents/{TEST_AGENT_ID}/recall",
            headers=headers,
            json={"query": "Python FastAPI technology stack", "limit": 5},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["agent_id"] == TEST_AGENT_ID
        assert "memories" in data
        assert "count" in data
        assert isinstance(data["memories"], list)

    @pytest.mark.asyncio
    async def test_11_recall_with_type_filter(self, http):
        """POST /{id}/recall — type filter is forwarded to Moorcheh."""
        headers = {**AUTH, "X-Session-Token": state["session_token"]}
        resp = await http.post(
            f"/api/v2/agents/{TEST_AGENT_ID}/recall",
            headers=headers,
            json={
                "query": "database deployment infrastructure",
                "type": ["fact", "decision"],
                "limit": 5,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["agent_id"] == TEST_AGENT_ID
        assert isinstance(data["memories"], list)

    @pytest.mark.asyncio
    async def test_12_answer(self, http):
        """POST /{id}/answer — RAG endpoint returns a generated answer."""
        headers = {**AUTH, "X-Session-Token": state["session_token"]}
        resp = await http.post(
            f"/api/v2/agents/{TEST_AGENT_ID}/answer",
            headers=headers,
            json={"question": "What technology stack does this agent use?"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "answer" in data
        assert "sources" in data
        assert data["agent_id"] == TEST_AGENT_ID
        # Moorcheh may return answer as string or dict depending on namespace state
        assert data["answer"] is not None

    @pytest.mark.asyncio
    async def test_13_recall_as_of_date_only(self, http):
        """POST /{id}/recall/as-of — date-only string converts to end-of-day."""
        headers = {**AUTH, "X-Session-Token": state["session_token"]}
        resp = await http.post(
            f"/api/v2/agents/{TEST_AGENT_ID}/recall/as-of",
            headers=headers,
            json={"as_of": "2026-12-31"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["temporal_mode"] == "as_of"
        assert "2026-12-31T23:59:59" in data["as_of_date"]
        assert "memories" in data

    @pytest.mark.asyncio
    async def test_13b_recall_as_of_full_datetime(self, http):
        """POST /{id}/recall/as-of — full ISO datetime is accepted."""
        headers = {**AUTH, "X-Session-Token": state["session_token"]}
        resp = await http.post(
            f"/api/v2/agents/{TEST_AGENT_ID}/recall/as-of",
            headers=headers,
            json={"as_of": "2026-06-15T12:00:00Z"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["temporal_mode"] == "as_of"

    @pytest.mark.asyncio
    async def test_14_recall_changed_since_date_only(self, http):
        """POST /{id}/recall/changed-since — date-only string converts to start-of-day."""
        headers = {**AUTH, "X-Session-Token": state["session_token"]}
        resp = await http.post(
            f"/api/v2/agents/{TEST_AGENT_ID}/recall/changed-since",
            headers=headers,
            json={"since": "2026-01-01"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["temporal_mode"] == "changed_since"
        assert "2026-01-01T00:00:00" in data["since_date"]
        assert "memories" in data

    @pytest.mark.asyncio
    async def test_14b_recall_changed_since_full_datetime(self, http):
        """POST /{id}/recall/changed-since — full ISO datetime is accepted."""
        headers = {**AUTH, "X-Session-Token": state["session_token"]}
        resp = await http.post(
            f"/api/v2/agents/{TEST_AGENT_ID}/recall/changed-since",
            headers=headers,
            json={"since": "2026-01-01T00:00:00Z"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["temporal_mode"] == "changed_since"

    @pytest.mark.asyncio
    async def test_15_recall_recent(self, http):
        """POST /{id}/recall/recent — returns newest memories."""
        headers = {**AUTH, "X-Session-Token": state["session_token"]}
        resp = await http.post(
            f"/api/v2/agents/{TEST_AGENT_ID}/recall/recent",
            headers=headers,
            json={"limit": 5},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["temporal_mode"] == "recent"
        assert "memories" in data
        assert "count" in data

    @pytest.mark.asyncio
    async def test_15b_recall_recent_with_type_filter(self, http):
        """POST /{id}/recall/recent — type filter narrows results."""
        headers = {**AUTH, "X-Session-Token": state["session_token"]}
        resp = await http.post(
            f"/api/v2/agents/{TEST_AGENT_ID}/recall/recent",
            headers=headers,
            json={"type": ["fact"], "limit": 3},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["temporal_mode"] == "recent"

    # ------------------------------------------------------------------
    # Conflicts
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_16_list_conflicts_empty(self, http):
        """GET /{id}/conflicts — returns empty list when no conflict file exists."""
        headers = {**AUTH, "X-Session-Token": state["session_token"]}
        resp = await http.get(
            f"/api/v2/agents/{TEST_AGENT_ID}/conflicts",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["agent_id"] == TEST_AGENT_ID
        assert isinstance(data["conflicts"], list)
        assert data["count"] == len(data["conflicts"])

    # ------------------------------------------------------------------
    # Session deactivation & agent deletion
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_17_deactivate_session(self, http):
        """POST /{id}/deactivate — ends the session and returns a summary."""
        headers = {**AUTH, "X-Session-Token": state["session_token"]}
        resp = await http.post(
            f"/api/v2/agents/{TEST_AGENT_ID}/deactivate",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "session_id" in data
        assert "ended_at" in data

    @pytest.mark.asyncio
    async def test_18_global_status_after_deactivate(self, http):
        """GET /api/v2/status — returns 404 once no session is active."""
        resp = await http.get("/api/v2/status")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_19_delete_agent_local_only(self, http):
        """DELETE /api/v2/agents/{id} — removes local metadata, keeps Moorcheh namespace."""
        resp = await http.delete(f"/api/v2/agents/{TEST_AGENT_ID}", headers=AUTH)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert TEST_AGENT_ID in data["message"]
        # Confirm local deletion
        get_resp = await http.get(f"/api/v2/agents/{TEST_AGENT_ID}", headers=AUTH)
        assert get_resp.status_code == 404
