"""Tools working together: project tags, and the session-start catch-up."""

import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from memanto.app.utils import client_identity
from memanto.app.utils.client_identity import project_name, project_tag
from memanto.cli.main import app

runner = CliRunner()


# Project tag


def test_project_name_is_the_git_root(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    repo = tmp_path / "my-repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "src" / "pkg").mkdir(parents=True)

    assert project_name(str(repo / "src" / "pkg")) == "my-repo"


def test_project_name_without_git_is_the_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    folder = tmp_path / "notes"
    folder.mkdir()

    assert project_name(str(folder)) == "notes"


def test_project_name_is_none_in_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)

    assert project_name() is None


def test_project_name_prefers_claude_project_dir(tmp_path, monkeypatch):
    project = tmp_path / "web"
    project.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    monkeypatch.chdir(tmp_path)

    assert project_name() == "web"


@pytest.mark.parametrize(
    ("name", "tag"),
    [
        ("memanto", "project_memanto"),
        ("Memanto-Cloud", "project_memanto_cloud"),
        ("my.app v2", "project_my_app_v2"),
        ("--", None),
        (None, None),
    ],
)
def test_project_tag_uses_only_filter_safe_characters(name, tag):
    assert project_tag(name) == tag


def test_project_tag_fits_the_tag_limit():
    tag = project_tag("x" * 100)
    assert tag is not None and len(tag) == 64


# memory sync --catch-up


@pytest.fixture
def sync_env(tmp_path):
    """`memory sync` with a mock client and a temp config dir."""
    client = MagicMock()
    client.recall.return_value = {"memories": []}
    cfg = MagicMock()
    cfg.config_dir = tmp_path
    cfg.get_active_session.return_value = ("team", "token")
    with (
        patch("memanto.cli.commands.memory_mgmt.get_client", return_value=client),
        patch("memanto.cli.commands.memory_mgmt.config_manager", cfg),
        patch(
            "memanto.cli.commands.memory_mgmt.detect_client",
            lambda: client_identity.client_from_tool("claude-code"),
        ),
        patch(
            "memanto.cli.connect.updater.inject_dynamic_memories",
            return_value={},
        ),
    ):
        yield SimpleNamespace(client=client, cursors=tmp_path / "cursors.json")


def _sync(project: Path):
    return runner.invoke(
        app, ["memory", "sync", "--project-dir", str(project), "--catch-up"]
    )


def test_first_catch_up_only_starts_the_clock(sync_env, tmp_path):
    result = _sync(tmp_path)

    assert result.exit_code == 0, result.output
    sync_env.client.recall_changed_since.assert_not_called()
    cursors = json.loads(sync_env.cursors.read_text(encoding="utf-8"))
    [(key, since)] = cursors.items()
    assert key == f"team|claude-code|{tmp_path.resolve()}"
    assert since.startswith("20")


def test_catch_up_lists_memories_from_other_tools(sync_env, tmp_path):
    _sync(tmp_path)
    first = json.loads(sync_env.cursors.read_text(encoding="utf-8"))
    long_text = "word " * 100
    sync_env.client.recall_changed_since.return_value = {
        "memories": [
            {
                "type": "fact",
                "content": "Deploys go\nthrough staging",
                "source": "cursor",
            },
            {"type": "decision", "content": long_text, "source": "user"},
        ]
    }

    result = _sync(tmp_path)

    assert result.exit_code == 0, result.output
    kwargs = sync_env.client.recall_changed_since.call_args.kwargs
    assert kwargs["agent_id"] == "team"
    assert kwargs["since"] == next(iter(first.values()))
    assert kwargs["status"] == "active"
    assert "Since your last session (2 new):" in result.output
    assert "- [FACT] Deploys go through staging (from Cursor)" in result.output
    decision = next(line for line in result.output.splitlines() if "[DECISION]" in line)
    assert decision.endswith("...") and "(from" not in decision
    second = json.loads(sync_env.cursors.read_text(encoding="utf-8"))
    assert next(iter(second.values())) >= next(iter(first.values()))


def test_catch_up_keeps_the_cursor_when_the_read_fails(sync_env, tmp_path):
    _sync(tmp_path)
    before = sync_env.cursors.read_text(encoding="utf-8")
    sync_env.client.recall_changed_since.side_effect = ConnectionError("offline")

    result = _sync(tmp_path)

    assert result.exit_code == 0, result.output
    assert "Could not load memories saved since the last session" in result.output
    assert sync_env.cursors.read_text(encoding="utf-8") == before


def test_sync_without_catch_up_leaves_cursors_alone(sync_env, tmp_path):
    result = runner.invoke(app, ["memory", "sync", "--project-dir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert not sync_env.cursors.exists()
    sync_env.client.recall_changed_since.assert_not_called()


# Claude Code SessionStart hook


def _load_hook():
    path = (
        Path(__file__).resolve().parent.parent
        / "memanto/cli/connect/assets/hooks/session_start.py"
    )
    spec = importlib.util.spec_from_file_location("memanto_session_start", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_session_start_passes_the_catch_up_into_the_session(monkeypatch):
    hook = _load_hook()
    out = (
        "OK Recalled 2 dynamic memories!\n"
        "\n"
        "Since your last session (2 new):\n"
        "- [FACT] Deploys go through staging (from Cursor)\n"
        "- [DECISION] Use uv for installs\n"
        "Completed in 0.4s\n"
    )
    calls = []

    def run(args, **_kw):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")

    monkeypatch.setattr(hook.subprocess, "run", run)

    summary = hook.sync_memory("/proj")

    assert calls[0][-1] == "--catch-up"
    assert summary == (
        "Memory refreshed — 2 active memories loaded.\n"
        "Since your last session (2 new):\n"
        "- [FACT] Deploys go through staging (from Cursor)\n"
        "- [DECISION] Use uv for installs"
    )


def test_session_start_without_catch_up_is_one_line(monkeypatch):
    hook = _load_hook()
    monkeypatch.setattr(
        hook.subprocess,
        "run",
        lambda args, **_kw: subprocess.CompletedProcess(
            args, 0, stdout="OK Recalled 1 dynamic memories!\n", stderr=""
        ),
    )

    assert hook.sync_memory("/proj") == "Memory refreshed — 1 active memory loaded."
