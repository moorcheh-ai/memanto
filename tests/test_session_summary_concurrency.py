"""Concurrency regressions for local session-summary persistence."""

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
        entry = (
            f"### [2026-07-20 12:00:0{index}] [FACT] concurrent-{index}\n"
            f"- **Memory ID**: `mem-{index}`\n"
            "- **Confidence**: `0.8`\n"
            "- **Status**: `active`\n"
            "- **Source**: `agent`\n"
            "- **Provenance**: `explicit_statement`\n"
            "- **Content**:\n"
            f"> payload-{index}\n\n"
            "---\n\n"
        )
        assert summary.count(entry) == 1
