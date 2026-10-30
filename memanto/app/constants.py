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
# A memory is `active` until an expiry policy, a conflict resolution, or an
# explicit `memanto memory expire` stamps it `expired`. Expiry is reversible
# (`restore`); hard deletion is a separate, destructive operation.
StatusType = Literal["active", "expired"]

VALID_STATUS_TYPES = {"active", "expired"}

# Recall status filters: `all` returns both states, labelled.
StatusFilter = Literal["all", "active", "expired"]

# Provenance Types
ProvenanceType = Literal[
    "explicit_statement",
    "inferred",
    "corrected",
    "validated",
    "observed",
    "imported",
]

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

# Directive/override shapes used to detect prompt-injection payloads.
# Shared by memory extraction and tag validation so every write path enforces
# the same rule set. Patterns are matched against lowercased text (they are
# compiled with re.IGNORECASE as well).
INJECTION_PATTERNS = (
    r"\bignore\s+previous\s+instructions\b",
    r"\bignore\s+prior\s+instructions\b",
    r"\bsystem\s+override\b",
    r"^system:\s*",
    r"\bexfiltrate\b",
    r"\bsend\s+all\s+memories\b",
    r"\boverride\s+previous\b",
    r"\bdisregard\s+previous\b",
)

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
