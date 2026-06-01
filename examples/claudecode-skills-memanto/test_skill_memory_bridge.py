from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from skill_memory_bridge import (
    LocalJsonlBackend,
    MemantoCliBackend,
    MemoryRecord,
    SkillMemoryBridge,
)


def test_mid_session_decision_is_recalled_by_later_skill(tmp_path: Path) -> None:
    """Later skills receive decisions captured during an earlier skill."""
    bridge = SkillMemoryBridge(
        LocalJsonlBackend(tmp_path / "memory.jsonl"),
        project_slug="checkout-service",
    )

    first = bridge.begin_skill(
        "/grill-with-docs",
        "Choose payment retry behavior.",
        cwd="/repo/checkout-service",
        files=["src/payments/capture.ts"],
    )
    bridge.record_event(
        first,
        "decision",
        "Use idempotency keys around payment capture because retries can double-charge.",
        files=["src/payments/capture.ts"],
        tags=["payments"],
        confidence=0.95,
    )
    bridge.end_skill(first, "Payment retry policy selected.")

    second = bridge.begin_skill(
        "/tdd",
        "Write payment capture tests.",
        cwd="/repo/checkout-service",
        files=["tests/payments/capture.test.ts"],
    )

    context = bridge.context_block(second)
    assert "idempotency keys" in context
    assert "double-charge" in context
    assert "[decision]" in context


def test_unimportant_tool_output_is_not_stored(tmp_path: Path) -> None:
    """Low-signal tool output is ignored while the run summary is retained."""
    backend = LocalJsonlBackend(tmp_path / "memory.jsonl")
    bridge = SkillMemoryBridge(backend, project_slug="docs")

    run = bridge.begin_skill("/handoff", "Summarize docs work.", cwd="/repo/docs")
    bridge.record_event(run, "tool_output", "3 files scanned.")
    memories = bridge.end_skill(run, "No reusable decisions.")

    assert len(memories) == 1
    assert memories[0].memory_type == "artifact"
    assert backend.recall("3 files scanned") == []


def test_context_block_reports_empty_memory(tmp_path: Path) -> None:
    """The context block is explicit when there are no recalled memories."""
    bridge = SkillMemoryBridge(
        LocalJsonlBackend(tmp_path / "memory.jsonl"),
        project_slug="empty",
    )

    run = bridge.begin_skill("/tdd", "Start clean.", cwd="/repo/empty")

    assert bridge.context_block(run) == (
        "MEMANTO_CONTEXT: no relevant cross-session memories found."
    )


def test_memanto_cli_backend_uses_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI adapter forwards configured timeouts to remember and recall."""
    calls: list[dict[str, Any]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        """Record subprocess calls without invoking the real Memanto CLI."""
        calls.append({"command": command, **kwargs})
        return subprocess.CompletedProcess(command, 0, stdout="memory", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    backend = MemantoCliBackend(timeout_seconds=2.5)

    backend.remember(
        MemoryRecord(memory_type="decision", title="Choice", content="Use JSONL.")
    )
    backend.recall("JSONL", limit=1)

    assert calls[0]["timeout"] == 2.5
    assert calls[1]["timeout"] == 2.5


def test_memanto_cli_backend_converts_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recall timeouts are converted into a backend-neutral TimeoutError."""
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        """Simulate a recall command that exceeds its timeout."""
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run)
    backend = MemantoCliBackend(timeout_seconds=1.0)

    with pytest.raises(TimeoutError, match="memanto recall timed out"):
        backend.recall("anything")


def test_memanto_cli_backend_converts_remember_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Remember timeouts are converted into a backend-neutral TimeoutError."""
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        """Simulate a remember command that exceeds its timeout."""
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run)
    backend = MemantoCliBackend(timeout_seconds=1.0)

    with pytest.raises(TimeoutError, match="memanto remember timed out after 1.0s"):
        backend.remember(
            MemoryRecord(memory_type="decision", title="Choice", content="Use JSONL.")
        )
