#!/usr/bin/env python3
"""UserPromptSubmit hook — dynamic injection before a skill runs.

Fires when the developer submits a prompt, before Claude processes it. If the
prompt invokes a skill (``/tdd``, ``/grill-with-docs``, …), we recall the
memories most relevant to that skill and inject them as ``additionalContext``
so Claude honours past decisions instead of re-asking.

This is what makes the layer *zero-touch*: it works on the real, unmodified
mattpocock skills — no forked ``-with-memory`` variants required.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    detect_skill,
    emit_additional_context,
    get_memory,
    memory_enabled,
    read_hook_input,
    run,
)

EVENT = "UserPromptSubmit"


def main() -> int:
    """Detect the invoked skill and inject its relevant memories as context.

    Reads the ``UserPromptSubmit`` payload from stdin, routes by skill, and
    emits an ``additionalContext`` block. Bare prompts are skipped to avoid
    polluting every turn.
    """
    if not memory_enabled():
        return 0

    data = read_hook_input()
    prompt = data.get("prompt", "") or ""
    skill = detect_skill(prompt)

    # Only inject when a skill is invoked. Bare prompts are left untouched so we
    # don't pollute every turn — SessionStart already provides the baseline
    # profile once per session.
    if not skill:
        return 0

    mem = get_memory()
    if mem is None:
        return 0

    profile = mem.recall_for_skill(skill, task_hint=prompt)
    emit_additional_context(EVENT, profile.format_context_block(skill_name=skill))
    return 0


if __name__ == "__main__":
    run(main)
