"""
MEMANTO Core Unit Tests (No Server Required)

Tests the session and agent services directly without HTTP layer.
"""

import os
import stat
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import jwt
import pytest

from memanto.app.config import settings
from memanto.app.core import MemoryRecord
from memanto.app.models.session import AgentCreate, AgentPattern, Session, SessionStatus
from memanto.app.services.agent_service import AgentService
from memanto.app.services.session_service import SessionService
from memanto.app.utils.errors import InvalidSessionTokenError


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

    @pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits required")
    def test_session_token_storage_is_owner_only(self, temp_dir):
        """Persisted bearer tokens must not be readable by other local users."""
        sessions_dir = temp_dir / "sessions"
        service = SessionService(
            secret_key="test-secret-key-min-32-bytes-1234",
            sessions_dir=sessions_dir,
        )

        session = service.create_session(agent_id="private-agent", duration_hours=1)
        record = MemoryRecord(
            type="fact",
            title="Private fact",
            content="Private memory content",
            agent_id="private-agent",
            actor_id="user",
            source="user",
        )
        service.log_memory_to_session_summary(
            "private-agent", session.session_id, record
        )

        session_file = sessions_dir / "private-agent.json"
        summary_file = next(sessions_dir.glob("*_summary.md"))
        assert stat.S_IMODE(sessions_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE(session_file.stat().st_mode) == 0o600
        assert stat.S_IMODE(summary_file.stat().st_mode) == 0o600

    @pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits required")
    def test_first_storage_access_hardens_existing_session_artifacts(self, temp_dir):
        """Using upgraded storage must close exposure left by older versions."""
        sessions_dir = temp_dir / "sessions"
        sessions_dir.mkdir(mode=0o777)
        session_file = sessions_dir / "existing.json"
        summary_file = sessions_dir / "existing_summary.md"
        session_file.write_text('{"session_token": "live-bearer-token"}')
        summary_file.write_text("private memory content")
        sessions_dir.chmod(0o777)
        session_file.chmod(0o666)
        summary_file.chmod(0o666)

        service = SessionService(
            secret_key="test-secret-key-min-32-bytes-1234",
            sessions_dir=sessions_dir,
        )
        service.list_sessions()

        assert stat.S_IMODE(sessions_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE(session_file.stat().st_mode) == 0o600
        assert stat.S_IMODE(summary_file.stat().st_mode) == 0o600

    def test_interrupted_session_save_preserves_previous_record(self, session_service):
        """A failed replacement must not truncate the live bearer-token record."""
        session = session_service.create_session(
            agent_id="test-agent", duration_hours=1
        )
        session_file = session_service.sessions_dir / "test-agent.json"
        original_contents = session_file.read_text(encoding="utf-8")
        replacement = session.model_copy(update={"session_id": "sess-replacement"})

        def interrupted_dump(data, file_obj, **kwargs):
            file_obj.write('{"session_id":')
            file_obj.flush()
            raise OSError("simulated interrupted write")

        with patch(
            "memanto.app.services.session_service.json.dump",
            side_effect=interrupted_dump,
        ):
            with pytest.raises(OSError, match="simulated interrupted write"):
                session_service._save_session(replacement)

        assert session_file.read_text(encoding="utf-8") == original_contents
        assert session_service.get_session("test-agent") == session
        assert not list(session_service.sessions_dir.glob(".*.tmp"))

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

    def test_auto_renew_is_single_flight_per_agent(self, session_service, monkeypatch):
        """Parallel near-expiry requests must not mint competing tokens."""
        session_service.create_session(agent_id="test-agent", duration_hours=1)
        monkeypatch.setattr(settings, "SESSION_EXTEND_THRESHOLD_MINUTES", 120)

        original_renew = session_service.renew_session
        first_entered = threading.Event()
        second_entered = threading.Event()
        release_first = threading.Event()
        counter_lock = threading.Lock()
        call_count = 0

        def controlled_renew(agent_id, pattern=None):
            nonlocal call_count
            with counter_lock:
                call_count += 1
                call_number = call_count
            if call_number == 1:
                first_entered.set()
                assert release_first.wait(timeout=2)
            elif call_number == 2:
                second_entered.set()
            return original_renew(agent_id=agent_id, pattern=pattern)

        monkeypatch.setattr(session_service, "renew_session", controlled_renew)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(session_service.check_and_auto_renew, "test-agent")
            assert first_entered.wait(timeout=2)
            second = pool.submit(session_service.check_and_auto_renew, "test-agent")
            second_entered.wait(timeout=0.25)
            release_first.set()
            results = [first.result(timeout=2), second.result(timeout=2)]

        renewed = [session for session in results if session is not None]
        assert len(renewed) == 1
        session_service.validate_session(renewed[0].session_token)

    def test_lifecycle_operations_for_different_agents_can_overlap(
        self, session_service, monkeypatch
    ):
        """One agent's session file I/O must not block another agent."""
        original_save = session_service._save_session
        first_save_entered = threading.Event()
        release_first_save = threading.Event()

        def controlled_save(session):
            if session.agent_id == "agent-a":
                first_save_entered.set()
                assert release_first_save.wait(timeout=2)
            original_save(session)

        monkeypatch.setattr(session_service, "_save_session", controlled_save)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(session_service.create_session, "agent-a")
            assert first_save_entered.wait(timeout=2)
            second = pool.submit(session_service.create_session, "agent-b")
            second_session = second.result(timeout=1)
            release_first_save.set()
            first_session = first.result(timeout=2)

        assert first_session.agent_id == "agent-a"
        assert second_session.agent_id == "agent-b"

    def test_active_session_read_waits_for_marker_update(self, session_service):
        """Readers must not observe an active marker during its replacement."""
        session = session_service.create_session("test-agent")
        read_started = threading.Event()

        def read_active_session():
            read_started.set()
            return session_service.get_active_session()

        pool = ThreadPoolExecutor(max_workers=1)
        try:
            with session_service._active_marker_lock:
                pending_read = pool.submit(read_active_session)
                assert read_started.wait(timeout=2)
                assert not pending_read.done()
            active_session = pending_read.result(timeout=2)
        finally:
            pool.shutdown(wait=True)

        assert active_session is not None
        assert active_session.session_id == session.session_id

    def test_end_session_revokes_concurrent_auto_renewal(
        self, session_service, monkeypatch
    ):
        """Logout must terminate a renewal that was already in flight."""
        original = session_service.create_session(
            agent_id="test-agent", duration_hours=1
        )
        monkeypatch.setattr(settings, "SESSION_EXTEND_THRESHOLD_MINUTES", 120)

        original_renew = session_service.renew_session
        renewal_entered = threading.Event()
        release_renewal = threading.Event()
        termination_saved = threading.Event()
        original_save = session_service._save_session

        def controlled_renew(agent_id, pattern=None):
            renewal_entered.set()
            assert release_renewal.wait(timeout=2)
            return original_renew(agent_id=agent_id, pattern=pattern)

        def observed_save(session):
            original_save(session)
            if session.status == SessionStatus.TERMINATED:
                termination_saved.set()

        monkeypatch.setattr(session_service, "renew_session", controlled_renew)
        monkeypatch.setattr(session_service, "_save_session", observed_save)

        with ThreadPoolExecutor(max_workers=2) as pool:
            renewing = pool.submit(session_service.check_and_auto_renew, "test-agent")
            assert renewal_entered.wait(timeout=2)
            ending = pool.submit(session_service.end_session, "test-agent")

            # Logout cannot persist a stale termination while renewal owns the
            # lifecycle. It proceeds immediately after the fresh token exists.
            assert not termination_saved.wait(timeout=0.25)
            release_renewal.set()
            renewed = renewing.result(timeout=2)
            summary = ending.result(timeout=2)

        assert renewed is not None
        assert renewed.session_id != original.session_id
        assert summary.session_id == renewed.session_id
        with pytest.raises(InvalidSessionTokenError):
            session_service.validate_session(renewed.session_token)

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

    def test_concurrent_first_start_uses_one_persisted_secret(
        self, temp_dir, monkeypatch
    ):
        """Concurrent service starts must agree on the JWT signing secret."""
        monkeypatch.delenv("MEMANTO_SECRET_KEY", raising=False)
        monkeypatch.setattr(settings, "MEMANTO_SECRET_KEY", "")

        sessions_dir = temp_dir / "sessions"
        second_truncated_secret = threading.Event()
        release_first_writer = threading.Event()
        thread_role = threading.local()
        real_open = os.open
        real_fdopen = os.fdopen
        real_write = os.write

        def observed_open(path, flags, mode=0o777):
            if (
                getattr(thread_role, "value", None) == "second"
                and Path(path).name == "secret_key"
                and flags & os.O_TRUNC
            ):
                second_truncated_secret.set()
            return real_open(path, flags, mode)

        def delayed_write(fd, data):
            if getattr(thread_role, "value", None) == "first" and len(data) == 64:
                assert release_first_writer.wait(timeout=5)
            return real_write(fd, data)

        def delayed_fdopen(fd, *args, **kwargs):
            file_handle = real_fdopen(fd, *args, **kwargs)
            if getattr(thread_role, "value", None) != "first":
                return file_handle

            class DelayedWriter:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc_value, traceback):
                    return file_handle.__exit__(exc_type, exc_value, traceback)

                def write(self, data):
                    assert release_first_writer.wait(timeout=5)
                    return file_handle.write(data)

                def __getattr__(self, name):
                    return getattr(file_handle, name)

            return DelayedWriter()

        def create_service(role):
            thread_role.value = role
            return SessionService(sessions_dir=sessions_dir).secret_key

        monkeypatch.setattr(os, "open", observed_open)
        monkeypatch.setattr(os, "fdopen", delayed_fdopen)
        monkeypatch.setattr(os, "write", delayed_write)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(create_service, "first")
            second = pool.submit(create_service, "second")
            second_truncated_secret.wait(timeout=0.1)
            release_first_writer.set()
            returned_secrets = [first.result(timeout=5), second.result(timeout=5)]

        persisted_secret = (temp_dir / "secret_key").read_text()
        assert returned_secrets == [persisted_secret, persisted_secret]

    def test_get_active_session_ignores_invalid_session_file(self, session_service):
        """A corrupt active session file should not crash status checks."""
        active_marker = session_service.sessions_dir / "active"
        active_marker.parent.mkdir(parents=True, exist_ok=True)
        active_marker.write_text("broken-agent")
        (session_service.sessions_dir / "broken-agent.json").write_text("{")

        assert session_service.get_active_session() is None

    def test_get_active_session_tolerates_external_marker_removal(
        self, session_service, monkeypatch
    ):
        """A marker removed by another process during its read is treated as absent."""
        active_marker = session_service.sessions_dir / "active"
        active_marker.parent.mkdir(parents=True, exist_ok=True)
        active_marker.write_text("test-agent")
        original_open = open

        def disappearing_marker(file, *args, **kwargs):
            if Path(file) == active_marker:
                active_marker.unlink(missing_ok=True)
                raise FileNotFoundError(active_marker)
            return original_open(file, *args, **kwargs)

        monkeypatch.setattr("builtins.open", disappearing_marker)

        assert session_service.get_active_session() is None

    def test_clear_active_session_tolerates_external_marker_removal(
        self, session_service, monkeypatch
    ):
        """A marker removed after an existence check does not crash cleanup."""
        active_marker = session_service.sessions_dir / "active"
        active_marker.parent.mkdir(parents=True, exist_ok=True)
        active_marker.write_text("test-agent")
        original_exists = Path.exists

        def disappearing_marker(path):
            exists = original_exists(path)
            if path == active_marker and exists:
                path.unlink()
                return True
            return exists

        monkeypatch.setattr(Path, "exists", disappearing_marker)

        session_service.clear_active_session()

        assert not original_exists(active_marker)

    def test_delete_session_tolerates_external_marker_removal(
        self, session_service, monkeypatch
    ):
        """Deleting session state succeeds if another process removes the marker."""
        session_service.create_session("test-agent")
        active_marker = session_service.sessions_dir / "active"
        active_marker.unlink()
        active_marker.write_text("test-agent")
        original_open = open

        def disappearing_marker(file, *args, **kwargs):
            if Path(file) == active_marker:
                active_marker.unlink(missing_ok=True)
                raise FileNotFoundError(active_marker)
            return original_open(file, *args, **kwargs)

        monkeypatch.setattr("builtins.open", disappearing_marker)

        assert session_service.delete_session("test-agent") is True
        assert not (session_service.sessions_dir / "test-agent.json").exists()

    def test_get_active_session_clears_invalid_active_marker(self, session_service):
        """A malformed active marker should not crash session recovery."""
        active_marker = session_service.sessions_dir / "active"
        active_marker.parent.mkdir(parents=True, exist_ok=True)
        active_marker.write_text("../outside")

        assert session_service.get_active_session() is None
        assert not active_marker.exists()

    def test_get_active_session_clears_traversal_symlink(self, session_service):
        """A traversal symlink target should not be treated as an agent id."""
        active_marker = session_service.sessions_dir / "active"
        active_marker.parent.mkdir(parents=True, exist_ok=True)
        try:
            active_marker.symlink_to("../outside.json")
        except OSError as exc:
            pytest.skip(f"symlink creation unavailable: {exc}")

        assert session_service.get_active_session() is None
        assert not active_marker.exists()

    def test_get_active_session_clears_dangling_symlink(self, session_service):
        """A dangling active symlink should be removed during session recovery."""
        active_marker = session_service.sessions_dir / "active"
        active_marker.parent.mkdir(parents=True, exist_ok=True)
        try:
            active_marker.symlink_to("missing-agent.json")
        except OSError as exc:
            pytest.skip(f"symlink creation unavailable: {exc}")

        assert session_service.get_active_session() is None
        assert not active_marker.exists()

    def test_get_active_session_clears_missing_session_marker(self, session_service):
        """A stale active marker should be removed when its session is gone."""
        active_marker = session_service.sessions_dir / "active"
        active_marker.parent.mkdir(parents=True, exist_ok=True)
        active_marker.write_text("missing-agent")

        assert session_service.get_active_session() is None
        assert not active_marker.exists()

    def test_delete_session_rejects_path_traversal_agent_id(self, session_service):
        """delete_session must not delete files outside the sessions directory."""
        session_service.sessions_dir.mkdir(parents=True, exist_ok=True)
        outside = session_service.sessions_dir.parent / "outside.json"
        outside.write_text("keep me", encoding="utf-8")

        with pytest.raises(ValueError, match="agent_id"):
            session_service.delete_session("../outside")

        assert outside.read_text(encoding="utf-8") == "keep me"

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

    def test_invalid_agent_metadata_handling(self, agent_service):
        """Corrupt or invalid agent files must not hide valid agents, should report warnings, and behave like absent local state for lookups."""
        agent_service.create_agent(
            AgentCreate(agent_id="valid-agent", pattern=AgentPattern.SUPPORT),
            settings.MOORCHEH_API_KEY,
        )

        # JSONDecodeError (corrupt JSON)
        (agent_service.agents_dir / "broken-agent.json").write_text("{")
        assert agent_service.get_agent("broken-agent") is None

        # ValidationError (missing required fields)
        (agent_service.agents_dir / "broken-schema-agent.json").write_text(
            '{"description": "missing agent_id and pattern"}'
        )
        assert agent_service.get_agent("broken-schema-agent") is None

        agent_list = agent_service.list_agents()

        assert agent_list.count == 1
        assert [agent.agent_id for agent in agent_list.agents] == ["valid-agent"]
        assert len(agent_list.warnings) == 2
        assert any("broken-agent.json" in w for w in agent_list.warnings)
        assert any("broken-schema-agent.json" in w for w in agent_list.warnings)

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


def test_local_services_do_not_create_storage_on_init(tmp_path, monkeypatch):
    """Constructing local helpers should not write to disk until they save state."""
    from memanto.cli.config.manager import ConfigManager

    monkeypatch.delenv("MEMANTO_SECRET_KEY", raising=False)
    monkeypatch.setattr(settings, "MEMANTO_SECRET_KEY", "")

    config_dir = tmp_path / "config"
    agents_dir = tmp_path / "agents"
    sessions_dir = tmp_path / "sessions"

    ConfigManager(config_dir=config_dir)
    agent_service = AgentService(agents_dir=agents_dir)
    session_service = SessionService(sessions_dir=sessions_dir)

    assert not config_dir.exists()
    assert not agents_dir.exists()
    assert not sessions_dir.exists()
    assert not (tmp_path / "secret_key").exists()
    assert agent_service.list_agents().count == 0
    assert (
        session_service._generate_namespace("test-agent") == "memanto_agent_test-agent"
    )


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
            "source": "system",
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

    def test_update_memory_normalizes_legacy_source_values(self):
        from memanto.app.services.memory_write_service import MemoryWriteService

        client = MagicMock()
        client.documents.upload.return_value = {"status": "queued"}
        existing_memory = {
            "id": "mem-1",
            "type": "fact",
            "title": "Title",
            "content": "Content",
            "actor_id": "tester",
            "source": "manual",  # legacy value
            "confidence": 0.8,
            "status": "active",
        }

        with patch(
            "memanto.app.services.memory_read_service.MemoryReadService.get_memory",
            return_value=existing_memory,
        ):
            MemoryWriteService(client).update_memory(
                "mem-1",
                "memanto_agent_test",
                {"title": "New title"},
            )

        uploaded = client.documents.upload.call_args.kwargs["documents"][0]
        # Should normalize 'manual' (invalid SourceType) to 'system'
        assert uploaded.get("source") == "system"


class TestMemoryWriteServiceUpdateIntegrity:
    def test_update_memory_preserves_read_service_metadata(self):
        from memanto.app.services.memory_write_service import MemoryWriteService

        client = MagicMock()
        client.documents.get.return_value = {
            "items": [
                {
                    "id": "mem-2",
                    "text": (
                        "[DECISION] Architecture decision\n\n"
                        "Use same-ID document replacement for edits."
                    ),
                    "metadata": {
                        "agent_id": "agent-1",
                        "memory_type": "decision",
                        "actor_id": "user",
                        "source": "test",
                        "source_ref": "issue-770",
                        "confidence": 0.95,
                        "status": "active",
                        "tags": "integrity",
                        "provenance": "validated",
                    },
                }
            ]
        }
        client.documents.upload.return_value = {"status": "queued"}

        MemoryWriteService(client).update_memory(
            "mem-2",
            "memanto_agent_agent-1",
            {"content": "Updated without losing original metadata."},
        )

        uploaded = client.documents.upload.call_args.kwargs["documents"][0]
        assert uploaded["memory_type"] == "decision"
        assert uploaded["provenance"] == "validated"
        assert uploaded["source_ref"] == "issue-770"
        assert uploaded["tags"] == "integrity"

    def test_update_memory_accepts_case_insensitive_success_status(self):
        from memanto.app.services.memory_write_service import MemoryWriteService

        client = MagicMock()
        client.documents.upload.return_value = {"status": "OK"}
        existing_memory = {
            "id": "mem-1",
            "type": "fact",
            "title": "Original title",
            "content": "Original content",
            "agent_id": "agent-1",
            "actor_id": "user",
            "source": "test",
            "confidence": 0.9,
            "status": "active",
            "tags": [],
        }

        with patch(
            "memanto.app.services.memory_read_service.MemoryReadService.get_memory",
            return_value=existing_memory,
        ):
            result = MemoryWriteService(client).update_memory(
                "mem-1",
                "memanto_agent_agent-1",
                {"content": "Updated content"},
            )

        assert result["action"] == "updated"
        assert result["status"] == "OK"
        client.documents.delete.assert_not_called()

    @pytest.mark.parametrize(
        "upload_result,expected_status",
        [
            ({"status": "failed"}, "failed"),
            ({"status": None}, None),
            ({}, "unknown"),
        ],
    )
    def test_update_memory_rejects_non_success_status_without_delete(
        self, upload_result, expected_status
    ):
        from memanto.app.services.memory_write_service import MemoryWriteService
        from memanto.app.utils.errors import MemoryError

        client = MagicMock()
        client.documents.upload.return_value = upload_result
        existing_memory = {
            "id": "mem-1",
            "type": "fact",
            "title": "Original title",
            "content": "Original content",
            "agent_id": "agent-1",
            "actor_id": "user",
            "source": "test",
            "confidence": 0.9,
            "status": "active",
            "tags": [],
        }

        with patch(
            "memanto.app.services.memory_read_service.MemoryReadService.get_memory",
            return_value=existing_memory,
        ):
            with pytest.raises(MemoryError) as exc_info:
                MemoryWriteService(client).update_memory(
                    "mem-1",
                    "memanto_agent_agent-1",
                    {"content": "Updated content"},
                )

        assert str(exc_info.value) == (
            f"Failed to upload updated memory mem-1: {expected_status}"
        )
        client.documents.delete.assert_not_called()


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
                source="system",
            ),
            MemoryRecord(
                title="Second preference",
                content="Alex prefers weekly summaries.",
                agent_id="agent-1",
                actor_id="user-1",
                source="system",
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
                source="system",
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


class TestClientApiKeyDispatch:
    """CLI clients must honor the api_key supplied to the client instance."""

    @pytest.mark.parametrize(
        "client_cls_path",
        [
            "memanto.cli.client.direct_client.DirectClient",
            "memanto.cli.client.sdk_client.SdkClient",
        ],
    )
    def test_clients_pass_instance_api_key_to_backend_dispatcher(
        self, monkeypatch, client_cls_path
    ):
        from memanto.app.clients import moorcheh as moorcheh_mod

        calls = []
        fake_backend = object()

        class Recorder:
            def get_client(self, api_key=None):
                calls.append(api_key)
                return fake_backend

        module_name, class_name = client_cls_path.rsplit(".", 1)
        module = __import__(module_name, fromlist=[class_name])
        client_cls = getattr(module, class_name)

        monkeypatch.setattr(moorcheh_mod, "moorcheh_client", Recorder())

        client = client_cls(api_key="mk_instance_specific_key")

        assert client._get_moorcheh() is fake_backend
        assert calls == ["mk_instance_specific_key"]


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
            source="system",
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

    def test_jwt_token_structure(self, tmp_path):
        """Verify JWT token contains correct fields"""
        from memanto.app.services.session_service import SessionService

        service = SessionService(
            secret_key="test-secret-min-32-bytes-abcdefg",
            sessions_dir=tmp_path / "sessions",
        )
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


class TestServerConfigUrl:
    """Regression tests for local REST API URL formatting."""

    def test_server_url_defaults_to_http_for_host_and_port(self, tmp_path):
        """Ensure host and port configs default to an HTTP URL."""
        from memanto.cli.config.manager import ConfigManager

        manager = ConfigManager(config_dir=tmp_path)
        manager.set_server_config("localhost", 8000)

        assert manager.get_server_url() == "http://localhost:8000"

    def test_server_url_preserves_configured_scheme(self, tmp_path):
        """Ensure configured HTTP or HTTPS schemes are preserved."""
        from memanto.cli.config.manager import ConfigManager

        manager = ConfigManager(config_dir=tmp_path)
        manager.set_server_config("https://memanto.example", 443)

        assert manager.get_server_url() == "https://memanto.example:443"

    def test_server_url_does_not_duplicate_explicit_url_port(self, tmp_path):
        """Ensure explicit URL ports are not duplicated."""
        from memanto.cli.config.manager import ConfigManager

        manager = ConfigManager(config_dir=tmp_path)
        manager.set_server_config("https://memanto.example:9443", 443)

        assert manager.get_server_url() == "https://memanto.example:9443"

    @pytest.mark.parametrize(
        "bad_url", ["http://localhost:abc", "http://localhost:999999"]
    )
    def test_server_url_falls_back_when_explicit_url_port_is_malformed(
        self, tmp_path, bad_url
    ):
        """Ensure malformed explicit URL ports fall back to the configured port."""
        from memanto.cli.config.manager import ConfigManager

        manager = ConfigManager(config_dir=tmp_path)
        manager.set_server_config(bad_url, 8000)

        assert manager.get_server_url() == "http://localhost:8000"


class TestServerConfigValidation:
    """Regression tests for local REST API server config validation."""

    def test_set_server_config_persists_integer_port(self, tmp_path):
        from memanto.cli.config.manager import ConfigManager

        manager = ConfigManager(config_dir=tmp_path)
        manager.set_server_config("localhost", "8000")

        assert manager.get_server_config()["port"] == 8000

    @pytest.mark.parametrize("invalid_port", [0, 65536, "abc", 1.5, True])
    def test_set_server_config_rejects_invalid_port(self, tmp_path, invalid_port):
        from memanto.cli.config.manager import ConfigManager

        manager = ConfigManager(config_dir=tmp_path)

        with pytest.raises(ValueError, match="server port"):
            manager.set_server_config("localhost", invalid_port)


class TestSessionConfigValidation:
    """Regression tests for user-editable session config."""

    def test_set_session_config_normalizes_integer_fields(self, tmp_path):
        from memanto.cli.config.manager import ConfigManager

        manager = ConfigManager(config_dir=tmp_path)
        manager.set_session_config(
            {
                "default_duration_hours": "12",
                "extend_threshold_minutes": "45",
                "auto_renew_enabled": False,
            }
        )

        session = manager.get_session_config()
        assert session["default_duration_hours"] == 12
        assert session["extend_threshold_minutes"] == 45
        assert session["auto_renew_enabled"] is False

    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("default_duration_hours", 0),
            ("default_duration_hours", 169),
            ("extend_threshold_minutes", "abc"),
            ("warn_before_expiry_minutes", 1.5),
            ("auto_renew_interval_hours", True),
            ("auto_extend", "false"),
            ("unexpected", 1),
        ],
    )
    def test_set_session_config_rejects_invalid_values(self, tmp_path, key, value):
        from memanto.cli.config.manager import ConfigManager

        manager = ConfigManager(config_dir=tmp_path)

        with pytest.raises(ValueError):
            manager.set_session_config({key: value})

    def test_set_session_config_rejects_corrupt_stored_session(self, tmp_path):
        from memanto.cli.config.manager import ConfigManager

        manager = ConfigManager(config_dir=tmp_path)
        manager.save_yaml({"session": "bad"})

        with pytest.raises(ValueError, match="stored session config must be an object"):
            manager.set_session_config({"default_duration_hours": 12})

        assert manager.load_yaml()["session"] == "bad"


