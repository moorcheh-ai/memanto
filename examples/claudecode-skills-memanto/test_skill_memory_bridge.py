from __future__ import annotations

import sys
from pathlib import Path

from skill_memory_bridge import (
    LocalJsonlBackend,
    Memory,
    SkillMemoryBridge,
    TranscriptDistiller,
)


def test_local_backend_recalls_relevant_memory(tmp_path: Path) -> None:
    backend = LocalJsonlBackend(tmp_path / "memory.jsonl")
    backend.remember(Memory("Use repository-local adapters", tags=("tdd",)))
    backend.remember(Memory("Prefer unrelated frontend colors", tags=("ui",)))

    recalled = backend.recall("tdd adapter")

    assert [memory.content for memory in recalled] == ["Use repository-local adapters"]


def test_distiller_extracts_typed_engineering_memories() -> None:
    transcript = """
    Decision: Use a repository-local adapter.
    Must: Exercise the bridge without credentials.
    Avoid: Storing secrets or raw hidden prompts.
    """

    memories = TranscriptDistiller().distill("tdd", transcript)

    assert [memory.memory_type for memory in memories] == [
        "decision",
        "instruction",
        "instruction",
    ]
    assert "repository-local adapter" in memories[0].content
    assert all("tdd" in memory.tags for memory in memories)


def test_bridge_injects_previous_context_and_stores_new_memories(
    tmp_path: Path,
) -> None:
    backend = LocalJsonlBackend(tmp_path / "memory.jsonl")
    backend.remember(Memory("Use a repository-local adapter", tags=("tdd",)))
    bridge = SkillMemoryBridge(backend)

    status = bridge.run(
        "tdd",
        [
            sys.executable,
            str(Path(__file__).with_name("demo_skills.py")),
            "tdd",
        ],
        task="adapter tests",
    )

    assert status == 0
    stored = backend.recall("network credentials", limit=10)
    assert any("without network credentials" in memory.content for memory in stored)


def test_bridge_returns_child_exit_code(tmp_path: Path) -> None:
    backend = LocalJsonlBackend(tmp_path / "memory.jsonl")
    bridge = SkillMemoryBridge(backend)

    status = bridge.run("tdd", [sys.executable, "-c", "raise SystemExit(7)"])

    assert status == 7
