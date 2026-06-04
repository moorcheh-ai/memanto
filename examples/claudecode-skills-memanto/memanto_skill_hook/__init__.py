"""
Memanto Skill Hook — Cross-Skill Memory for mattpocock/skills Workflow

This module provides a lightweight integration layer between the
mattpocock/skills developer workflow and Memanto's persistent memory.

Instead of treating each skill invocation (/grill-with-docs, /tdd, /handoff)
as an isolated event, the hook:

  1. On skill start: queries Memanto for memories relevant to the current
     file path or task, and returns them as a context string to inject.
  2. On skill complete: passes the interaction summary to Memanto so its
     backend LLM can update the developer's "Engineering Profile".

Usage as a library:

    from memanto_skill_hook import SkillMemory

    mem = SkillMemory()

    # Before running a skill — get relevant context
    context = mem.on_skill_start(
        skill_name="/tdd",
        file_path="src/api/routes.ts",
        task_description="Write tests for the new user endpoint",
    )
    print(context)  # inject into your prompt

    # After running a skill — distill and store learnings
    mem.on_skill_complete(
        skill_name="/tdd",
        summary="Wrote 12 tests using Vitest. Preferred AAA pattern.
                 Discovered that the auth middleware must be mocked.",
        file_path="src/api/routes.ts",
    )

Usage via CLI wrapper (for terminal scripts):

    # Before skill
    python -m memanto_skill_hook pre --skill /tdd --file src/api/routes.ts \
        --task "Write tests for the new user endpoint"

    # After skill
    python -m memanto_skill_hook post --skill /tdd \
        --file src/api/routes.ts \
        --summary "Wrote 12 tests using Vitest. Preferred AAA pattern."
"""

from memanto_skill_hook.memory import SkillMemory

__all__ = ["SkillMemory"]
__version__ = "0.1.0"
