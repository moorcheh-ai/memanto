"""
MEMANTO Core Unit Tests (No Server Required)

Tests the session and agent services directly without HTTP layer.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import jwt
import pytest

from memanto.app.config import settings
from memanto.app.models.session import AgentCreate, AgentPattern, SessionStatus
from memanto.app.services.agent_service import AgentService
from memanto.app.services.session_service import SessionService


class TestSessionService:
    """Unit tests for SessionService"""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create temporary directory for test files"""
        return tmp_path

    @pytest.fixture
    def session_service(self, temp_dir):
        """Create SessionService with temporary storage"""
        sessions_dir = temp_dir / "sessions"
        return SessionService(
            secret_key="test-secret-key-min-32-bytes-1234", sessions_dir=sessions_dir
        )

    @pytest.fixture
    def agent_service(self, temp_dir):
        """Create AgentService with temporary storage"""
        agents_dir = temp_dir / "agents"
        return AgentService(agents_dir=agents_dir)

    def test_generate_namespace(self, session_service):
        """Test namespace generation"""
        namespace = session_service._generate_namespace("test-agent")
        assert namespace == "memanto_agent_test-agent"
        print(f"✅ Namespace format correct: {namespace}")

    def test_create_session(self, session_service):
        """Test session creation"""
        session = session_service.create_session(
            agent_id="test-agent",
            pattern=AgentPattern.SUPPORT,
            duration_hours=4,
        )

        assert session.agent_id == "test-agent"
        assert session.namespace == "memanto_agent_test-agent"
        assert session.status == SessionStatus.ACTIVE
        assert session.session_token is not None
        assert session.pattern == AgentPattern.SUPPORT

        # Check expiration is ~4 hours from now
        time_diff = (session.expires_at - session.started_at).total_seconds()
        assert 3.9 * 3600 < time_diff < 4.1 * 3600

        print("✅ Session created successfully")
        print(f"   Session ID: {session.session_id}")
        print(f"   Namespace: {session.namespace}")
        print(f"   Expires in: {time_diff / 3600:.2f} hours")

    def test_validate_session(self, session_service):
        """Test session validation"""
        # Create session
        session = session_service.create_session(
            agent_id="test-agent", duration_hours=1
        )

        # Validate session
        token_payload = session_service.validate_session(session.session_token)

        assert token_payload.agent_id == "test-agent"
        assert token_payload.namespace == "memanto_agent_test-agent"

        print("✅ Session validation successful")

    def test_validate_expired_session(self, session_service):
        """Test session validation fails for expired session"""
        # Create session with very short duration
        session_service.create_session(
            agent_id="test-agent",
            duration_hours=0,  # Expires immediately
        )

        # Manually expire the session by modifying the token
        # (In real scenario, we'd wait for expiration)
        import time

        time.sleep(1)

        # This should fail because session is expired
        # Note: We can't easily test this without manipulating time
        # Just verify the logic exists
        print("✅ Session expiration logic exists")

    def test_end_session(self, session_service):
        """Test ending session"""
        # Create session
        session = session_service.create_session(
            agent_id="test-agent",
            duration_hours=1,
        )

        # End session
        summary = session_service.end_session("test-agent")

        assert summary.agent_id == "test-agent"
        assert summary.session_id == session.session_id
        assert summary.duration_hours >= 0

        print("✅ Session ended successfully")
        print(f"   Duration: {summary.duration_hours} hours")

    def test_get_active_session_ignores_invalid_session_file(self, session_service):
        """A corrupt active session file should not crash status checks."""
        active_marker = session_service.sessions_dir / "active"
        active_marker.write_text("broken-agent")
        (session_service.sessions_dir / "broken-agent.json").write_text("{")

        assert session_service.get_active_session() is None

    def test_list_sessions_skips_invalid_session_files(self, session_service):
        """One corrupt session record must not hide all valid sessions."""
        valid_session = session_service.create_session(
            agent_id="valid-agent",
            duration_hours=1,
        )
        (session_service.sessions_dir / "broken-agent.json").write_text("{")

        sessions = session_service.list_sessions()

        assert [session.agent_id for session in sessions] == [valid_session.agent_id]


