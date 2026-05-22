"""Credential-free validation for the Claude Code skills Memanto example."""

from __future__ import annotations

import tempfile
from pathlib import Path

from mattpocock_adapter import install_wrappers
from skill_memory import LocalJsonlBackend, SkillMemoryBridge


def main() -> int:
    with tempfile.TemporaryDirectory() as raw_tmp:
        tmp = Path(raw_tmp)
        store = tmp / "memories.jsonl"
        backend = LocalJsonlBackend(store)
        bridge = SkillMemoryBridge(backend)

        transcript = "\n".join(
            [
                "decision: use a repository-local service layer for billing",
                "preference: keep React toolbars dense and keyboard-friendly",
                "instruction: run focused unit tests before broad integration tests",
            ]
        )
        stored = bridge.after_skill("/grill-with-docs", transcript, tmp / "repo")
        assert len(stored) == 3

        context = bridge.before_skill(
            "/tdd",
            "write billing service tests for React toolbar behavior",
            tmp / "repo",
        )
        assert "repository-local service layer" in context
        assert "focused unit tests" in context

        wrappers = install_wrappers(tmp / "bin", bridge_dir=Path(__file__).parent)
        assert {path.name for path in wrappers} == {"grill-with-docs", "tdd", "handoff"}

    print("claudecode-skills-memanto validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
