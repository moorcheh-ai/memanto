"""Regression tests for cross-process session revocation races."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event

import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

from memanto.app.config import settings
from memanto.app.models.session import AgentInfo, AgentPattern
from memanto.app.routes import auth_deps, sessions
from memanto.app.services.agent_service import AgentService
from memanto.app.services.session_service import SessionService
from memanto.app.utils.errors import InvalidSessionTokenError


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
    delete_started = Event()
    original_save = renewal_worker._save_session

    def pause_before_real_save(session):
        if session.session_id != original.session_id:
            save_reached.set()
            assert allow_save.wait(timeout=2)
        original_save(session)

    monkeypatch.setattr(renewal_worker, "_save_session", pause_before_real_save)

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
                delete_started.set()
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
                delete_started.set()
                return deletion_worker.delete_session("victim")

            pending_delete = pool.submit(session_delete)

        # Deletion cannot unlink state while renewal owns the shared OS lock.
        assert delete_started.wait(timeout=2)
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
    ending_started = Event()
    original_save = renewal_worker._save_session

    def pause_before_real_save(session):
        if session.session_id != original.session_id:
            save_reached.set()
            assert allow_save.wait(timeout=2)
        original_save(session)

    monkeypatch.setattr(renewal_worker, "_save_session", pause_before_real_save)

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending_renewal = pool.submit(renewal_worker.check_and_auto_renew, "victim")
        assert save_reached.wait(timeout=2)
        pending_end = pool.submit(
            lambda: (ending_started.set(), ending_worker.end_session("victim"))[1]
        )
        assert ending_started.wait(timeout=2)
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
    delete_started = Event()
    original_save = recreate_worker._save_session

    def pause_before_real_save(session):
        if session.session_id != original.session_id:
            save_reached.set()
            assert allow_save.wait(timeout=2)
        original_save(session)

    monkeypatch.setattr(recreate_worker, "_save_session", pause_before_real_save)

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending_recreate = pool.submit(
            recreate_worker.check_and_auto_recreate, original.session_token
        )
        assert save_reached.wait(timeout=2)
        pending_delete = pool.submit(
            lambda: (delete_started.set(), deletion_worker.delete_session("victim"))[1]
        )
        assert delete_started.wait(timeout=2)
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
