import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from memanto.app.config import settings
from memanto.app.services.session_service import SessionService
from memanto.app.utils.errors import InvalidSessionTokenError


def test_logout_serializes_with_renewal_across_service_instances(tmp_path, monkeypatch):
    """Independent workers sharing session storage must share lifecycle lock.

    Two SessionService instances model separate worker processes: before the
    fix each owned an unrelated threading.RLock, so worker B could finish
    logout while worker A was paused inside renewal, after which A published a
    new valid bearer token. A filesystem-backed lifecycle lock must force B to
    wait and terminate A's replacement session instead.
    """
    sessions_dir = tmp_path / "sessions"
    secret = "cross-process-session-lifecycle-test-secret-32b"
    renewing_worker = SessionService(secret_key=secret, sessions_dir=sessions_dir)
    logout_worker = SessionService(secret_key=secret, sessions_dir=sessions_dir)

    original = renewing_worker.create_session(agent_id="test-agent", duration_hours=1)
    monkeypatch.setattr(settings, "SESSION_EXTEND_THRESHOLD_MINUTES", 120)

    original_renew = renewing_worker.renew_session
    renewal_entered = threading.Event()
    release_renewal = threading.Event()

    def controlled_renew(agent_id, pattern=None):
        renewal_entered.set()
        assert release_renewal.wait(timeout=3)
        return original_renew(agent_id=agent_id, pattern=pattern)

    monkeypatch.setattr(renewing_worker, "renew_session", controlled_renew)

    with ThreadPoolExecutor(max_workers=2) as pool:
        renewing = pool.submit(renewing_worker.check_and_auto_renew, "test-agent")
        assert renewal_entered.wait(timeout=3)

        ending = pool.submit(logout_worker.end_session, "test-agent")
        # A second SessionService instance has a different in-memory lock. The
        # only thing that can keep logout pending here is cross-process locking.
        assert not ending.done()

        release_renewal.set()
        renewed = renewing.result(timeout=3)
        summary = ending.result(timeout=3)

    assert renewed is not None
    assert renewed.session_id != original.session_id
    assert summary.session_id == renewed.session_id
    with pytest.raises(InvalidSessionTokenError):
        renewing_worker.validate_session(renewed.session_token)
