from __future__ import annotations

import tempfile
from pathlib import Path

from memanto_skill_memory.backends import LocalJsonlBackend
from memanto_skill_memory.hook import SkillMemoryBridge
from memanto_skill_memory.models import SkillEvent


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        bridge = SkillMemoryBridge(
            backend=LocalJsonlBackend(Path(tmpdir) / "memories.jsonl")
        )
        bridge.after_skill(
            SkillEvent(
                skill_name="grill-with-docs",
                prompt="Review service boundaries",
                transcript=(
                    "Decision: keep HTTP clients in src/services so components "
                    "stay framework-only."
                ),
                cwd="/demo",
            )
        )
        context = bridge.before_skill(
            SkillEvent(
                skill_name="tdd",
                prompt="Add a client test",
                transcript="",
                cwd="/demo",
            )
        )

    assert "HTTP clients in src/services" in context
    assert "Source: grill-with-docs" in context
    print("offline validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
