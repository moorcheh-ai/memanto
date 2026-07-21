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

# Source Types
# Source Types — the canonical built-in values.
# The type annotation remains ``str`` for backwards-compatibility with
# free-form agent names, but ``VALID_SOURCE_TYPES`` is the authoritative
# list of well-known values and should be used for validation.
SourceType = str  # e.g., "user", "agent", "tool", "system", or a specific agent name

# The well-known source values that routes/services should validate against.
# Custom agent names are still valid; this set covers the built-in ones.
KNOWN_SOURCE_TYPES: frozenset[str] = frozenset({
    "user",
    "agent",
    "tool",
    "system",
})

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