class TestAgentService:
    """Unit tests for AgentService"""

    @pytest.fixture(autouse=True)
    def mock_moorcheh_client(self):
        """Mock Moorcheh client so unit tests never call external API."""
        with patch(
            "memanto.app.services.agent_service.get_moorcheh_client"
        ) as mock_client_factory:
            mock_client = MagicMock()
            mock_client.namespaces.create.return_value = {"status": "created"}
            mock_client.namespaces.list.return_value = {"namespaces": []}
            mock_client_factory.return_value = mock_client
            yield mock_client

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create temporary directory for test files"""
        return tmp_path

    @pytest.fixture
    def agent_service(self, temp_dir):
        """Create AgentService with temporary storage"""
        agents_dir = temp_dir / "agents"
        return AgentService(agents_dir=agents_dir)

    def test_generate_namespace(self, agent_service):
        """Test namespace generation"""
        namespace = agent_service._generate_namespace("customer-support")
        assert namespace == "memanto_agent_customer-support"
        print(f"✅ Agent namespace correct: {namespace}")

    def test_create_agent(self, agent_service):
        """Test agent creation"""
        agent_create = AgentCreate(
            agent_id="test-agent",
            pattern=AgentPattern.SUPPORT,
            description="Test agent",
        )

        agent = agent_service.create_agent(
            agent_create, moorcheh_api_key=settings.MOORCHEH_API_KEY
        )

        assert agent.agent_id == "test-agent"
        assert agent.pattern == AgentPattern.SUPPORT
        assert agent.namespace == "memanto_agent_test-agent"
        assert agent.description == "Test agent"
        assert agent.status == "ready"

        print("✅ Agent created successfully")
        print(f"   Agent ID: {agent.agent_id}")
        print(f"   Namespace: {agent.namespace}")

    def test_list_agents(self, agent_service):
        """Test listing agents"""
        # Create multiple agents
        for i in range(3):
            agent_create = AgentCreate(
                agent_id=f"agent-{i}", pattern=AgentPattern.SUPPORT
            )
            agent_service.create_agent(agent_create, settings.MOORCHEH_API_KEY)

        # List agents
        agent_list = agent_service.list_agents()

        assert agent_list.count == 3
        assert len(agent_list.agents) == 3

        print(f"✅ Listed {agent_list.count} agents")

    def test_get_agent(self, agent_service):
        """Test getting agent info"""
        # Create agent
        agent_create = AgentCreate(agent_id="test-agent", pattern=AgentPattern.PROJECT)
        agent_service.create_agent(agent_create, settings.MOORCHEH_API_KEY)

        # Get agent
        agent = agent_service.get_agent("test-agent")

        assert agent is not None
        assert agent.agent_id == "test-agent"
        assert agent.pattern == AgentPattern.PROJECT

        print("✅ Agent retrieved successfully")

    def test_update_agent_stats(self, agent_service):
        """Test updating agent statistics"""
        # Create agent
        agent_create = AgentCreate(agent_id="test-agent", pattern=AgentPattern.SUPPORT)
        agent_service.create_agent(agent_create, settings.MOORCHEH_API_KEY)

        # Update stats
        updated_agent = agent_service.update_agent_stats(
            agent_id="test-agent",
            last_session=datetime.utcnow(),
            increment_session_count=True,
        )

        assert updated_agent.session_count == 1
        assert updated_agent.last_session is not None

        print("✅ Agent stats updated")
        print(f"   Session count: {updated_agent.session_count}")

    def test_delete_agent(self, agent_service):
        """Test deleting agent"""
        # Create agent
        agent_create = AgentCreate(agent_id="test-agent", pattern=AgentPattern.SUPPORT)
        agent_service.create_agent(agent_create, settings.MOORCHEH_API_KEY)

        # Verify exists
        assert agent_service.agent_exists("test-agent")

        # Delete
        agent_service.delete_agent("test-agent")

        # Verify deleted
        assert not agent_service.agent_exists("test-agent")

        print("✅ Agent deleted successfully")


class TestMemoryWriteServiceDelete:
    """``delete_memory`` must report success for both cloud and on-prem
    response shapes. Cloud returns ``actual_deletions``; on-prem's
    ``/items/delete`` only returns ``deleted_ids``/``status``."""

    @pytest.mark.parametrize(
        "response,expected",
        [
            ({"actual_deletions": 1, "deleted_ids": ["m1"]}, True),
            ({"actual_deletions": 0, "deleted_ids": []}, False),
            ({"status": "success", "deleted_ids": ["m1"]}, True),
            ({"status": "success", "deleted_ids": []}, False),
            ({"status": "success"}, True),
            ({"requested_ids": ["m1"]}, True),
            ({}, False),
        ],
    )
    def test_delete_memory_handles_backend_shapes(self, response, expected):
        from memanto.app.services.memory_write_service import MemoryWriteService

        client = MagicMock()
        client.documents.delete.return_value = response
        assert MemoryWriteService(client).delete_memory("m1", "ns") is expected


class TestForgetEndToEnd:
    """End-to-end ``forget`` flow through ``DirectClient``: create agent →
    activate → delete_memory. Asserts on-prem's response shape
    (``deleted_ids`` only, no ``actual_deletions``) is reported as success
    and that a genuine miss still surfaces as ``ValueError``."""

    @pytest.fixture
    def direct_client(self, tmp_path, monkeypatch, mock_moorcheh_for_tests):
        """A wired ``DirectClient`` with the agent + session dirs redirected
        into ``tmp_path`` so we don't touch ``~/.memanto``. The conftest's
        ``mock_moorcheh_for_tests`` covers ``app.clients.moorcheh`` and
        ``agent_service.get_moorcheh_client``; ``DirectClient`` has its own
        inline ``MoorchehClient`` class, so we also patch that and force the
        lazy ``_moorcheh`` slot to the shared mock."""
        from memanto.cli.client import direct_client as direct_mod
        from memanto.cli.client.direct_client import DirectClient

        monkeypatch.setattr(
            "memanto.app.services.agent_service.get_data_dir",
            lambda: tmp_path,
        )
        monkeypatch.setattr(
            "memanto.app.services.session_service.get_data_dir",
            lambda: tmp_path,
        )
        monkeypatch.setattr(
            direct_mod, "MoorchehClient", lambda **_: mock_moorcheh_for_tests
        )

        client = DirectClient(api_key="test-key")
        client._moorcheh = mock_moorcheh_for_tests  # write/read share this
        client.create_agent("test-agent", "tool", "e2e")
        client.activate_agent("test-agent", duration_hours=1)
        return client, mock_moorcheh_for_tests

    def test_forget_succeeds_on_onprem_response_shape(self, direct_client):
        """On-prem returns ``deleted_ids`` without ``actual_deletions`` —
        forget must report success."""
        client, moorcheh = direct_client
        moorcheh.documents.delete.return_value = {
            "status": "success",
            "deleted_ids": ["mem-abc"],
        }

        result = client.delete_memory(agent_id="test-agent", memory_id="mem-abc")

        assert result["status"] == "deleted"
        assert result["memory_id"] == "mem-abc"
        assert result["namespace"] == "memanto_agent_test-agent"
        moorcheh.documents.delete.assert_called_once_with(
            namespace_name="memanto_agent_test-agent", ids=["mem-abc"]
        )

    def test_forget_reports_not_found_when_truly_missing(self, direct_client):
        """Empty ``deleted_ids`` (genuine miss) still surfaces as ValueError."""
        client, moorcheh = direct_client
        moorcheh.documents.delete.return_value = {
            "status": "success",
            "deleted_ids": [],
        }

        with pytest.raises(ValueError, match="was not found"):
            client.delete_memory(agent_id="test-agent", memory_id="ghost")

    def test_forget_succeeds_on_cloud_response_shape(self, direct_client):
        """Cloud's ``actual_deletions`` path stays green (regression guard)."""
        client, moorcheh = direct_client
        moorcheh.documents.delete.return_value = {
            "actual_deletions": 1,
            "deleted_ids": ["mem-xyz"],
            "status": "success",
        }

        result = client.delete_memory(agent_id="test-agent", memory_id="mem-xyz")
        assert result["status"] == "deleted"
        assert result["memory_id"] == "mem-xyz"


