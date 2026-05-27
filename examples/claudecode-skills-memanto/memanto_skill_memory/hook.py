from __future__ import annotations

import os

from memanto_skill_memory.backends import MemoryBackend
from memanto_skill_memory.distill import HeuristicSkillDistiller
from memanto_skill_memory.models import MemoryCandidate, RecallResult, SkillEvent


class SkillMemoryBridge:
    """Pre/post lifecycle bridge that gives skills shared engineering memory."""

    def __init__(
        self,
        backend: MemoryBackend,
        distiller: HeuristicSkillDistiller | None = None,
    ) -> None:
        self.backend = backend
        self.distiller = distiller or HeuristicSkillDistiller()

    def before_skill(self, event: SkillEvent, limit: int = 5) -> str:
        query = " ".join([event.skill_name, event.prompt, event.cwd])
        recalled = self.backend.recall(query, limit=limit)
        context = format_recalled_context(recalled)
        os.environ["MEMANTO_SKILL_CONTEXT"] = context
        return context

    def after_skill(self, event: SkillEvent) -> list[MemoryCandidate]:
        memories = self.distiller.distill(event)
        if not memories:
            return []
        return self.backend.remember(memories, event)


def format_recalled_context(recalled: list[RecallResult]) -> str:
    if not recalled:
        return ""

    lines = [
        "## Memanto engineering memory",
        "",
        "Relevant prior decisions and constraints recalled before this skill run:",
    ]
    for result in recalled:
        memory = result.memory
        lines.append(
            f"- [{memory.memory_type}] {memory.title}: {memory.content} "
            f"(Source: {result.event.skill_name}, score: {result.score:.2f})"
        )
    return "\n".join(lines)
