"""Tests for agent creation race condition fix (#1453).

Covers:
- Atomic file creation prevents TOCTOU race
- Agent limit enforced (returns 403, not silent 200)
- Duplicate agent returns 409 (not 200)
- Concurrent creation only allows one winner
- Cleanup on limit exceeded (no orphan files)
"""

import json
import os
import shutil
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from memanto.app.models.session import AgentCreate
from memanto.app.services.agent_service import AgentService
from memanto.app.utils.errors import AgentAlreadyExistsError, AgentLimitExceededError


@pytest.fixture
def tmp_agents_dir():
    """Create a temp directory for agent metadata."""
    d = Path(tempfile.mkdtemp())
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def service(tmp_agents_dir):
    """AgentService with isolated temp directory."""
    return AgentService(agents_dir=tmp_agents_dir)


class TestAtomicCreation:
    """Verify atomic file creation prevents race condition."""

    @patch("memanto.app.services.agent_service.get_moorcheh_client")
    def test_first_creation_succeeds(self, mock_client, service):
        """First agent creation should succeed."""
        mock_client.return_value.namespaces.create.return_value = None
        with patch.dict(os.environ, {"MEMANTO_MAX_AGENTS": "10"}):
            agent = service.create_agent(
                AgentCreate(agent_id="test-1", pattern="tool"),
                moorcheh_api_key="test-key"
            )
        assert agent.agent_id == "test-1"
        assert agent.status == "ready"

    @patch("memanto.app.services.agent_service.get_moorcheh_client")
    def test_duplicate_creation_raises_conflict(self, mock_client, service):
        """Creating same agent twice raises AgentAlreadyExistsError."""
        mock_client.return_value.namespaces.create.return_value = None
        with patch.dict(os.environ, {"MEMANTO_MAX_AGENTS": "10"}):
            service.create_agent(
                AgentCreate(agent_id="dup-test", pattern="tool"),
                moorcheh_api_key="test-key"
            )
            with pytest.raises(AgentAlreadyExistsError):
                service.create_agent(
                    AgentCreate(agent_id="dup-test", pattern="tool"),
                    moorcheh_api_key="test-key"
                )

    @patch("memanto.app.services.agent_service.get_moorcheh_client")
    def test_concurrent_creation_only_one_wins(self, mock_client, service):
        """Concurrent creation of the same agent — only one succeeds."""
        mock_client.return_value.namespaces.create.return_value = None
        results = {"success": 0, "conflict": 0}
        lock = threading.Lock()

        def create_agent():
            try:
                with patch.dict(os.environ, {"MEMANTO_MAX_AGENTS": "100"}):
                    service.create_agent(
                        AgentCreate(agent_id="race-test", pattern="tool"),
                        moorcheh_api_key="test-key"
                    )
                with lock:
                    results["success"] += 1
            except AgentAlreadyExistsError:
                with lock:
                    results["conflict"] += 1

        threads = [threading.Thread(target=create_agent) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results["success"] == 1, "Only one thread should succeed"
        assert results["conflict"] == 9, "All others should get conflict"


class TestAgentLimit:
    """Verify plan-based agent limit enforcement."""

    @patch("memanto.app.services.agent_service.get_moorcheh_client")
    def test_limit_enforced_community_plan(self, mock_client, service):
        """Community plan (2 agents) — third creation raises error."""
        mock_client.return_value.namespaces.create.return_value = None

        with patch.dict(os.environ, {"MEMANTO_MAX_AGENTS": "2"}):
            service.create_agent(
                AgentCreate(agent_id="agent-1", pattern="tool"),
                moorcheh_api_key="key"
            )
            service.create_agent(
                AgentCreate(agent_id="agent-2", pattern="tool"),
                moorcheh_api_key="key"
            )
            with pytest.raises(AgentLimitExceededError):
                service.create_agent(
                    AgentCreate(agent_id="agent-3", pattern="tool"),
                    moorcheh_api_key="key"
                )

    @patch("memanto.app.services.agent_service.get_moorcheh_client")
    def test_cleanup_on_limit_exceeded(self, mock_client, service):
        """Orphan file removed when limit is exceeded."""
        mock_client.return_value.namespaces.create.return_value = None

        with patch.dict(os.environ, {"MEMANTO_MAX_AGENTS": "1"}):
            service.create_agent(
                AgentCreate(agent_id="first", pattern="tool"),
                moorcheh_api_key="key"
            )
            with pytest.raises(AgentLimitExceededError):
                service.create_agent(
                    AgentCreate(agent_id="second", pattern="tool"),
                    moorcheh_api_key="key"
                )

        # Verify orphan file was cleaned up
        assert not (service.agents_dir / "second.json").exists()

    @patch("memanto.app.services.agent_service.get_moorcheh_client")
    def test_limit_configurable_via_env(self, mock_client, service):
        """MEMANTO_MAX_AGENTS env var controls the limit."""
        mock_client.return_value.namespaces.create.return_value = None

        with patch.dict(os.environ, {"MEMANTO_MAX_AGENTS": "5"}):
            for i in range(5):
                service.create_agent(
                    AgentCreate(agent_id=f"agent-{i}", pattern="tool"),
                    moorcheh_api_key="key"
                )
            with pytest.raises(AgentLimitExceededError):
                service.create_agent(
                    AgentCreate(agent_id="agent-5", pattern="tool"),
                    moorcheh_api_key="key"
                )

    def test_get_max_agents_default(self, service):
        """Default max agents is 2 (community plan)."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MEMANTO_MAX_AGENTS", None)
            assert service._get_max_agents() == 2

    def test_get_max_agents_invalid_env(self, service):
        """Invalid MEMANTO_MAX_AGENTS falls back to 2."""
        with patch.dict(os.environ, {"MEMANTO_MAX_AGENTS": "not_a_number"}):
            assert service._get_max_agents() == 2


class TestErrorResponses:
    """Verify correct HTTP status codes."""

    def test_already_exists_maps_to_409(self):
        """AgentAlreadyExistsError → HTTP 409."""
        from memanto.app.utils.errors import map_error_to_http_exception
        err = AgentAlreadyExistsError("Agent 'x' already exists")
        http_err = map_error_to_http_exception(err)
        assert http_err.status_code == 409

    def test_limit_exceeded_maps_to_403(self):
        """AgentLimitExceededError → HTTP 403."""
        from memanto.app.utils.errors import map_error_to_http_exception
        err = AgentLimitExceededError("Agent limit reached (2)")
        http_err = map_error_to_http_exception(err)
        assert http_err.status_code == 403


class TestCleanupOnFailure:
    """Verify placeholder file is removed when creation fails after claim."""

    @patch("memanto.app.services.agent_service.get_moorcheh_client")
    def test_cleanup_on_namespace_failure(self, mock_client, service):
        """Placeholder file removed if namespace creation raises."""

        def fail_namespace(*args, **kwargs):
            # Prove the claim/placeholder exists before the failure path cleans it up
            assert (service.agents_dir / "fail-agent.json").exists()
            raise RuntimeError("connection refused")

        mock_client.return_value.namespaces.create.side_effect = fail_namespace

        with patch.dict(os.environ, {"MEMANTO_MAX_AGENTS": "10"}):
            with pytest.raises(Exception, match="Failed to create namespace"):
                service.create_agent(
                    AgentCreate(agent_id="fail-agent", pattern="tool"),
                    moorcheh_api_key="key"
                )

        # Placeholder must be cleaned up
        assert not (service.agents_dir / "fail-agent.json").exists()

    @patch("memanto.app.services.agent_service.get_moorcheh_client")
    def test_retry_after_failure_succeeds(self, mock_client, service):
        """After a failed creation + cleanup, retrying should work."""
        # First call fails
        mock_client.return_value.namespaces.create.side_effect = RuntimeError("timeout")
        with patch.dict(os.environ, {"MEMANTO_MAX_AGENTS": "10"}):
            with pytest.raises(Exception):
                service.create_agent(
                    AgentCreate(agent_id="retry-agent", pattern="tool"),
                    moorcheh_api_key="key"
                )

        # Second call succeeds
        mock_client.return_value.namespaces.create.side_effect = None
        mock_client.return_value.namespaces.create.return_value = None
        with patch.dict(os.environ, {"MEMANTO_MAX_AGENTS": "10"}):
            agent = service.create_agent(
                AgentCreate(agent_id="retry-agent", pattern="tool"),
                moorcheh_api_key="key"
            )
        assert agent.agent_id == "retry-agent"
