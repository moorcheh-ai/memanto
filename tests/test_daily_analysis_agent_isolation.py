"""Daily analysis must not consume another agent's local session history."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from memanto.app.config import settings
from memanto.app.core import MemoryRecord
from memanto.app.models.session import AgentCreate
from memanto.app.routes import memory
from memanto.app.services import daily_analysis_service, session_service
from memanto.app.services.agent_service import AgentService
from memanto.app.services.summary_visualization_service import (
    SummaryVisualizationService,
)

DATE = "2026-10-13"
AGENT = "team"
OTHER_AGENT = f"{AGENT}_{DATE}_private"
PRIVATE_TEXT = "Synthetic private acquisition plan: Project Juniper."


@pytest.fixture
def analysis_env(tmp_path, monkeypatch, request):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(settings, "MEMANTO_BACKEND", getattr(request, "param", "cloud"))
    sessions = session_service.SessionService(
        secret_key="synthetic-audit-key-" * 3,
    )
    monkeypatch.setattr(session_service, "_session_service", sessions)
    agents = AgentService()
    tokens = {}
    for agent_id, content in (
        (AGENT, "Public team plan."),
        (OTHER_AGENT, PRIVATE_TEXT),
    ):
        agents.create_agent(AgentCreate(agent_id=agent_id))
        session = sessions.create_session(agent_id)
        tokens[agent_id] = session.session_token
        record = MemoryRecord(
            agent_id=agent_id,
            actor_id=agent_id,
            source="user",
            type="fact",
            title=content,
            content=content,
            created_at=datetime(2026, 10, 13, 12, tzinfo=timezone.utc),
        )
        sessions.log_memory_to_session_summary(agent_id, session.session_id, record)

    backend = MagicMock()
    backend.answer.generate.return_value = {"answer": "Benign daily report."}
    monkeypatch.setattr(daily_analysis_service, "get_moorcheh_client", lambda: backend)
    monkeypatch.setattr(
        daily_analysis_service, "get_active_embedding_model", lambda: None
    )
    app = FastAPI()
    app.include_router(memory.router, prefix="/api/v2/agents")
    return app, sessions, tokens, backend


async def test_scoped_summary_request_excludes_other_agents_history(analysis_env):
    """Real JWT auth and DirectClient must keep local analysis agent-scoped."""
    app, _sessions, tokens, backend = analysis_env
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("192.0.2.10", 12345)),
        base_url="http://memanto.test",
        headers={"X-Session-Token": tokens[AGENT]},
    ) as client:
        denied = await client.post(
            f"/api/v2/agents/{OTHER_AGENT}/daily-summary", json={"date": DATE}
        )
        assert denied.status_code == 403
        backend.answer.generate.assert_not_called()
        response = await client.post(
            f"/api/v2/agents/{AGENT}/daily-summary", json={"date": DATE}
        )

    assert response.status_code == 200, response.text
    call = backend.answer.generate.call_args.kwargs
    assert call["namespace"] == f"memanto_agent_{AGENT}"
    assert "Public team plan." in call["query"]
    assert PRIVATE_TEXT not in call["query"]
    assert PRIVATE_TEXT not in call["header_prompt"]
    assert response.json()["summary"]["sessions_count"] == 1


@pytest.mark.parametrize("analysis_env", ["on-prem"], indirect=True)
async def test_scoped_onprem_conflicts_exclude_other_agents_history(analysis_env):
    """Wrong-agent log text must never reach the on-prem conflict model."""
    app, _sessions, tokens, backend = analysis_env
    backend.answer.generate.return_value = {"answer": "[]"}
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("192.0.2.10", 12345)),
        base_url="http://memanto.test",
        headers={"X-Session-Token": tokens[AGENT]},
    ) as client:
        response = await client.post(
            f"/api/v2/agents/{AGENT}/conflicts/generate", json={"date": DATE}
        )

    assert response.status_code == 200, response.text
    call = backend.answer.generate.call_args.kwargs
    assert call["namespace"] == f"memanto_agent_{AGENT}"
    assert "Public team plan." in call["query"]
    assert PRIVATE_TEXT not in call["query"]
    assert PRIVATE_TEXT not in call["header_prompt"]


def test_visualizations_exclude_other_agents_history(analysis_env):
    """The local chart parser must enforce the same scope as the AI input."""
    _app, sessions, _tokens, _backend = analysis_env
    records = SummaryVisualizationService()._parse_session_files(
        AGENT, DATE, sessions.sessions_dir
    )
    assert [record["title"] for record in records] == ["Public team plan."]


@pytest.mark.parametrize("operation", ["generate_summary", "generate_conflict_report"])
def test_other_agents_logs_alone_do_not_trigger_analysis(
    analysis_env, monkeypatch, operation
):
    _app, sessions, _tokens, backend = analysis_env
    monkeypatch.setattr(settings, "MEMANTO_BACKEND", "on-prem")
    for path in sessions.sessions_dir.glob(f"{AGENT}_{DATE}_sess_*_summary.md"):
        path.unlink()
    service = daily_analysis_service.DailyAnalysisService()

    assert getattr(service, operation)(AGENT, DATE) == {"status": "no_sessions"}
    backend.answer.generate.assert_not_called()


def test_date_shaped_agent_keeps_its_own_history(analysis_env):
    _app, _sessions, _tokens, backend = analysis_env
    service = daily_analysis_service.DailyAnalysisService()

    result = service.generate_summary(OTHER_AGENT, DATE)

    assert result["sessions_count"] == 1
    query = backend.answer.generate.call_args.kwargs["query"]
    assert PRIVATE_TEXT in query
    assert "Public team plan." not in query


@pytest.mark.parametrize(
    "header",
    [
        "",
        f"# Session Summary for {OTHER_AGENT}\n",
        f"# Session Summary for {AGENT}suffix\n",
        f"# Session Summary for {AGENT} " + "x" * 1000 + "\n",
        f"Unbound log\n# Session Summary for {AGENT}\n",
    ],
    ids=["missing", "other-agent", "prefix", "long", "forged-body-header"],
)
def test_unbound_logs_fail_closed(tmp_path, monkeypatch, header):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    (tmp_path / f"{AGENT}_{DATE}_legacy_summary.md").write_text(
        header + PRIVATE_TEXT, encoding="utf-8"
    )
    backend = MagicMock()
    monkeypatch.setattr(daily_analysis_service, "get_moorcheh_client", lambda: backend)
    service = daily_analysis_service.DailyAnalysisService(
        sessions_dir=tmp_path, summaries_dir=tmp_path / "summaries"
    )

    assert service.generate_summary(AGENT, DATE) == {"status": "no_sessions"}
    backend.answer.generate.assert_not_called()


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_legacy_session_ids_and_multiple_sessions_are_preserved(analysis_env, newline):
    _app, sessions, _tokens, backend = analysis_env
    content = f"# Session Summary for {AGENT}{newline}Earlier team session.{newline}"
    (
        sessions.sessions_dir / f"{AGENT}_{DATE}_legacy_session_01_summary.md"
    ).write_bytes(content.encode("utf-8"))
    # A real, same-agent log from another day is not relevant to this request.
    (sessions.sessions_dir / f"{AGENT}_2026-10-12_old_summary.md").write_text(
        f"# Session Summary for {AGENT}\nYesterday only.", encoding="utf-8"
    )

    result = daily_analysis_service.DailyAnalysisService().generate_summary(AGENT, DATE)

    assert result["sessions_count"] == 2
    query = backend.answer.generate.call_args.kwargs["query"]
    assert "Earlier team session." in query
    assert "Public team plan." in query
    assert PRIVATE_TEXT not in query
    assert "Yesterday only." not in query


def test_summary_symlink_is_not_consumed(analysis_env, tmp_path):
    _app, sessions, _tokens, backend = analysis_env
    outside = tmp_path / "outside.md"
    outside.write_text(f"# Session Summary for {AGENT}\nOutside log.", encoding="utf-8")
    (sessions.sessions_dir / f"{AGENT}_{DATE}_linked_summary.md").symlink_to(outside)

    result = daily_analysis_service.DailyAnalysisService().generate_summary(AGENT, DATE)

    assert result["sessions_count"] == 1
    assert "Outside log." not in backend.answer.generate.call_args.kwargs["query"]
