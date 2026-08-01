"""
ID Generation Utilities
"""

import re
import time
import uuid


def generate_id() -> str:
    """Generate generic unique ID"""
    return uuid.uuid4().hex[:12]


def generate_memory_id(prefix: str = "mem") -> str:
    """Generate deterministic memory ID"""
    return f"{prefix}_{generate_id()}"


def generate_ulid() -> str:
    """Generate ULID (Universally Unique Lexicographically Sortable Identifier)"""
    # Simplified ULID implementation
    timestamp = int(time.time() * 1000)  # milliseconds
    random_part = uuid.uuid4().hex[:10]
    return f"{timestamp:013x}{random_part}"


def generate_session_id() -> str:
    """Generate session ID"""
    return f"s_{uuid.uuid4().hex[:8]}"


def is_valid_memory_id(memory_id: str) -> bool:
    """Validate memory ID format using strict pattern.

    Only allows alphanumeric characters, hyphens, and underscores.
    Requires minimum length of 5 characters.
    Must contain at least one underscore (to separate prefix from random part).
    """
    if not memory_id or len(memory_id) < 5:
        return False
    if "_" not in memory_id:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_-]+", memory_id))
