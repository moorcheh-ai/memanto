"""Which tool drove which MEMANTO session, and which tools are live now.

``SessionService`` owns sessions; this module does not invent any. It only
records, for every memory operation, the tool that made it and the MEMANTO
session it belonged to. Two things fall out of that log:

* **Session entries.** A session's row can name the tools that took part in it,
  instead of just an agent id.
* **Liveness.** A tool that touched memory in the last few minutes is connected
  right now - the only claim that can be made honestly about a stateless CLI
  caller.

Design constraints:

* **Never break a memory operation.** Logging sits on the hot path of every
  remember and recall. Every public entry point swallows its own failures - a
  telemetry line is never worth failing a durable write over.
* **Append-only, derive on read.** A single ``O_APPEND`` line per event is
  atomic enough for concurrent CLI processes without a lock, and a crashed
  writer leaves no half-built index behind.
* **Bounded on disk.** Files older than :data:`RETENTION_DAYS` are pruned once
  per process.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from memanto.app.utils.client_identity import (
    ClientIdentity,
    detect_client,
    get_memanto_session,
)
from memanto.app.utils.temporal_helpers import utc_now

logger = logging.getLogger(__name__)

# A tool that touched memory inside this window counts as connected right now.
LIVE_WINDOW_SECONDS = 300
# Days of event files kept on disk.
RETENTION_DAYS = 30

_service: ActivityService | None = None
_pruned_this_process = False


def get_activity_service() -> ActivityService:
    """Shared :class:`ActivityService` singleton."""
    global _service
    if _service is None:
        _service = ActivityService()
    return _service


class ActivityService:
    """Append-only log of tool activity, grouped by MEMANTO session on read."""

    def __init__(self, activity_dir: Path | None = None):
        if activity_dir is None:
            from memanto.app.config import get_data_dir

            activity_dir = get_data_dir() / "activity"
        self.activity_dir = activity_dir

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def log_event(
        self,
        op: str,
        agent_id: str | None,
        count: int = 0,
        identity: ClientIdentity | None = None,
        session_id: str | None = None,
    ) -> None:
        """Record one memory operation. Best effort; never raises.

        Args:
            op: ``remember``, ``recall`` or ``answer``.
            agent_id: The MEMANTO agent the operation targeted.
            count: Memories written, or returned by a read.
            identity: Overrides tool detection (used by tests and the MCP layer).
            session_id: Overrides the bound MEMANTO session.
        """
        try:
            self._log_event(op, agent_id, count, identity, session_id)
        except Exception as exc:
            logger.debug("Activity logging failed for op=%s: %s", op, exc)

    def _log_event(
        self,
        op: str,
        agent_id: str | None,
        count: int,
        identity: ClientIdentity | None,
        session_id: str | None,
    ) -> None:
        identity = identity or detect_client()
        now = utc_now()
        event = {
            "ts": now.isoformat(),
            "tool": identity.tool,
            "display": identity.display,
            "session": session_id or get_memanto_session(),
            "agent_id": agent_id,
            "project_dir": identity.project_dir,
            "op": op,
            "n": count,
        }
        self._append(event, now)
        self._prune_once()

    def _append(self, event: dict[str, Any], now: datetime) -> None:
        """Append one JSON line to today's event file."""
        self.activity_dir.mkdir(parents=True, exist_ok=True)
        path = self.activity_dir / f"events-{now.strftime('%Y-%m-%d')}.jsonl"
        line = json.dumps(event, ensure_ascii=False) + "\n"
        # O_APPEND makes a single short write atomic against other processes,
        # which is what keeps concurrent CLI invocations from interleaving
        # halves of two events on one line.
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)

    def _prune_once(self) -> None:
        """Delete event files past retention, at most once per process."""
        global _pruned_this_process
        if _pruned_this_process:
            return
        _pruned_this_process = True
        cutoff = (utc_now() - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
        for path in self.activity_dir.glob("events-*.jsonl"):
            if path.stem.removeprefix("events-") < cutoff:
                try:
                    path.unlink()
                except OSError:
                    continue

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def iter_events(self, days: int = 7) -> Iterator[dict[str, Any]]:
        """Yield events from the last *days* daily files, oldest first."""
        if not self.activity_dir.exists():
            return
        cutoff = (utc_now() - timedelta(days=max(days, 1) - 1)).strftime("%Y-%m-%d")
        for path in sorted(self.activity_dir.glob("events-*.jsonl")):
            if path.stem.removeprefix("events-") < cutoff:
                continue
            try:
                with open(path, encoding="utf-8") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            # A torn final line from a killed process. Skip it
                            # rather than discarding the whole day's file.
                            continue
                        if isinstance(event, dict):
                            yield event
            except OSError:
                continue

    def live_tools(self, days: int = 7) -> list[dict[str, Any]]:
        """Per-tool usage totals over the window, most recently seen first."""
        tools: dict[str, dict[str, Any]] = {}
        for event in self.iter_events(days):
            tool = event.get("tool")
            if not tool:
                continue
            entry = tools.setdefault(
                tool,
                {
                    "tool": tool,
                    "display": event.get("display") or tool,
                    "writes": 0,
                    "reads": 0,
                    "memories_written": 0,
                    "memories_read": 0,
                    "last_seen": None,
                },
            )
            self._tally(entry, event)
            ts = event.get("ts")
            if ts and (entry["last_seen"] is None or ts > entry["last_seen"]):
                entry["last_seen"] = ts

        now = utc_now()
        for entry in tools.values():
            entry["live"] = self._is_live(entry["last_seen"], now)
        return sorted(tools.values(), key=lambda t: t["last_seen"] or "", reverse=True)

    def list_sessions(self, days: int = 7) -> list[dict[str, Any]]:
        """MEMANTO sessions from the window, each with the tools that used it.

        Built by merging two sources: the activity log, which is the only place
        past sessions survive (``SessionService`` keeps one file per agent, so
        a new session overwrites the last), and the live session records, so a
        session that has been activated but not yet used still shows up.
        """
        sessions: dict[str, dict[str, Any]] = {}

        for event in self.iter_events(days):
            session_id = event.get("session")
            if not session_id:
                # Operations outside a session (direct service calls, anonymous
                # REST) still count toward tool liveness, but they are not part
                # of any session's story.
                continue
            entry = sessions.get(session_id)
            if entry is None:
                entry = {
                    "session_id": session_id,
                    "agent_id": event.get("agent_id"),
                    "project_dir": event.get("project_dir"),
                    "started_at": event.get("ts"),
                    "last_seen": event.get("ts"),
                    "expires_at": None,
                    "active": False,
                    "tools": [],
                    "writes": 0,
                    "reads": 0,
                    "memories_written": 0,
                    "memories_read": 0,
                }
                sessions[session_id] = entry

            ts = event.get("ts")
            if ts:
                if not entry["started_at"] or ts < entry["started_at"]:
                    entry["started_at"] = ts
                if not entry["last_seen"] or ts > entry["last_seen"]:
                    entry["last_seen"] = ts
            self._tally(entry, event)
            self._tally_tool(entry, event)

        self._merge_live_sessions(sessions)

        now = utc_now()
        for entry in sessions.values():
            entry["status"] = self._status_for(entry, now)
            entry["tools"].sort(key=lambda t: t["last_seen"] or "", reverse=True)
        return sorted(
            sessions.values(), key=lambda s: s.get("last_seen") or "", reverse=True
        )

    @staticmethod
    def _tally(entry: dict[str, Any], event: dict[str, Any]) -> None:
        """Fold one event's operation counts into a running total."""
        op = event.get("op")
        count = int(event.get("n") or 0)
        if op == "remember":
            entry["writes"] += 1
            entry["memories_written"] += max(count, 1)
        elif op in ("recall", "answer"):
            entry["reads"] += 1
            entry["memories_read"] += count

    def _tally_tool(self, entry: dict[str, Any], event: dict[str, Any]) -> None:
        """Track per-tool participation within one session."""
        tool = event.get("tool")
        if not tool:
            return
        record = next((t for t in entry["tools"] if t["tool"] == tool), None)
        if record is None:
            record = {
                "tool": tool,
                "display": event.get("display") or tool,
                "writes": 0,
                "reads": 0,
                "memories_written": 0,
                "memories_read": 0,
                "last_seen": None,
            }
            entry["tools"].append(record)
        self._tally(record, event)
        ts = event.get("ts")
        if ts and (record["last_seen"] is None or ts > record["last_seen"]):
            record["last_seen"] = ts

    @staticmethod
    def _merge_live_sessions(sessions: dict[str, dict[str, Any]]) -> None:
        """Overlay the authoritative session records from ``SessionService``.

        The log knows when a session was *used*; only the session file knows
        when it was actually started, when it expires, and whether it is still
        active. Where both exist the session file wins.

        A session file that is neither active nor present in the activity
        window is not added: ``SessionService`` keeps one file per agent
        forever, so every agent ever created would otherwise show up as an
        empty row and bury the sessions that actually did something.
        """
        try:
            from memanto.app.services.session_service import get_session_service

            live = get_session_service().list_sessions()
        except Exception as exc:
            logger.debug("Could not read live sessions: %s", exc)
            return

        for session in live:
            entry = sessions.get(session.session_id)
            if entry is None:
                if not session.is_active():
                    continue
                entry = {
                    "session_id": session.session_id,
                    "agent_id": session.agent_id,
                    "project_dir": None,
                    "started_at": session.started_at.isoformat(),
                    # No events means no tool has touched memory in this
                    # session yet. Seeding last_seen from started_at would make
                    # a freshly activated agent read as "live" without a single
                    # tool behind it.
                    "last_seen": None,
                    "expires_at": None,
                    "active": False,
                    "tools": [],
                    "writes": 0,
                    "reads": 0,
                    "memories_written": 0,
                    "memories_read": 0,
                }
                sessions[session.session_id] = entry
            entry["agent_id"] = session.agent_id
            entry["started_at"] = session.started_at.isoformat()
            entry["expires_at"] = session.expires_at.isoformat()
            entry["active"] = session.is_active()

    @staticmethod
    def _is_live(last_seen: str | None, now: datetime) -> bool:
        if not last_seen:
            return False
        try:
            age = (now - datetime.fromisoformat(last_seen)).total_seconds()
        except (TypeError, ValueError):
            return False
        return age <= LIVE_WINDOW_SECONDS

    def _status_for(self, entry: dict[str, Any], now: datetime) -> str:
        """Classify a session as live, active, or ended.

        ``live`` means a tool touched memory just now. ``active`` means the
        MEMANTO session is still valid but quiet - the session record is
        authoritative here, so a session does not read as finished merely
        because nobody has used it for a while.
        """
        if self._is_live(entry.get("last_seen"), now):
            return "live"
        return "active" if entry.get("active") else "ended"

    def get_session(
        self, session_id: str, days: int = RETENTION_DAYS
    ) -> dict[str, Any]:
        """Return one session's summary plus its full event timeline."""
        events = [e for e in self.iter_events(days) if e.get("session") == session_id]
        summary = next(
            (s for s in self.list_sessions(days) if s["session_id"] == session_id), None
        )
        return {"session": summary, "events": events}


def log_memory_activity(op: str, agent_id: str | None, count: int = 0) -> None:
    """Fail-safe entry point for the memory services.

    Kept as a free function so call sites read as one line on the hot path and
    cannot accidentally propagate a telemetry failure into a memory operation.
    """
    try:
        get_activity_service().log_event(op=op, agent_id=agent_id, count=count)
    except Exception as exc:
        logger.debug("Activity logging unavailable: %s", exc)
