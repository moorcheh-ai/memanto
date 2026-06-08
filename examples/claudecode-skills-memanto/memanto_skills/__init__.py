"""
memanto_skills — Cross-session memory layer for mattpocock/skills + Claude Code.

Exposes the public API:
    MemantoSkillsClient  — lifecycle + recall/remember primitives
    MemoryProfile        — the persisted engineering profile
    format_context_block — format recalled memories for skill injection
"""

from .client import MemantoSkillsClient
from .profile import MemoryProfile
from .utils import format_context_block

__all__ = ["MemantoSkillsClient", "MemoryProfile", "format_context_block"]
