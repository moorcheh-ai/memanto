"""Phase 2: browser sign-in, `memanto connect` with no tool, first-run backend choice."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from memanto.app.clients.backend import Backend
from memanto.cli.client.device_auth import DeviceLoginError, device_login
from memanto.cli.commands import auth as auth_module
from memanto.cli.commands import connect as connect_module
from memanto.cli.commands import core as core_module
from memanto.cli.config.manager import ConfigManager
from memanto.cli.main import app

CODE = {
    "device_code": "dev-123",
    "user_code": "BCDF-GHJK",
    "verification_uri": "https://console.test/cli/authorize",
    "verification_uri_complete": "https://console.test/cli/authorize?code=BCDF-GHJK",
    "interval": 5,
    "expires_in": 600,
}


def _token_api(token_responses: list[httpx.Response]):
    """Mock gateway: /cli/device-code returns CODE, /cli/token pops *token_responses*."""
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append({"path": request.url.path, "body": json.loads(request.content)})
        if request.url.path == "/cli/device-code":
            return httpx.Response(200, json=CODE)
        return token_responses.pop(0)

    return httpx.MockTransport(handler), seen


def _pending(error: str = "authorization_pending") -> httpx.Response:
    return httpx.Response(400, json={"error": error})


# device_login


def test_device_login_polls_until_approved():
    transport, seen = _token_api(
        [
            _pending(),
            _pending("slow_down"),
            httpx.Response(200, json={"api_key": "mk_dev", "user_email": "a@b.c"}),
        ]
    )
    shown: list[tuple[str, bool]] = []
    sleeps: list[float] = []

    result = device_login(
        "https://api.test",
        on_code=lambda code, opened: shown.append((code["user_code"], opened)),
        open_browser=lambda url: True,
        sleep=sleeps.append,
        transport=transport,
    )

    assert result == {"api_key": "mk_dev", "user_email": "a@b.c"}
    assert shown == [("BCDF-GHJK", True)]
    assert sleeps == [5, 5, 10]  # slow_down adds 5 seconds
    assert seen[0]["body"]["client_name"] == "memanto-cli"
    assert seen[1] == {"path": "/cli/token", "body": {"device_code": "dev-123"}}


@pytest.mark.parametrize(
    ("error", "message"),
    [("access_denied", "denied"), ("expired_token", "expired")],
)
def test_device_login_stops_on_denied_or_expired(error, message):
    transport, _ = _token_api([_pending(error)])

    with pytest.raises(DeviceLoginError, match=message):
        device_login(
            "https://api.test",
            on_code=lambda c, o: None,
            open_browser=lambda u: True,
            sleep=lambda s: None,
            transport=transport,
        )


def test_device_login_reports_no_browser():
    transport, _ = _token_api([httpx.Response(200, json={"api_key": "mk_dev"})])
    shown: list[bool] = []

    device_login(
        "https://api.test",
        on_code=lambda c, opened: shown.append(opened),
        open_browser=lambda u: False,
        sleep=lambda s: None,
        transport=transport,
    )

    assert shown == [False]


def test_device_login_surfaces_device_limit_message():
    transport, _ = _token_api(
        [
            httpx.Response(
                403,
                json={
                    "error": "device_limit",
                    "error_description": "Remove one under Computers",
                },
            )
        ]
    )

    with pytest.raises(DeviceLoginError, match="Remove one under Computers"):
        device_login(
            "https://api.test",
            on_code=lambda c, o: None,
            open_browser=lambda u: True,
            sleep=lambda s: None,
            transport=transport,
        )


# memanto login (browser)


@pytest.fixture
def cm(tmp_path: Path, monkeypatch) -> ConfigManager:
    for var in ("MEMANTO_API_KEY", "MEMANTO_API_URL", "MOORCHEH_API_KEY"):
        monkeypatch.setenv(var, "")
    manager = ConfigManager(config_dir=tmp_path / ".memanto")
    monkeypatch.setattr(manager, "clear_active_session", lambda: None)
    for module in (auth_module, connect_module, core_module):
        monkeypatch.setattr(module, "config_manager", manager)
    return manager


def test_login_without_key_signs_in_through_browser(cm, monkeypatch):
    import memanto.cli.client.device_auth as device_auth

    def fake_login(base_url, on_code, **_):
        on_code(CODE, False)
        return {
            "api_key": "mk_device",
            "user_email": "dev@example.com",
            "plan": "launch",
        }

    monkeypatch.setattr(device_auth, "device_login", fake_login)

    result = CliRunner().invoke(app, ["login"])

    assert result.exit_code == 0, result.output
    assert "BCDF-GHJK" in result.output
    assert "Open the link on any device" in result.output
    assert "dev@example.com" in result.output
    assert cm.get_memanto_api_key() == "mk_device"
    assert cm.get_backend() == Backend.MEMANTO_CLOUD


def test_login_denied_exits_1_without_saving(cm, monkeypatch):
    import memanto.cli.client.device_auth as device_auth

    def denied(base_url, on_code, **_):
        raise DeviceLoginError("Sign-in was denied.")

    monkeypatch.setattr(device_auth, "device_login", denied)

    result = CliRunner().invoke(app, ["login"])

    assert result.exit_code == 1
    assert "Sign-in was denied" in result.output
    assert cm.get_memanto_api_key() is None


def test_login_ctrl_c_cancels_cleanly(cm, monkeypatch):
    import memanto.cli.client.device_auth as device_auth

    def interrupted(base_url, on_code, **_):
        raise KeyboardInterrupt

    monkeypatch.setattr(device_auth, "device_login", interrupted)

    result = CliRunner().invoke(app, ["login"])

    assert result.exit_code == 1
    assert "Sign-in cancelled" in result.output


# memanto connect (no tool)


class FakeClient:
    def __init__(self, agents: list[dict[str, Any]]) -> None:
        self.agents = agents
        self.created: list[str] = []
        self.activated: list[str] = []

    def list_agents(self) -> dict[str, Any]:
        return {"agents": self.agents}

    def create_agent(self, agent_id: str, pattern: str = "tool") -> dict[str, Any]:
        self.created.append(agent_id)
        return {"agent_id": agent_id}

    def activate_agent(self, agent_id: str) -> dict[str, Any]:
        self.activated.append(agent_id)
        return {"agent_id": agent_id}


@pytest.fixture
def connect_env(cm, monkeypatch, tmp_path):
    """Signed-in Memanto Cloud config, claude-code detected, installs recorded."""
    cm.set_backend(Backend.MEMANTO_CLOUD)
    cm.set_memanto_api_key("mk_abc")
    monkeypatch.setattr(cm, "get_active_session", lambda: (None, None))
    installs: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        connect_module,
        "detect_agents_in_project",
        lambda path: [connect_module.AGENT_REGISTRY["claude-code"]],
    )
    monkeypatch.setattr(
        connect_module,
        "install_agent",
        lambda name, project_dir, is_global, mcp_agent_id=None: installs.append(
            (name, mcp_agent_id)
        )
        or {"steps": ["ok"], "errors": []},
    )
    project = tmp_path / "project"
    project.mkdir()
    return installs, project


def test_connect_yes_uses_detected_tools_and_most_recent_agent(
    connect_env, monkeypatch
):
    installs, project = connect_env
    client = FakeClient(
        [
            {"agent_id": "old", "created_at": "2026-01-01"},
            {"agent_id": "new", "created_at": "2026-10-01"},
        ]
    )
    monkeypatch.setattr(connect_module, "get_client", lambda: client)

    result = CliRunner().invoke(app, ["connect", "--yes", "-p", str(project)])

    assert result.exit_code == 0, result.output
    assert installs == [("claude-code", "new")]
    assert client.activated == ["new"]
    assert "Open a new Claude Code session to start" in result.output
    assert "See your connections" in result.output


def test_connect_yes_creates_default_agent_when_none(connect_env, monkeypatch):
    installs, project = connect_env
    client = FakeClient([])
    monkeypatch.setattr(connect_module, "get_client", lambda: client)

    result = CliRunner().invoke(app, ["connect", "--yes", "-p", str(project)])

    assert result.exit_code == 0, result.output
    assert client.created == ["my-agent"]
    assert installs == [("claude-code", "my-agent")]


def test_connect_interactive_accepts_defaults(connect_env, monkeypatch):
    installs, project = connect_env
    client = FakeClient([{"agent_id": "shared", "created_at": "2026-10-01"}])
    monkeypatch.setattr(connect_module, "get_client", lambda: client)

    result = CliRunner().invoke(app, ["connect", "-p", str(project)], input="\n\n")

    assert result.exit_code == 0, result.output
    assert "(detected)" in result.output
    assert installs == [("claude-code", "shared")]


def test_connect_signs_in_first_when_not_configured(cm, monkeypatch, tmp_path):
    calls: list[str] = []

    def fake_sign_in(key=None):
        calls.append("sign_in")
        raise SystemExit(0)

    monkeypatch.setattr(auth_module, "sign_in", fake_sign_in)

    result = CliRunner().invoke(app, ["connect", "--yes", "-p", str(tmp_path)])

    assert calls == ["sign_in"]
    assert result.exit_code == 0


# First run


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        ("\n", Backend.MEMANTO_CLOUD),
        ("2\n\n", Backend.CLOUD),
        ("2\n2\n", Backend.ON_PREM),
    ],
)
def test_first_run_defaults_to_memanto_cloud(monkeypatch, answers, expected):
    import typer

    answers_iter = iter(answers.split("\n"))
    monkeypatch.setattr(
        typer, "prompt", lambda text, default=None, **_: next(answers_iter) or default
    )

    assert core_module._prompt_backend_choice() == expected
