"""
Memanto - Your agents focus. Memanto remembers.
"""Memanto - A companion memory agent with persistent memory for AI agents."""

from memanto.core import Memanto
from memanto.config import Config
from memanto.memory import Memory
from memanto.errors import MemantoError, ConfigurationError, APIError

__all__ = [
    "Memanto",
    "Config", 
    "Memory",
    "MemantoError",
    "ConfigurationError",
    "APIError",
]
"""
