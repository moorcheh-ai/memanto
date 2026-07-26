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
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from memanto.app.models.session import AgentCreate
from memanto.app.services.agent_service import AgentService
from memanto.app.utils.errors import (
    AgentAlreadyExistsError,
    AgentLimitExceededError,
    NamespaceError,
)


def _mp_create_worker(agents_dir: str, agent_id: str, queue) -> None:
    """Module-level worker for process-isolated capacity-lock test."""
    os.environ["MEMANTO_MAX_AGENTS"] = "2"
    from unittest.mock import MagicMock, patch

    from memanto.app.models.session import AgentCreate as _AgentCreate
    from memanto.app.services.agent_service import AgentService as _AgentService
    from memanto.app.utils.errors import AgentLimitExceededError as _Limit

    service = _AgentService(agents_dir=Path(agents_dir))
    mock_client = MagicMock()
    mock_client.namespaces.create.return_value = None
    try:
        with patch(
            "memanto.app.services.agent_service.get_moorcheh_client",
            return_value=mock_client,
        ):
            service.create_agent(
                _AgentCreate(agent_id=agent_id, pattern="tool"),
                moorcheh_api_key="key",
            )
        queue.put(("ok", agent_id))
    except _Limit:
        queue.put(("limit", agent_id))
    except Exception as exc:  # pragma: no cover
        queue.put(("err", f"{type(exc).__name__}:{exc}"))


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

    @patch("memanto.app.services.agent_service.get_moorcheh_client")
    def test_concurrent_distinct_ids_respect_limit(self, mock_client, service):
        """Distinct IDs under a limit of 2 → exactly 2 succeed, rest hit limit."""
        mock_client.return_value.namespaces.create.return_value = None
        successes: list[str] = []
        limits = 0
        lock = threading.Lock()

        def create_one(agent_id: str):
            nonlocal limits
            try:
                service.create_agent(
                    AgentCreate(agent_id=agent_id, pattern="tool"),
                    moorcheh_api_key="key",
                )
                with lock:
                    successes.append(agent_id)
            except AgentLimitExceededError:
                with lock:
                    limits += 1

        with patch.dict(os.environ, {"MEMANTO_MAX_AGENTS": "2"}):
            threads = [
                threading.Thread(target=create_one, args=(f"agent-{i}",))
                for i in range(8)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert len(successes) == 2, f"expected 2 agents, got {successes}"
        assert limits == 6, f"expected 6 limit errors, got {limits}"
        assert len(list(service.agents_dir.glob("*.json"))) == 2

    def test_multiprocess_distinct_ids_respect_limit(self, tmp_agents_dir):
        """Process-isolated creators share capacity lock across AgentService instances."""
        import multiprocessing as mp

        ctx = mp.get_context("spawn")
        queue = ctx.Queue()
        procs = [
            ctx.Process(
                target=_mp_create_worker,
                args=(str(tmp_agents_dir), f"proc-{i}", queue),
            )
            for i in range(8)
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=60)
            assert p.exitcode == 0, f"worker exit {p.exitcode}"

        results = [queue.get(timeout=1) for _ in range(8)]
        oks = [r for r in results if r[0] == "ok"]
        limits = [r for r in results if r[0] == "limit"]
        assert len(oks) == 2, f"expected 2 ok, got {results}"
        assert len(limits) == 6, f"expected 6 limit, got {results}"
        assert len(list(tmp_agents_dir.glob("*.json"))) == 2


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
            with pytest.raises(NamespaceError, match="Failed to create namespace"):
                service.create_agent(
                    AgentCreate(agent_id="fail-agent", pattern="tool"),
                    moorcheh_api_key="key"
                )

        # Placeholder must be cleaned up
        assert not (service.agents_dir / "fail-agent.json").exists()

    @patch("memanto.app.services.agent_service.get_moorcheh_client")
    def test_cleanup_on_save_failure(self, mock_client, service):
        """Placeholder removed if metadata save fails after namespace creation."""
        mock_client.return_value.namespaces.create.return_value = None

        with patch.dict(os.environ, {"MEMANTO_MAX_AGENTS": "10"}):
            with patch.object(
                service, "_save_agent", side_effect=OSError("disk full")
            ):
                with pytest.raises(OSError, match="disk full"):
                    service.create_agent(
                        AgentCreate(agent_id="save-fail-agent", pattern="tool"),
                        moorcheh_api_key="key",
                    )

        assert not (service.agents_dir / "save-fail-agent.json").exists()

    @patch("memanto.app.services.agent_service.get_moorcheh_client")
    def test_retry_after_failure_succeeds(self, mock_client, service):
        """After a failed creation + cleanup, retrying should work."""
        # First call fails
        mock_client.return_value.namespaces.create.side_effect = RuntimeError("timeout")
        with patch.dict(os.environ, {"MEMANTO_MAX_AGENTS": "10"}):
            with pytest.raises(NamespaceError, match="Failed to create namespace"):
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


class TestPlaceholderTolerance:
    """Empty / corrupt claim files must not crash readers."""

    def test_list_skips_empty_and_corrupt(self, service, tmp_agents_dir):
        (tmp_agents_dir / "empty.json").write_text("")
        (tmp_agents_dir / "bad.json").write_text("{not-json")
        listed = service.list_agents()
        assert listed.count == 0

    def test_get_returns_none_for_placeholder(self, service, tmp_agents_dir):
        (tmp_agents_dir / "ghost.json").write_text("")
        assert service.get_agent("ghost") is None

    @patch("memanto.app.services.agent_service.get_moorcheh_client")
    def test_namespace_timeout_cleans_placeholder(self, mock_client, service):
        """Hung namespace create times out and releases the claim."""

        def hang(*args, **kwargs):
            time.sleep(5)
            return None

        mock_client.return_value.namespaces.create.side_effect = hang
        with patch.dict(
            os.environ,
            {"MEMANTO_MAX_AGENTS": "10", "MEMANTO_NAMESPACE_CREATE_TIMEOUT_SEC": "0.2"},
        ):
            # Re-import timeout constant is baked at module load — patch the module attr
            import memanto.app.services.agent_service as mod

            with patch.object(mod, "_NAMESPACE_CREATE_TIMEOUT_SEC", 0.2):
                with pytest.raises(NamespaceError, match="Timed out"):
                    service.create_agent(
                        AgentCreate(agent_id="hang-agent", pattern="tool"),
                        moorcheh_api_key="key",
                    )
        assert not (service.agents_dir / "hang-agent.json").exists()