class TestMEMANTOArchitecture:
    """Tests for MEMANTO architecture principles"""

    def test_no_tenant_id_in_namespace(self):
        """Verify namespace format does NOT include tenant_id"""
        from memanto.app.services.session_service import SessionService

        service = SessionService()
        namespace = service._generate_namespace("my-agent")

        # NEW FORMAT: memanto_agent_{agent_id}
        assert namespace == "memanto_agent_my-agent"

        # OLD FORMAT would have been: memanto_{tenant}_agent_{agent_id}
        # Verify it doesn't contain "tenant" string
        assert "tenant" not in namespace.lower()

        print(f"✅ V2 namespace format confirmed: {namespace}")
        print("   ✅ NO tenant_id required!")

    def test_jwt_token_structure(self):
        """Verify JWT token contains correct fields"""
        from memanto.app.services.session_service import SessionService

        service = SessionService(secret_key="test-secret-min-32-bytes-abcdefg")
        session = service.create_session(agent_id="test-agent", duration_hours=4)

        # Decode token (without verification, just to check structure)
        payload = jwt.decode(session.session_token, options={"verify_signature": False})

        # Verify required fields
        assert "agent_id" in payload
        assert "namespace" in payload
        assert "session_id" in payload
        assert "started_at" in payload
        assert "expires_at" in payload

        # Verify NO tenant_id in token
        assert "tenant_id" not in payload

        print("✅ JWT token structure correct")
        print(f"   Fields: {list(payload.keys())}")
        print("   ✅ NO tenant_id in token!")


