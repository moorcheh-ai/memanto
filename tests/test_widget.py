"""Tests for the desktop widget backend and ``memanto widget on/off``."""

from datetime import timedelta
from typing import Any, cast

import pytest
from filelock import FileLock
from typer.testing import CliRunner

from memanto.app.clients.backend import Backend
from memanto.app.services.session_service import SessionService
from memanto.cli.client.sdk_client import SdkClient
from memanto.cli.config.manager import ConfigManager
from memanto.cli.widget import api as widget_api
from memanto.cli.widget.api import WidgetApi
from memanto.cli.widget.app import lock_path


class FakeClient:
    """Stands in for SdkClient/HostedClient; activation goes through real sessions."""

    def __init__(self, sessions: SessionService) -> None:
        self.sessions = sessions
        self.agent_id: str | None = None
        self.session_token: str | None = None
        self.activated: list[str] = []
        self.answered: list[tuple[str, str]] = []

    def activate_agent(self, agent_id: str) -> dict[str, Any]:
        self.activated.append(agent_id)
        session = self.sessions.create_session(agent_id)
        return {"session_token": session.session_token}

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        return {
            "agent_id": agent_id,
            "namespace": f"memanto_agent_{agent_id}",
            "memory_count": 0,
            "session_count": 3,
        }

    def list_agents(self) -> dict[str, Any]:
        return {"agents": [{"agent_id": "a"}, {"agent_id": "b", "description": "B"}]}

    def answer(self, agent_id: str, question: str) -> dict[str, Any]:
        self.answered.append((agent_id, question))
        return {"answer": "purple"}

    def get_account(self) -> dict[str, Any]:
        return {"plan": "pro", "usage": {"api_calls": {"used": 5, "limit": 100}}}

    def _get_moorcheh(self) -> Any:
        class Namespaces:
            def list(self) -> dict[str, Any]:
                return {
                    "namespaces": [
                        {"namespace_name": "memanto_agent_other", "item_count": 7},
                        {"namespace_name": "memanto_agent_a", "item_count": 42},
                    ]
                }

        class Moorcheh:
            namespaces = Namespaces()

        return Moorcheh()


@pytest.fixture
def sessions(tmp_path, monkeypatch) -> SessionService:
    service = SessionService(secret_key="k" * 32, sessions_dir=tmp_path / "sessions")
    monkeypatch.setattr(widget_api, "get_session_service", lambda: service)
    return service


def _api(tmp_path, sessions: SessionService, backend: Backend = Backend.CLOUD):
    cm = ConfigManager(config_dir=tmp_path / "cfg")
    cm.set_backend(backend)
    client = FakeClient(sessions)
    return WidgetApi(cm, client_factory=lambda _cm: cast(SdkClient, client)), client


def test_switch_joins_live_session_without_replacing_it(tmp_path, sessions):
    api, client = _api(tmp_path, sessions)
    token_a = sessions.create_session("a").session_token
    sessions.create_session("b")

    state = api.switch("a")

    assert state["agent"]["id"] == "a"
    assert sessions.get_active_session().agent_id == "a"
    # Other tools holding a's token stay signed in.
    assert sessions.get_session("a").session_token == token_a
    assert client.activated == []


def test_switch_activates_agent_without_a_live_session(tmp_path, sessions):
    api, client = _api(tmp_path, sessions)

    state = api.switch("c")

    assert client.activated == ["c"]
    assert state["agent"]["id"] == "c"


def test_join_session_ignores_expired_session(tmp_path, sessions):
    sessions.create_session("a", duration_hours=0)
    assert sessions.join_session("a") is None
    assert sessions.join_session("missing") is None


def test_reset_starts_a_fresh_session_for_the_active_agent(tmp_path, sessions):
    api, client = _api(tmp_path, sessions)
    old = sessions.create_session("a").session_token

    api.reset()

    assert client.activated == ["a"]
    assert sessions.get_session("a").session_token != old


def test_reset_and_ask_report_missing_agent(tmp_path, sessions):
    api, _ = _api(tmp_path, sessions)
    assert api.reset() == {"error": "No active agent to reset."}
    assert api.ask("hi") == {"error": "Pick an agent first."}


def test_ask_answers_for_the_active_agent(tmp_path, sessions):
    api, client = _api(tmp_path, sessions)
    sessions.create_session("a")

    assert api.ask("launch color?") == {"answer": "purple"}
    assert client.answered == [("a", "launch color?")]


def test_state_local_reads_live_memory_count(tmp_path, sessions):
    api, _ = _api(tmp_path, sessions, Backend.CLOUD)
    sessions.create_session("a", duration_hours=2)

    state = api.state()

    assert state["backend"] == "cloud"
    assert state["agent"]["memory_count"] == 42
    assert state["agent"]["session_count"] == 3
    assert state["account"] is None
    assert (
        timedelta(hours=1, minutes=59).total_seconds()
        < state["session"]["remaining_seconds"]
        <= timedelta(hours=2).total_seconds()
    )


def test_state_memanto_cloud_uses_agent_count_and_account(tmp_path, sessions):
    api, _ = _api(tmp_path, sessions, Backend.MEMANTO_CLOUD)
    sessions.create_session("a")

    state = api.state()

    assert state["backend_label"] == "Memanto Cloud"
    assert state["agent"]["memory_count"] == 0
    assert state["account"]["plan"] == "pro"


