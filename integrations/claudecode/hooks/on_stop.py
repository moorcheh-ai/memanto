#!/usr/bin/env python3
"""Stop hook — active extraction after a skill session finishes.

Fires when Claude finishes responding. We read the conversation transcript,
detect which skill was used, and hand the session summary to Memanto's backend
LLM, which distills durable engineering memories and persists them. Future
sessions then inherit those decisions automatically.

Register this hook with ``"async": true`` so distillation runs in the
background and never delays the developer. It produces no output and never
blocks — on any failure it simply exits 0.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    get_memory,
    memory_enabled,
    read_hook_input,
    read_transcript_for_distillation,
    run,
)


def main() -> int:
    """Read the finished transcript and distill it into typed memories.

    Skips when ``stop_hook_active`` is set so the same session is never
    distilled twice on re-fires. Runs asynchronously and silently — failure
    paths exit 0 instead of surfacing errors to the developer.
    """
    if not memory_enabled():
        return 0

    data = read_hook_input()
    # When another Stop hook blocked and forced Claude to continue, the hook
    # fires again with stop_hook_active=true. Skip re-distilling the same
    # session so memories aren't stored twice.
    if data.get("stop_hook_active"):
        return 0

    # Single pass: finds the original /skill across the FULL transcript,
    # then returns only the tail for LLM distillation. This avoids tagging
    # long sessions as skill:unknown when the opening prompt has fallen
    # outside the truncation window.
    skill, transcript = read_transcript_for_distillation(data.get("transcript_path"))
    if not transcript:
        return 0

    mem = get_memory()
    if mem is None:
        return 0

    mem.distill_and_store(skill, transcript)
    return 0


if __name__ == "__main__":
    run(main)
