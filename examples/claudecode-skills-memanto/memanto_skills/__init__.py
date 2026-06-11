"""Cross-session engineering memory for Claude Code + mattpocock/skills.

Memanto becomes a global, active memory companion across skill executions.
Three real Claude Code lifecycle hooks make it work without manual effort:

* ``SessionStart``     -> inject the accumulated Engineering Profile once.
* ``UserPromptSubmit`` -> recall memories relevant to the skill being invoked
                          and inject them before Claude reads the prompt.
* ``Stop``             -> distill the just-finished session into typed memories
                          using Memanto's backend LLM, then persist them.

The public surface is intentionally tiny:

    from memanto_skills import SkillMemory

    mem = SkillMemory()              # reads MOORCHEH_API_KEY + MEMANTO_AGENT_ID
    block = mem.recall_for_skill("tdd", task_hint="auth module")
    mem.distill_and_store("tdd", transcript)
"""

from __future__ import annotations

from .client import SkillMemory
from .config import SkillsConfig
from .profile import MemoryProfile

__all__ = ["SkillMemory", "SkillsConfig", "MemoryProfile"]
__version__ = "0.1.0"
