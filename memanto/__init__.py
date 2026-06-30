"""
Memanto - Memory that AI Agents Love!
"""Memanto - Memory that AI Agents Love!

A companion memory agent that lets your agents focus and improve while you
keep ownership of everything they learn.
"""

from memanto.client import MemantoClient
from memanto.config import MemantoConfig
from memanto.exceptions import MemantoError, AuthenticationError, RateLimitError

__all__ = [
    "MemantoClient",
    "MemantoConfig", 
    "MemantoError",
    "AuthenticationError",
    "RateLimitError",
]
"""
