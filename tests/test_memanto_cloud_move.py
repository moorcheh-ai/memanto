"""Phase 3: moving local memories to Memanto Cloud, the login choice, `memanto use`, the notice."""

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from memanto.app.clients.backend import Backend
from memanto.app.utils.errors import AgentAlreadyExistsError, MemoryOperationError
from memanto.cli.client.hosted_client import HostedClient
from memanto.cli.commands import auth as auth_module
from memanto.cli.commands import config_cmd as config_cmd_module
from memanto.cli.commands import core as core_module
from memanto.cli.commands import migrate as migrate_module
from memanto.cli.config.manager import ConfigManager
from memanto.cli.main import app
from memanto.cli.migrate import cloud_move


def _memory(mid: str, created_at: str, **extra: Any) -> dict[str, Any]:
    return {"id": mid, "content": f"memory {mid}", "created_at": created_at, **extra}


class FakeLocal:
    """Local SdkClient: agent registry plus newest-first ``search_recent``."""

    def __init__(self, memories: dict[str, list[dict[str, Any]]]) -> None:
        self.memories = memories
        self.status_asked: list[str] = []

    def list_agents(self) -> dict[str, Any]:
        return {"agents": [{"agent_id": a} for a in self.memories]}

    def _get_read_service(self) -> "FakeLocal":
        return self

    def search_recent(self, agent_id: str, limit: Any, status: str) -> dict:
        assert limit is None
        self.status_asked.append(status)
        newest_first = sorted(
            self.memories[agent_id], key=lambda m: m["created_at"], reverse=True
        )
        return {"results": newest_first}


class FakeHosted:
    """HostedClient stand-in recording created agents and imported items."""

    def __init__(self, existing: list[str] | None = None) -> None:
        self.agents = set(existing or [])
        self.created: list[str] = []
        self.imported: dict[str, list[dict[str, Any]]] = {}
        self.fail_on_batch: int | None = None  # raise on the Nth import call
        self.reject_contents: set[str] = set()
        self.create_error: Exception | None = None
        self.calls = 0

    def list_agents(self) -> dict[str, Any]:
        return {"agents": [{"agent_id": a} for a in sorted(self.agents)]}

    def create_agent(self, agent_id: str) -> dict[str, Any]:
        if self.create_error:
            raise self.create_error
        if agent_id in self.agents:
            raise AgentAlreadyExistsError(agent_id)
        self.agents.add(agent_id)
        self.created.append(agent_id)
        return {"agent_id": agent_id}

    def import_memories(self, agent_id: str, items: list[dict]) -> dict[str, Any]:
        self.calls += 1
        if self.fail_on_batch == self.calls:
            raise ConnectionError("network dropped")
        results = []
        for item in items:
            if item["content"] in self.reject_contents:
                results.append(
                    {"id": None, "status": "failed", "reason": "Invalid tag"}
                )
            else:
                self.imported.setdefault(agent_id, []).append(item)
                results.append({"id": f"cloud-{len(self.imported[agent_id])}"})
        return {"results": results}


@pytest.fixture
def state_file(tmp_path: Path) -> Path:
    return tmp_path / "migrate" / "cloud-state.json"


# Engine


