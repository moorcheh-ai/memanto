"""
MEMANTO Core Architecture - Namespace Strategy & Memory Records
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints, field_validator

from memanto.app.constants import (
    MemoryType,
    ProvenanceType,
    StatusType,
)

MemoryTag = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
]
BoundedTags = Annotated[list[MemoryTag], Field(max_length=20)]

BoundedSourceRef = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=512)
]

# Who wrote the memory: "user", "agent", "cursor", "codex", "claude_code",
# "mem0", ... Deliberately open so every writer is identifiable in recall and
# in the UI, but bounded to the Moorcheh filter-token charset so that
# `#source:<value>` stays a usable observability filter — a space or a '#' in
# the label would corrupt the query syntax it is embedded in.
SOURCE_MAX_LENGTH = 64
SOURCE_PATTERN = r"^[A-Za-z0-9._-]+$"

MemorySource = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=SOURCE_MAX_LENGTH,
        pattern=SOURCE_PATTERN,
    ),
]

_SOURCE_RE = re.compile(SOURCE_PATTERN)

# Why a memory was expired: a policy rule name, "manual", or
# "conflict-resolution". Bounded to the same filter-token charset as
# ``MemorySource`` so `#expired_by:<value>` stays a usable Moorcheh filter.
EXPIRED_BY_MAX_LENGTH = 64
EXPIRED_BY_PATTERN = SOURCE_PATTERN

BoundedExpiredBy = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=EXPIRED_BY_MAX_LENGTH,
        pattern=EXPIRED_BY_PATTERN,
    ),
]


def is_valid_source(value: Any) -> bool:
    """Return True when *value* is a source label ``MemorySource`` accepts."""
    if not isinstance(value, str):
        return False
    token = value.strip()
    return bool(_SOURCE_RE.fullmatch(token)) and len(token) <= SOURCE_MAX_LENGTH


def is_valid_expired_by(value: Any) -> bool:
    """Return True when *value* is a reason label ``BoundedExpiredBy`` accepts."""
    if not isinstance(value, str):
        return False
    token = value.strip()
    return bool(_SOURCE_RE.fullmatch(token)) and len(token) <= EXPIRED_BY_MAX_LENGTH


def agent_namespace(agent_id: str) -> str:
    """Map an agent_id to its Moorcheh namespace: memanto_agent_{agent_id}."""
    return f"memanto_agent_{agent_id}"


class MemoryRecord(BaseModel):
    """Structured memory record with standardized format"""

    # Core fields
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: MemoryType | None = None
    title: str = Field(max_length=100)
    content: str = Field(max_length=10000)

    @field_validator("title", mode="before")
    @classmethod
    def _normalize_title_newlines(cls, value: Any) -> Any:
        """Collapse line breaks in titles to single spaces.

        Titles are single-line labels: the serialized document format is
        ``[TYPE] title\\n\\ncontent``, so a newline inside the title corrupts
        the title/content boundary on readback (the ``[TYPE]`` prefix leaks
        into the recalled title and compounds on every update). Newline titles
        arrive from any caller, including the derived-title fallback that
        slices multi-line content.
        """
        if isinstance(value, str) and ("\n" in value or "\r" in value):
            return re.sub(r"[ \t]*[\r\n]+[ \t]*", " ", value).strip()
        return value

    # Metadata fields
    agent_id: str
    actor_id: str
    source: MemorySource
    source_ref: BoundedSourceRef | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    status: StatusType = "active"
    tags: BoundedTags = Field(default_factory=list)

    # Provenance
    provenance: ProvenanceType = "explicit_statement"

    # Timestamps (auto-populated by server)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Expiry stamp. Both are set together when a memory moves to `expired` and
    # cleared together on restore, so `status == "expired"` always carries a
    # when and a why. ``expired_by`` names the cause: a policy rule name,
    # ``manual``, or ``conflict-resolution``.
    expired_at: datetime | None = None
    expired_by: BoundedExpiredBy | None = None

    def to_moorcheh_document(self) -> dict[str, Any]:
        """
        Convert to Moorcheh document format with flat metadata fields.

        Moorcheh stores metadata as flat fields on the document, which enables
        powerful filtering using the # syntax (e.g., #memory_type:fact #confidence>0.8)
        """
        memory_type = self.type or "fact"

        # Format text as standardized card for semantic search
        text = f"[{memory_type.upper()}] {self.title}\n\n{self.content}"
        if self.tags:
            text += f"\n\nTags: {', '.join(self.tags)}"

        # Build document with flat metadata fields (not nested!)
        document = {
            "id": self.id,
            "text": text,
            # Metadata fields (flat structure for Moorcheh filtering)
            "memory_type": memory_type,
            "agent_id": self.agent_id,
            "actor_id": self.actor_id,
            "source": self.source,
            "confidence": self.confidence,
            "status": self.status,
            # Provenance
            "provenance": self.provenance,
            # Timestamps
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

        # Add optional fields only if present
        if self.source_ref:
            document["source_ref"] = self.source_ref
        if self.tags:
            document["tags"] = ",".join(self.tags)  # Comma-separated for filtering
        if self.expired_at:
            if isinstance(self.expired_at, datetime):
                document["expired_at"] = self.expired_at.isoformat()
            else:
                document["expired_at"] = str(self.expired_at)
        if self.expired_by:
            document["expired_by"] = self.expired_by

        return document

    def namespace(self) -> str:
        """The Moorcheh namespace this memory belongs to."""
        return agent_namespace(self.agent_id)

    def expire(self, reason: str, when: datetime | None = None) -> None:
        """Mark this memory expired, stamping when it happened and why."""
        self.status = "expired"
        self.expired_at = when or datetime.now(timezone.utc)
        self.expired_by = reason

    def restore(self) -> None:
        """Return this memory to the active state, clearing the expiry stamp."""
        self.status = "active"
        self.expired_at = None
        self.expired_by = None
