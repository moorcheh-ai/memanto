"""Memanto integration for mattpocock/skills developer workflow.

This module provides an integration layer that enables Memanto to act as a
global, active memory companion across different skill executions in the
mattpocock/skills ecosystem.
"""

from memanto.integrations.mattpocock_skills.integration import (
    MattpocockSkillsIntegration,
    SkillContext,
    SkillExecution,
    enable_memanto_skills,
)

__all__ = [
    "MattpocockSkillsIntegration",
    "SkillContext",
    "SkillExecution",
    "enable_memanto_skills",
]