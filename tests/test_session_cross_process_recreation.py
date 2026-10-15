"""Exercise expired-session recreation versus logout in independent processes."""

from __future__ import annotations

import multiprocessing
from pathlib import Path

import pytest

from memanto.app.config import settings
from memanto.app.services.session_service import SessionService
from memanto.app.utils.errors import InvalidSessionTokenError

_SECRET = "cross-process-recreation-test-secret-key-123456"
_AGENT_ID = "recreation-race-agent"


def _recreate_worker(sessions_dir, token, entered, release, results):
    """Pause after the old expired session was accepted for recreation."""
    settings.SESSION_AUTO_RECREATE_ENABLED = True
    service = SessionService(secret_key=_SECRET, sessions_dir=Path(sessions_dir))
    original_create = service.create_session

    def paused_create(agent_id, pattern=None, duration_hours=None):
        entered.set()
        if not release.wait(timeout=10):
            raise TimeoutError("Parent did not release recreation")
        return original_create(agent_id, pattern, duration_hours)

    service.create_session = paused_create
    try:
        renewed = service.check_and_auto_recreate(token)
        if renewed is None:
            results.put(("recreate_error", "expired session was not recreated"))
        else:
            results.put(("recreated", renewed.session_id, renewed.session_token))
    except Exception as exc:
        results.put(("recreate_error", repr(exc)))


def _logout_worker(sessions_dir, called, body_entered, results):
    """Expose when logout enters the mutation body, after acquiring its lock."""
    service = SessionService(secret_key=_SECRET, sessions_dir=Path(sessions_dir))
    original_end = service._end_session

    def observed_end(agent_id):
        body_entered.set()
        return original_end(agent_id)

    service._end_session = observed_end
    try:
        called.set()
        ended = service.end_session(_AGENT_ID)
        results.put(("logged_out", ended.session_id))
    except Exception as exc:
        results.put(("logout_error", repr(exc)))


def test_logout_revokes_inflight_auto_recreation_across_processes(tmp_path):
    """Logout must terminate a recreation begun by another OS process.

    The original cross-process gap held only a process-local RLock while
    validating expired state. Logout could therefore finish before the
    recreation published an ACTIVE token. The shared lifecycle file lock
    must cover both the state check and the new token write.
    """
    sessions_dir = tmp_path / "sessions"
    service = SessionService(secret_key=_SECRET, sessions_dir=sessions_dir)
    expired = service.create_session(agent_id=_AGENT_ID, duration_hours=0)

    context = multiprocessing.get_context("spawn")
    entered, release = context.Event(), context.Event()
    called, body_entered = context.Event(), context.Event()
    results = context.Queue()
    recreating = context.Process(
        target=_recreate_worker,
        args=(str(sessions_dir), expired.session_token, entered, release, results),
    )
    logging_out = context.Process(
        target=_logout_worker,
        args=(str(sessions_dir), called, body_entered, results),
    )

    try:
        recreating.start()
        assert entered.wait(timeout=10), "recreation never reached its pause"
        logging_out.start()
        assert called.wait(timeout=10), "logout process did not start"
        assert not body_entered.wait(timeout=0.4), (
            "logout entered while recreation still held the lifecycle lock"
        )
        release.set()
        recreating.join(timeout=15)
        logging_out.join(timeout=15)
        assert recreating.exitcode == 0
        assert logging_out.exitcode == 0
        outcomes = [results.get(timeout=5) for _ in range(2)]
        outcomes_by_type = {entry[0]: entry for entry in outcomes}
        assert set(outcomes_by_type) == {"recreated", "logged_out"}, outcomes
        renewed_id, renewed_token = outcomes_by_type["recreated"][1:]
        assert renewed_id != expired.session_id
        assert outcomes_by_type["logged_out"][1] == renewed_id
        with pytest.raises(InvalidSessionTokenError):
            service.validate_session(renewed_token)
    finally:
        release.set()
        for process in (recreating, logging_out):
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        results.close()


def _renew_worker(sessions_dir, entered, release, results):
    """Pause a real worker during near-expiry session renewal."""
    settings.SESSION_AUTO_RENEW_ENABLED = True
    settings.SESSION_EXTEND_THRESHOLD_MINUTES = 120
    service = SessionService(secret_key=_SECRET, sessions_dir=Path(sessions_dir))
    original_renew = service.renew_session

    def paused_renew(agent_id, pattern=None):
        entered.set()
        if not release.wait(timeout=10):
            raise TimeoutError("Parent did not release renewal")
        return original_renew(agent_id, pattern)

    service.renew_session = paused_renew
    try:
        renewed = service.check_and_auto_renew(_AGENT_ID)
        if renewed is None:
            results.put(("renew_error", "near-expiry session not renewed"))
        else:
            results.put(("renewed", renewed.session_id, renewed.session_token))
    except Exception as exc:
        results.put(("renew_error", repr(exc)))


def test_logout_revokes_inflight_renewal_across_real_processes(tmp_path):
    """An independent logout process must revoke the in-flight new token."""
    sessions_dir = tmp_path / "sessions"
    service = SessionService(secret_key=_SECRET, sessions_dir=sessions_dir)
    original = service.create_session(agent_id=_AGENT_ID, duration_hours=1)

    context = multiprocessing.get_context("spawn")
    entered, release = context.Event(), context.Event()
    called, body_entered = context.Event(), context.Event()
    results = context.Queue()
    renewing = context.Process(
        target=_renew_worker, args=(str(sessions_dir), entered, release, results)
    )
    logging_out = context.Process(
        target=_logout_worker,
        args=(str(sessions_dir), called, body_entered, results),
    )

    try:
        renewing.start()
        assert entered.wait(timeout=10), "renewal never reached its pause"
        logging_out.start()
        assert called.wait(timeout=10), "logout process did not start"
        assert not body_entered.wait(timeout=0.4), (
            "logout mutated persisted state during in-flight renewal"
        )
        release.set()
        renewing.join(timeout=15)
        logging_out.join(timeout=15)
        assert renewing.exitcode == 0
        assert logging_out.exitcode == 0
        outcomes = [results.get(timeout=5) for _ in range(2)]
        by_type = {entry[0]: entry for entry in outcomes}
        assert set(by_type) == {"renewed", "logged_out"}, outcomes
        renewed_id, renewed_token = by_type["renewed"][1:]
        assert renewed_id != original.session_id
        assert by_type["logged_out"][1] == renewed_id
        with pytest.raises(InvalidSessionTokenError):
            service.validate_session(renewed_token)
    finally:
        release.set()
        for process in (renewing, logging_out):
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        results.close()
