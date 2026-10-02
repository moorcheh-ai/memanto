"""
Session Service for MEMANTO

Handles session creation, validation, and management.
Uses JWT tokens for stateless authentication.
"""

import errno
import json
import logging
import os
import secrets
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
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
from memanto.app.utils.temporal_helpers import as_utc_aware, utc_now
from memanto.app.utils.validation import validate_safe_id

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

    _PRIVATE_FILE_MODE = 0o600
    _PRIVATE_DIR_MODE = 0o700

    def __init__(self, secret_key: str | None = None, sessions_dir: Path | None = None):
        """
        Initialize session service

        Args:
            secret_key: Secret key for JWT signing (defaults to env var or generated)
            sessions_dir: Directory for session storage (defaults to ~/.memanto/sessions/)
        """
        self.sessions_dir = sessions_dir or get_data_dir() / "sessions"
        self._secret_key: str | None = secret_key or settings.MEMANTO_SECRET_KEY or None
        self._storage_hardened = False
        # Serialize lifecycle operations for the same agent so renewal cannot
        # publish a fresh bearer token after logout has completed. Keep the
        # process-wide active marker on its own narrower lock so unrelated
        # agents can create, renew, and terminate sessions concurrently.
        self._agent_locks: dict[str, threading.RLock] = {}
        self._agent_locks_guard = threading.Lock()
        self._active_marker_lock = threading.RLock()
        self._summary_lock = threading.Lock()

    @property
    def secret_key(self) -> str:
        """JWT signing key, generated only when token operations need it."""
        if self._secret_key is None:
            self._secret_key = self._generate_secure_secret_key()
        return self._secret_key

    def _lock_for_agent(self, agent_id: str) -> threading.RLock:
        """Return the stable lifecycle lock for one agent."""
        validate_safe_id(agent_id, "agent_id")
        with self._agent_locks_guard:
            lock = self._agent_locks.get(agent_id)
            if lock is None:
                lock = threading.RLock()
                self._agent_locks[agent_id] = lock
            return lock

    @staticmethod
    def _set_private_permissions(path: Path, mode: int) -> None:
        """Best-effort owner-only permissions for persisted session state."""
        try:
            path.chmod(mode)
        except OSError:
            # Windows ACLs are not represented by POSIX mode bits. Creation and
            # access still follow the owning user's ACL in that environment.
            pass

    def _harden_session_storage(self) -> None:
        """Create and protect both new and pre-existing session artifacts.

        Session JSON files contain live bearer tokens, while summary files can
        contain private memory content. A normal ``mkdir``/``open`` sequence on
        POSIX inherits the process umask and commonly creates these as 0755 and
        0644, allowing other local accounts to traverse and read them.
        """
        if self._storage_hardened and self.sessions_dir.exists():
            return
        self.sessions_dir.mkdir(
            parents=True, exist_ok=True, mode=self._PRIVATE_DIR_MODE
        )
        self._set_private_permissions(self.sessions_dir, self._PRIVATE_DIR_MODE)
        for path in self.sessions_dir.iterdir():
            if path.is_symlink() or not path.is_file():
                continue
            self._set_private_permissions(path, self._PRIVATE_FILE_MODE)
        self._storage_hardened = True

    def _open_private_text(self, path: Path, flags: int, mode: str, **kwargs):
        """Open a text file with owner-only permissions from first creation."""
        fd = os.open(str(path), flags, self._PRIVATE_FILE_MODE)
        try:
            try:
                fchmod = getattr(os, "fchmod", None)
                if fchmod is not None:
                    fchmod(fd, self._PRIVATE_FILE_MODE)
            except OSError:
                # Best-effort only: some platforms and filesystems reject fchmod
                # even though os.open already created the file with this mode.
                pass
            return os.fdopen(fd, mode, **kwargs)
        except Exception:
            os.close(fd)
            raise

    def _write_private_json_atomic(self, path: Path, data: Any) -> None:
        """Atomically replace a private JSON file after a complete durable write.

        Writing directly to the live path with ``O_TRUNC`` can destroy the only
        valid session record if serialization or the process fails mid-write.
        A sibling temporary file keeps readers on the previous complete record
        until the replacement is ready.
        """
        tmp_path = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            with self._open_private_text(
                tmp_path, flags, "w", encoding="utf-8"
            ) as tmp_file:
                json.dump(data, tmp_file, indent=2)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            os.replace(tmp_path, path)
            self._set_private_permissions(path, self._PRIVATE_FILE_MODE)
        finally:
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                # Expected on the success path: os.replace already moved the
                # temp file onto the target, so there is nothing left to clean up.
                pass

    def _generate_secure_secret_key(self) -> str:
        """Generate (or reuse) a persisted fallback secret for JWT signing.

        Persisted alongside the sessions directory so sessions survive
        process restarts instead of every new process invalidating all
        existing session tokens. A cross-process lock serializes the initial
        read/write so concurrent first-start workers cannot return divergent
        secrets. The file has restrictive permissions from creation, and an
        existing-but-empty file (e.g. left behind by a crash mid-write) is
        safely rewritten by the lock holder.
        """
        secret_file = self.sessions_dir.parent / "secret_key"
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        lock_file = secret_file.with_name(f"{secret_file.name}.lock")
        with self._exclusive_file_lock(lock_file):
            existing = self._read_persisted_secret(secret_file)
            if existing is not None:
                return existing

            secret = secrets.token_hex(32)
            fd, temp_name = tempfile.mkstemp(
                prefix=f".{secret_file.name}.", dir=secret_file.parent
            )
            temp_file = Path(temp_name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as file_handle:
                    file_handle.write(secret)
                    file_handle.flush()
                    os.fsync(file_handle.fileno())
                os.replace(temp_file, secret_file)
                try:
                    secret_file.chmod(0o600)
                except OSError:
                    pass  # Windows may not support chmod
            finally:
                temp_file.unlink(missing_ok=True)
            return secret

    @staticmethod
    @contextmanager
    def _exclusive_file_lock(lock_file: Path) -> Iterator[None]:
        """Hold an advisory cross-process lock on one byte of ``lock_file``."""
        fd = os.open(str(lock_file), os.O_CREAT | os.O_RDWR, 0o600)
        locked = False
        try:
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"\0")
                os.fsync(fd)
            os.lseek(fd, 0, os.SEEK_SET)

            if os.name == "nt":
                import msvcrt

                while True:
                    try:
                        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
                        break
                    except OSError as exc:
                        if exc.errno not in {
                            errno.EACCES,
                            errno.EAGAIN,
                            errno.EDEADLK,
                        }:
                            raise
                        os.lseek(fd, 0, os.SEEK_SET)
                        time.sleep(0.05)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX)  # type: ignore[attr-defined]
            locked = True
            yield
        finally:
            if locked:
                os.lseek(fd, 0, os.SEEK_SET)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
                else:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_UN)  # type: ignore[attr-defined]
            os.close(fd)

    @staticmethod
    def _read_persisted_secret(secret_file: Path) -> str | None:
        """Read the persisted JWT secret, treating a missing/empty file as absent."""
        if not secret_file.exists():
            return None
        content = secret_file.read_text().strip()
        return content or None

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
        with self._lock_for_agent(agent_id):
            return self._create_session(agent_id, pattern, duration_hours)

    def _create_session(
        self,
        agent_id: str,
        pattern: AgentPattern | None,
        duration_hours: int | None,
    ) -> Session:
        """Create and publish a session while the agent lifecycle lock is held."""
        # Use config default if not explicitly provided
        if duration_hours is None:
            duration_hours = settings.SESSION_DEFAULT_DURATION_HOURS

        if not isinstance(duration_hours, (int, float)) or duration_hours < 0:
            raise ValueError(
                "duration_hours must be a non-negative number of hours, "
                f"got {duration_hours!r}"
            )

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
            if utc_now() > as_utc_aware(token.expires_at):
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
        validate_safe_id(agent_id, "agent_id")
        session_file = self.sessions_dir / f"{agent_id}.json"
        return self._load_session_file(session_file)

    def _read_active_marker_agent_id(self) -> str | None:
        """Read the agent_id the active marker points at, or None.

        Caller must hold ``_active_marker_lock``.
        """
        active_link = self.sessions_dir / "active"
        try:
            # Read symlink (or file on Windows). Another process can replace
            # or remove the marker while this process holds its local lock.
            if active_link.is_symlink():
                return active_link.readlink().stem
            with open(active_link) as f:
                return f.read().strip()
        except OSError:
            return None

    def get_active_session(self) -> Session | None:
        """
        Get currently active session

        Returns:
            Session object or None when there is no active marker, or the
            marker named a session that has lapsed and could not be
            auto-recreated.
        """
        with self._active_marker_lock:
            agent_id = self._read_active_marker_agent_id()
            if agent_id is None:
                return None

            try:
                session = self.get_session(agent_id)
            except (ValueError, OSError):
                # An empty or malformed marker (e.g. a crash between unlink and
                # the fallback write in _set_active_session) fails validate_safe_id.
                # An overlong marker can also raise OSError (ENAMETOOLONG) when
                # probing the session path. Either way: no active session.
                return None
            if not session:
                return None

            if session.is_active():
                return session

            expired_token = session.session_token

        # The marker names a session that has lapsed. Auto-recreate has to run
        # outside the marker lock: it takes the agent lifecycle lock, and
        # delete_session takes those two in the opposite order, so holding both
        # here would invert the lock order.
        #
        # This is what keeps MEMANTO usable after an idle gap. Every CLI entry
        # point resolves its session through this marker, so clearing it on
        # expiry stranded the caller with "No active session. Call
        # activate_agent()" regardless of the auto-recreate setting.
        recreated = self.check_and_auto_recreate(expired_token)
        if recreated is not None:
            return recreated

        # Recreation declined (disabled by config, or the session was
        # terminated). Drop the stale marker, but only if it still names the
        # same lapsed session - another thread may have activated since.
        with self._active_marker_lock:
            if self._read_active_marker_agent_id() == agent_id:
                try:
                    current = self.get_session(agent_id)
                except (ValueError, OSError):
                    current = None
                if current is None or not current.is_active():
                    self._clear_active_session()
        return None

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
        with self._lock_for_agent(agent_id):
            return self._end_session(agent_id)

    def _end_session(self, agent_id: str) -> SessionSummary:
        """Terminate a session while excluding concurrent token rotation."""
        session = self.get_session(agent_id)
        if not session:
            raise SessionNotFoundError(f"No session found for agent {agent_id}")

        ended_at = utc_now()
        duration = (ended_at - as_utc_aware(session.started_at)).total_seconds() / 3600

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

        # Validation and renewal must be one operation. Without the per-agent
        # lifecycle lock, parallel requests can all observe the same
        # near-expiry session, mint competing tokens, and immediately
        # invalidate every replacement except the last file write. The same
        # lock also makes logout authoritative over an in-flight renewal.
        with self._lock_for_agent(agent_id):
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

    def check_and_auto_recreate(
        self,
        session_token: str,
    ) -> Session | None:
        """
        Recreate an expired session as a fresh one if auto-recreate is enabled.

        Complements check_and_auto_renew: renewal keeps a *live* session
        going near expiry, while this path transparently issues a brand-new
        session (new JWT, fresh expiry window) when a caller presents the
        token of a session that has already fully lapsed. Deliberately
        terminated sessions are never resurrected; callers must activate
        explicitly after logout. Authorization is the route layer's job
        (management credential or loopback), same as explicit activation.

        Args:
            session_token: The expired JWT presented by the caller
        Returns:
            New Session if recreated, None when recreation does not apply
        """
        if not settings.SESSION_AUTO_RECREATE_ENABLED:
            return None

        try:
            payload = jwt.decode(session_token, self.secret_key, algorithms=["HS256"])
            token = SessionToken(**payload)
        except (jwt.InvalidTokenError, ValidationError):
            # Not ours / malformed / unsignable: leave it to normal validation
            # to surface the right error.
            return None

        try:
            agent_lock = self._lock_for_agent(token.agent_id)
        except ValueError:
            # A token we signed but whose agent_id is no longer a safe id.
            # Leave it to normal validation to reject rather than raising an
            # unhandled 500 out of the auth dependency.
            return None

        with agent_lock:
            session = self.get_session(token.agent_id)
            if not session or session.session_id != token.session_id:
                # Unknown agent, or the persisted record was replaced by a
                # newer session — never supersede it from a stale token.
                return None

            if session.status == SessionStatus.TERMINATED or session.is_active():
                # Logout is authoritative; live sessions are handled by the
                # regular validation/auto-renewal flow instead.
                return None

            return self.create_session(
                agent_id=token.agent_id,
                pattern=session.pattern,
                duration_hours=settings.SESSION_DEFAULT_DURATION_HOURS,
            )

    def _save_session(self, session: Session) -> None:
        """Save session to file.

        Deliberately does NOT use the shared ``atomic_write_text`` helper that
        agent metadata and CLI config use. Both are crash-safe, but session
        files hold live bearer tokens, so this path additionally hardens the
        containing directory to 0o700 and any pre-existing session files to
        0o600 before writing. Swapping in the generic helper would silently
        drop that hardening.
        """
        validate_safe_id(session.agent_id, "agent_id")
        self._harden_session_storage()
        session_file = self.sessions_dir / f"{session.agent_id}.json"
        self._write_private_json_atomic(session_file, session.model_dump(mode="json"))

    def _load_session_file(self, session_file: Path) -> Session | None:
        """Load one session file, treating corrupt local state as absent."""
        try:
            if not session_file.exists():
                return None
        except OSError as exc:
            # e.g. ENAMETOOLONG from a corrupt active-marker agent_id
            logger.warning("Skipping invalid session path %s: %s", session_file, exc)
            return None
        self._harden_session_storage()

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
        validate_safe_id(agent_id, "agent_id")
        validate_safe_id(session_id, "session_id")
        dt_now = getattr(memory_record, "created_at", utc_now())
        timestamp = dt_now.strftime("%Y-%m-%d %H:%M:%S")
        date_str = dt_now.strftime("%Y-%m-%d")

        summary_file = (
            self.sessions_dir / f"{agent_id}_{date_str}_{session_id}_summary.md"
        )
        self._harden_session_storage()

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

        lines = [f"### [{timestamp}] [{memory_type}] {title}\n"]
        if memory_id:
            lines.append(f"- **Memory ID**: `{memory_id}`\n")
        lines.append(f"- **Confidence**: `{confidence}`\n")
        if status:
            lines.append(f"- **Status**: `{status}`\n")
        if source:
            lines.append(f"- **Source**: `{source}`\n")
        if provenance:
            lines.append(f"- **Provenance**: `{provenance}`\n")
        if tags:
            lines.append(f"- **Tags**: {', '.join(f'`{t}`' for t in tags)}\n")
        lines.append("- **Content**:\n")
        lines.append(f"> {content.replace(chr(10), chr(10) + '> ')}\n\n")
        lines.append("---\n\n")

        self._append_session_summary(
            summary_file=summary_file,
            agent_id=agent_id,
            session_id=session_id,
            entry="".join(lines),
        )

    def try_log_memory_to_session_summary(
        self,
        agent_id: str,
        session_id: str,
        memory_record: Any,
        memory_id: str | None = None,
    ) -> bool:
        """Best-effort summary logging for an already committed memory.

        The remote memory store is authoritative. Once that write succeeds, an
        auxiliary local Markdown failure must not make callers report the
        operation as failed (and potentially retry it with a new memory ID).
        """
        try:
            self.log_memory_to_session_summary(
                agent_id=agent_id,
                session_id=session_id,
                memory_record=memory_record,
                memory_id=memory_id,
            )
        except Exception as exc:
            logger.warning(
                "Memory %s was committed for agent %s, but session summary "
                "logging failed: %s",
                memory_id or getattr(memory_record, "id", "unknown"),
                agent_id,
                exc,
            )
            return False
        return True

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
        validate_safe_id(agent_id, "agent_id")
        validate_safe_id(session_id, "session_id")

        dt_now = utc_now()
        timestamp = dt_now.strftime("%Y-%m-%d %H:%M:%S")
        date_str = dt_now.strftime("%Y-%m-%d")

        summary_file = (
            self.sessions_dir / f"{agent_id}_{date_str}_{session_id}_summary.md"
        )
        self._harden_session_storage()

        entry = (
            f"### [{timestamp}] [DELETED] Memory Deleted\n"
            f"- **Memory ID**: `{memory_id}`\n"
            "- **Confidence**: `1.0`\n"
            "---\n\n"
        )
        self._append_session_summary(
            summary_file=summary_file,
            agent_id=agent_id,
            session_id=session_id,
            entry=entry,
        )

    def _append_session_summary(
        self,
        summary_file: Path,
        agent_id: str,
        session_id: str,
        entry: str,
    ) -> None:
        """Append one complete entry without racing header creation or peer writes."""
        with self._summary_lock:
            header = ""
            if not summary_file.exists():
                header = (
                    f"# Session Summary for {agent_id}\n"
                    f"**Session ID:** `{session_id}`\n\n"
                    "---\n\n"
                )

            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
            with self._open_private_text(
                summary_file, flags, "a", encoding="utf-8"
            ) as f:
                f.write(header + entry)

    def try_log_memory_deletion_to_session_summary(
        self,
        agent_id: str,
        session_id: str,
        memory_id: str,
    ) -> bool:
        """Best-effort summary logging for an already committed deletion."""
        try:
            self.log_memory_deletion_to_session_summary(
                agent_id=agent_id,
                session_id=session_id,
                memory_id=memory_id,
            )
        except Exception as exc:
            logger.warning(
                "Memory %s was deleted for agent %s, but session summary "
                "logging failed: %s",
                memory_id,
                agent_id,
                exc,
            )
            return False
        return True

    def _set_active_session(self, agent_id: str) -> None:
        """Mark session as active"""
        validate_safe_id(agent_id, "agent_id")
        with self._active_marker_lock:
            self._harden_session_storage()
            active_link = self.sessions_dir / "active"

            # Remove existing active link
            active_link.unlink(missing_ok=True)

            # Create new active marker
            # On Windows, write agent_id to file instead of symlink
            try:
                active_link.symlink_to(f"{agent_id}.json")
            except (OSError, NotImplementedError):
                # Fallback for Windows or systems without symlink support
                flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
                with self._open_private_text(active_link, flags, "w") as f:
                    f.write(agent_id)

    def _clear_active_session(self) -> None:
        """Clear active session marker"""
        with self._active_marker_lock:
            active_link = self.sessions_dir / "active"
            active_link.unlink(missing_ok=True)

    def clear_active_session(self) -> None:
        """Public alias: clear the active-session marker without ending the session."""
        self._clear_active_session()

    def delete_session(self, agent_id: str) -> bool:
        """
        Remove persisted session state for an agent.

        Used when an agent is deleted: the agent metadata is gone, so a saved
        session for that agent must not remain usable through X-Session-Token.
        """
        with self._lock_for_agent(agent_id), self._active_marker_lock:
            active_link = self.sessions_dir / "active"
            active_agent_id: str | None = None

            try:
                if active_link.is_symlink():
                    active_agent_id = active_link.readlink().stem
                else:
                    with open(active_link) as f:
                        active_agent_id = f.read().strip()
            except OSError as exc:
                # Best-effort: a missing or unreadable active marker must not
                # block deleting this agent's persisted session state. Leaving
                # active_agent_id as None simply skips the marker cleanup below.
                logger.debug(
                    "Could not read active session marker '%s': %s", active_link, exc
                )

            session_file = self.sessions_dir / f"{agent_id}.json"
            deleted = session_file.exists()
            session_file.unlink(missing_ok=True)

            if active_agent_id == agent_id:
                self._clear_active_session()

            return deleted

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

        return sorted(sessions, key=lambda s: as_utc_aware(s.started_at), reverse=True)
