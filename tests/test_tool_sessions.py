"""Tests for tool attribution and the MEMANTO-session activity view."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from memanto.app.services.activity_service import (
    LIVE_WINDOW_SECONDS,
    ActivityService,
)
from memanto.app.utils.client_identity import (
    ClientIdentity,
    client_from_tool,
    detect_client,
    normalize_tool,
    reset_client,
    set_client,
    set_memanto_session,
)
from memanto.app.utils.temporal_helpers import utc_now


@pytest.fixture
def activity(tmp_path, monkeypatch):
    service = ActivityService(activity_dir=tmp_path / "activity")
    # No real session files in a test run; the merge step is exercised
    # explicitly by the tests that care about it.
    monkeypatch.setattr(
        ActivityService, "_merge_live_sessions", staticmethod(lambda sessions: None)
    )
    return service


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Strip every tool marker so detection starts from a known state."""
    for name in list(dict(__import__("os").environ)):
        if name.startswith(
            (
                "MEMANTO_CLIENT",
                "CLAUDECODE",
                "CLAUDE_CODE",
                "CURSOR_",
                "CODEX_",
                "WINDSURF_",
                "GEMINI_",
                "GOOSE_",
                "OPENCODE",
                "CLINE_",
                "CONTINUE_",
                "PI_",
                "ANTIGRAVITY_",
            )
        ):
            monkeypatch.delenv(name, raising=False)
    set_memanto_session(None)


# --------------------------------------------------------------------------
# Client identity
# --------------------------------------------------------------------------


def test_detect_client_returns_unknown_without_markers():
    identity = detect_client()
    assert identity.tool == "unknown"
    assert identity.is_known is False


def test_explicit_env_wins_over_a_sniffed_marker(monkeypatch):
    monkeypatch.setenv("MEMANTO_CLIENT", "Cursor")
    monkeypatch.setenv("CLAUDECODE", "1")

    assert detect_client().tool == "cursor"


def test_env_signature_identifies_the_tool(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")

    identity = detect_client()

    assert identity.tool == "claude-code"
    assert identity.display == "Claude Code"


def test_bound_context_overrides_environment(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    bound = ClientIdentity(tool="codex", display="Codex CLI")
    token = set_client(bound)
    try:
        assert detect_client() is bound
    finally:
        reset_client(token)
    assert detect_client().tool == "claude-code"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Visual Studio Code", "github-copilot"),
        ("claude-ai", "claude-code"),
        ("Cursor", "cursor"),
        ("Roo Code", "roo"),
        ("", "unknown"),
        (None, "unknown"),
    ],
)
def test_normalize_tool_folds_client_names(raw, expected):
    assert normalize_tool(raw) == expected


# --------------------------------------------------------------------------
# Activity log
# --------------------------------------------------------------------------


def _identity(tool="cursor", project="/p"):
    return ClientIdentity(tool=tool, display=tool.title(), project_dir=project)


