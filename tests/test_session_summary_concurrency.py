"""Concurrency regressions for local session summaries."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
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
    worker_count = 8
    first_exists_checks = Barrier(worker_count)
    original_exists = Path.exists

    def synchronize_initial_absence_check(path):
        exists = original_exists(path)
        if path.name.endswith("_summary.md") and not exists:
            try:
                first_exists_checks.wait(timeout=0.1)
            except BrokenBarrierError:
                pass
        return exists

    monkeypatch.setattr(Path, "exists", synchronize_initial_absence_check)

    def log_memory(index):
        record = MemoryRecord(
            type="fact",
            title=f"concurrent-{index}",
            content=f"payload-{index}",
            agent_id="agent-race",
            actor_id="agent-race",
            source="agent",
            created_at=datetime(2026, 7, 20, 12, 0, index),
        )
        service.log_memory_to_session_summary(
            agent_id="agent-race",
            session_id="sess-race",
            memory_record=record,
            memory_id=f"mem-{index}",
        )

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        list(executor.map(log_memory, range(worker_count)))

    summary_file = service.sessions_dir / "agent-race_2026-07-20_sess-race_summary.md"
    summary = summary_file.read_text(encoding="utf-8")

    assert summary.count("# Session Summary for agent-race") == 1
    for index in range(worker_count):
        assert summary.count(f"### [2026-07-20 12:00:0{index}]") == 1
        assert summary.count(f"`mem-{index}`") == 1
