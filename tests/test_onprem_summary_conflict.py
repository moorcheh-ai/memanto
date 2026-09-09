from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from memanto.app.config import settings
from memanto.app.models.session import Session
from memanto.app.routes.auth_deps import get_moorcheh_api_key
from memanto.app.routes.memory import (
    ConflictDetectRequest,
    ConflictResolveRequest,
    DailySummaryRequest,
    generate_conflict_report,
    generate_daily_summary,
    list_conflicts,
    resolve_conflict,
)
from memanto.cli.client.direct_client import DirectClient


def test_direct_client_init_onprem_without_api_key(monkeypatch):
    """Verify DirectClient initialization in on-prem mode tolerates omitted or empty API keys."""
    monkeypatch.setattr(settings, "MEMANTO_BACKEND", "on-prem")
    monkeypatch.setattr(settings, "MOORCHEH_API_KEY", "")

    client_default = DirectClient()
    assert client_default.api_key == ""

    client_empty = DirectClient("")
    assert client_empty.api_key == ""

    client_none = DirectClient(None)
    assert client_none.api_key == ""

    client_placeholder = DirectClient("on-prem")
    assert client_placeholder.api_key == "on-prem"


def test_direct_client_init_cloud_requires_api_key(monkeypatch):
    """Verify DirectClient initialization in cloud mode raises ValueError when no key is available."""
    monkeypatch.setattr(settings, "MEMANTO_BACKEND", "cloud")
    monkeypatch.setattr(settings, "MOORCHEH_API_KEY", "")

    with pytest.raises(ValueError, match="api_key must be a non-empty string"):
        DirectClient("")

    with pytest.raises(ValueError, match="api_key must be a non-empty string"):
        DirectClient(None)

    client = DirectClient("my-cloud-key")
    assert client.api_key == "my-cloud-key"


def test_direct_client_init_cloud_falls_back_to_settings_key(monkeypatch):
    """Verify DirectClient() without explicit key falls back to settings.MOORCHEH_API_KEY in cloud mode."""
    monkeypatch.setattr(settings, "MEMANTO_BACKEND", "cloud")
    monkeypatch.setattr(settings, "MOORCHEH_API_KEY", "mk_configured_cloud_key")

    client_default = DirectClient()
    assert client_default.api_key == "mk_configured_cloud_key"

    client_none = DirectClient(None)
    assert client_none.api_key == "mk_configured_cloud_key"

    client_empty = DirectClient("")
    assert client_empty.api_key == "mk_configured_cloud_key"


def test_get_moorcheh_api_key_dependency_onprem(monkeypatch):
    """Verify get_moorcheh_api_key returns 'on-prem' when running with on-prem backend."""
    monkeypatch.setattr(settings, "MEMANTO_BACKEND", "on-prem")
    monkeypatch.setattr(settings, "MOORCHEH_API_KEY", "")

    key = get_moorcheh_api_key()
    assert key == "on-prem"


@pytest.mark.asyncio
async def test_daily_summary_and_conflicts_onprem_routes(monkeypatch):
    """Verify daily summary and conflict management endpoints execute cleanly in on-prem mode."""
    monkeypatch.setattr(settings, "MEMANTO_BACKEND", "on-prem")
    monkeypatch.setattr(settings, "MOORCHEH_API_KEY", "")

    now = datetime.now(timezone.utc)
    fake_session = Session(
        session_id="test-session-id",
        session_token="test-token",
        agent_id="test-agent",
        namespace="memanto_agent_test_agent",
        started_at=now,
        expires_at=now + timedelta(hours=1),
    )

    with patch("memanto.app.routes.memory.DirectClient") as mock_direct_cls:
        mock_instance = mock_direct_cls.return_value
        mock_instance.generate_daily_summary.return_value = {
            "summary": {"status": "success"},
            "export": {"status": "ok"},
        }
        mock_instance.generate_conflict_report.return_value = {"conflicts": []}
        mock_instance.list_conflicts.return_value = []
        mock_instance.resolve_conflict.return_value = {"action": "keep_old"}

        api_key = get_moorcheh_api_key()
        assert api_key == "on-prem"

        # Daily summary
        summary_res = await generate_daily_summary(
            agent_id="test-agent",
            request=DailySummaryRequest(),
            session=fake_session,
            moorcheh_api_key=api_key,
        )
        assert summary_res["agent_id"] == "test-agent"
        mock_direct_cls.assert_called_with("on-prem")

        # Conflict report generation
        conflict_gen_res = await generate_conflict_report(
            agent_id="test-agent",
            request=ConflictDetectRequest(),
            session=fake_session,
            moorcheh_api_key=api_key,
        )
        assert conflict_gen_res["agent_id"] == "test-agent"

        # List conflicts
        conflicts_list_res = await list_conflicts(
            agent_id="test-agent",
            date=None,
            session=fake_session,
            moorcheh_api_key=api_key,
        )
        assert conflicts_list_res["agent_id"] == "test-agent"
        assert conflicts_list_res["conflicts"] == []

        # Resolve conflict
        resolve_res = await resolve_conflict(
            agent_id="test-agent",
            request=ConflictResolveRequest(conflict_index=0, action="keep_old"),
            session=fake_session,
            moorcheh_api_key=api_key,
        )
        assert resolve_res["agent_id"] == "test-agent"
        assert resolve_res["action"] == "keep_old"
