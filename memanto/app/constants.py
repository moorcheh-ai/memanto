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
# Open by design: a source names *who wrote the memory* — "user", "agent",
# "cursor", "codex", "claude_code", "mem0", any integration or MCP client — so
# recall can be attributed and filtered per writer. This lenient alias is for
# reading back stored records; writes go through ``core.MemorySource``, which
# bounds the label so it stays a valid `#source:<value>` filter token.
SourceType = str

# Status Types
StatusType = Literal["active"]

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

# Trust fields removed from the schema. Must not be resurrected during update.
REMOVED_TRUST_FIELDS = frozenset(
    {
        "superseded_by",
        "supersedes",
        "validated_at",
        "validation_count",
        "contradiction_detected",
    }
)
