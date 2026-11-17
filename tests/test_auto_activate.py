"""Auto-activate: resume the last active agent when none is active.

One ``sessions/active`` marker is shared by the CLI, coding-tool hooks, the MCP
server, the widget and the REST server, so resuming it in
``SessionService.get_active_session`` covers every tool at once.
"""

import pytest
from typer.testing import CliRunner

from memanto.app.config import settings
from memanto.app.services.session_service import SessionService
from memanto.cli.config.manager import ConfigManager


@pytest.fixture
def sessions(tmp_path, monkeypatch) -> SessionService:
    monkeypatch.setattr(settings, "SESSION_AUTO_ACTIVATE_ENABLED", True)
    monkeypatch.setattr(settings, "MEMANTO_BACKEND", "cloud")
    return SessionService(secret_key="k" * 32, sessions_dir=tmp_path / "sessions")


def test_activating_records_the_last_active_agent(sessions):
    sessions.create_session("a")
    sessions.create_session("b")
    assert sessions.get_last_active() == {"agent_id": "b", "paused": False}


def test_resumes_the_live_session_without_replacing_it(sessions):
    live = sessions.create_session("a")
    sessions.clear_active_session()  # e.g. a backend switch round trip

    resumed = sessions.get_active_session()

    assert resumed is not None
    assert resumed.session_token == live.session_token
    assert sessions.get_session("a").session_token == live.session_token


def test_starts_a_fresh_session_when_the_last_one_lapsed(sessions):
    lapsed = sessions.create_session("a", duration_hours=0)
    sessions.clear_active_session()

    resumed = sessions.get_active_session()

    assert resumed is not None and resumed.is_active()
    assert resumed.agent_id == "a"
    assert resumed.session_token != lapsed.session_token


def test_off_by_default(sessions, monkeypatch):
    monkeypatch.setattr(settings, "SESSION_AUTO_ACTIVATE_ENABLED", False)
    sessions.create_session("a")
    sessions.clear_active_session()
    assert sessions.get_active_session() is None


def test_off_also_stops_renew_and_recreate(sessions, monkeypatch):
    """One switch: with it off, sessions simply end when they expire."""
    monkeypatch.setattr(settings, "SESSION_AUTO_ACTIVATE_ENABLED", False)
    near_expiry = sessions.create_session("a", duration_hours=0)
    assert sessions.check_and_auto_renew("a") is None
    assert sessions.check_and_auto_recreate(near_expiry.session_token) is None
    assert sessions.get_active_session() is None

    monkeypatch.setattr(settings, "SESSION_AUTO_ACTIVATE_ENABLED", True)
    recreated = sessions.check_and_auto_recreate(near_expiry.session_token)
    assert recreated is not None and recreated.is_active()


def test_expired_session_with_switch_off_says_how_to_fix_it(sessions, monkeypatch):
    """Long-running clients (MCP, widget) get an actionable error, not a bare expiry."""
    import time

    from memanto.app.utils.errors import SessionExpiredError
    from memanto.cli.client.sdk_client import SdkClient

    monkeypatch.setattr(settings, "SESSION_AUTO_ACTIVATE_ENABLED", False)
    lapsed = sessions.create_session("a", duration_hours=0)
    time.sleep(1)
    client = SdkClient(api_key="test-key")
    monkeypatch.setattr(client, "_get_session_service", lambda: sessions)
    client.agent_id, client.session_token = "a", lapsed.session_token

    with pytest.raises(SessionExpiredError, match="auto-activate on"):
        client._get_validated_session_for_agent("a")


def test_deactivate_pauses_until_an_agent_is_activated_again(sessions):
    sessions.create_session("a")
    sessions.clear_active_session(pause_auto_activate=True)

    assert sessions.get_active_session() is None
    assert sessions.get_last_active() == {"agent_id": "a", "paused": True}

    sessions.create_session("b")
    sessions.clear_active_session()
    resumed = sessions.get_active_session()
    assert resumed is not None and resumed.agent_id == "b"


def test_ending_a_session_pauses_and_is_not_resurrected(sessions):
    sessions.create_session("a")
    sessions.end_session("a")  # REST /deactivate

    assert sessions.get_active_session() is None
    assert sessions.get_last_active() == {"agent_id": "a", "paused": True}


