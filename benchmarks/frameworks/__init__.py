"""Memory framework adapters for benchmarking."""

from typing import Dict, Type
from .base import BaseFramework
from .memanto_framework import MemantoFramework

# Optional frameworks - only import if dependencies available
try:
    from .mem0_framework import Mem0Framework
except ImportError:
    Mem0Framework = None  # type: ignore

__all__ = ["BaseFramework", "MemantoFramework", "Mem0Framework", "get_framework"]


def get_framework(name: str) -> Type[BaseFramework]:
    """Get a framework class by name."""
    frameworks: Dict[str, Type[BaseFramework]] = {
        "memanto": MemantoFramework,
    }
    if Mem0Framework is not None:
        frameworks["mem0"] = Mem0Framework  # type: ignore
    
    if name not in frameworks:
        raise ValueError(f"Unknown framework: {name}. Available: {list(frameworks.keys())}")
    return frameworks[name]