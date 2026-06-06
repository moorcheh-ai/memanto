"""Memory backend implementations for benchmarking."""

from .base import BaseMemoryBackend, MemoryResult
from .memanto_backend import MemantoBackend

__all__ = ["BaseMemoryBackend", "MemoryResult", "MemantoBackend"]

# Optional backends (require extra dependencies)
try:
    from .mem0_backend import Mem0Backend
    __all__.append("Mem0Backend")
except ImportError:
    Mem0Backend = None  # type: ignore

def get_backend(name: str):
    """Get a backend by name."""
    from . import memanto_backend, mem0_backend
    backends = {
        "memanto": memanto_backend.MemantoBackend,
        "mem0": mem0_backend.Mem0Backend if Mem0Backend else None,
    }
    backend = backends.get(name)
    if backend is None:
        raise ValueError(f"Unknown backend: {name}")
    return backend