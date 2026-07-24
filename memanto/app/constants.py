from typing import Literal

# Memory Types
MemoryType = Literal[
    "fact",
    "preference",
    "goal",
    "decision",
    "artifact",
    "learning",
    "event",
    "instruction",
    "relationship",
    "context",
    "observation",
    "commitment",
    "error",
]

# Source Types — validated set of known sources.
# Arbitrary strings are still accepted for forward compatibility with custom
# agent names, but a validation helper is provided to warn on unknowns.
KNOWN_SOURCE_TYPES = frozenset({"user", "agent", "tool", "system"})
SourceType = str  # Runtime type remains str for backward compat


def is_known_source_type(source: str) -> bool:
    """Check whether source is a recognized source type.

    Custom agent names (e.g. 'agent_hermes') are valid but not in the known set.
    Returns True for known types, False for unrecognized strings.
    """
    return source in KNOWN_SOURCE_TYPES or source.startswith("agent_")

# Status Types
StatusType = Literal["active", "superseded", "deleted", "provisional"]

# Provenance Types
ProvenanceType = Literal[
    "explicit_statement",
    "inferred",
    "corrected",
    "validated",
    "observed",
    "imported",
]

# Validation Modes
ValidationMode = Literal["strict", "lenient", "off"]

# Actor Types
ActorType = Literal["user", "agent", "system"]

# Source Enumerations for Provenance
ProvenanceSource = Literal["user", "agent", "tool", "system"]

# Valid Lists for runtime checks
VALID_MEMORY_TYPES = {
    "fact",
    "preference",
    "goal",
    "decision",
    "artifact",
    "learning",
    "event",
    "instruction",
    "relationship",
    "context",
    "observation",
    "commitment",
    "error",
}

VALID_PROVENANCE_TYPES = {
    "explicit_statement",
    "inferred",
    "corrected",
    "validated",
    "observed",
    "imported",
}

ALLOWED_UPDATE_FIELDS = {
    "title",
    "content",
    "type",
    "confidence",
    "tags",
    "source",
}

VALID_PATTERNS = {"support", "project", "tool"}
