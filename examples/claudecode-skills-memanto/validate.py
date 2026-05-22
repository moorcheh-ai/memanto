from __future__ import annotations

import os
import tempfile
from pathlib import Path

from skill_memory_bridge import JsonlMemoryBackend, SkillMemoryBridge


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "skills.jsonl"
        bridge = SkillMemoryBridge(
            JsonlMemoryBackend(store), source="claude_code_skills_validate"
        )
        first = bridge.after_skill(
            skill="grill-with-docs",
            task="Review checkout flow",
            cwd="demo-shop",
            transcript=(
                "Decision: use server actions for checkout mutations.\n"
                "Instruction: keep payment tokens out of browser code.\n"
                "Preference: write focused Playwright smoke tests."
            ),
        )
        context = bridge.before_skill(
            skill="tdd",
            task="Add checkout tests",
            cwd="demo-shop",
        )
        assert first == 3
        assert "server actions" in context
        assert "payment tokens" in context
        assert os.environ["MEMANTO_SKILL_CONTEXT"] == context
    print("credential_free_validation=passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