def test_state_without_active_agent(tmp_path, sessions):
    api, _ = _api(tmp_path, sessions)
    state = api.state()
    assert state["agent"] is None and state["session"] is None


def test_agents_lists_ids_and_descriptions(tmp_path, sessions):
    api, _ = _api(tmp_path, sessions)
    assert api.agents() == {
        "agents": [{"id": "a", "description": ""}, {"id": "b", "description": "B"}]
    }


# ---------------------------------------------------------------- CLI


@pytest.fixture
def widget_cmd(tmp_path, monkeypatch):
    from memanto.cli.commands import widget

    cm = ConfigManager(config_dir=tmp_path)
    monkeypatch.setattr(widget, "config_manager", cm)
    return widget, cm


def test_install_command_prefers_pip(widget_cmd, monkeypatch):
    widget, _ = widget_cmd
    monkeypatch.setattr(widget.importlib.util, "find_spec", lambda name: object())
    cmd = widget.install_command()
    assert cmd[1:4] == ["-m", "pip", "install"]
    assert cmd[-1] == widget.WEBVIEW_REQUIREMENT


def test_install_command_falls_back_to_uv(widget_cmd, monkeypatch):
    widget, _ = widget_cmd
    monkeypatch.setattr(widget.importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(widget.shutil, "which", lambda name: "/bin/uv")
    cmd = widget.install_command()
    assert cmd[:3] == ["/bin/uv", "pip", "install"]
    assert "--python" in cmd


def test_install_command_without_pip_or_uv(widget_cmd, monkeypatch):
    widget, _ = widget_cmd
    monkeypatch.setattr(widget.importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(widget.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError):
        widget.install_command()


def test_is_widget_running_follows_the_lock(widget_cmd):
    widget, cm = widget_cmd
    assert widget.is_widget_running() is False

    holder = FileLock(str(lock_path(cm)))
    holder.acquire()
    try:
        assert widget.is_widget_running() is True
    finally:
        holder.release()
    assert widget.is_widget_running() is False


def test_spawn_widget_creates_missing_config_dir(tmp_path, monkeypatch):
    from memanto.cli.commands import widget

    cm = ConfigManager(config_dir=tmp_path / "fresh" / ".memanto")
    monkeypatch.setattr(widget, "config_manager", cm)
    started = []
    monkeypatch.setattr(
        widget.subprocess, "Popen", lambda args, **kw: started.append(args)
    )

    widget._spawn_widget()

    assert started
    assert (cm.config_dir / "widget.log").exists()


def test_widget_off_when_not_running_clears_stale_pid(widget_cmd):
    from memanto.cli.commands._shared import app

    widget, cm = widget_cmd
    (cm.config_dir / "widget.pid").write_text("999999", encoding="utf-8")

    result = CliRunner().invoke(app, ["widget", "off"])

    assert result.exit_code == 0
    assert "already off" in result.output
    assert not (cm.config_dir / "widget.pid").exists()


def test_widget_rejects_unknown_action():
    from memanto.cli.commands._shared import app

    result = CliRunner().invoke(app, ["widget", "toggle"])
    assert result.exit_code != 0


# ---------------------------------------------------------------- placement

AREA = (0, 0, 1536, 816)  # work area, logical px
TILE = (56, 56)
PANEL = (340, 480)


@pytest.mark.parametrize(
    "tile, expected",
    [
        # bottom-right corner: grows up and left, keeping that corner
        ((1464, 744, 56, 56), (1180, 320, (True, True))),
        # top-left corner: grows down and right
        ((0, 0, 56, 56), (0, 0, (False, False))),
        # top-right corner: grows down and left
        ((1480, 0, 56, 56), (1196, 0, (True, False))),
        # bottom-left corner: grows up and right
        ((0, 760, 56, 56), (0, 336, (False, True))),
    ],
)
def test_panel_opens_toward_free_space(tile, expected):
    assert widget_api.panel_position(tile, AREA, PANEL) == expected


def test_panel_is_clamped_inside_the_work_area():
    # Tile partly dragged past the right and top edges.
    x, y, _ = widget_api.panel_position((1520, -20, 56, 56), AREA, PANEL)
    assert 0 <= x <= AREA[2] - PANEL[0]
    assert 0 <= y <= AREA[3] - PANEL[1]


def test_panel_on_a_second_screen_stays_on_it():
    second = (1536, 0, 1920, 1032)
    x, y, _ = widget_api.panel_position((3400, 960, 56, 56), second, PANEL)
    assert second[0] <= x and x + PANEL[0] <= second[0] + second[2]
    assert y + PANEL[1] <= second[3]


@pytest.mark.parametrize(
    "tile",
    [(1464, 744, 56, 56), (0, 0, 56, 56), (1480, 0, 56, 56), (0, 760, 56, 56)],
)
def test_collapse_returns_tile_to_where_it_opened(tile):
    x, y, anchor = widget_api.panel_position(tile, AREA, PANEL)
    assert widget_api.tile_position((x, y, *PANEL), anchor, TILE) == tile[:2]