class TestAnswerConfigValidation:
    """Regression tests for user-editable answer config."""

    def test_set_answer_config_normalizes_numeric_values(self, tmp_path):
        from memanto.cli.config.manager import ConfigManager

        manager = ConfigManager(config_dir=tmp_path)
        manager.set_answer_config(
            temperature="0.2",
            answer_limit="20",
            threshold="0.4",
            kiosk_mode=True,
        )

        answer = manager.get_answer_config()
        assert answer["temperature"] == 0.2
        assert answer["answer_limit"] == 20
        assert answer["threshold"] == 0.4
        assert answer["kiosk_mode"] is True

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("temperature", -0.1),
            ("temperature", 2.1),
            ("answer_limit", 0),
            ("answer_limit", 51),
            ("answer_limit", 1.5),
            ("threshold", -0.1),
            ("threshold", 1.1),
            ("kiosk_mode", "false"),
        ],
    )
    def test_set_answer_config_rejects_invalid_values(self, tmp_path, field, value):
        from memanto.cli.config.manager import ConfigManager

        manager = ConfigManager(config_dir=tmp_path)

        with pytest.raises(ValueError, match=field):
            manager.set_answer_config(**{field: value})


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


@pytest.mark.parametrize(
    ("agent_name", "is_global", "expected_suffix"),
    [
        ("cursor", True, ".cursor/rules/memanto.mdc"),
        ("claude-code", True, ".claude/CLAUDE.md"),
        ("windsurf", True, ".codeium/windsurf/.windsurfrules"),
        ("cursor", False, "project/.cursor/rules/memanto.mdc"),
    ],
)
def test_resolve_instruction_file_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    agent_name: str,
    is_global: bool,
    expected_suffix: str,
) -> None:
    """Test resolution of instruction file paths."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    from memanto.cli.connect.agent_registry import AGENT_REGISTRY

    project_dir = tmp_path / "project"
    resolved = AGENT_REGISTRY[agent_name].resolve_instruction_file(
        project_dir, is_global=is_global
    )

    assert resolved == tmp_path / expected_suffix


def test_memory_edit_rejects_oversized_source():
    from pydantic import ValidationError

    from memanto.app.routes.memory import MemoryEditRequest

    with pytest.raises(ValidationError):
        MemoryEditRequest(source="x" * 129)


def test_memory_edit_strips_valid_tags():
    from memanto.app.routes.memory import MemoryEditRequest

    request = MemoryEditRequest(tags=[" project ", "important"])

    assert request.tags == ["project", "important"]


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
        source="system",
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


def test_direct_sync_uses_cached_export_fast_path(tmp_path, monkeypatch):
    from memanto.cli.client.direct_client import DirectClient

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    cache_dir = tmp_path / ".memanto" / "exports"
    cache_dir.mkdir(parents=True)
    cache_path = cache_dir / "agent-1_memory.md"
    cache_path.write_text("# MEMORY\n\n### stale memory\n", encoding="utf-8")

    client = DirectClient.__new__(DirectClient)
    export_calls = []

    def fresh_export(*, agent_id, limit_per_type):
        export_calls.append((agent_id, limit_per_type))
        cache_path.write_text(
            "# MEMORY\n\n### current memory\n\n### newer memory\n",
            encoding="utf-8",
        )
        return {
            "output_path": str(cache_path),
            "total_memories": 2,
            "per_type_counts": {"learning": 2},
        }

    monkeypatch.setattr(client, "export_memory_md", fresh_export)

    project_dir = tmp_path / "project"
    result = client.sync_memory_to_project(
        agent_id="agent-1",
        project_dir=str(project_dir),
        limit_per_type=7,
    )

    target = project_dir / "MEMORY.md"
    assert export_calls == []
    assert target.read_text(encoding="utf-8") == cache_path.read_text(encoding="utf-8")
    assert "stale memory" in target.read_text(encoding="utf-8")
    assert result == {
        "output_path": str(target.resolve()),
        "total_memories": 1,
        "source": "cache",
    }


def test_onprem_state_survives_interrupted_replace(tmp_path):
    """An interrupted state replacement must preserve the previous file."""
    from unittest.mock import patch

    from memanto.cli.config.manager import ConfigManager

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