def test_deleted_agent_is_forgotten(sessions):
    sessions.create_session("a")
    sessions.delete_session("a")
    assert sessions.get_last_active() is None
    assert sessions.get_active_session() is None


def test_last_active_agent_is_kept_per_backend(sessions, monkeypatch):
    sessions.create_session("cloud-agent")
    monkeypatch.setattr(settings, "MEMANTO_BACKEND", "memanto-cloud")
    sessions.clear_active_session()
    assert sessions.get_active_session() is None  # nothing recorded on Cloud yet

    sessions.create_session("hosted-agent")
    monkeypatch.setattr(settings, "MEMANTO_BACKEND", "cloud")
    sessions.clear_active_session()
    resumed = sessions.get_active_session()
    assert resumed is not None and resumed.agent_id == "cloud-agent"


def test_record_is_not_listed_as_a_session(sessions):
    sessions.create_session("a")
    assert [s.agent_id for s in sessions.list_sessions()] == ["a"]


def test_an_existing_active_agent_wins(sessions):
    sessions.create_session("a")
    sessions.create_session("b")
    assert sessions.get_active_session().agent_id == "b"


def test_a_failed_record_write_never_fails_activation(sessions, monkeypatch):
    """Windows can refuse the atomic replace while another process reads it."""
    real_write = sessions._write_private_json_atomic

    def flaky(path, data):
        if path == sessions._last_active_path():
            raise PermissionError("[WinError 5] Access is denied")
        real_write(path, data)

    monkeypatch.setattr(sessions, "_write_private_json_atomic", flaky)

    session = sessions.create_session("a")
    sessions.clear_active_session(pause_auto_activate=True)

    assert session.is_active()
    assert sessions.get_last_active() is None


def test_an_unreadable_session_file_means_nothing_to_resume(sessions):
    sessions.create_session("a")
    sessions.clear_active_session()
    (sessions.sessions_dir / "a.json").write_text("{not json", encoding="utf-8")

    assert sessions.get_active_session() is None


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


@pytest.fixture
def cli(tmp_path, monkeypatch, sessions):
    from memanto.cli.commands import _shared, agent
    from memanto.cli.main import app

    cm = ConfigManager(config_dir=tmp_path / "home")
    monkeypatch.setattr(agent, "config_manager", cm)
    monkeypatch.setattr(_shared, "config_manager", cm)
    monkeypatch.setattr(
        "memanto.app.services.session_service.get_session_service", lambda: sessions
    )
    monkeypatch.setattr(settings, "SESSION_AUTO_ACTIVATE_ENABLED", False)

    def run(*args):
        return CliRunner().invoke(app, list(args))

    return run, cm


def test_auto_activate_command_turns_it_on_and_off(cli):
    run, cm = cli

    result = run("agent", "auto-activate", "on")
    assert result.exit_code == 0, result.output
    assert cm.get_session_config()["auto_activate_enabled"] is True
    assert settings.SESSION_AUTO_ACTIVATE_ENABLED is True

    result = run("agent", "auto-activate")
    assert "Auto-activate: on" in result.output

    result = run("agent", "auto-activate", "off")
    assert result.exit_code == 0, result.output
    assert cm.get_session_config()["auto_activate_enabled"] is False


def test_auto_activate_command_rejects_other_values(cli):
    run, _ = cli
    result = run("agent", "auto-activate", "maybe")
    assert result.exit_code != 0


def test_activate_shows_how_to_skip_it_next_time(cli, monkeypatch):
    from memanto.cli.commands import agent

    run, cm = cli

    class _Client:
        def activate_agent(self, agent_id, duration_hours):
            return {"expires_at": "later"}

    monkeypatch.setattr(agent, "get_client", lambda: _Client())

    result = run("agent", "activate", "a")
    assert "memanto agent auto-activate on" in result.output

    cm.set_session_config({"auto_activate_enabled": True})
    result = run("agent", "activate", "a")
    assert "auto-activate on" not in result.output


def test_deactivate_pauses_auto_activate(cli, sessions, monkeypatch):
    run, cm = cli
    cm.set_session_config({"auto_activate_enabled": True})
    monkeypatch.setattr(settings, "SESSION_AUTO_ACTIVATE_ENABLED", True)
    sessions.create_session("a")

    result = run("agent", "deactivate")

    assert result.exit_code == 0, result.output
    assert "paused" in result.output
    assert sessions.get_active_session() is None
