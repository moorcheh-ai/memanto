"""Concurrency regressions for local session-summary persistence."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier, BrokenBarrierError

from memanto.app.core import MemoryRecord
from memanto.app.services.session_service import SessionService


def test_concurrent_summary_writes_create_one_header(monkeypatch, tmp_path):
    """Concurrent API workers must not race first-write header creation."""
    service = SessionService(
        secret_key="test-secret-key-min-32-bytes-1234",
        sessions_dir=tmp_path / "sessions",
    )
    service._harden_session_storage()
    worker_count = 8
    first_exists_checks = Barrier(worker_count)
    original_exists = Path.exists

    def synchronize_initial_absence_check(path):
        exists = original_exists(path)
        if path.name.endswith("_summary.md") and not exists:
            try:
                first_exists_checks.wait(timeout=0.5)
            except BrokenBarrierError:
                # The barrier only widens the race window so the test is more
                # likely to catch duplicate headers. If it times out or breaks,
                # continue with the real exists() result rather than failing.
                pass
        return exists

    monkeypatch.setattr(Path, "exists", synchronize_initial_absence_check)

    def log_memory(index):
        # created_at mirrors a write happening "now": summary files are
        # archived by WRITE time (see session_service), so a fixed past
        # created_at would land this entry in a different (historical) file
        # and the concurrency assertions below could never observe it.
        now = datetime.now(timezone.utc)
        record = MemoryRecord(
            type="fact",
            title=f"concurrent-{index}",
            content=f"payload-{index}",
            agent_id="agent-race",
            actor_id="agent-race",
            source="agent",
            created_at=now.replace(microsecond=0),
        )
        service.log_memory_to_session_summary(
            agent_id="agent-race",
            session_id="sess-race",
            memory_record=record,
            memory_id=f"mem-{index}",
        )

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        list(executor.map(log_memory, range(worker_count)))

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    summary_file = service.sessions_dir / f"agent-race_{today}_sess-race_summary.md"
    summary = summary_file.read_text(encoding="utf-8")

    assert summary.count("# Session Summary for agent-race") == 1
    for index in range(worker_count):
        # The header's timestamp is the write time (runtime-dependent), so
        # assert on the stable parts of each entry instead.
        assert summary.count(f"- **Memory ID**: `mem-{index}`") == 1
        assert summary.count(f"> payload-{index}") == 1
