"""Regression tests for crash-safe local state persistence."""

import os
from datetime import datetime
from unittest.mock import patch

import pytest

from memanto.app.models.session import AgentInfo, AgentPattern, SessionStatus
from memanto.app.services.agent_service import AgentService
from memanto.app.services.session_service import SessionService
from memanto.cli.config.manager import ConfigManager


def test_onprem_state_survives_interrupted_replace(tmp_path):
    """An interrupted state replacement must preserve the previous file."""
    manager = ConfigManager(tmp_path)
    manager.set_onprem_state(
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )
    state_path = manager._onprem_state_path()
    original = state_path.read_text(encoding="utf-8")

    with (
        patch(
            "memanto.app.utils.atomic_write.os.replace",
            side_effect=OSError("simulated interruption"),
        ),
        pytest.raises(OSError, match="simulated interruption"),
    ):
        manager.set_onprem_state(llm_model="qwen3:8b")

    assert state_path.read_text(encoding="utf-8") == original
    assert manager.get_onprem_state() == {
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-small",
    }
    assert list(state_path.parent.glob(f".{state_path.name}.*.tmp")) == []


def test_yaml_config_survives_interrupted_replace(tmp_path):
    """An interrupted YAML replacement must preserve the previous config."""
    manager = ConfigManager(tmp_path)
    manager.set("backend", "cloud")
    original = manager.config_file.read_text(encoding="utf-8")

    with (
        patch(
            "memanto.app.utils.atomic_write.os.replace",
            side_effect=OSError("simulated interruption"),
        ),
        pytest.raises(OSError, match="simulated interruption"),
    ):
        manager.set("backend", "on-prem")

    assert manager.config_file.read_text(encoding="utf-8") == original
    assert manager.get("backend") == "cloud"
    assert list(tmp_path.glob(f".{manager.config_file.name}.*.tmp")) == []


def test_connections_survive_interrupted_replace(tmp_path):
    """An interrupted registry replacement must preserve existing connections."""
    manager = ConfigManager(tmp_path)
    original_connections = {
        "claude": {"projects": ["/existing/project"], "installed_global": True}
    }
    manager._save_connections(original_connections)
    original = manager.connections_file.read_text(encoding="utf-8")

    with (
        patch(
            "memanto.app.utils.atomic_write.os.replace",
            side_effect=OSError("simulated interruption"),
        ),
        pytest.raises(OSError, match="simulated interruption"),
    ):
        manager._save_connections(
            {"claude": {"projects": ["/new/project"], "installed_global": False}}
        )

    assert manager.connections_file.read_text(encoding="utf-8") == original
    assert manager.load_connections() == original_connections
    assert list(tmp_path.glob(f".{manager.connections_file.name}.*.tmp")) == []


def test_cleanup_error_does_not_mask_replace_failure(tmp_path):
    """Cleanup failures must not replace the original persistence error."""
    manager = ConfigManager(tmp_path)
    state_path = manager._onprem_state_path()

    with (
        patch(
            "memanto.app.utils.atomic_write.os.replace",
            side_effect=OSError("replace failed"),
        ),
        patch(
            "memanto.app.utils.atomic_write.Path.unlink",
            side_effect=PermissionError("temporary file is locked"),
        ),
        pytest.raises(OSError, match="replace failed"),
    ):
        manager.set_onprem_state(llm_model="qwen3:8b")

    leftovers = list(state_path.parent.glob(f".{state_path.name}.*.tmp"))
    assert len(leftovers) == 1
    leftovers[0].unlink()


def test_agent_metadata_survives_interrupted_replace(tmp_path):
    """An interrupted agent update must preserve the previous metadata."""
    service = AgentService(agents_dir=tmp_path / "agents")
    agent = AgentInfo(
        agent_id="test-agent",
        namespace="memanto_agent_test-agent",
        pattern=AgentPattern.PROJECT,
        description="Original description",
        created_at=datetime(2026, 7, 16),
        status="ready",
    )
    service._save_agent(agent)
    agent_file = service._get_agent_file(agent.agent_id)
    original = agent_file.read_text(encoding="utf-8")
    agent.description = "Updated description"

    with (
        patch(
            "memanto.app.utils.atomic_write.os.replace",
            side_effect=OSError("simulated interruption"),
        ),
        pytest.raises(OSError, match="simulated interruption"),
    ):
        service._save_agent(agent)

    assert agent_file.read_text(encoding="utf-8") == original
    assert service.get_agent(agent.agent_id).description == "Original description"
    assert list(agent_file.parent.glob(f".{agent_file.name}.*.tmp")) == []


def test_session_metadata_survives_interrupted_replace(tmp_path):
    """An interrupted session update must preserve the active session."""
    service = SessionService(
        secret_key="test-secret-key-min-32-bytes-1234",
        sessions_dir=tmp_path / "sessions",
    )
    session = service.create_session(
        agent_id="test-agent",
        pattern=AgentPattern.PROJECT,
        duration_hours=1,
    )
    session_file = service.sessions_dir / "test-agent.json"
    original = session_file.read_text(encoding="utf-8")
    session.status = SessionStatus.TERMINATED

    with (
        patch(
            "memanto.app.utils.atomic_write.os.replace",
            side_effect=OSError("simulated interruption"),
        ),
        pytest.raises(OSError, match="simulated interruption"),
    ):
        service._save_session(session)

    assert session_file.read_text(encoding="utf-8") == original
    assert service.get_session("test-agent").status == SessionStatus.ACTIVE
    assert list(session_file.parent.glob(f".{session_file.name}.*.tmp")) == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are not portable")
def test_atomic_state_files_are_owner_only(tmp_path):
    """Atomically persisted local state files must be owner-readable only."""
    manager = ConfigManager(tmp_path)

    manager.set("backend", "cloud")
    manager.set_onprem_state(llm_model="qwen3:8b")
    manager._save_connections({"claude": {"projects": [], "installed_global": True}})

    agent_service = AgentService(agents_dir=tmp_path / "agents")
    agent_service._save_agent(
        AgentInfo(
            agent_id="test-agent",
            namespace="memanto_agent_test-agent",
            pattern=AgentPattern.PROJECT,
            created_at=datetime(2026, 7, 16),
            status="ready",
        )
    )
    session_service = SessionService(
        secret_key="test-secret-key-min-32-bytes-1234",
        sessions_dir=tmp_path / "sessions",
    )
    session_service.create_session(agent_id="test-agent", duration_hours=1)

    for path in (
        manager.config_file,
        manager._onprem_state_path(),
        manager.connections_file,
        agent_service._get_agent_file("test-agent"),
        session_service.sessions_dir / "test-agent.json",
    ):
        assert path.stat().st_mode & 0o777 == 0o600
