"""
Memanto - Memory that AI Agents Love!
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from memanto.client import Memanto

__all__ = ["Memanto"]


def __getattr__(name: str) -> Any:
    # Lazy so `import memanto` (and the CLI startup path) stays fast.
    if name == "Memanto":
        from memanto.client import Memanto

        return Memanto
    raise AttributeError(f"module 'memanto' has no attribute {name!r}")
