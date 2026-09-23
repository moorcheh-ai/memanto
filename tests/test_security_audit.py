"""
Security Regression Tests for Memanto Defensive Security Audit.

Tests cover:
1. Path Traversal / Arbitrary File Write prevention in Daily Summary output_path.
2. Multi-tenant API key isolation in DirectClient, SdkClient, and AgentService.
3. State bleed prevention across concurrent agents in MCP MemantoLifecycle.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from memanto.app.main import app
from memanto.app.models.session import AgentCreate, AgentPattern
from memanto.app.services.agent_service import AgentService
from memanto.app.services.daily_analysis_service import DailyAnalysisService
from memanto.cli.client.direct_client import DirectClient
from memanto.cli.client.sdk_client import SdkClient

# ============================================================================
# Vulnerability 1: Arbitrary File Write / Path Traversal in Daily Summary
# ============================================================================


def test_daily_analysis_service_rejects_path_traversal(tmp_path):
    """DailyAnalysisService.generate_summary must reject output_path outside summaries_dir."""
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir(parents=True)
    summaries_dir = tmp_path / "summaries"
    summaries_dir.mkdir(parents=True)

    dummy_session = sessions_dir / "testagent_2026-03-24_sess1_summary.md"
    dummy_session.write_text("Session log content", encoding="utf-8")

    service = DailyAnalysisService(
        sessions_dir=sessions_dir, summaries_dir=summaries_dir
    )

    escape_path = str(tmp_path / "outside" / "evil.md")
    with patch("memanto.app.services.daily_analysis_service.get_moorcheh_client") as mock_client:
        mock_client.return_value.answer.generate.return_value = {
            "answer": "Generated AI Summary"
        }
        with pytest.raises((ValueError, PermissionError)) as exc_info:
            service.generate_summary("testagent", "2026-03-24", output_path=escape_path)
        err = str(exc_info.value).lower()
        assert "summaries" in err or "traversal" in err or "invalid" in err or "outside" in err


def test_daily_summary_endpoint_rejects_path_traversal():
    """POST /api/v2/agents/{agent_id}/daily-summary must reject output_path traversing outside."""
    client = TestClient(app)

    agent_id = "sec-agent-traversal"
    create_resp = client.post(
        "/api/v2/agents",
        json={"agent_id": agent_id, "pattern": "tool"},
    )
    assert create_resp.status_code in (201, 409)

    activate_resp = client.post(f"/api/v2/agents/{agent_id}/activate")
    assert activate_resp.status_code == 200
    token = activate_resp.json()["session_token"]

    traversal_path = "../../etc/passwd"
    resp = client.post(
        f"/api/v2/agents/{agent_id}/daily-summary",
        headers={"X-Session-Token": token},
        json={"date": "2026-03-24", "output_path": traversal_path},
    )
    assert resp.status_code in (400, 422)
    detail = str(resp.json()).lower()
    assert "output_path" in detail or "invalid" in detail or "traversal" in detail or "outside" in detail


# ============================================================================
# Vulnerability 2: Multi-tenant API Key Isolation
# ============================================================================


def test_direct_client_honors_api_key():
    """DirectClient must pass its own api_key to MoorchehClient, not server default."""
    tenant_key = "moorcheh-tenant-b-secret-key-12345"

    with patch("memanto.app.clients.moorcheh.moorcheh_client.get_client") as mock_get_client:
        client = DirectClient(api_key=tenant_key)
        client._get_moorcheh()
        mock_get_client.assert_called_with(api_key=tenant_key)


def test_sdk_client_honors_api_key():
    """SdkClient must pass its own api_key to MoorchehClient, not server default."""
    tenant_key = "moorcheh-tenant-c-secret-key-67890"

    with patch("memanto.app.clients.moorcheh.moorcheh_client.get_client") as mock_get_client:
        client = SdkClient(api_key=tenant_key)
        client._get_moorcheh()
        mock_get_client.assert_called_with(api_key=tenant_key)


def test_agent_service_create_agent_honors_api_key(tmp_path):
    """AgentService.create_agent must use the provided moorcheh_api_key."""
    tenant_key = "moorcheh-tenant-agent-key-99999"
    service = AgentService(agents_dir=tmp_path / "agents")

    agent_create = AgentCreate(agent_id="test-tenant-agent", pattern=AgentPattern.TOOL)

    with patch("memanto.app.services.agent_service.get_moorcheh_client") as mock_get_moorcheh_client:
        mock_moorcheh = MagicMock()
        mock_get_moorcheh_client.return_value = mock_moorcheh
        service.create_agent(agent_create, moorcheh_api_key=tenant_key)

        mock_get_moorcheh_client.assert_called_with(api_key=tenant_key)


# ============================================================================
# Vulnerability 3: MCP Lifecycle Multi-agent State Bleed & Race Condition
# ============================================================================


def test_mcp_lifecycle_agent_isolation_prevents_state_bleed(tmp_path):
    """MemantoLifecycle must maintain isolated client/session state per agent."""
    import sys
    mcp_path = str(Path(__file__).parent.parent / "integrations" / "mcp")
    if mcp_path not in sys.path:
        sys.path.insert(0, mcp_path)

    from memanto_mcp.config import MCPServerSettings
    from memanto_mcp.lifecycle import MemantoLifecycle

    settings = MCPServerSettings(
        moorcheh_api_key="test-api-key",
        agent_auto_create=True,
    )
    lifecycle = MemantoLifecycle(settings)

    # Prepare two agents
    agent_1 = "mcp-agent-one"
    agent_2 = "mcp-agent-two"

    # Ensure ready for agent 1
    lifecycle.ensure_ready(agent_1)
    client_1 = lifecycle.get_client(agent_1)
    assert client_1.agent_id == agent_1

    # Ensure ready for agent 2
    lifecycle.ensure_ready(agent_2)
    client_2 = lifecycle.get_client(agent_2)
    assert client_2.agent_id == agent_2

    # Verify agent 1's client state was not overwritten by agent 2
    client_1_after = lifecycle.get_client(agent_1)
    assert client_1_after.agent_id == agent_1
    assert client_1_after.agent_id != client_2.agent_id
