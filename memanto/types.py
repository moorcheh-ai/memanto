from enum import Enum
from typing import Literal

KNOWN_SOURCE_TYPES = frozenset(["user", "agent", "tool", "system"])

class SourceType(str, Enum):
    USER = "user"
    AGENT = "agent"
    TOOL = "tool"
    SYSTEM = "system"

    @classmethod
    def validate(cls, value: str) -> Literal["user", "agent", "tool", "system"]:
        """
        Validate the source type.

        Args:
            value: The source type to validate.

        Returns:
            The validated source type.

        Raises:
            ValueError: If the source type is not recognized.
        """
        if value not in KNOWN_SOURCE_TYPES:
            raise ValueError(f"Unknown source type '{value}'. Must be one of {KNOWN_SOURCE_TYPES}.")
        return value