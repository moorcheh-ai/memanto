"""Bounty #770 round 7 — memory-integrity fixes across extraction, session
summary archiving, JWT validation, export timestamps, and session duration.

Run:  python -m pytest tests/failing_tests/test_bounty_770_round7.py -v
      (or:  python tests/failing_tests/test_bounty_770_round7.py)

Bugs covered:
  1. conversation_memory_extraction_service._conversation_text truncated the
     NEWEST messages (the ones this request is actually about) instead of the
     oldest, and returned "" for a single oversized message -> the extraction
     query became empty (ValueError / 400) or stale.
  2. session_service.log_memory_to_session_summary archived summary files by
     memory.created_at; imported/backfilled memories with an old created_at
     were written to an old date's file that daily_analysis_service (glob on
     today) never reads -> today's activity permanently missing from summaries.
  3. session_service.validate_session did not catch pydantic.ValidationError
     when a signature-valid token lacked payload fields -> unhandled 500
     instead of InvalidSessionTokenError.
  4. memory_export_service.format_memory_md used naive local datetime.now()
     for "Generated:" while every memory timestamp is UTC ISO -> mixed time
     bases in one exported file (off-by-one-day near midnight UTC+8).
  5. session_service._create_session accepted duration_hours <= 0, producing
     an immediately-expired session while the CLI reported success.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ---------------------------------------------------------------------------
# 1. _conversation_text keeps newest messages, never returns ""
# ---------------------------------------------------------------------------

def test_conversation_text_keeps_newest_not_oldest():
    """When the transcript exceeds the budget, the truncated query must keep
    the LATEST messages (what this request is about), not the oldest."""
    import memanto.app.services.conversation_memory_extraction_service as m

    svc = m.ConversationMemoryExtractionService.__new__(
        m.ConversationMemoryExtractionService
    )
    svc.MAX_CONTENT_CHARS = 100

    messages = [
        {"role": "user", "content": "A" * 40},
        {"role": "assistant", "content": "B" * 40},
        {"role": "user", "content": "C" * 40},
    ]
    result = svc._conversation_text(messages)
    # Oldest two messages total 82+ chars > 100, so at least message 3 (C)
    # must survive; the oldest (A) must be the one dropped.
    assert "C" * 40 in result, "newest message must survive truncation"
    assert ("A" * 40) not in result, "oldest message must be dropped first"


def test_conversation_text_single_oversized_message_never_empty():
    """A single message longer than the budget must still produce a non-empty
    query (the caller raises on empty), instead of returning ''."""
    import memanto.app.services.conversation_memory_extraction_service as m

    svc = m.ConversationMemoryExtractionService.__new__(
        m.ConversationMemoryExtractionService
    )
    svc.MAX_CONTENT_CHARS = 100

    result = svc._conversation_text(
        [{"role": "user", "content": "Z" * 500}]
    )
    assert result, "oversized single message must not yield an empty query"
    assert "Z" * 500 in result


# ---------------------------------------------------------------------------
# 2. Session summary files archived by write time, not memory.created_at
# ---------------------------------------------------------------------------

def test_summary_file_uses_write_time_not_created_at(tmp_path):
    """Importing a memory with an old created_at must still log it into
    TODAY's summary file (the one daily_analysis_service globs)."""
    import memanto.app.services.session_service as m

    svc = m.SessionService.__new__(m.SessionService)
    svc.sessions_dir = tmp_path
    svc.sessions_dir.mkdir(parents=True, exist_ok=True)
    svc._summary_lock = __import__("threading").RLock()
    svc._harden_session_storage = lambda: None

    class _Rec:
        created_at = datetime(2020, 3, 1, tzinfo=timezone.utc)
        type = "fact"
        title = "t"
        content = "c"
        confidence = 0.9
        id = "m1"
        source = "user"
        provenance = "explicit_statement"
        status = "active"
        tags = []

    svc.log_memory_to_session_summary("ag1", "sess1", _Rec())

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    old_file = tmp_path / f"ag1_2020-03-01_sess1_summary.md"
    today_file = tmp_path / f"ag1_{today}_sess1_summary.md"
    assert not old_file.exists(), (
        "summary must not be archived by memory.created_at (2020-03-01)"
    )
    assert today_file.exists(), (
        "summary must be written to today's file so daily analysis sees it"
    )


