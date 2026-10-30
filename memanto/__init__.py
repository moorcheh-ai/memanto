"""
Memanto - Memory that AI Agents Love!
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from memanto.app.services.conversation_memory_extraction_service import (
        NothingToExtractError,
    )
    from memanto.client import Memanto

__all__ = ["Memanto", "NothingToExtractError"]


def __getattr__(name: str) -> Any:
    # Lazy so `import memanto` (and the CLI startup path) stays fast.
    if name == "Memanto":
        from memanto.client import Memanto

        return Memanto
    if name == "NothingToExtractError":
        from memanto.app.services.conversation_memory_extraction_service import (
            NothingToExtractError,
        )

        return NothingToExtractError
    raise AttributeError(f"module 'memanto' has no attribute {name!r}")
