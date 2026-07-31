"""
Tests for agent deletion resource cleanup.

Verifies that delete_agent removes all associated resources:
- Agent metadata file
- Stale lock files
- Session files
- Conflict reports
- Analysis files
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from memanto.app.services.agent_service import AgentService
from memanto.app.models.session import AgentCreate, AgentInfo


@pytest.fixture
def temp_agents_dir():
    with tempfile.TemporaryDirectory() as tmp:
        agents_dir = Path(tmp) / "agents"
        sessions_dir = Path(tmp) / "sessions"
        conflicts_dir = Path(tmp) / "conflicts"
        analysis_dir = Path(tmp) / "analysis"
        agents_dir.mkdir(parents=True)
        sessions_dir.mkdir(parents=True)
        conflicts_dir.mkdir(parents=True)
        analysis_dir.mkdir(parents=True)
        yield {
            "agents": agents_dir,
            "sessions": sessions_dir,
            "conflicts": conflicts_dir,
            "analysis": analysis_dir,
            "base": Path(tmp),
        }


def _create_test_agent(service, agent_id="test-agent"):
    agent_file = service.agents_dir / f"{agent_id}.json"
    agent = AgentInfo(
        agent_id=agent_id,
        namespace=f"memanto_agent_{agent_id}",
        pattern="support",
        description="Test agent",
        created_at=datetime.now(timezone.utc),
        memory_count=0,
        session_count=0,
        status="ready",
    )
    service._save_agent(agent)
    return agent


class TestDeleteAgentResourceCleanup:

    def test_delete_removes_metadata_file(self, temp_agents_dir):
        service = AgentService(agents_dir=temp_agents_dir["agents"])
        _create_test_agent(service, "agent-a")
        assert service._get_agent_file("agent-a").exists()
        service.delete_agent("agent-a")
        assert not service._get_agent_file("agent-a").exists()

    def test_delete_removes_stale_lock_file(self, temp_agents_dir):
        service = AgentService(agents_dir=temp_agents_dir["agents"])
        _create_test_agent(service, "agent-b")
        lock_file = service._get_agent_file("agent-b").with_suffix(".json.lock")
        lock_file.write_text("")
        service.delete_agent("agent-b")
        assert not lock_file.exists()

    def test_delete_removes_session_files(self, temp_agents_dir):
        service = AgentService(agents_dir=temp_agents_dir["agents"])
        _create_test_agent(service, "agent-c")
        sessions_dir = temp_agents_dir["sessions"]
        session_file = sessions_dir / "agent-c_sess_001.json"
        session_file.write_text(json.dumps({"session_id": "sess_001"}))
        service.delete_agent("agent-c")
        assert not session_file.exists()

    def test_delete_removes_conflict_reports(self, temp_agents_dir):
        service = AgentService(agents_dir=temp_agents_dir["agents"])
        _create_test_agent(service, "agent-d")
        conflicts_dir = temp_agents_dir["conflicts"]
        conflict_file = conflicts_dir / "agent-d_2026-07-31_conflicts.json"
        conflict_file.write_text("[]")
        service.delete_agent("agent-d")
        assert not conflict_file.exists()

    def test_delete_removes_analysis_files(self, temp_agents_dir):
        service = AgentService(agents_dir=temp_agents_dir["agents"])
        _create_test_agent(service, "agent-e")
        analysis_dir = temp_agents_dir["analysis"]
        analysis_file = analysis_dir / "agent-e_2026-07-31.json"
        analysis_file.write_text("{}")
        service.delete_agent("agent-e")
        assert not analysis_file.exists()

    def test_delete_does_not_affect_other_agents(self, temp_agents_dir):
        service = AgentService(agents_dir=temp_agents_dir["agents"])
        _create_test_agent(service, "agent-x")
        _create_test_agent(service, "agent-y")
        sessions_dir = temp_agents_dir["sessions"]
        (sessions_dir / "agent-x_sess_001.json").write_text("{}")
        (sessions_dir / "agent-y_sess_002.json").write_text("{}")
        service.delete_agent("agent-x")
        assert not (sessions_dir / "agent-x_sess_001.json").exists()
        assert (sessions_dir / "agent-y_sess_002.json").exists()
        assert service._get_agent_file("agent-y").exists()

    def test_delete_raises_for_nonexistent_agent(self, temp_agents_dir):
        from memanto.app.utils.errors import AgentNotFoundError
        service = AgentService(agents_dir=temp_agents_dir["agents"])
        with pytest.raises(AgentNotFoundError):
            service.delete_agent("nonexistent-agent")

    @patch("memanto.app.services.agent_service.get_moorcheh_client")
    def test_delete_attempts_namespace_deletion(self, mock_client_factory, temp_agents_dir):
        service = AgentService(agents_dir=temp_agents_dir["agents"])
        _create_test_agent(service, "agent-ns")
        mock_client = MagicMock()
        mock_client_factory.return_value = mock_client
        service.delete_agent("agent-ns", moorcheh_api_key="test-key")
        mock_client.namespaces.delete.assert_called_once_with("memanto_agent_agent-ns")

    @patch("memanto.app.services.agent_service.get_moorcheh_client")
    def test_delete_succeeds_even_if_namespace_deletion_fails(self, mock_client_factory, temp_agents_dir):
        service = AgentService(agents_dir=temp_agents_dir["agents"])
        _create_test_agent(service, "agent-fail")
        mock_client = MagicMock()
        mock_client.namespaces.delete.side_effect = Exception("Network error")
        mock_client_factory.return_value = mock_client
        service.delete_agent("agent-fail", moorcheh_api_key="test-key")
        assert not service._get_agent_file("agent-fail").exists()

    def test_recreate_agent_after_delete_does_not_resurrect_memories(self, temp_agents_dir):
        service = AgentService(agents_dir=temp_agents_dir["agents"])
        _create_test_agent(service, "agent-reborn")
        sessions_dir = temp_agents_dir["sessions"]
        conflicts_dir = temp_agents_dir["conflicts"]
        (sessions_dir / "agent-reborn_sess_old.json").write_text("{}")
        (conflicts_dir / "agent-reborn_2026-07-30_conflicts.json").write_text("[]")
        service.delete_agent("agent-reborn")
        assert not (sessions_dir / "agent-reborn_sess_old.json").exists()
        assert not (conflicts_dir / "agent-reborn_2026-07-30_conflicts.json").exists()
        _create_test_agent(service, "agent-reborn")
        assert service.get_agent("agent-reborn") is not None
        assert service.get_agent("agent-reborn").memory_count == 0
