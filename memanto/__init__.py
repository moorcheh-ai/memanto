"""Memanto - Memory that AI Agents Love!"""

__version__ = "0.1.0"

# Import key classes for easy access
from memanto.core import Memanto
from memanto.config import Config
from memanto.exceptions import MemantoError, ConfigurationError, APIError

__all__ = [
    "Memanto",
    "Config", 
    "MemantoError",
    "ConfigurationError",
    "APIError",
]
