"""
ID Generation Utilities
"""

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
    """Validate memory ID format.
    
    Accepts alphanumeric characters, hyphens, and underscores.
    Minimum length: 4 characters.
    Consistent with SafeDeletion._is_valid_memory_id().
    """
    if not memory_id or len(memory_id) < 4:
        return False
    import re
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', memory_id))