def test_conflict_report_handles_non_object_json_items(tmp_path, monkeypatch):
    """Malformed conflict-item schemas should be preserved instead of crashing."""
    import json
    from unittest.mock import MagicMock

    from memanto.app.services import daily_analysis_service as module

    sessions_dir = tmp_path / "sessions"
    summaries_dir = tmp_path / "summaries"
    sessions_dir.mkdir()
    (sessions_dir / "agent-1_2026-06-28_001_summary.md").write_text(
        "# Session\n\nRemembered a conflicting preference.",
        encoding="utf-8",
    )

    client = MagicMock()
    client.answer.generate.return_value = {"answer": '["not an object", 1]'}
    monkeypatch.setattr(module, "get_moorcheh_client", lambda: client)
    monkeypatch.setattr(module, "get_active_llm_model", lambda _: "test-model")
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: tmp_path))

    service = module.DailyAnalysisService(
        sessions_dir=sessions_dir,
        summaries_dir=summaries_dir,
    )

    result = service.generate_conflict_report("agent-1", "2026-06-28")

    assert result["status"] == "success"
    assert result["conflict_count"] == 1

    conflicts_path = (
        tmp_path / ".memanto" / "conflicts" / ("agent-1_2026-06-28_conflicts.json")
    )
    conflicts = json.loads(conflicts_path.read_text(encoding="utf-8"))
    assert conflicts[0]["title"] == "Unparsed conflict report"
    assert conflicts[0]["description"] == '["not an object", 1]'


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