def test_moves_every_field_oldest_first_and_renames_clashes(state_file):
    local = FakeLocal(
        {
            "work": [
                _memory(
                    "m2",
                    "2025-02-01T00:00:00Z",
                    type="decision",
                    title="Deploy",
                    tags=["infra"],
                    confidence=0.6,
                    provenance="inferred",
                    source="claude",
                    status="active",
                    score=None,
                ),
                _memory("m1", "2025-01-01T00:00:00Z"),
            ],
            "notes": [_memory("n1", "2024-05-05T00:00:00Z")],
            "empty": [],
        }
    )
    hosted = FakeHosted(existing=["work"])

    report = cloud_move.move_to_cloud(local, hosted, state_file, "on-prem")

    assert hosted.created == ["work-local", "notes"]
    assert report.empty == ["empty"]
    assert local.status_asked == ["active", "active", "active"]
    work = hosted.imported["work-local"]
    assert [i["content"] for i in work] == ["memory m1", "memory m2"]
    assert work[1] == {
        "content": "memory m2",
        "type": "decision",
        "title": "Deploy",
        "confidence": 0.6,
        "tags": ["infra"],
        "source": "claude",
        "provenance": "inferred",
        "created_at": "2025-02-01T00:00:00Z",
    }
    assert [(a.local_id, a.cloud_id, a.moved) for a in report.agents] == [
        ("work", "work-local", 2),
        ("notes", "notes", 1),
    ]
    state = json.loads(state_file.read_text())
    assert state["source_backend"] == "on-prem"
    assert state["agents"]["work"]["complete"] is True


def test_title_only_memory_moves_title_and_blank_one_is_reported(state_file):
    local = FakeLocal(
        {
            "a": [
                {"id": "t", "title": "Just a title", "content": "", "created_at": "1"},
                {"id": "b", "title": "", "content": "  ", "created_at": "2"},
            ]
        }
    )
    hosted = FakeHosted()

    report = cloud_move.move_to_cloud(local, hosted, state_file, "on-prem")

    assert [i["content"] for i in hosted.imported["a"]] == ["Just a title"]
    assert report.agents[0].failed == [("b", "no content")]


def test_interrupted_move_resumes_without_duplicates(state_file):
    memories = [
        _memory(f"m{i:03d}", f"2025-01-01T00:00:{i % 60:02d}Z") for i in range(250)
    ]
    local = FakeLocal({"big": memories})
    hosted = FakeHosted()
    hosted.fail_on_batch = 2

    with pytest.raises(ConnectionError):
        cloud_move.move_to_cloud(local, hosted, state_file, "cloud")
    assert len(hosted.imported["big"]) == 100

    hosted.fail_on_batch = None
    report = cloud_move.move_to_cloud(local, hosted, state_file, "cloud")

    assert hosted.created == ["big"]  # not created twice
    contents = [i["content"] for i in hosted.imported["big"]]
    assert len(contents) == 250 and len(set(contents)) == 250
    assert report.agents[0].already_moved == 100
    assert report.agents[0].moved == 150


def test_rejected_memories_are_retried_on_the_next_run(state_file):
    local = FakeLocal({"a": [_memory("ok", "1"), _memory("bad", "2")]})
    hosted = FakeHosted()
    hosted.reject_contents = {"memory bad"}

    first = cloud_move.move_to_cloud(local, hosted, state_file, "on-prem")
    assert first.agents[0].failed == [("bad", "Invalid tag")]
    assert json.loads(state_file.read_text())["agents"]["a"]["complete"] is False

    hosted.reject_contents = set()
    second = cloud_move.move_to_cloud(local, hosted, state_file, "on-prem")

    assert second.agents[0].moved == 1
    assert [i["content"] for i in hosted.imported["a"]] == ["memory ok", "memory bad"]


def test_agent_limit_stops_new_agents_but_finishes_started_ones(state_file):
    local = FakeLocal({"started": [_memory("s1", "1")], "new": [_memory("x", "1")]})
    hosted = FakeHosted()
    cloud_move.save_state(
        state_file,
        {
            "version": 1,
            "source_backend": "on-prem",
            "agents": {
                "started": {
                    "cloud_agent_id": "started",
                    "moved_ids": [],
                    "complete": False,
                }
            },
        },
    )
    hosted.create_error = MemoryOperationError(
        "Memanto Cloud plan limit reached: agents"
    )

    report = cloud_move.move_to_cloud(local, hosted, state_file, "on-prem")

    assert report.not_moved == ["new"]
    assert "plan limit" in (report.stop_reason or "")
    assert [i["content"] for i in hosted.imported["started"]] == ["memory s1"]


