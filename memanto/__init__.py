"""
Memanto - Memory that AI Agents Love!
"""Memanto - Memory that AI Agents Love!

A companion memory agent that lets your agents focus and improve while you
keep ownership of everything they learn.
"""

__version__ = "0.1.0"

from memanto.core import Memanto
from memanto.types import Memory, MemoryQuery, MemoryResult

__all__ = ["Memanto", "Memory", "MemoryQuery", "MemoryResult"]

# Re-export main classes for convenience
from memanto import core, types, utils, errors
"""