# ---------------------------------------------------------------------------
# 3. validate_session maps payload ValidationError to InvalidSessionTokenError
# ---------------------------------------------------------------------------

def test_validate_session_missing_fields_is_invalid_token(tmp_path):
    """A signature-valid JWT missing required payload fields must raise
    InvalidSessionTokenError (client error), never a raw ValidationError."""
    import jwt

    import memanto.app.services.session_service as m
    from memanto.app.utils.errors import InvalidSessionTokenError

    svc = m.SessionService.__new__(m.SessionService)
    svc.sessions_dir = tmp_path
    svc.sessions_dir.mkdir(parents=True, exist_ok=True)
    svc._secret_key = "test-secret"
    svc._agent_locks = {}
    svc._agent_locks_guard = __import__("threading").Lock()
    svc._active_marker_lock = __import__("threading").RLock()
    svc._summary_lock = __import__("threading").RLock()
    svc._storage_hardened = True

    # Signed with the valid key but missing namespace/expires_at/started_at.
    token = jwt.encode(
        {"agent_id": "a", "session_id": "s"}, "test-secret", algorithm="HS256"
    )
    try:
        svc.validate_session(token)
        raise AssertionError("must raise InvalidSessionTokenError")
    except InvalidSessionTokenError:
        pass
    except Exception as exc:  # noqa: BLE001 - assert the exact contract
        raise AssertionError(
            f"expected InvalidSessionTokenError, got {type(exc).__name__}: {exc}"
        )


# ---------------------------------------------------------------------------
# 4. Export header timestamp is timezone-aware UTC
# ---------------------------------------------------------------------------

def test_export_generated_at_is_utc_aware():
    """'Generated:' must be a UTC ISO timestamp (same time base as every
    memory created_at), not naive local time."""
    import memanto.app.services.memory_export_service as m

    svc = m.MemoryExportService.__new__(m.MemoryExportService)

    out = svc.format_memory_md(
        "ag1",
        {"fact": [{"title": "t", "content": "c", "created_at": "2026-08-07T08:00:00+00:00"}]},
        generated_at=None,
    )
    gen_line = [ln for ln in out.splitlines() if ln.startswith("> Generated:")]
    assert gen_line, "header must include Generated:"
    stamp = gen_line[0].replace("> Generated:", "").strip()
    assert "+00:00" in stamp or stamp.endswith("Z"), (
        f"Generated timestamp must carry UTC offset, got: {stamp!r}"
    )


# ---------------------------------------------------------------------------
# 5. _create_session rejects non-positive durations
# ---------------------------------------------------------------------------

def test_create_session_rejects_nonpositive_duration(tmp_path):
    """duration_hours <= 0 must raise ValueError instead of minting an
    already-expired session that the CLI then reports as success."""
    import memanto.app.services.session_service as m

    svc = m.SessionService.__new__(m.SessionService)
    svc.sessions_dir = tmp_path
    svc.sessions_dir.mkdir(parents=True, exist_ok=True)
    svc._secret_key = "test-secret"
    svc._agent_locks = {}
    svc._agent_locks_guard = __import__("threading").Lock()
    svc._active_marker_lock = __import__("threading").RLock()
    svc._summary_lock = __import__("threading").RLock()
    svc._storage_hardened = True
    svc._save_session = lambda s: None
    svc._set_active_session = lambda a: None

    for bad in (0, -1, -24):
        try:
            svc._create_session("ag1", None, duration_hours=bad)
            raise AssertionError(f"duration_hours={bad} must raise ValueError")
        except ValueError:
            pass


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        test_conversation_text_keeps_newest_not_oldest()
        test_conversation_text_single_oversized_message_never_empty()
        test_summary_file_uses_write_time_not_created_at(p)
        test_validate_session_missing_fields_is_invalid_token(p)
        test_export_generated_at_is_utc_aware()
        test_create_session_rejects_nonpositive_duration(p)
    print("ALL ROUND 7 TESTS PASSED")