def test_progress_from_another_backend_is_ignored(state_file):
    cloud_move.save_state(
        state_file,
        {
            "version": 1,
            "source_backend": "cloud",
            "agents": {
                "a": {"cloud_agent_id": "a", "moved_ids": ["m1"], "complete": True}
            },
        },
    )
    hosted = FakeHosted(existing=["a"])

    report = cloud_move.move_to_cloud(
        FakeLocal({"a": [_memory("m1", "1")]}), hosted, state_file, "on-prem"
    )

    assert report.agents[0].cloud_id == "a-local"
    assert report.agents[0].moved == 1


# CLI


@pytest.fixture
def cm(tmp_path: Path, monkeypatch) -> ConfigManager:
    for var in ("MEMANTO_API_KEY", "MEMANTO_API_URL", "MOORCHEH_API_KEY"):
        monkeypatch.setenv(var, "")
    manager = ConfigManager(config_dir=tmp_path / ".memanto")
    monkeypatch.setattr(manager, "clear_active_session", lambda: None)
    for module in (auth_module, config_cmd_module, core_module, migrate_module):
        monkeypatch.setattr(module, "config_manager", manager)
    monkeypatch.setattr(HostedClient, "get_account", lambda self: {"email": "a@b.c"})
    monkeypatch.setattr(HostedClient, "sign_out_device", lambda self: True)
    return manager


@pytest.fixture
def moves(monkeypatch) -> list[Backend]:
    calls: list[Backend] = []
    monkeypatch.setattr(migrate_module, "run_cloud_move", calls.append)
    return calls


def _on_prem(cm: ConfigManager) -> None:
    cm.set_backend(Backend.ON_PREM)


@pytest.mark.parametrize(
    ("answer", "backend", "moved"),
    [
        ("1", Backend.MEMANTO_CLOUD, [Backend.ON_PREM]),
        ("2", Backend.MEMANTO_CLOUD, []),
        ("3", Backend.ON_PREM, []),
    ],
)
def test_login_on_local_backend_asks_what_to_do(
    cm, moves, monkeypatch, answer, backend, moved
):
    _on_prem(cm)
    monkeypatch.setattr(auth_module, "_stdin_is_terminal", lambda: True)

    result = CliRunner().invoke(app, ["login", "--key", "mk_new"], input=f"{answer}\n")

    assert result.exit_code == 0, result.output
    assert "What should happen to its memories?" in result.output
    assert cm.get_backend() == backend
    assert moves == moved
    assert cm.get_memanto_api_key() == "mk_new"
    if backend == Backend.MEMANTO_CLOUD:
        assert cm.get("previous_backend") == "on-prem"
    else:
        assert "memanto use cloud" in result.output


def test_login_without_terminal_switches_without_asking(cm, moves):
    _on_prem(cm)

    result = CliRunner().invoke(app, ["login", "--key", "mk_new"])

    assert result.exit_code == 0, result.output
    assert "What should happen" not in result.output
    assert cm.get_backend() == Backend.MEMANTO_CLOUD
    assert moves == []


@pytest.mark.parametrize(
    ("target", "backend"),
    [
        ("moorcheh", Backend.CLOUD),
        ("on-prem", Backend.ON_PREM),
        ("local", Backend.ON_PREM),
    ],
)
def test_use_maps_names_to_backends(cm, monkeypatch, target, backend):
    switched: list[Backend] = []
    monkeypatch.setattr(config_cmd_module, "switch_to_backend", switched.append)

    result = CliRunner().invoke(app, ["use", target])

    assert result.exit_code == 0, result.output
    assert switched == [backend]


def test_use_rejects_unknown_backend(cm):
    result = CliRunner().invoke(app, ["use", "mars"])

    assert result.exit_code == 1
    assert "memanto use cloud | moorcheh | on-prem" in result.output


def test_use_cloud_when_signed_in_switches_and_remembers_previous(cm):
    _on_prem(cm)
    cm.set_memanto_api_key("mk_abc")

    result = CliRunner().invoke(app, ["use", "cloud"])

    assert result.exit_code == 0, result.output
    assert cm.get_backend() == Backend.MEMANTO_CLOUD
    assert cm.get("previous_backend") == "on-prem"


