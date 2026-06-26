"""
Memanto - Your agents focus. Memanto remembers.
"""Memanto - A companion memory agent with persistent memory for AI agents."""

from memanto.client import MemantoClient
from memanto.config import Config
from memanto.memory import Memory
from memanto.errors import MemantoError, AuthenticationError, ConfigurationError

__all__ = [
    "MemantoClient",
    "Config",
    "Memory",
    "MemantoError",
    "AuthenticationError",
    "ConfigurationError",
]
"""
