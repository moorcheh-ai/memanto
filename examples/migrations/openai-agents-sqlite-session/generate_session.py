#!/usr/bin/env python3
"""
Populate a real OpenAI Agents SDK ``SQLiteSession`` — the migration's source data.

Everything that touches storage here is the genuine SDK: ``agents.Runner`` drives
the agent loop, executes ``@function_tool`` calls, and persists every turn through
``agents.SQLiteSession``. The database this writes is therefore produced by the
source tool, not hand-authored.

The only stand-in is the model. Following the SDK's own test pattern, ``ScriptedModel``
implements ``agents.models.interface.Model`` and replays a fixed list of Responses
outputs, so the demo needs no API key and no paid calls. **The assistant replies and
tool arguments below are scripted demo copy, not generated text** — the point of the
exercise is the session lifecycle and the on-disk item shapes, which are identical
either way. Swap ``ScriptedModel`` for ``model="gpt-4o-mini"`` and the same script
runs against a live model.

Usage:
    python generate_session.py --db ./sample/source/agent_sessions.db \
        --snapshot ./sample/source/session_snapshot.json
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sqlite3
import sys
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from agents import Agent, Runner, SQLiteSession, function_tool, set_tracing_disabled
    from agents.items import ModelResponse
    from agents.models.interface import Model
    from agents.usage import Usage
    from openai.types.responses import (
        ResponseFunctionToolCall,
        ResponseOutputMessage,
        ResponseOutputText,
        ResponseReasoningItem,
    )
except ImportError as exc:  # pragma: no cover - dependency guard
    raise SystemExit(
        "openai-agents is required to generate the source session.\n"
        "    pip install -r requirements.txt\n"
        f"(import failed: {exc})"
    )

MAIN_SESSION_ID = "workspace-buddy-demo"
SMOKE_SESSION_ID = "sandbox-smoke-test"


# ---------------------------------------------------------------------------
# Demo infrastructure: a deterministic local model (no API key, no network)
# ---------------------------------------------------------------------------


def _assistant_message(message_id: str, text: str) -> ResponseOutputMessage:
    return ResponseOutputMessage(
        id=message_id,
        content=[ResponseOutputText(text=text, type="output_text", annotations=[])],
        role="assistant",
        status="completed",
        type="message",
    )


def _function_call(
    call_id: str, name: str, arguments: dict[str, Any]
) -> ResponseFunctionToolCall:
    return ResponseFunctionToolCall(
        id=f"fc_{call_id}",
        call_id=call_id,
        type="function_call",
        name=name,
        arguments=json.dumps(arguments),
    )


def _reasoning(item_id: str) -> ResponseReasoningItem:
    """A reasoning item — the SDK persists it, and the adapter must skip it."""
    return ResponseReasoningItem(id=item_id, summary=[], type="reasoning")


class ScriptedModel(Model):
    """Replays a fixed list of model outputs, one per ``get_response`` call."""

    def __init__(self, steps: list[list[Any]]):
        self._steps = list(steps)
        self._index = 0

    async def get_response(self, *args: Any, **kwargs: Any) -> ModelResponse:
        if self._index >= len(self._steps):
            raise AssertionError(
                f"ScriptedModel exhausted after {self._index} calls — the scenario "
                "and the script are out of sync."
            )
        output = self._steps[self._index]
        self._index += 1
        return ModelResponse(output=list(output), usage=Usage(), response_id=None)

    def stream_response(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        raise NotImplementedError("The demo does not stream.")

    @property
    def calls(self) -> int:
        return self._index


# ---------------------------------------------------------------------------
# Tools — real @function_tool functions the Runner actually executes
# ---------------------------------------------------------------------------


@function_tool
def lookup_team_calendar(team: str, horizon_days: int) -> str:
    """Look up a team's scheduled deploy window.

    Args:
        team: Team whose calendar to read.
        horizon_days: How many days ahead to search.
    """
    return json.dumps(
        {
            "team": team,
            "horizon_days": horizon_days,
            "deploy_window": "Tuesday 14:00-16:00 UTC",
            "freeze": "none",
            "source": "demo-calendar-fixture",
        }
    )


@function_tool
def record_incident(component: str, summary: str, occurrences: int) -> str:
    """File an incident note against a component.

    Args:
        component: Component that failed.
        summary: One-line description of the failure.
        occurrences: How many times it happened.
    """
    return json.dumps(
        {
            "incident_id": "INC-2141",
            "component": component,
            "summary": summary,
            "occurrences": occurrences,
            "status": "open",
        }
    )


# ---------------------------------------------------------------------------
# Scenario
# ---------------------------------------------------------------------------


@dataclass
class Turn:
    """One user turn. ``user`` is either plain text or Responses content blocks."""

    user: str | list[dict[str, Any]]
    note: str


#: An evolving workspace-assistant conversation: standing rules, a fact, a tool
#: lookup, a correction that supersedes the tool's answer, a reversed preference,
#: a commitment, and an incident logged through a second tool.
SCENARIO: list[Turn] = [
    Turn(
        user=(
            "Standing rule for this workspace: reply in metric units and keep answers "
            "to three sentences or fewer."
        ),
        note="preference / standing instruction",
    ),
    Turn(
        user=(
            "The orders service runs on PostgreSQL 16 and deploys from the release "
            "branch."
        ),
        note="fact about the system",
    ),
    Turn(
        # Structured Responses content blocks rather than a plain string — the
        # adapter has to handle both shapes.
        user=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "What is the deploy window for the platform team over the "
                            "next month?"
                        ),
                    }
                ],
            }
        ],
        note="structured content blocks + tool call",
    ),
    Turn(
        user=(
            "Correction: the deploy window moved to Thursday 09:00 UTC. The Tuesday "
            "slot is retired, so ignore what the calendar returned."
        ),
        note="correction that supersedes the tool result",
    ),
    Turn(
        user=(
            "Actually, drop the three-sentence rule. I would rather get detailed "
            "answers with bullet points."
        ),
        note="preference reversal",
    ),
    Turn(
        user=(
            "I promised the platform team a migration plan for the orders service by "
            "2026-08-14."
        ),
        note="commitment with a due date",
    ),
    Turn(
        user=(
            "Log an incident: the staging rollout failed twice last week because the "
            "pgbouncer connection pool was too small."
        ),
        note="second tool call",
    ),
]

#: One scripted model output per ``get_response`` call, in order. A turn that
#: calls a tool consumes two calls: the call, then the reply after the result.
SCRIPT: list[list[Any]] = [
    [
        _assistant_message(
            "msg_0001",
            "Understood — metric units only, three sentences maximum. I have stored "
            "that as a standing rule for this workspace.",
        )
    ],
    [
        _assistant_message(
            "msg_0002",
            "Noted: the orders service runs on PostgreSQL 16 and ships from the "
            "release branch. I will assume that stack for future answers.",
        )
    ],
    [
        _reasoning("rs_0001"),
        _function_call(
            "call_0001",
            "lookup_team_calendar",
            {"team": "platform", "horizon_days": 30},
        ),
    ],
    [
        _assistant_message(
            "msg_0003",
            "The platform team's deploy window is Tuesday 14:00-16:00 UTC, with no "
            "freeze in the next 30 days.",
        )
    ],
    [
        _assistant_message(
            "msg_0004",
            "Corrected: the deploy window is Thursday 09:00 UTC and the Tuesday slot "
            "is retired. I will use the Thursday window from now on.",
        )
    ],
    [
        _assistant_message(
            "msg_0005",
            "The three-sentence limit is dropped. I will answer in detail with bullet "
            "points from here on.",
        )
    ],
    [
        _assistant_message(
            "msg_0006",
            "Recorded your commitment: a migration plan for the orders service, due to "
            "the platform team by 2026-08-14.",
        )
    ],
    [
        _function_call(
            "call_0002",
            "record_incident",
            {
                "component": "pgbouncer",
                "summary": "Staging rollout failed: connection pool too small",
                "occurrences": 2,
            },
        )
    ],
    [
        _assistant_message(
            "msg_0007",
            "Logged as INC-2141 against pgbouncer, two occurrences, status open.",
        )
    ],
]

SMOKE_SCRIPT: list[list[Any]] = [
    [_assistant_message("msg_1001", "Sandbox session acknowledged.")]
]


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def _build_agent(script: list[list[Any]]) -> tuple[Agent, ScriptedModel]:
    model = ScriptedModel(script)
    agent = Agent(
        name="Workspace Buddy",
        instructions=(
            "You are a workspace assistant. Follow the user's standing rules and use "
            "the available tools when a question needs live data."
        ),
        model=model,
        tools=[lookup_team_calendar, record_incident],
    )
    return agent, model


async def run_scenario(db_path: Path, turn_delay: float) -> dict[str, int]:
    """Drive the real Runner + SQLiteSession across every scenario turn."""
    set_tracing_disabled(True)

    agent, model = _build_agent(SCRIPT)
    session = SQLiteSession(MAIN_SESSION_ID, str(db_path))
    try:
        for index, turn in enumerate(SCENARIO, start=1):
            result = await Runner.run(agent, turn.user, session=session)
            preview = " ".join(str(result.final_output).split())[:70]
            print(f"  turn {index} ({turn.note}): {preview}...")
            if turn_delay and index < len(SCENARIO):
                # Real elapsed time, so each turn lands in its own SQLite second
                # (CURRENT_TIMESTAMP has one-second resolution).
                time.sleep(turn_delay)
    finally:
        session.close()

    # A second session in the same database proves --list-sessions / --session.
    smoke_agent, smoke_model = _build_agent(SMOKE_SCRIPT)
    smoke_session = SQLiteSession(SMOKE_SESSION_ID, str(db_path))
    try:
        await Runner.run(smoke_agent, "Ping the sandbox.", session=smoke_session)
        print(f"  {SMOKE_SESSION_ID}: 1 turn")
    finally:
        smoke_session.close()

    return {"model_calls": model.calls + smoke_model.calls}


# ---------------------------------------------------------------------------
# Snapshot — commit the raw source rows as evidence (the .db itself is gitignored)
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _package_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("openai-agents")
    except PackageNotFoundError:  # pragma: no cover
        return "unknown"


def _read_snapshot_sha256(db_path: Path) -> str:
    """Hash the database the way the adapter does — via a consistent snapshot that
    includes WAL state — so the committed capture and the migration report can be
    checked against each other."""
    import okf_adapter

    with okf_adapter.consistent_snapshot(db_path) as snapshot:
        return _sha256(snapshot)


def write_snapshot(db_path: Path, snapshot_path: Path) -> dict[str, Any]:
    """Dump the database's schema and raw rows verbatim, for committed evidence."""
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        schema = dict(
            conn.execute(
                "SELECT name, sql FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        )
        sessions = [
            {"session_id": sid, "created_at": created, "updated_at": updated}
            for sid, created, updated in conn.execute(
                "SELECT session_id, created_at, updated_at FROM agent_sessions "
                "ORDER BY session_id"
            )
        ]
        messages = [
            {
                "id": row_id,
                "session_id": sid,
                "message_data": data,
                "created_at": created,
            }
            for row_id, sid, data, created in conn.execute(
                "SELECT id, session_id, message_data, created_at FROM agent_messages "
                "ORDER BY id"
            )
        ]
    finally:
        conn.close()

    snapshot = {
        "_comment": (
            "Verbatim dump of the SQLite database written by the OpenAI Agents SDK "
            "(agents.Runner + agents.SQLiteSession). Committed because *.db is "
            "gitignored; message_data holds the exact TEXT the SDK stored."
        ),
        "source": {
            "tool": "openai-agents (OpenAI Agents SDK) SQLiteSession",
            "package_version": _package_version(),
            "python": sys.version.split()[0],
            "db_file": db_path.name,
            # Raw main-file hash, for reference only: under WAL it can be
            # identical for two different logical states.
            "db_file_sha256": _sha256(db_path),
            # The authoritative one — matches the migration report's field.
            "read_snapshot_sha256": _read_snapshot_sha256(db_path),
        },
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "schema": schema,
        "agent_sessions": sessions,
        "agent_messages": messages,
    }
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Populate a real OpenAI Agents SDK SQLiteSession for migration."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("sample/source/agent_sessions.db"),
        help="Where to write the SDK's SQLite database.",
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=Path("sample/source/session_snapshot.json"),
        help="Where to dump the raw rows as committed evidence.",
    )
    parser.add_argument(
        "--turn-delay",
        type=float,
        default=1.1,
        help="Seconds between turns so each lands in its own SQLite second.",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Append to an existing database instead of starting fresh.",
    )
    args = parser.parse_args(argv)

    args.db.parent.mkdir(parents=True, exist_ok=True)
    if not args.keep:
        for suffix in ("", "-wal", "-shm"):
            Path(str(args.db) + suffix).unlink(missing_ok=True)

    print(f"openai-agents {_package_version()} -> {args.db}")
    stats = asyncio.run(run_scenario(args.db, args.turn_delay))

    snapshot = write_snapshot(args.db, args.snapshot)
    print(
        f"\nSessions : {len(snapshot['agent_sessions'])}\n"
        f"Items    : {len(snapshot['agent_messages'])}\n"
        f"Model    : {stats['model_calls']} scripted calls (no network)\n"
        f"Snapshot : {args.snapshot}\n"
        f"Read snapshot sha256: {snapshot['source']['read_snapshot_sha256']}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
