"""
Session Models for MEMANTO

Defines session-based authentication models for the new architecture.
Replaces tenant_id with Moorcheh API key-based identity.
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from memanto.app.utils.temporal_helpers import as_utc_naive, utc_now


class SessionStatus(str, Enum):
    """Session status enum"""

    ACTIVE = "active"
    EXPIRED = "expired"
    TERMINATED = "terminated"


class AgentPattern(str, Enum):
    """Agent pattern types for memory organization"""

    SUPPORT = "support"
    PROJECT = "project"
    TOOL = "tool"


class SessionCreate(BaseModel):
    """Request to create/activate a session"""

    agent_id: str = Field(..., description="Agent identifier")
    duration_hours: int | None = Field(
        default=None,
        description="Session duration in hours (default: from server config)",
    )


class SessionToken(BaseModel):
    """JWT token payload structure"""

    agent_id: str
    namespace: str
    session_id: str
    started_at: datetime
    expires_at: datetime


class Session(BaseModel):
    """Active session information"""

    session_id: str
    session_token: str
    agent_id: str
    namespace: str
    started_at: datetime
    expires_at: datetime
    pattern: AgentPattern | None = None
    status: SessionStatus = SessionStatus.ACTIVE
    metadata: dict[str, Any] | None = None

    def is_expired(self) -> bool:
        """Check if session is expired"""
        return utc_now() > as_utc_naive(self.expires_at)

    def is_active(self) -> bool:
        """Check if session is active"""
        return self.status == SessionStatus.ACTIVE and not self.is_expired()

    def time_remaining(self) -> timedelta:
        """Get time remaining in session"""
        return as_utc_naive(self.expires_at) - utc_now()


class SessionInfo(BaseModel):
    """Session information response"""

    session_id: str
    agent_id: str
    namespace: str
    started_at: datetime
    expires_at: datetime
    status: SessionStatus
    time_remaining_seconds: int
    pattern: AgentPattern | None = None


class SessionSummary(BaseModel):
    """Summary of ended session"""

    session_id: str
    agent_id: str
    started_at: datetime
    ended_at: datetime
    duration_hours: float
    memories_created: int
    summary_memory_id: str | None = None


class AgentCreate(BaseModel):
    """Request to create a new agent"""

    agent_id: str = Field(
        ...,
        description="Unique agent identifier (alphanumeric, hyphens, underscores)",
        pattern=r"^[a-zA-Z0-9_-]+$",
    )
    pattern: AgentPattern = Field(
        default=AgentPattern.SUPPORT,
        description="Agent pattern for memory organization",
    )
    description: str | None = Field(
        None, description="Human-readable description of the agent"
    )


class AgentInfo(BaseModel):
    """Agent information"""

    agent_id: str
    namespace: str
    pattern: AgentPattern
    description: str | None = None
    created_at: datetime
    last_session: datetime | None = None
    memory_count: int = 0
    session_count: int = 0
    status: str = "inactive"


class AgentList(BaseModel):
    """List of agents"""

    agents: list[AgentInfo]
    count: int
