"""
Session Service for MEMANTO

Handles session creation, validation, and management.
Uses JWT tokens for stateless authentication.
"""

import json
import logging
import os
from datetime import timedelta
from pathlib import Path
from typing import Any

import jwt
from pydantic import ValidationError

from memanto.app.config import get_data_dir, settings
from memanto.app.core import agent_namespace
from memanto.app.models.session import (
    AgentPattern,
    Session,
    SessionStatus,
    SessionSummary,
    SessionToken,
)
from memanto.app.utils.errors import (
    InvalidSessionTokenError,
    SessionExpiredError,
    SessionNotFoundError,
)
from memanto.app.utils.ids import generate_id
from memanto.app.utils.temporal_helpers import utc_now

_session_service = None
logger = logging.getLogger(__name__)


def get_session_service() -> "SessionService":
    """
    Shared SessionService singleton.

    Used by both FastAPI routes and CLI clients so they all share the
    same secret key and session storage configuration.
    """
    global _session_service
    if _session_service is None:
        _session_service = SessionService(secret_key=settings.MEMANTO_SECRET_KEY)
    return _session_service


class SessionService:
    """Service for managing sessions"""

    def __init__(self, secret_key: str | None = None, sessions_dir: Path | None = None):
        """
        Initialize session service

        Args:
            secret_key: Secret key for JWT signing (defaults to env var or generated)
            sessions_dir: Directory for session storage (defaults to ~/.memanto/sessions/)
        """
        resolved_secret_key = (
            secret_key
            or os.getenv("MEMANTO_SECRET_KEY")
            or "memanto-default-secret-change-in-production"
        )
        self.secret_key: str = resolved_secret_key
        self.sessions_dir = sessions_dir or get_data_dir() / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _generate_namespace(self, agent_id: str) -> str:
        """
        Generate the Moorcheh namespace for an agent.

        Format: memanto_agent_{agent_id}
        """
        return agent_namespace(agent_id)

    def _generate_session_id(self) -> str:
        """Generate unique session ID"""

        return f"sess_{generate_id()}"

    def create_session(
        self,
        agent_id: str,
        pattern: AgentPattern | None = None,
        duration_hours: int | None = None,
    ) -> Session:
        """
        Create a new session for an agent

        Args:
            agent_id: Agent identifier
            pattern: Agent pattern (support, project, tool)
            duration_hours: Session duration in hours

        Returns:
            Session object with JWT token
        """
        # Use config default if not explicitly provided
        if duration_hours is None:
            duration_hours = settings.SESSION_DEFAULT_DURATION_HOURS

        session_id = self._generate_session_id()
        namespace = self._generate_namespace(agent_id)
        started_at = utc_now()
        expires_at = started_at + timedelta(hours=duration_hours)

        # Create JWT payload
        token_payload = SessionToken(
            agent_id=agent_id,
            namespace=namespace,
            session_id=session_id,
            started_at=started_at,
            expires_at=expires_at,
        )

        # Generate JWT token
        session_token = jwt.encode(
            token_payload.model_dump(mode="json"), self.secret_key, algorithm="HS256"
        )

        # Create session object
        session = Session(
            session_id=session_id,
            session_token=session_token,
            agent_id=agent_id,
            namespace=namespace,
            started_at=started_at,
            expires_at=expires_at,
            pattern=pattern,
            status=SessionStatus.ACTIVE,
        )

        # Save session to file
        self._save_session(session)

        # Mark as active session
        self._set_active_session(agent_id)

        return session

    def validate_session(self, session_token: str) -> SessionToken:
        """
        Validate session token

        Args:
            session_token: JWT session token
        Returns:
            Decoded SessionToken

        Raises:
            InvalidSessionTokenError: If token is invalid
            SessionExpiredError: If session is expired
        """
        try:
            # Decode JWT
            payload = jwt.decode(session_token, self.secret_key, algorithms=["HS256"])

            # Convert to SessionToken
            token = SessionToken(**payload)

            # Validate expiration
            if utc_now() > token.expires_at:
                raise SessionExpiredError(
                    f"Session {token.session_id} expired at {token.expires_at}"
                )
            try:
                session = self.get_session(token.agent_id)
                if (
                    not session
                    or session.session_id != token.session_id
                    or not session.is_active()
                ):
                    raise InvalidSessionTokenError(
                        f"Session {token.session_id} is no longer active"
                    )
            except (OSError, json.JSONDecodeError, ValidationError) as exc:
                raise InvalidSessionTokenError(
                    f"Session {token.session_id} is no longer active"
                ) from exc

            return token

        except jwt.ExpiredSignatureError:
            raise SessionExpiredError("Session token expired")
        except jwt.InvalidTokenError as e:
            raise InvalidSessionTokenError(f"Invalid session token: {str(e)}")

    def get_session(self, agent_id: str) -> Session | None:
        """
        Get session for agent

        Args:
            agent_id: Agent identifier

        Returns:
            Session object or None if not found
        """
        session_file = self.sessions_dir / f"{agent_id}.json"
        return self._load_session_file(session_file)

    def get_active_session(self) -> Session | None:
        """
        Get currently active session

        Returns:
            Session object or None if no active session or session is expired
        """
        active_link = self.sessions_dir / "active"
        if not active_link.exists():
            return None

        # Read symlink (or file on Windows)
        if active_link.is_symlink():
            target = active_link.readlink()
            agent_id = target.stem
        else:
            with open(active_link) as f:
                agent_id = f.read().strip()

        session = self.get_session(agent_id)
        if not session:
            return None

        # If session is expired, clear the stale active marker and return None
        if not session.is_active():
            self._clear_active_session()
            return None

        return session

    def end_session(self, agent_id: str) -> SessionSummary:
        """
        End session for agent

        Args:
            agent_id: Agent identifier

        Returns:
            SessionSummary with session statistics

        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        session = self.get_session(agent_id)
        if not session:
            raise SessionNotFoundError(f"No session found for agent {agent_id}")

        ended_at = utc_now()
        duration = (ended_at - session.started_at).total_seconds() / 3600

        # Update session status
        session.status = SessionStatus.TERMINATED
        self._save_session(session)

        # Clear active session if this was active
        active_session = self.get_active_session()
        if active_session and active_session.agent_id == agent_id:
            self._clear_active_session()

        # TODO: Get actual memory count from backend
        memories_created = 0

        return SessionSummary(
            session_id=session.session_id,
            agent_id=agent_id,
            started_at=session.started_at,
            ended_at=ended_at,
            duration_hours=round(duration, 2),
            memories_created=memories_created,
        )

    def renew_session(
        self,
        agent_id: str,
        pattern: AgentPattern | None = None,
    ) -> Session:
        """
        Renew session by creating a fresh one (new JWT, new expiry window).

        This is the auto-renewal mechanism: when a session nears expiry,
        a completely new session is issued so the agent can keep working
        without interruption.

        Args:
            agent_id: Agent identifier
            pattern: Agent pattern (carried over from previous session)

        Returns:
            New Session object with fresh token and expiry
        """
        renew_hours = settings.SESSION_AUTO_RENEW_INTERVAL_HOURS
        return self.create_session(
            agent_id=agent_id,
            pattern=pattern,
            duration_hours=renew_hours,
        )

    def check_and_auto_renew(
        self,
        agent_id: str,
    ) -> Session | None:
        """
        Check if the current session is near expiry and auto-renew if enabled.

        "Near expiry" is defined by SESSION_EXTEND_THRESHOLD_MINUTES.
        If auto-renewal is enabled and the session is within the threshold,
        a brand-new session is created (new JWT token, fresh expiry window).

        Args:
            agent_id: Agent identifier
        Returns:
            New Session if renewed, None if no renewal was needed
        """
        if not settings.SESSION_AUTO_RENEW_ENABLED:
            return None

        session = self.get_session(agent_id)
        if not session or not session.is_active():
            return None

        remaining = session.time_remaining()
        threshold = timedelta(minutes=settings.SESSION_EXTEND_THRESHOLD_MINUTES)

        if remaining <= threshold:
            # Renew with a fresh session
            return self.renew_session(
                agent_id=agent_id,
                pattern=session.pattern,
            )

        return None

    def _save_session(self, session: Session) -> None:
        """Save session to file"""
        session_file = self.sessions_dir / f"{session.agent_id}.json"
        with open(session_file, "w") as f:
            json.dump(session.model_dump(mode="json"), f, indent=2)

    def _load_session_file(self, session_file: Path) -> Session | None:
        """Load one session file, treating corrupt local state as absent."""
        if not session_file.exists():
            return None

        try:
            with open(session_file) as f:
                data = json.load(f)
            return Session(**data)
        except (OSError, json.JSONDecodeError, TypeError, ValidationError) as exc:
            logger.warning("Skipping invalid session file %s: %s", session_file, exc)
            return None

    def log_memory_to_session_summary(
        self,
        agent_id: str,
        session_id: str,
        memory_record: Any,
        memory_id: str | None = None,
    ) -> None:
        """
        Appends a memory to the local session's Markdown summary file.

        Args:
            agent_id: The agent's identifier
            session_id: The current session's identifier
            memory_record: The MemoryRecord object
            memory_id: The Moorcheh memory ID (if available)
        """
        # Get the timestamp of memory to determine the date string
        dt_now = getattr(memory_record, "created_at", utc_now())
        timestamp = dt_now.strftime("%Y-%m-%d %H:%M:%S")
        date_str = dt_now.strftime("%Y-%m-%d")

        summary_file = (
            self.sessions_dir / f"{agent_id}_{date_str}_{session_id}_summary.md"
        )

        # Determine if we need to write the header
        write_header = not summary_file.exists()

        # Format the memory into Markdown
        memory_type = (getattr(memory_record, "type", None) or "unclassified").upper()
        title = getattr(memory_record, "title", "Untitled")
        content = getattr(memory_record, "content", "")
        confidence = getattr(memory_record, "confidence", 1.0)
        # Fall back to the record's own id so the ID is logged on every path
        memory_id = memory_id or getattr(memory_record, "id", None)
        source = getattr(memory_record, "source", None)
        provenance = getattr(memory_record, "provenance", None)
        status = getattr(memory_record, "status", None)
        tags = getattr(memory_record, "tags", None)

        with open(summary_file, "a", encoding="utf-8") as f:
            if write_header:
                f.write(f"# Session Summary for {agent_id}\n")
                f.write(f"**Session ID:** `{session_id}`\n\n")
                f.write("---\n\n")

            f.write(f"### [{timestamp}] [{memory_type}] {title}\n")
            if memory_id:
                f.write(f"- **Memory ID**: `{memory_id}`\n")
            f.write(f"- **Confidence**: `{confidence}`\n")
            if status:
                f.write(f"- **Status**: `{status}`\n")
            if source:
                f.write(f"- **Source**: `{source}`\n")
            if provenance:
                f.write(f"- **Provenance**: `{provenance}`\n")
            if tags:
                f.write(f"- **Tags**: {', '.join(f'`{t}`' for t in tags)}\n")
            f.write("- **Content**:\n")
            f.write(f"> {content.replace(chr(10), chr(10) + '> ')}\n\n")
            f.write("---\n\n")

    def log_memory_deletion_to_session_summary(
        self,
        agent_id: str,
        session_id: str,
        memory_id: str,
    ) -> None:
        """
        Appends a memory deletion event to the local session's Markdown summary file.

        Args:
            agent_id: The agent's identifier
            session_id: The current session's identifier
            memory_id: The Moorcheh memory ID that was deleted
        """
        dt_now = utc_now()
        timestamp = dt_now.strftime("%Y-%m-%d %H:%M:%S")
        date_str = dt_now.strftime("%Y-%m-%d")

        summary_file = (
            self.sessions_dir / f"{agent_id}_{date_str}_{session_id}_summary.md"
        )

        write_header = not summary_file.exists()

        with open(summary_file, "a", encoding="utf-8") as f:
            if write_header:
                f.write(f"# Session Summary for {agent_id}\n")
                f.write(f"**Session ID:** `{session_id}`\n\n")
                f.write("---\n\n")

            f.write(f"### [{timestamp}] [DELETED] Memory Deleted\n")
            f.write(f"- **Memory ID**: `{memory_id}`\n")
            f.write("- **Confidence**: `1.0`\n")
            f.write("---\n\n")

    def _set_active_session(self, agent_id: str) -> None:
        """Mark session as active"""
        active_link = self.sessions_dir / "active"

        # Remove existing active link
        if active_link.exists():
            active_link.unlink()

        # Create new active marker
        # On Windows, write agent_id to file instead of symlink
        try:
            active_link.symlink_to(f"{agent_id}.json")
        except (OSError, NotImplementedError):
            # Fallback for Windows or systems without symlink support
            with open(active_link, "w") as f:
                f.write(agent_id)

    def _clear_active_session(self) -> None:
        """Clear active session marker"""
        active_link = self.sessions_dir / "active"
        if active_link.exists():
            active_link.unlink()

    def clear_active_session(self) -> None:
        """Public alias: clear the active-session marker without ending the session."""
        self._clear_active_session()

    def list_sessions(self) -> list[Session]:
        """
        List all sessions

        Returns:
            List of Session objects
        """
        sessions = []
        for session_file in self.sessions_dir.glob("*.json"):
            session = self._load_session_file(session_file)
            if session is not None:
                sessions.append(session)

        return sorted(sessions, key=lambda s: s.started_at, reverse=True)
