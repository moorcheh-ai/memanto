"""
Memanto - Memory that AI Agents Love!
"""Memanto - Memory that AI Agents Love!

A companion memory agent that lets your agents focus and improve while you
keep ownership of everything they learn.
"""

__version__ = "0.1.0"

from memanto.core import Memory, MemoryConfig
from memanto.errors import MemantoError, APIError, AuthenticationError

__all__ = ["Memory", "MemoryConfig", "MemantoError", "APIError", "AuthenticationError"]


def get_version() -> str:
    return __version__
"""
