"""
Memanto - Memory that AI Agents Love!
"""Memanto - Memory that AI Agents Love!"""

from memanto.core.agent import MemantoAgent
from memanto.core.memory import MemoryStore
from memanto.core.recall import ContextInjector
from memanto.integrations.skills import SkillIntegration

__version__ = "0.1.0"

__all__ = [
    "MemantoAgent",
    "MemoryStore", 
    "ContextInjector",
    "SkillIntegration",
]
"""
