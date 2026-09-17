"""Regression tests for cross-process session revocation races."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Event

import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

from memanto.app.config import settings
from memanto.app.models.session import AgentInfo, AgentPattern
from memanto.app.routes import auth_deps, sessions
from memanto.app.services.agent_service import AgentService
from memanto.app.services.session_service import SessionService
from memanto.app.utils.errors import AgentNotFoundError, InvalidSessionTokenError
from memanto.cli.client.direct_client import DirectClient
from memanto.cli.client.sdk_client import SdkClient


def _request_with_token(token: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v2/agents/victim/recall",
            "raw_path": b"/api/v2/agents/victim/recall",
            "query_string": b"",
            "headers": [(b"x-session-token", token.encode())],
            "client": ("203.0.113.10", 12345),
            "server": ("testserver", 80),
        }
    )


def _signal_before_exclusive_lock(monkeypatch, service, lock_attempted: Event):
    """Signal at the real OS-lock boundary for a competing operation."""
    original_lock = service._exclusive_file_lock

    @contextmanager
    def signal_before_lock(lock_file):
        lock_attempted.set()
        with original_lock(lock_file):
            yield

    monkeypatch.setattr(service, "_exclusive_file_lock", signal_before_lock)


@pytest.mark.parametrize("full_agent_delete", [False, True])
def test_cross_instance_deletion_remains_authoritative_over_renewal(
    tmp_path, monkeypatch, full_agent_delete
):
    """Deletion wins even when another worker has begun a real renewal write."""
    sessions_dir = tmp_path / "sessions"
    renewal_worker = SessionService(sessions_dir=sessions_dir)
    deletion_worker = SessionService(sessions_dir=sessions_dir)
    original = renewal_worker.create_session("victim", duration_hours=1)

    monkeypatch.setattr(settings, "SESSION_AUTO_RENEW_ENABLED", True)
    monkeypatch.setattr(settings, "SESSION_EXTEND_THRESHOLD_MINUTES", 120)

    save_reached = Event()
    allow_save = Event()
    delete_lock_attempted = Event()
    original_save = renewal_worker._save_session

    def pause_before_real_save(session):
        if session.session_id != original.session_id:
            save_reached.set()
            assert allow_save.wait(timeout=2)
        original_save(session)

    monkeypatch.setattr(renewal_worker, "_save_session", pause_before_real_save)
    _signal_before_exclusive_lock(monkeypatch, deletion_worker, delete_lock_attempted)

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending_renewal = pool.submit(renewal_worker.check_and_auto_renew, "victim")
        assert save_reached.wait(timeout=2)

        if full_agent_delete:
            agents = AgentService(agents_dir=tmp_path / "agents")
            agents._save_agent(
                AgentInfo(
                    agent_id="victim",
                    namespace="memanto_agent_victim",
                    pattern=AgentPattern.SUPPORT,
                    created_at=datetime.now(timezone.utc),
                )
            )
            monkeypatch.setattr(sessions, "agent_service", agents)
            monkeypatch.setattr(
                sessions, "get_session_service", lambda: deletion_worker
            )

            def route_delete():
                return asyncio.run(
                    sessions.delete_agent(
                        "victim", delete_backup_too=False, moorcheh_api_key="dummy"
                    )
                )

            pending_delete = pool.submit(
                route_delete,
            )
        else:

            def session_delete():
                return deletion_worker.delete_session("victim")

            pending_delete = pool.submit(session_delete)

        # Deletion cannot unlink state while renewal owns the shared OS lock.
        assert delete_lock_attempted.wait(timeout=2)
        assert not pending_delete.done()
        allow_save.set()
        renewed = pending_renewal.result(timeout=2)
        delete_result = pending_delete.result(timeout=2)

    assert renewed is not None
    assert renewed.session_id != original.session_id
    assert renewed.session_token != original.session_token
    assert not (sessions_dir / "victim.json").exists()
    if full_agent_delete:
        assert "successfully deleted" in delete_result["message"]
        assert agents.get_agent("victim") is None
    else:
        assert delete_result is True

    # This is the normal auth dependency used by v2 memory routes.
    monkeypatch.setattr(auth_deps, "get_session_service", lambda: deletion_worker)
    with pytest.raises(HTTPException, match="SessionNotFound|InvalidSessionToken"):
        auth_deps.get_current_session(
            _request_with_token(renewed.session_token),
            Response(),
            x_session_token=renewed.session_token,
        )

    restarted_worker = SessionService(sessions_dir=sessions_dir)
    with pytest.raises(InvalidSessionTokenError):
        restarted_worker.validate_session(renewed.session_token)


def test_auto_renew_still_works_without_revocation(tmp_path, monkeypatch):
    """The cross-process lock does not change ordinary renewal behavior."""
    service = SessionService(sessions_dir=tmp_path / "sessions")
    original = service.create_session("victim", duration_hours=1)
    monkeypatch.setattr(settings, "SESSION_AUTO_RENEW_ENABLED", True)
    monkeypatch.setattr(settings, "SESSION_EXTEND_THRESHOLD_MINUTES", 120)

    renewed = service.check_and_auto_renew("victim")

    assert renewed is not None
    assert renewed.session_id != original.session_id
    service.validate_session(renewed.session_token)


def test_cross_instance_deletion_remains_authoritative_over_session_creation(
    tmp_path, monkeypatch
):
    """Explicit creation cannot persist a replacement after deletion begins."""
    sessions_dir = tmp_path / "sessions"
    creation_worker = SessionService(sessions_dir=sessions_dir)
    deletion_worker = SessionService(sessions_dir=sessions_dir)
    original = creation_worker.create_session("victim", duration_hours=1)
    save_reached = Event()
    allow_save = Event()
    delete_lock_attempted = Event()
    original_save = creation_worker._save_session

    def pause_before_real_save(session):
        if session.session_id != original.session_id:
            save_reached.set()
            assert allow_save.wait(timeout=2)
        original_save(session)

    monkeypatch.setattr(creation_worker, "_save_session", pause_before_real_save)
    _signal_before_exclusive_lock(monkeypatch, deletion_worker, delete_lock_attempted)

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending_create = pool.submit(creation_worker.create_session, "victim")
        assert save_reached.wait(timeout=2)
        pending_delete = pool.submit(deletion_worker.delete_session, "victim")
        assert delete_lock_attempted.wait(timeout=2)
        assert not pending_delete.done()
        allow_save.set()
        replacement = pending_create.result(timeout=2)
        assert pending_delete.result(timeout=2) is True

    assert not (sessions_dir / "victim.json").exists()
    monkeypatch.setattr(auth_deps, "get_session_service", lambda: deletion_worker)
    with pytest.raises(HTTPException, match="SessionNotFound|InvalidSessionToken"):
        auth_deps.get_current_session(
            _request_with_token(replacement.session_token),
            Response(),
            x_session_token=replacement.session_token,
        )


def test_active_marker_clear_does_not_remove_another_workers_marker(
    tmp_path, monkeypatch
):
    """A conditional clear cannot remove a marker replaced by another worker."""
    sessions_dir = tmp_path / "sessions"
    clearing_worker = SessionService(sessions_dir=sessions_dir)
    setting_worker = SessionService(sessions_dir=sessions_dir)
    clearing_worker.create_session("agent-a", duration_hours=1)
    setting_worker.create_session("agent-b", duration_hours=1)
    clearing_worker._set_active_session("agent-a")
    marker_read = Event()
    allow_clear = Event()
    setting_lock_attempted = Event()
    original_read = clearing_worker._read_active_marker_agent_id

    def pause_after_read():
        agent_id = original_read()
        if agent_id == "agent-a":
            marker_read.set()
            assert allow_clear.wait(timeout=2)
        return agent_id

    monkeypatch.setattr(
        clearing_worker, "_read_active_marker_agent_id", pause_after_read
    )
    _signal_before_exclusive_lock(monkeypatch, setting_worker, setting_lock_attempted)

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending_delete = pool.submit(clearing_worker.delete_session, "agent-a")
        assert marker_read.wait(timeout=2)
        pending_set = pool.submit(setting_worker._set_active_session, "agent-b")
        assert setting_lock_attempted.wait(timeout=2)
        assert not pending_set.done()
        allow_clear.set()
        assert pending_delete.result(timeout=2) is True
        pending_set.result(timeout=2)

    active = setting_worker.get_active_session()
    assert active is not None
    assert active.agent_id == "agent-b"


def test_cross_instance_end_session_remains_authoritative_over_renewal(
    tmp_path, monkeypatch
):
    """Deactivation waits for renewal, then revokes its replacement token."""
    sessions_dir = tmp_path / "sessions"
    renewal_worker = SessionService(sessions_dir=sessions_dir)
    ending_worker = SessionService(sessions_dir=sessions_dir)
    original = renewal_worker.create_session("victim", duration_hours=1)
    monkeypatch.setattr(settings, "SESSION_AUTO_RENEW_ENABLED", True)
    monkeypatch.setattr(settings, "SESSION_EXTEND_THRESHOLD_MINUTES", 120)

    save_reached = Event()
    allow_save = Event()
    ending_lock_attempted = Event()
    original_save = renewal_worker._save_session

    def pause_before_real_save(session):
        if session.session_id != original.session_id:
            save_reached.set()
            assert allow_save.wait(timeout=2)
        original_save(session)

    monkeypatch.setattr(renewal_worker, "_save_session", pause_before_real_save)
    _signal_before_exclusive_lock(monkeypatch, ending_worker, ending_lock_attempted)

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending_renewal = pool.submit(renewal_worker.check_and_auto_renew, "victim")
        assert save_reached.wait(timeout=2)
        pending_end = pool.submit(ending_worker.end_session, "victim")
        assert ending_lock_attempted.wait(timeout=2)
        assert not pending_end.done()
        allow_save.set()
        renewed = pending_renewal.result(timeout=2)
        summary = pending_end.result(timeout=2)

    assert renewed is not None
    assert summary.agent_id == "victim"
    assert ending_worker.get_session("victim") is not None
    monkeypatch.setattr(auth_deps, "get_session_service", lambda: ending_worker)
    with pytest.raises(HTTPException, match="SessionNotFound|InvalidSessionToken"):
        auth_deps.get_current_session(
            _request_with_token(renewed.session_token),
            Response(),
            x_session_token=renewed.session_token,
        )


def test_cross_instance_deletion_remains_authoritative_over_auto_recreate(
    tmp_path, monkeypatch
):
    """Deletion waits for an expired-session recreation and then removes it."""
    sessions_dir = tmp_path / "sessions"
    recreate_worker = SessionService(sessions_dir=sessions_dir)
    deletion_worker = SessionService(sessions_dir=sessions_dir)
    original = recreate_worker.create_session("victim", duration_hours=0)
    monkeypatch.setattr(settings, "SESSION_AUTO_RECREATE_ENABLED", True)

    save_reached = Event()
    allow_save = Event()
    delete_lock_attempted = Event()
    original_save = recreate_worker._save_session

    def pause_before_real_save(session):
        if session.session_id != original.session_id:
            save_reached.set()
            assert allow_save.wait(timeout=2)
        original_save(session)

    monkeypatch.setattr(recreate_worker, "_save_session", pause_before_real_save)
    _signal_before_exclusive_lock(monkeypatch, deletion_worker, delete_lock_attempted)

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending_recreate = pool.submit(
            recreate_worker.check_and_auto_recreate, original.session_token
        )
        assert save_reached.wait(timeout=2)
        pending_delete = pool.submit(deletion_worker.delete_session, "victim")
        assert delete_lock_attempted.wait(timeout=2)
        assert not pending_delete.done()
        allow_save.set()
        recreated = pending_recreate.result(timeout=2)
        assert pending_delete.result(timeout=2) is True

    assert recreated is not None
    assert not (sessions_dir / "victim.json").exists()
    monkeypatch.setattr(auth_deps, "get_session_service", lambda: deletion_worker)
    with pytest.raises(HTTPException, match="SessionNotFound|InvalidSessionToken"):
        auth_deps.get_current_session(
            _request_with_token(recreated.session_token),
            Response(),
            x_session_token=recreated.session_token,
        )


def test_deletion_before_renewal_or_recreation_cannot_restore_a_session(
    tmp_path, monkeypatch
):
    """A later lifecycle check cannot recreate a session already deleted."""
    service = SessionService(sessions_dir=tmp_path / "sessions")
    original = service.create_session("victim", duration_hours=1)
    monkeypatch.setattr(settings, "SESSION_AUTO_RENEW_ENABLED", True)
    monkeypatch.setattr(settings, "SESSION_AUTO_RECREATE_ENABLED", True)
    monkeypatch.setattr(settings, "SESSION_EXTEND_THRESHOLD_MINUTES", 120)

    assert service.delete_session("victim") is True
    assert service.check_and_auto_renew("victim") is None
    assert service.check_and_auto_recreate(original.session_token) is None
    assert service.get_session("victim") is None


def test_agent_lifecycle_lock_does_not_block_an_independent_agent(
    tmp_path, monkeypatch
):
    """A lifecycle operation for one agent does not serialize other agents."""
    service = SessionService(sessions_dir=tmp_path / "sessions")
    service.create_session("agent-a", duration_hours=1)
    original_b = service.create_session("agent-b", duration_hours=1)
    monkeypatch.setattr(settings, "SESSION_AUTO_RENEW_ENABLED", True)
    monkeypatch.setattr(settings, "SESSION_EXTEND_THRESHOLD_MINUTES", 120)
    lock_held = Event()
    release_lock = Event()

    def hold_agent_a_lock():
        with service._cross_process_lifecycle_lock("agent-a"):
            lock_held.set()
            assert release_lock.wait(timeout=2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending_a = pool.submit(hold_agent_a_lock)
        assert lock_held.wait(timeout=2)
        renewed_b = pool.submit(service.check_and_auto_renew, "agent-b").result(
            timeout=1
        )
        release_lock.set()
        pending_a.result(timeout=2)

    assert renewed_b is not None
    assert renewed_b.session_id != original_b.session_id


def test_session_can_be_created_again_after_deletion(tmp_path):
    """Deletion releases lifecycle state; later explicit activation remains valid."""
    service = SessionService(sessions_dir=tmp_path / "sessions")
    original = service.create_session("victim", duration_hours=1)

    assert service.delete_session("victim") is True
    with pytest.raises(InvalidSessionTokenError):
        service.validate_session(original.session_token)

    reactivated = service.create_session("victim", duration_hours=1)
    assert reactivated.session_id != original.session_id
    service.validate_session(reactivated.session_token)


def test_full_agent_delete_blocks_a_prechecked_session_creation(tmp_path, monkeypatch):
    """Creation rechecks metadata after waiting for full deletion to finish."""
    sessions_dir = tmp_path / "sessions"
    creation_worker = SessionService(sessions_dir=sessions_dir)
    deletion_worker = SessionService(sessions_dir=sessions_dir)
    creation_worker.create_session("victim", duration_hours=1)
    agents = AgentService(agents_dir=tmp_path / "agents")
    agents._save_agent(
        AgentInfo(
            agent_id="victim",
            namespace="memanto_agent_victim",
            pattern=AgentPattern.SUPPORT,
            created_at=datetime.now(timezone.utc),
        )
    )
    activation_checked = Event()
    allow_creation = Event()
    creation_lock_attempted = Event()
    metadata_delete_ready = Event()
    allow_metadata_delete = Event()
    agent_file = agents._get_agent_file("victim")
    original_unlink = Path.unlink

    def pause_before_metadata_unlink(path, *args, **kwargs):
        if path == agent_file:
            metadata_delete_ready.set()
            assert allow_metadata_delete.wait(timeout=2)
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", pause_before_metadata_unlink)
    monkeypatch.setattr(sessions, "agent_service", agents)
    monkeypatch.setattr(sessions, "get_session_service", lambda: deletion_worker)
    _signal_before_exclusive_lock(monkeypatch, creation_worker, creation_lock_attempted)

    def create_after_activation_check():
        agent = agents.get_agent("victim")
        assert agent is not None
        activation_checked.set()
        assert allow_creation.wait(timeout=2)
        return creation_worker.create_session(
            "victim",
            pattern=agent.pattern,
            agent_exists=lambda: agents.agent_exists("victim"),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending_create = pool.submit(create_after_activation_check)
        assert activation_checked.wait(timeout=2)
        pending_delete = pool.submit(
            lambda: asyncio.run(
                sessions.delete_agent(
                    "victim", delete_backup_too=False, moorcheh_api_key="dummy"
                )
            )
        )
        assert metadata_delete_ready.wait(timeout=2)
        allow_creation.set()
        assert creation_lock_attempted.wait(timeout=2)
        assert not pending_create.done()
        allow_metadata_delete.set()
        pending_delete.result(timeout=2)

        with pytest.raises(AgentNotFoundError):
            pending_create.result(timeout=2)

    assert agents.get_agent("victim") is None
    assert creation_worker.get_session("victim") is None


def _assert_activation_stats_cannot_resurrect_agent(
    tmp_path, monkeypatch, activate, *, route_activates=False
):
    """Verify deletion remains authoritative over a paused stats write."""
    sessions_dir = tmp_path / "sessions"
    activation_worker = SessionService(sessions_dir=sessions_dir)
    deletion_worker = SessionService(sessions_dir=sessions_dir)
    agents = AgentService(agents_dir=tmp_path / "agents")
    agents._save_agent(
        AgentInfo(
            agent_id="victim",
            namespace="memanto_agent_victim",
            pattern=AgentPattern.SUPPORT,
            created_at=datetime.now(timezone.utc),
        )
    )
    stats_save_ready = Event()
    allow_stats_save = Event()
    delete_lock_attempted = Event()
    original_save = agents._save_agent

    def pause_before_stats_save(agent):
        stats_save_ready.set()
        assert allow_stats_save.wait(timeout=2)
        original_save(agent)

    monkeypatch.setattr(agents, "_save_agent", pause_before_stats_save)
    monkeypatch.setattr(sessions, "agent_service", agents)
    if route_activates:
        calls = 0

        def session_service_for_route():
            nonlocal calls
            calls += 1
            return activation_worker if calls == 1 else deletion_worker

        monkeypatch.setattr(sessions, "get_session_service", session_service_for_route)
    else:
        monkeypatch.setattr(sessions, "get_session_service", lambda: deletion_worker)
    _signal_before_exclusive_lock(monkeypatch, deletion_worker, delete_lock_attempted)

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending_activation = pool.submit(activate, activation_worker, agents)
        assert stats_save_ready.wait(timeout=2)

        pending_delete = pool.submit(
            lambda: asyncio.run(
                sessions.delete_agent(
                    "victim", delete_backup_too=False, moorcheh_api_key="dummy"
                )
            )
        )
        assert delete_lock_attempted.wait(timeout=2)
        assert not pending_delete.done()

        allow_stats_save.set()
        pending_activation.result(timeout=2)
        pending_delete.result(timeout=2)

    assert agents.get_agent("victim") is None


def test_api_activation_stats_write_cannot_recreate_deleted_agent(
    tmp_path, monkeypatch
):
    """API activation keeps stats update inside the lifecycle transaction."""

    def activate(session_service, _agents):
        return asyncio.run(
            sessions.activate_agent(
                "victim",
                _request_with_token("unused"),
                Response(),
                moorcheh_api_key="dummy",
            )
        )

    _assert_activation_stats_cannot_resurrect_agent(
        tmp_path, monkeypatch, activate, route_activates=True
    )


@pytest.mark.parametrize("client_class", [DirectClient, SdkClient])
def test_client_activation_stats_write_cannot_recreate_deleted_agent(
    tmp_path, monkeypatch, client_class
):
    """Local clients use the same lifecycle scope as API activation."""

    def activate(session_service, agents):
        client = client_class(api_key="dummy")
        monkeypatch.setattr(client, "_get_session_service", lambda: session_service)
        monkeypatch.setattr(client, "_get_agent_service", lambda: agents)
        return client.activate_agent("victim")

    _assert_activation_stats_cannot_resurrect_agent(tmp_path, monkeypatch, activate)


def _assert_activation_uses_recreated_metadata_after_same_id_recreation(
    tmp_path, monkeypatch, activate, *, route_activates=False
):
    """Verify activation uses metadata loaded after same-ID recreation."""
    sessions_dir = tmp_path / "sessions"
    activation_worker = SessionService(sessions_dir=sessions_dir)
    deletion_worker = SessionService(sessions_dir=sessions_dir)
    agents = AgentService(agents_dir=tmp_path / "agents")
    agents._save_agent(
        AgentInfo(
            agent_id="victim",
            namespace="memanto_agent_victim",
            pattern=AgentPattern.SUPPORT,
            created_at=datetime.now(timezone.utc),
        )
    )
    before_lifecycle_transaction = Event()
    allow_activation = Event()
    original_transaction = activation_worker.agent_lifecycle_transaction

    @contextmanager
    def pause_before_lifecycle_transaction(agent_id):
        before_lifecycle_transaction.set()
        assert allow_activation.wait(timeout=2)
        with original_transaction(agent_id):
            yield

    monkeypatch.setattr(
        activation_worker,
        "agent_lifecycle_transaction",
        pause_before_lifecycle_transaction,
    )
    monkeypatch.setattr(sessions, "agent_service", agents)
    if route_activates:
        calls = 0

        def session_service_for_route():
            nonlocal calls
            calls += 1
            return activation_worker if calls == 1 else deletion_worker

        monkeypatch.setattr(sessions, "get_session_service", session_service_for_route)
    else:
        monkeypatch.setattr(sessions, "get_session_service", lambda: deletion_worker)

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending_activation = pool.submit(activate, activation_worker, agents)
        assert before_lifecycle_transaction.wait(timeout=2)

        pending_delete = pool.submit(
            lambda: asyncio.run(
                sessions.delete_agent(
                    "victim", delete_backup_too=False, moorcheh_api_key="dummy"
                )
            )
        )
        pending_delete.result(timeout=2)
        assert agents.get_agent("victim") is None

        # Recreate local metadata with a distinct pattern; creating a backend
        # namespace is deliberately out of scope for this local regression.
        agents._save_agent(
            AgentInfo(
                agent_id="victim",
                namespace="memanto_agent_victim",
                pattern=AgentPattern.PROJECT,
                created_at=datetime.now(timezone.utc),
            )
        )
        allow_activation.set()
        pending_activation.result(timeout=2)

    persisted = activation_worker.get_session("victim")
    assert persisted is not None
    assert persisted.pattern == AgentPattern.PROJECT
    assert agents.get_agent("victim").pattern == AgentPattern.PROJECT


def test_api_activation_uses_recreated_metadata_after_same_id_recreation(
    tmp_path, monkeypatch
):
    """API activation reloads metadata inside the lifecycle transaction."""

    def activate(_session_service, _agents):
        return asyncio.run(
            sessions.activate_agent(
                "victim",
                _request_with_token("unused"),
                Response(),
                moorcheh_api_key="dummy",
            )
        )

    _assert_activation_uses_recreated_metadata_after_same_id_recreation(
        tmp_path, monkeypatch, activate, route_activates=True
    )


@pytest.mark.parametrize("client_class", [DirectClient, SdkClient])
def test_client_activation_uses_recreated_metadata_after_same_id_recreation(
    tmp_path, monkeypatch, client_class
):
    """Local clients reload metadata inside the lifecycle transaction."""

    def activate(session_service, agents):
        client = client_class(api_key="dummy")
        monkeypatch.setattr(client, "_get_session_service", lambda: session_service)
        monkeypatch.setattr(client, "_get_agent_service", lambda: agents)
        return client.activate_agent("victim")

    _assert_activation_uses_recreated_metadata_after_same_id_recreation(
        tmp_path, monkeypatch, activate
    )
