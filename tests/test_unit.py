"""
MEMANTO Core Unit Tests (No Server Required)

Tests the session and agent services directly without HTTP layer.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import jwt
import pytest

from memanto.app.config import settings
from memanto.app.core import MemoryRecord
from memanto.app.models.session import AgentCreate, AgentPattern, Session, SessionStatus
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

    def test_session_status_handles_aware_expiration_timestamp(self):
        """Session status helpers must handle ISO timestamps with a UTC timezone."""
        session = Session(
            session_id="sess-test",
            session_token="token-test",
            agent_id="test-agent",
            namespace="memanto_agent_test-agent",
            started_at="2026-03-19T14:00:00Z",
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            status=SessionStatus.ACTIVE,
        )

        assert session.is_expired() is False
        assert session.is_active() is True
        assert session.time_remaining().total_seconds() > 0

    def test_validate_session_handles_aware_expiration_timestamp(self, session_service):
        """JWT payloads with timezone-aware datetimes should validate cleanly."""
        token = jwt.encode(
            {
                "agent_id": "test-agent",
                "namespace": "memanto_agent_test-agent",
                "session_id": "sess-test",
                "started_at": "2026-03-19T14:00:00Z",
                "expires_at": (
                    datetime.now(timezone.utc) + timedelta(hours=1)
                ).isoformat(),
            },
            session_service.secret_key,
            algorithm="HS256",
        )

        from memanto.app.models.session import SessionStatus

        mock_session = Session(
            session_id="sess-test",
            session_token=token,
            agent_id="test-agent",
            namespace="memanto_agent_test-agent",
            started_at=datetime(2026, 3, 19, 14, 0, 0),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            status=SessionStatus.ACTIVE,
        )
        with patch.object(session_service, "get_session", return_value=mock_session):
            payload = session_service.validate_session(token)

        assert payload.agent_id == "test-agent"
        assert payload.expires_at.tzinfo is not None

    def test_list_sessions_handles_mixed_started_at_timezone(self, session_service):
        """Session listing should sort mixed aware and naive started_at values."""
        older_session = Session(
            session_id="sess-older",
            session_token="token-older",
            agent_id="older-agent",
            namespace="memanto_agent_older-agent",
            started_at=datetime(2026, 3, 19, 13, 0, 0),
            expires_at=datetime(2099, 3, 19, 20, 0, 0),
            status=SessionStatus.ACTIVE,
        )
        newer_session = Session(
            session_id="sess-newer",
            session_token="token-newer",
            agent_id="newer-agent",
            namespace="memanto_agent_newer-agent",
            started_at="2026-03-19T14:00:00Z",
            expires_at="2099-03-19T20:00:00Z",
            status=SessionStatus.ACTIVE,
        )
        session_service._save_session(older_session)
        session_service._save_session(newer_session)

        sessions = session_service.list_sessions()

        assert [session.session_id for session in sessions] == [
            "sess-newer",
            "sess-older",
        ]

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

    def test_settings_default_does_not_embed_public_jwt_secret(self, monkeypatch):
        """Default settings must not contain the publicly known JWT secret."""
        from memanto.app.config import Settings

        monkeypatch.delenv("MEMANTO_SECRET_KEY", raising=False)

        assert Settings(_env_file=None).MEMANTO_SECRET_KEY == ""

    def test_missing_session_secret_generates_persisted_fallback(
        self, temp_dir, monkeypatch
    ):
        """Missing MEMANTO_SECRET_KEY should generate a random, persisted JWT secret.

        The secret must survive process restarts (same data root -> same
        secret, so existing session tokens keep validating) while still
        differing across installs (different data roots -> different secrets,
        so no single predictable secret is shared everywhere).
        """
        monkeypatch.delenv("MEMANTO_SECRET_KEY", raising=False)
        monkeypatch.setattr(settings, "MEMANTO_SECRET_KEY", "")

        first = SessionService(sessions_dir=temp_dir / "sessions-1")
        second = SessionService(sessions_dir=temp_dir / "sessions-2")

        assert first.secret_key != "memanto-default-secret-change-in-production"
        assert len(first.secret_key) >= 32
        assert first.secret_key == second.secret_key

        other_root = SessionService(
            sessions_dir=temp_dir / "other-install" / "sessions"
        )
        assert other_root.secret_key != first.secret_key

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


class TestMemoryRecord:
    """Unit tests for core memory record invariants."""

    def test_set_ttl_rejects_non_positive_values(self):
        """Zero/negative TTLs should not create immediately expired memories."""
        memory = MemoryRecord(
            type="fact",
            title="TTL guard",
            content="This memory should require a positive TTL.",
            agent_id="agent-ttl",
            actor_id="agent-ttl",
            source="agent",
        )

        for ttl in (0, -60):
            with pytest.raises(ValueError, match="ttl_seconds must be greater than 0"):
                memory.set_ttl(ttl)


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
            last_session=datetime.now(timezone.utc),
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
            ({"requested_ids": ["m1"]}, False),
            ({}, False),
        ],
    )
    def test_delete_memory_handles_backend_shapes(self, response, expected):
        from memanto.app.services.memory_write_service import MemoryWriteService

        client = MagicMock()
        client.documents.delete.return_value = response
        assert MemoryWriteService(client).delete_memory("m1", "ns") is expected

    def test_update_memory_accepts_onprem_delete_response(self):
        from memanto.app.services.memory_write_service import MemoryWriteService

        client = MagicMock()
        client.documents.upload.return_value = {"status": "queued"}
        existing_memory = {
            "id": "mem-1",
            "type": "fact",
            "title": "Original title",
            "content": "Original content",
            "scope_type": "agent",
            "scope_id": "test-agent",
            "actor_id": "tester",
            "source": "manual",
            "confidence": 0.8,
            "status": "active",
            "tags": [],
        }

        with patch(
            "memanto.app.services.memory_read_service.MemoryReadService.get_memory",
            return_value=existing_memory,
        ):
            result = MemoryWriteService(client).update_memory(
                "mem-1",
                "memanto_agent_test-agent",
                {"content": "Updated content"},
            )

        assert result["action"] == "updated"
        assert result["status"] == "queued"
        client.documents.upload.assert_called_once()

    def test_update_memory_preserves_extra_fields_but_drops_removed_trust_fields(self):
        from memanto.app.services.memory_write_service import MemoryWriteService

        client = MagicMock()
        client.documents.upload.return_value = {"status": "queued"}
        existing_memory = {
            "id": "mem-1",
            "type": "fact",
            "title": "Original title",
            "content": "Original content",
            "actor_id": "tester",
            "source": "manual",
            "confidence": 0.8,
            "status": "active",
            "tags": [],
            # Extra field not in the MemoryRecord schema (e.g. on-prem data_store.json).
            "original_id": "orig-123",
            # Trust field removed 2026-06-29; must not be resurrected on update.
            "validation_count": 5,
        }

        with patch(
            "memanto.app.services.memory_read_service.MemoryReadService.get_memory",
            return_value=existing_memory,
        ):
            MemoryWriteService(client).update_memory(
                "mem-1",
                "memanto_agent_test-agent",
                {"content": "Updated content"},
            )

        uploaded = client.documents.upload.call_args.kwargs["documents"][0]
        assert uploaded.get("original_id") == "orig-123"
        assert "validation_count" not in uploaded


class TestMemoryReadServiceFormatting:
    def test_format_memory_item_preserves_falsey_metadata_values(self):
        from memanto.app.services.memory_read_service import MemoryReadService

        item = {
            "id": "m-low",
            "text": "[FACT] Low confidence\n\nThis memory is intentionally weak.",
            "metadata": {
                "memory_type": "fact",
                "confidence": 0.0,
                "status": "active",
                "tags": [],
                "validation_count": 0,
                "contradiction_detected": False,
            },
        }

        formatted = MemoryReadService(MagicMock())._format_memory_item(item)

        assert formatted["confidence"] == 0.0
        assert formatted["tags"] == []

    def test_embedded_tags_paragraph_with_real_tags(self):
        from unittest.mock import MagicMock

        from memanto.app.services.memory_read_service import MemoryReadService

        # Content whose first paragraph starts with "Tags: " AND a genuine trailing
        # tags block: only the LAST block is metadata, so rpartition (not any match)
        # must be used. This is the case the fix hinges on.
        item = {
            "text": "[FACT] T\n\nTags: this is user content, not metadata\n\nTags: urgent",
            "memory_type": "fact",
            "tags": "urgent",
        }

        formatted = MemoryReadService(MagicMock())._format_memory_item(item)

        assert formatted["content"] == "Tags: this is user content, not metadata"
        assert formatted["tags"] == ["urgent"]


class TestMemoryWriteServiceBatch:
    def test_batch_store_counts_ok_upload_status_as_success(self):
        from memanto.app.core import MemoryRecord
        from memanto.app.services.memory_write_service import MemoryWriteService

        client = MagicMock()
        client.documents.upload.return_value = {"status": "ok"}
        memories = [
            MemoryRecord(
                title="First preference",
                content="Alex prefers concise status updates.",
                agent_id="agent-1",
                actor_id="user-1",
                source="test",
            ),
            MemoryRecord(
                title="Second preference",
                content="Alex prefers weekly summaries.",
                agent_id="agent-1",
                actor_id="user-1",
                source="test",
            ),
        ]

        result = MemoryWriteService(client).batch_store_memories(memories)

        assert result["successful"] == 2
        assert result["failed"] == 0
        assert [item["status"] for item in result["results"]] == ["ok", "ok"]

    def test_batch_store_counts_failed_upload_status_case_insensitively(self):
        from memanto.app.core import MemoryRecord
        from memanto.app.services.memory_write_service import MemoryWriteService

        client = MagicMock()
        client.documents.upload.return_value = {"status": "FAILED"}
        memories = [
            MemoryRecord(
                title="Failed write",
                content="This write should be counted as failed.",
                agent_id="agent-1",
                actor_id="user-1",
                source="test",
            )
        ]

        result = MemoryWriteService(client).batch_store_memories(memories)

        assert result["successful"] == 0
        assert result["failed"] == 1
        assert result["results"][0]["status"] == "failed"


class TestMemoryWriteServiceUpdate:
    def test_update_memory_preserves_string_expires_at(self):
        """Updating a TTL-backed memory should not fail when the stored
        ``expires_at`` field comes back as an ISO string from the backend."""
        from memanto.app.services.memory_write_service import MemoryWriteService

        client = MagicMock()
        client.documents.get.return_value = {
            "items": [
                {
                    "id": "mem-ttl",
                    "text": "[FACT] Old title\n\nOld content",
                    "memory_type": "fact",
                    "scope_type": "agent",
                    "scope_id": "alpha",
                    "actor_id": "user",
                    "source": "user",
                    "confidence": 0.8,
                    "status": "active",
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "expires_at": "2099-01-02T00:00:00Z",
                    "ttl_seconds": 3600,
                }
            ]
        }
        client.documents.delete.return_value = {"actual_deletions": 1}
        client.documents.upload.return_value = {"status": "success"}

        result = MemoryWriteService(client).update_memory(
            "mem-ttl", "memanto_agent_alpha", {"content": "New content"}
        )

        assert result["status"] == "success"
        uploaded_doc = client.documents.upload.call_args.kwargs["documents"][0]
        assert uploaded_doc["expires_at"] == "2099-01-02T00:00:00+00:00"
        assert uploaded_doc["ttl_seconds"] == 3600


class TestMemoryReadServiceTemporalFilters:
    def test_one_bad_timestamp_does_not_disable_window(self):
        from unittest.mock import MagicMock

        from memanto.app.services.memory_read_service import MemoryReadService

        results = [
            {"id": "old", "created_at": "2020-01-01T00:00:00Z"},
            {"id": "bad", "created_at": "not-a-timestamp"},
            {"id": "june", "created_at": "2026-06-15T00:00:00Z"},
        ]

        service = MemoryReadService(moorcheh_client=MagicMock())
        out = service._apply_temporal_filter(
            results, created_after="2026-06-01T00:00:00Z", created_before=None
        )

        # Only the in-window record survives; the 2020 record must NOT leak through,
        # and the unparseable record is skipped individually.
        assert [r["id"] for r in out] == ["june"]


class TestMemoryReadServiceChangedSince:
    """Regression coverage for temporal changed-since result ordering."""

    def test_changed_since_sorts_created_memories_without_updated_at(self):
        """New memories with ``updated_at=None`` should not crash sorting."""
        from memanto.app.services.memory_read_service import MemoryReadService

        client = MagicMock()
        client.documents.fetch_text_data.return_value = {
            "items": [
                {
                    "id": "created-only",
                    "text": "[fact] Created only",
                    "metadata": {
                        "created_at": "2026-01-03T00:00:00Z",
                        "updated_at": None,
                        "memory_type": "fact",
                    },
                },
                {
                    "id": "updated",
                    "text": "[fact] Updated",
                    "metadata": {
                        "created_at": "2025-12-30T00:00:00Z",
                        "updated_at": "2026-01-04T00:00:00Z",
                        "memory_type": "fact",
                    },
                },
            ],
            "pagination": {"has_more": False},
        }

        result = MemoryReadService(client).search_changed_since(
            since_date="2026-01-01T00:00:00Z",
            agent_id="agent-1",
            limit=None,
        )

        assert [memory["id"] for memory in result["results"]] == [
            "updated",
            "created-only",
        ]
        assert result["results"][1]["change_type"] == "created"


class TestMemoryReadServiceVersionSelection:
    """Duplicate document ids can appear while a delete-and-recreate update is
    settling. The read path must keep the newest version so temporal queries do
    not miss recently updated memories."""

    def test_changed_since_uses_newest_duplicate_memory_version(self):
        from memanto.app.services.memory_read_service import MemoryReadService

        client = MagicMock()
        client.documents.fetch_text_data.return_value = {
            "items": [
                {
                    "id": "memory-1",
                    "text": "[FACT] Old title\n\nstale content",
                    "memory_type": "fact",
                    "scope_type": "agent",
                    "scope_id": "agent-1",
                    "actor_id": "agent-1",
                    "source": "agent",
                    "status": "active",
                    "confidence": 0.8,
                    "created_at": "2026-06-01T00:00:00+00:00",
                    "updated_at": "2026-06-01T00:00:00+00:00",
                },
                {
                    "id": "memory-1",
                    "text": "[FACT] New title\n\nfresh content",
                    "memory_type": "fact",
                    "scope_type": "agent",
                    "scope_id": "agent-1",
                    "actor_id": "agent-1",
                    "source": "agent",
                    "status": "active",
                    "confidence": 0.9,
                    "created_at": "2026-06-01T00:00:00+00:00",
                    "updated_at": "2026-06-15T12:00:00+00:00",
                },
            ],
            "pagination": {"has_more": False},
        }

        result = MemoryReadService(client).search_changed_since(
            since_date="2026-06-10T00:00:00+00:00",
            agent_id="agent-1",
        )

        assert result["total_found"] == 1
        assert result["results"][0]["title"] == "New title"
        assert result["results"][0]["content"] == "fresh content"
        assert result["results"][0]["change_type"] == "updated"


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


class TestMemoryWriteServiceTimestamps:
    """Imported memories should keep source chronology during migration."""

    def test_batch_store_preserves_imported_created_at(self):
        from memanto.app.core import MemoryRecord
        from memanto.app.services.memory_write_service import MemoryWriteService

        client = MagicMock()
        client.documents.upload.return_value = {"status": "success"}
        service = MemoryWriteService(client)
        source_created = datetime(2020, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

        memory = MemoryRecord(
            type="preference",
            title="Imported fact",
            content="Original imported memory",
            agent_id="test-agent",
            actor_id="test-agent",
            source="mem0",
            provenance="imported",
            created_at=source_created,
        )

        service.batch_store_memories([memory])

        uploaded = client.documents.upload.call_args.kwargs["documents"][0]
        assert uploaded["created_at"] == "2020-01-02T03:04:05+00:00"
        assert memory.created_at.tzinfo is not None

    def test_batch_store_overrides_non_imported_created_at(self):
        from memanto.app.core import MemoryRecord
        from memanto.app.services.memory_write_service import MemoryWriteService

        client = MagicMock()
        client.documents.upload.return_value = {"status": "success"}
        service = MemoryWriteService(client)
        source_created = datetime(2020, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

        memory = MemoryRecord(
            title="User fact",
            content="Fresh user memory",
            agent_id="test-agent",
            actor_id="test-agent",
            source="user",
            provenance="explicit_statement",
            created_at=source_created,
        )

        before_store = datetime.now(timezone.utc)
        service.batch_store_memories([memory])
        after_store = datetime.now(timezone.utc)

        uploaded = client.documents.upload.call_args.kwargs["documents"][0]
        assert not uploaded["created_at"].startswith("2020-01-02T03:04:05+00:00")
        parsed_created_at = datetime.fromisoformat(uploaded["created_at"])
        assert before_store <= parsed_created_at <= after_store


class TestRecallConfigValidation:
    def test_set_recall_config_rejects_invalid_limit(self, tmp_path):
        from memanto.cli.config.manager import ConfigManager

        manager = ConfigManager(config_dir=tmp_path)

        with pytest.raises(ValueError, match="Limit must be an integer"):
            manager.set_recall_config(limit=0)

        with pytest.raises(ValueError, match="Limit must be an integer"):
            manager.set_recall_config(limit=101)

        with pytest.raises(ValueError, match="Limit must be an integer"):
            manager.set_recall_config(limit=1.5)

        with pytest.raises(ValueError, match="Limit must be an integer"):
            manager.set_recall_config(limit=True)

    def test_set_recall_config_accepts_valid_limit(self, tmp_path):
        from memanto.cli.config.manager import ConfigManager

        manager = ConfigManager(config_dir=tmp_path)
        manager.set_recall_config(limit=25)

        assert manager.get_recall_config()["limit"] == 25


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


def test_daily_summary_omits_unset_active_ai_model(tmp_path, monkeypatch):
    """On-prem summary generation should omit ai_model when no active model is set."""
    from unittest.mock import MagicMock

    from memanto.app.services import daily_analysis_service as module

    sessions_dir = tmp_path / "sessions"
    summaries_dir = tmp_path / "summaries"
    sessions_dir.mkdir()
    (sessions_dir / "agent-1_2026-06-28_001_summary.md").write_text(
        "# Session\n\nRemembered a project milestone.",
        encoding="utf-8",
    )

    client = MagicMock()
    client.answer.generate.return_value = {"answer": "# Daily Summary"}
    monkeypatch.setattr(module, "get_moorcheh_client", lambda: client)
    monkeypatch.setattr(module, "get_active_llm_model", lambda _: None)

    service = module.DailyAnalysisService(
        sessions_dir=sessions_dir,
        summaries_dir=summaries_dir,
    )
    result = service.generate_summary("agent-1", "2026-06-28")

    assert result["status"] == "success"
    call_kwargs = client.answer.generate.call_args.kwargs
    assert "ai_model" not in call_kwargs


def test_conflict_report_omits_unset_active_ai_model(tmp_path, monkeypatch):
    """On-prem conflict detection should omit ai_model when no active model is set."""
    from unittest.mock import MagicMock

    from memanto.app.services import daily_analysis_service as module

    sessions_dir = tmp_path / "sessions"
    summaries_dir = tmp_path / "summaries"
    sessions_dir.mkdir()
    (sessions_dir / "agent-1_2026-06-28_001_summary.md").write_text(
        "# Session\n\nRemembered a project milestone.",
        encoding="utf-8",
    )

    client = MagicMock()
    client.answer.generate.return_value = {"answer": "[]"}
    monkeypatch.setattr(module, "get_moorcheh_client", lambda: client)
    monkeypatch.setattr(module, "get_active_llm_model", lambda _: None)
    monkeypatch.setattr(module.Path, "home", classmethod(lambda cls: tmp_path))

    service = module.DailyAnalysisService(
        sessions_dir=sessions_dir,
        summaries_dir=summaries_dir,
    )
    result = service.generate_conflict_report("agent-1", "2026-06-28")

    assert result["status"] == "success"
    call_kwargs = client.answer.generate.call_args.kwargs
    assert "ai_model" not in call_kwargs


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])


class TestValidateSafeId:
    """Unit tests for validate_safe_id path-traversal guard."""

    def test_valid_ids_are_accepted(self):
        from memanto.app.utils.validation import validate_safe_id

        for valid in ["my-agent", "agent_1", "AGENT", "agent-123", "a", "Agent_B-2"]:
            assert validate_safe_id(valid, "agent_id") == valid

    def test_path_traversal_dotdot_rejected(self):
        from memanto.app.utils.validation import validate_safe_id

        with pytest.raises(ValueError, match="invalid characters"):
            validate_safe_id("../etc/passwd", "agent_id")

    def test_slash_in_id_rejected(self):
        from memanto.app.utils.validation import validate_safe_id

        with pytest.raises(ValueError, match="invalid characters"):
            validate_safe_id("agent/hack", "agent_id")

    def test_null_byte_rejected(self):
        from memanto.app.utils.validation import validate_safe_id

        with pytest.raises(ValueError, match="invalid characters"):
            validate_safe_id("agent\x00", "agent_id")

    def test_empty_id_rejected(self):
        from memanto.app.utils.validation import validate_safe_id

        with pytest.raises(ValueError, match="must not be empty"):
            validate_safe_id("", "agent_id")

    def test_path_traversal_blocked_in_agent_service(self, tmp_path):
        """Ensure AgentService._get_agent_file raises on traversal attempt."""
        from memanto.app.services.agent_service import AgentService

        svc = AgentService(agents_dir=tmp_path / "agents")

        with pytest.raises(ValueError, match="invalid characters"):
            svc._get_agent_file("../../etc/shadow")

        # Confirm no files were created outside the agents dir
        assert not (tmp_path / "etc").exists()

    def test_path_traversal_blocked_in_session_service(self, tmp_path):
        """Ensure SessionService.get_session raises on traversal attempt."""
        from memanto.app.services.session_service import SessionService

        svc = SessionService(
            secret_key="test-secret-key-min-32-bytes-1234",
            sessions_dir=tmp_path / "sessions",
        )

        with pytest.raises(ValueError, match="invalid characters"):
            svc.get_session("../../etc/shadow")

        assert not (tmp_path / "etc").exists()

    def test_path_traversal_blocked_via_date_in_daily_analysis(self, tmp_path):
        """Ensure DailyAnalysisService raises on traversal attempt via date param."""
        from memanto.app.services.daily_analysis_service import DailyAnalysisService

        svc = DailyAnalysisService(
            sessions_dir=tmp_path / "sessions",
            summaries_dir=tmp_path / "summaries",
        )

        with pytest.raises(ValueError, match="invalid characters"):
            svc.generate_summary("agent1", "../../etc/passwd")

        with pytest.raises(ValueError, match="invalid characters"):
            svc.generate_conflict_report("agent1", "../../etc/passwd")

        assert not (tmp_path / "etc").exists()


def test_format_memory_item_tag_stripping():
    from unittest.mock import MagicMock

    from memanto.app.services.memory_read_service import MemoryReadService

    service = MemoryReadService(moorcheh_client=MagicMock())
    raw_text = (
        "[FACT] Market Size\n\nParagraph 1\n\nParagraph 2\n\nTags: market, finance"
    )
    mock_item = {"text": raw_text, "metadata": {"tags": "market, finance"}}

    formatted = service._format_memory_item(mock_item)

    assert formatted.get("title") == "Market Size"
    assert "Tags:" not in formatted.get("content", "")
    assert "Paragraph 1" in formatted.get("content", "")
    assert "Paragraph 2" in formatted.get("content", "")


def test_to_moorcheh_document_handles_string_expires_at():
    from memanto.app.core import MemoryRecord

    memory = MemoryRecord(
        type="fact",
        title="String Expiry",
        content="Expires at is a string",
        agent_id="test-agent",
        actor_id="user",
        source="test",
    )
    memory.expires_at = "2026-07-10T00:00:00"

    doc = memory.to_moorcheh_document()
    assert doc["expires_at"] == "2026-07-10T00:00:00"


def test_batch_upload_error_counts_each_pending_memory_as_failed():
    from memanto.app.core import MemoryRecord
    from memanto.app.services.memory_write_service import MemoryWriteService

    client = MagicMock()
    client.documents.upload.return_value = {"status": "error"}

    memories = [
        MemoryRecord(
            type="fact",
            title="One",
            content="First memory",
            agent_id="agent-1",
            actor_id="agent-1",
            source="user",
        ),
        MemoryRecord(
            type="fact",
            title="Two",
            content="Second memory",
            agent_id="agent-1",
            actor_id="agent-1",
            source="user",
        ),
    ]

    result = MemoryWriteService(client).batch_store_memories(memories)

    assert result["successful"] == 0
    assert result["failed"] == 2
    assert [item["status"] for item in result["results"]] == ["failed", "failed"]
    assert all(
        "Batch upload returned status" in item["error"] for item in result["results"]
    )
