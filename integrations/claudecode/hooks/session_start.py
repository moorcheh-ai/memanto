#!/usr/bin/env python3
"""SessionStart hook — brief Claude with the accumulated Engineering Profile.

Fires once when a session starts/resumes. Injects a compact snapshot of the
developer's most recent engineering memories so every session begins already
aware of established conventions — not just sessions that invoke a skill.

Registered for command hooks (the only type SessionStart supports).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    emit_additional_context,
    get_memory,
    memory_enabled,
    run,
)

EVENT = "SessionStart"


def main() -> int:
    """Recall the Engineering Profile and emit it as SessionStart context.

    Exits 0 silently when ``MOORCHEH_API_KEY`` is unset or the SDK cannot be
    initialised, so Claude Code is never blocked by this hook.
    """
    if not memory_enabled():
        return 0
    mem = get_memory()
    if mem is None:
        return 0
    emit_additional_context(EVENT, mem.profile_block())
    return 0


if __name__ == "__main__":
    run(main)
