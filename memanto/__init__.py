"""
Memanto - Your agents focus. Memanto remembers.
"""Memanto - A companion memory agent with persistent memory capabilities."""

from memanto.core import Memanto
from memanto.config import Config
from memanto.exceptions import (
    MemantoError,
    ConfigurationError,
    APIError,
    MemoryError,
)

__version__ = "0.1.0"

__all__ = ["Memanto", "Config", "MemantoError", "ConfigurationError", "APIError", "MemoryError"]

"""