def test_use_cloud_when_signed_out_signs_in(cm, monkeypatch):
    _on_prem(cm)
    signed_in: list[bool] = []
    monkeypatch.setattr(auth_module, "sign_in", lambda: signed_in.append(True))

    result = CliRunner().invoke(app, ["use", "cloud"])

    assert result.exit_code == 0, result.output
    assert signed_in == [True]


def test_migrate_to_cloud_needs_sign_in(cm, moves):
    result = CliRunner().invoke(app, ["migrate", "to-cloud"])

    assert result.exit_code == 1
    assert "memanto login" in result.output
    assert moves == []


def test_migrate_to_cloud_moves_from_previous_backend(cm, moves):
    cm.set_backend(Backend.MEMANTO_CLOUD)
    cm.set("previous_backend", "cloud")
    cm.set_memanto_api_key("mk_abc")

    result = CliRunner().invoke(app, ["migrate", "to-cloud"])

    assert result.exit_code == 0, result.output
    assert moves == [Backend.CLOUD]


def test_migrate_to_cloud_from_flag_and_nothing_to_move(cm, moves):
    cm.set_backend(Backend.MEMANTO_CLOUD)
    cm.set_memanto_api_key("mk_abc")

    assert CliRunner().invoke(app, ["migrate", "to-cloud"]).exit_code == 1
    result = CliRunner().invoke(app, ["migrate", "to-cloud", "--from", "on-prem"])

    assert result.exit_code == 0, result.output
    assert moves == [Backend.ON_PREM]


def test_run_cloud_move_reads_through_the_source_backend(cm, monkeypatch):
    from memanto.app.config import settings

    cm.set_backend(Backend.MEMANTO_CLOUD)
    cm.set_memanto_api_key("mk_abc")
    seen: list[str] = []

    def fake_move(local, hosted, path, source, on_progress=None):
        seen.append(settings.MEMANTO_BACKEND)
        assert isinstance(hosted, HostedClient)
        return cloud_move.MoveReport()

    monkeypatch.setattr(cloud_move, "move_to_cloud", fake_move)
    monkeypatch.setattr(settings, "MEMANTO_BACKEND", "memanto-cloud")

    migrate_module.run_cloud_move(Backend.ON_PREM)

    assert seen == ["on-prem"]
    assert settings.MEMANTO_BACKEND == "memanto-cloud"


# One-time notice


@pytest.fixture
def terminal(monkeypatch) -> None:
    monkeypatch.setattr(core_module, "_stdout_is_terminal", lambda: True)


NOTICE = "Memanto Cloud keeps your memories"


def test_notice_shows_once_after_a_regular_command(cm, terminal):
    _on_prem(cm)

    first = CliRunner().invoke(app, ["config", "show"])
    second = CliRunner().invoke(app, ["config", "show"])

    assert NOTICE in first.output and "memanto login" in first.output
    assert NOTICE not in second.output


def test_no_notice_after_cloud_commands(cm, terminal, monkeypatch):
    _on_prem(cm)
    monkeypatch.setattr(config_cmd_module, "switch_to_backend", lambda backend: None)

    result = CliRunner().invoke(app, ["use", "on-prem"])

    assert NOTICE not in result.output
    assert cm.get("cloud_notice_shown") is None


@pytest.mark.parametrize("backend", [Backend.MEMANTO_CLOUD, None])
def test_no_notice_on_memanto_cloud_or_before_setup(cm, terminal, backend):
    if backend:
        cm.set_backend(backend)

    CliRunner().invoke(app, ["config", "show"])

    assert cm.get("cloud_notice_shown") is None


def test_no_notice_when_output_is_not_a_terminal(cm):
    _on_prem(cm)

    result = CliRunner().invoke(app, ["config", "show"])

    assert NOTICE not in result.output
    assert cm.get("cloud_notice_shown") is None