def test_log_event_writes_one_json_line(activity):
    activity.log_event("remember", agent_id="dev", count=1, identity=_identity())

    files = list(activity.activity_dir.glob("events-*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["tool"] == "cursor"
    assert event["op"] == "remember"
    assert event["agent_id"] == "dev"


def test_log_event_never_raises_on_broken_storage(tmp_path):
    # A file where the activity directory should be: every write will fail.
    blocker = tmp_path / "activity"
    blocker.write_text("not a directory", encoding="utf-8")
    service = ActivityService(activity_dir=blocker)

    service.log_event("remember", agent_id="dev", count=1)  # must not raise


def test_bound_memanto_session_lands_on_the_event(activity):
    set_memanto_session("sess-42")
    try:
        activity.log_event("remember", agent_id="dev", count=1, identity=_identity())
    finally:
        set_memanto_session(None)

    event = json.loads(
        next(activity.activity_dir.glob("events-*.jsonl"))
        .read_text(encoding="utf-8")
        .strip()
    )
    assert event["session"] == "sess-42"


def test_live_tools_reports_recent_use(activity):
    activity.log_event("remember", "dev", count=1, identity=_identity("cursor"))
    activity.log_event("recall", "dev", count=4, identity=_identity("claude-code"))

    tools = {t["tool"]: t for t in activity.live_tools()}

    assert set(tools) == {"cursor", "claude-code"}
    assert tools["cursor"]["memories_written"] == 1
    assert tools["claude-code"]["memories_read"] == 4
    assert all(t["live"] for t in tools.values())


def test_a_tool_stops_being_live_once_it_goes_quiet(activity, monkeypatch):
    activity.log_event("remember", "dev", count=1, identity=_identity())
    real_now = utc_now()

    monkeypatch.setattr(
        "memanto.app.services.activity_service.utc_now",
        lambda: real_now + timedelta(seconds=LIVE_WINDOW_SECONDS + 30),
    )

    assert activity.live_tools()[0]["live"] is False


def test_session_lists_every_tool_that_took_part(activity):
    activity.log_event(
        "remember", "dev", count=1, identity=_identity("claude-code"), session_id="s1"
    )
    activity.log_event(
        "recall", "dev", count=5, identity=_identity("cursor"), session_id="s1"
    )
    activity.log_event(
        "remember", "dev", count=1, identity=_identity("cursor"), session_id="s1"
    )

    sessions = activity.list_sessions()

    assert len(sessions) == 1
    session = sessions[0]
    assert session["session_id"] == "s1"
    assert session["agent_id"] == "dev"
    assert session["memories_written"] == 2
    assert session["memories_read"] == 5
    assert session["status"] == "live"
    tools = {t["tool"]: t for t in session["tools"]}
    assert set(tools) == {"claude-code", "cursor"}
    assert tools["cursor"]["memories_written"] == 1
    assert tools["cursor"]["memories_read"] == 5
    assert tools["claude-code"]["memories_written"] == 1


def test_two_memanto_sessions_stay_separate(activity):
    activity.log_event(
        "remember", "dev", count=1, identity=_identity("cursor"), session_id="s1"
    )
    activity.log_event(
        "remember", "docs", count=1, identity=_identity("codex"), session_id="s2"
    )

    sessions = {s["session_id"]: s for s in activity.list_sessions()}

    assert set(sessions) == {"s1", "s2"}
    assert sessions["s1"]["agent_id"] == "dev"
    assert sessions["s2"]["agent_id"] == "docs"


def test_events_without_a_session_still_count_toward_liveness(activity):
    """A session-less call is real usage, but it belongs to no session's story."""
    activity.log_event("recall", "dev", count=2, identity=_identity("cursor"))

    assert activity.list_sessions() == []
    assert activity.live_tools()[0]["tool"] == "cursor"


def test_quiet_but_unexpired_session_reads_as_active(tmp_path, monkeypatch):
    """The session record, not the activity gap, decides if a session is over."""
    service = ActivityService(activity_dir=tmp_path / "activity")
    real_now = utc_now()
    service.log_event(
        "remember", "dev", count=1, identity=_identity("cursor"), session_id="s1"
    )

    class _LiveSession:
        session_id = "s1"
        agent_id = "dev"
        started_at = real_now
        expires_at = real_now + timedelta(hours=8)

        def is_active(self):
            return True

    monkeypatch.setattr(
        "memanto.app.services.session_service.get_session_service",
        lambda: type("S", (), {"list_sessions": lambda self: [_LiveSession()]})(),
    )
    monkeypatch.setattr(
        "memanto.app.services.activity_service.utc_now",
        lambda: real_now + timedelta(seconds=LIVE_WINDOW_SECONDS + 60),
    )

    session = service.list_sessions()[0]

    assert session["status"] == "active"
    assert session["expires_at"] == (real_now + timedelta(hours=8)).isoformat()


def test_active_session_with_no_activity_still_appears(tmp_path, monkeypatch):
    """An agent activated but not yet used is a real session; show it."""
    service = ActivityService(activity_dir=tmp_path / "activity")
    started = utc_now()

    class _LiveSession:
        session_id = "fresh"
        agent_id = "dev"
        started_at = started
        expires_at = started + timedelta(hours=8)

        def is_active(self):
            return True

    monkeypatch.setattr(
        "memanto.app.services.session_service.get_session_service",
        lambda: type("S", (), {"list_sessions": lambda self: [_LiveSession()]})(),
    )

    sessions = service.list_sessions()

    assert [s["session_id"] for s in sessions] == ["fresh"]
    assert sessions[0]["tools"] == []
    assert sessions[0]["status"] == "active"


def test_dead_session_files_do_not_flood_the_list(tmp_path, monkeypatch):
    """SessionService keeps one file per agent forever, active or not.

    Merging them all in would bury the sessions that actually did something
    under an empty row for every agent ever created.
    """
    service = ActivityService(activity_dir=tmp_path / "activity")
    service.log_event(
        "remember", "dev", count=1, identity=_identity("cursor"), session_id="s1"
    )
    started = utc_now()

    def _session(session_id, agent_id, active):
        return type(
            "Sess",
            (),
            {
                "session_id": session_id,
                "agent_id": agent_id,
                "started_at": started,
                "expires_at": started + timedelta(hours=8),
                "is_active": lambda self: active,
            },
        )()

    monkeypatch.setattr(
        "memanto.app.services.session_service.get_session_service",
        lambda: type(
            "S",
            (),
            {
                "list_sessions": lambda self: [
                    _session("s1", "dev", False),
                    _session("still-open", "docs", True),
                    _session("long-dead", "old-agent", False),
                ]
            },
        )(),
    )

    ids = {s["session_id"] for s in service.list_sessions()}

    # s1 has activity, still-open is active; long-dead has neither.
    assert ids == {"s1", "still-open"}


def test_get_session_returns_summary_and_timeline(activity):
    activity.log_event(
        "remember", "dev", count=1, identity=_identity(), session_id="s1"
    )
    activity.log_event("recall", "dev", count=3, identity=_identity(), session_id="s1")
    activity.log_event(
        "remember", "dev", count=1, identity=_identity(), session_id="other"
    )

    detail = activity.get_session("s1")

    assert detail["session"]["session_id"] == "s1"
    assert len(detail["events"]) == 2


def test_torn_line_does_not_discard_the_day(activity):
    activity.log_event(
        "remember", "dev", count=1, identity=_identity(), session_id="s1"
    )
    path = next(activity.activity_dir.glob("events-*.jsonl"))
    with open(path, "a", encoding="utf-8") as handle:
        handle.write('{"ts": "2026-0')  # killed mid-write

    assert len(activity.list_sessions()) == 1


# --------------------------------------------------------------------------
# HTTP attribution
# --------------------------------------------------------------------------


def _identity_probe_app():
    """A FastAPI app carrying the real middleware plus an identity echo route."""
    from fastapi import FastAPI

    import memanto.app.main as main_module

    app = FastAPI()
    app.middleware("http")(main_module.attribute_calling_tool)

    @app.get("/probe")
    def probe():
        identity = detect_client()
        return {"tool": identity.tool, "project_dir": identity.project_dir}

    return app


def test_http_caller_is_named_by_its_headers():
    from fastapi.testclient import TestClient

    client = TestClient(_identity_probe_app())
    resp = client.get(
        "/probe",
        headers={"X-Memanto-Client": "Cursor", "X-Memanto-Project": "/repo"},
    )

    assert resp.json() == {"tool": "cursor", "project_dir": "/repo"}


def test_anonymous_http_caller_is_never_attributed_to_the_server_env(monkeypatch):
    """A header-less request must not inherit the server process's own markers.

    Otherwise an editor that launched `memanto server` would be credited with
    every anonymous REST call the server ever handled.
    """
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CLAUDECODE", "1")
    client = TestClient(_identity_probe_app())

    assert client.get("/probe").json()["tool"] == "unknown"


# --------------------------------------------------------------------------
# Explicit tool declaration (--tool / --source)
# --------------------------------------------------------------------------


def test_client_from_tool_normalizes_and_labels():
    identity = client_from_tool("Claude Code")

    assert identity.tool == "claude-code"
    assert identity.display == "Claude Code"


def test_recall_tool_flag_beats_environment(monkeypatch, tmp_path):
    """An agent naming itself is exact; the environment is only a guess."""
    from unittest.mock import MagicMock, patch

    from typer.testing import CliRunner

    from memanto.cli.commands._shared import app

    monkeypatch.setenv("CLAUDECODE", "1")
    captured = {}

    client = MagicMock()
    client.recall.return_value = {"memories": []}

    def _capture(*_args, **_kwargs):
        captured["tool"] = detect_client().tool
        return {"memories": []}

    client.recall.side_effect = _capture

    with (
        patch("memanto.cli.commands.memory.get_client", return_value=client),
        patch(
            "memanto.cli.commands.memory.config_manager.get_active_session",
            return_value=("dev", "token"),
        ),
    ):
        result = CliRunner().invoke(app, ["recall", "anything", "--tool", "cursor"])

    assert result.exit_code == 0, result.output
    assert captured["tool"] == "cursor"


def test_answer_accepts_the_tool_flag(monkeypatch):
    from unittest.mock import MagicMock, patch

    from typer.testing import CliRunner

    from memanto.cli.commands._shared import app

    monkeypatch.setenv("CLAUDECODE", "1")
    captured = {}
    client = MagicMock()

    def _capture(*_args, **_kwargs):
        captured["tool"] = detect_client().tool
        return {"answer": "ok", "context_memories": []}

    client.answer.side_effect = _capture

    with (
        patch("memanto.cli.commands.memory.get_client", return_value=client),
        patch(
            "memanto.cli.commands.memory.config_manager.get_active_session",
            return_value=("dev", "token"),
        ),
    ):
        result = CliRunner().invoke(app, ["answer", "what?", "--tool", "codex"])

    assert result.exit_code == 0, result.output
    assert captured["tool"] == "codex"


def test_remember_source_names_the_calling_tool(monkeypatch):
    """`remember` has no --tool: --source already names the writer."""
    from memanto.cli.commands.memory import _tool_from_source

    assert _tool_from_source("cursor") == "cursor"
    assert _tool_from_source("claude-code") == "claude-code"


def test_a_human_source_does_not_become_a_connected_tool():
    """A memory dictated by a person is still made by some tool.

    Treating "user" as the caller would put a person on the connected-tools
    diagram; falling through lets environment detection name the real tool.
    """
    from memanto.cli.commands.memory import _tool_from_source

    assert _tool_from_source("user") is None
    assert _tool_from_source("User") is None
    assert _tool_from_source("agent") is None
    assert _tool_from_source(None) is None
