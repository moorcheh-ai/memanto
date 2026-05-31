from __future__ import annotations

from pathlib import Path

from skill_memory_bridge import LocalJsonlBackend, SkillMemoryBridge


def test_mid_session_decision_is_recalled_by_later_skill(tmp_path: Path) -> None:
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
    backend = LocalJsonlBackend(tmp_path / "memory.jsonl")
    bridge = SkillMemoryBridge(backend, project_slug="docs")

    run = bridge.begin_skill("/handoff", "Summarize docs work.", cwd="/repo/docs")
    bridge.record_event(run, "tool_output", "3 files scanned.")
    memories = bridge.end_skill(run, "No reusable decisions.")

    assert len(memories) == 1
    assert memories[0].memory_type == "artifact"
    assert backend.recall("3 files scanned") == []


def test_context_block_reports_empty_memory(tmp_path: Path) -> None:
    bridge = SkillMemoryBridge(
        LocalJsonlBackend(tmp_path / "memory.jsonl"),
        project_slug="empty",
    )

    run = bridge.begin_skill("/tdd", "Start clean.", cwd="/repo/empty")

    assert bridge.context_block(run) == (
        "MEMANTO_CONTEXT: no relevant cross-session memories found."
    )
