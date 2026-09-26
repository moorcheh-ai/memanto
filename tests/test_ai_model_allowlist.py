"""ai_model request parameter is gated by ANSWER_ALLOWED_MODELS.

Session-token holders previously could force arbitrary backend models on
/answer and /remember/extract, overriding the operator's configured model
(cost/quota abuse and memory-context egress to unapproved models).
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

os.environ["MOORCHEH_API_KEY"] = "test-api-key"

from memanto.app.config import settings
from memanto.app.main import app


@pytest.fixture
async def env(tmp_path):
    with (
        patch("memanto.app.services.agent_service.Path.home", return_value=tmp_path),
        patch("memanto.app.services.session_service.Path.home", return_value=tmp_path),
    ):
        from memanto.app.routes.sessions import agent_service
        from memanto.app.services import session_service as ssm

        ssm._session_service = None
        ss = ssm.get_session_service()
        agent_service.agents_dir = tmp_path / ".memanto" / "agents"
        agent_service.agents_dir.mkdir(parents=True, exist_ok=True)
        ss.sessions_dir.mkdir(parents=True, exist_ok=True)

        from memanto.app.clients.moorcheh import moorcheh_client

        moorcheh_client.reset_client()

        mock_instance = MagicMock()
        mock_instance.namespaces.create.return_value = {"status": "created"}
        mock_instance.namespaces.list.return_value = {"namespaces": []}
        mock_instance.answer.generate.return_value = {"answer": "ok", "sources": []}

        with (
            patch(
                "memanto.app.services.agent_service.get_moorcheh_client",
                return_value=mock_instance,
            ),
            patch(
                "memanto.app.clients.moorcheh.MoorchehClient",
                return_value=mock_instance,
            ),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac, mock_instance
        ssm._session_service = None


async def _activate(ac):
    auth = {"Authorization": f"Bearer {settings.MOORCHEH_API_KEY}"}
    await ac.post("/api/v2/agents", headers=auth, json={"agent_id": "victim-agent"})
    r = await ac.post("/api/v2/agents/victim-agent/activate", headers=auth)
    return {"X-Session-Token": r.json()["session_token"]}


@pytest.mark.asyncio
async def test_answer_rejects_unlisted_ai_model(env, monkeypatch):
    monkeypatch.setattr(settings, "ANSWER_ALLOWED_MODELS", "")
    ac, mock_instance = env
    headers = await _activate(ac)

    r = await ac.post(
        "/api/v2/agents/victim-agent/answer",
        headers=headers,
        json={"question": "hello", "ai_model": "attacker.premium-model"},
    )
    assert r.status_code == 400
    mock_instance.answer.generate.assert_not_called()


@pytest.mark.asyncio
async def test_answer_allows_allowlisted_ai_model(env, monkeypatch):
    monkeypatch.setattr(
        settings,
        "ANSWER_ALLOWED_MODELS",
        "anthropic.claude-sonnet-4-6,openai.gpt-5",
    )
    ac, mock_instance = env
    headers = await _activate(ac)

    r = await ac.post(
        "/api/v2/agents/victim-agent/answer",
        headers=headers,
        json={"question": "hello", "ai_model": "openai.gpt-5"},
    )
    assert r.status_code == 200, r.text
    assert mock_instance.answer.generate.call_args.kwargs["ai_model"] == "openai.gpt-5"


@pytest.mark.asyncio
async def test_extract_rejects_unlisted_ai_model(env, monkeypatch):
    monkeypatch.setattr(settings, "ANSWER_ALLOWED_MODELS", "")
    ac, mock_instance = env
    headers = await _activate(ac)

    r = await ac.post(
        "/api/v2/agents/victim-agent/remember/extract",
        headers=headers,
        json={
            "messages": [{"role": "user", "content": "remember that I like tea"}],
            "dry_run": True,
            "ai_model": "attacker.premium-model",
        },
    )
    assert r.status_code == 400
    mock_instance.answer.generate.assert_not_called()


@pytest.mark.asyncio
async def test_answer_without_ai_model_uses_default(env, monkeypatch):
    monkeypatch.setattr(settings, "ANSWER_ALLOWED_MODELS", "")
    ac, mock_instance = env
    headers = await _activate(ac)

    r = await ac.post(
        "/api/v2/agents/victim-agent/answer",
        headers=headers,
        json={"question": "hello"},
    )
    assert r.status_code == 200, r.text
    assert (
        mock_instance.answer.generate.call_args.kwargs["ai_model"]
        == settings.ANSWER_MODEL
    )
