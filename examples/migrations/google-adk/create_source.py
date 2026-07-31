#!/usr/bin/env python3
"""Create a real Google ADK 2.6 SQLite source store for the showcase."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from scenario import APP_NAME, SESSIONS, USER_ID


def _epoch(value: str, offset_seconds: int) -> float:
    return (
        datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        + offset_seconds
    )


async def create_database(path: Path, *, force: bool = False) -> dict[str, Any]:
    """Populate ``path`` exclusively through the public Google ADK API."""
    try:
        import google.adk
        from google.adk.events import Event, EventActions
        from google.adk.sessions.sqlite_session_service import SqliteSessionService
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError(
            "google-adk is required. Run: uv pip install google-adk==2.6.0"
        ) from exc

    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not force:
            raise RuntimeError(f"Source database already exists: {path}")
        path.unlink()

    service = SqliteSessionService(str(path))
    events_written = 0
    state_updates = 0
    for session_number, source_session in enumerate(SESSIONS, 1):
        session = await service.create_session(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=source_session["id"],
        )
        for turn_number, turn in enumerate(source_session["turns"], 1):
            delta = dict(turn.get("state_delta") or {})
            event = Event(
                invocation_id=f"inv-{session_number:02d}-{turn_number:02d}",
                author=turn["author"],
                content=types.Content(
                    role="user" if turn["author"] == "user" else "model",
                    parts=[types.Part(text=turn["text"])],
                ),
                actions=EventActions(state_delta=delta),
                timestamp=_epoch(source_session["timestamp"], turn_number),
            )
            await service.append_event(session=session, event=event)
            events_written += 1
            state_updates += len(delta)

    final_session = await service.get_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=SESSIONS[-1]["id"],
    )
    return {
        "schema": "google-adk-source-run/v1",
        "generator": "create_source.py",
        "google_adk_version": getattr(google.adk, "__version__", "unknown"),
        "service": "google.adk.sessions.SqliteSessionService",
        "database_name": path.name,
        "app_name": APP_NAME,
        "user_id": USER_ID,
        "sessions_created": len(SESSIONS),
        "events_written": events_written,
        "state_updates_written": state_updates,
        "final_merged_state_keys": sorted(
            (final_session.state if final_session else {}).keys()
        ),
        "used_public_service_api": True,
        "used_raw_sql_in_generator": False,
        "used_llm": False,
        "llm_disclosure": (
            "The run is deterministic and offline: scripted user/agent turns are "
            "persisted by the official ADK service without calling an LLM."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", "-o", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--evidence", type=Path, help="Optional JSON run evidence path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        evidence = asyncio.run(create_database(args.output, force=args.force))
    except (RuntimeError, OSError) as exc:
        print(f"error: {exc}")
        return 2
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(
        f"OK: Google ADK {evidence['google_adk_version']} wrote "
        f"{evidence['sessions_created']} sessions and {evidence['events_written']} "
        f"events to {args.output.resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
