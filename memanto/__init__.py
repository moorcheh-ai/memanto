"""
Memanto - Your agents focus. Memanto remembers.
"""Memanto - A companion memory agent with its own intelligence.

This package provides persistent memory capabilities for AI agents,
backed by the moorcheh.ai retrieval engine.
"""

from memanto.client import MemantoClient
from memanto.memory import MemoryManager
from memanto.config import Config

__all__ = [
    "MemantoClient",
    "MemoryManager", 
    "Config",
]
"""
