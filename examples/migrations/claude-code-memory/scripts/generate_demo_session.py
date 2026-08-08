"""Generate a realistic Claude Code session archive for the demo.

The generator writes a ``.jsonl`` file in the exact schema Claude Code uses
(top-level ``type``, nested ``message``, ``content`` blocks, timestamps,
session metadata). It produces a believable multi-turn session where a
developer asks Claude to build a FastAPI service, expresses preferences,
makes decisions, and captures instructions/commitments.

Run:
    python scripts/generate_demo_session.py --output demo_source/demo_session.jsonl
"""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Fixed namespace so every run produces the exact same archive (byte-stable
# demo artifact). Labels identify each record within the session.
_DEMO_NS = uuid.UUID("d13f8f06-9b63-4b3a-9f04-7f9a1c2d3e4f")


def _uuid(label: str) -> str:
    """Return a deterministic UUID for a demo record label."""
    return str(uuid.uuid5(_DEMO_NS, label))


def _ts(base: datetime, minutes: int) -> str:
    """Return an ISO-8601 timestamp offset from the session start."""
    return (base + timedelta(minutes=minutes)).isoformat(timespec="milliseconds")


def _turn(
    *,
    msg_type: str,
    role: str,
    content,
    timestamp: str,
    session_id: str,
    cwd: str,
    branch: str,
    message_id: str | None = None,
    parent: str | None = None,
    is_meta: bool = False,
) -> dict:
    """Build one Claude Code JSONL record from its parts."""
    return {
        "parentUuid": parent,
        "isSidechain": False,
        "userType": "external",
        "cwd": cwd,
        "sessionId": session_id,
        "version": "2.1.74",
        "gitBranch": branch,
        "type": msg_type,
        "message": {
            "role": role,
            "content": content,
        },
        "uuid": message_id or _uuid(),
        "timestamp": timestamp,
        "isMeta": is_meta,
    }


def _user_text(text: str, **kwargs) -> dict:
    """Build a user message record with string content."""
    return _turn(msg_type="user", role="user", content=text, **kwargs)


def _assistant_text(text: str, **kwargs) -> dict:
    """Build an assistant message record with a text content block."""
    content = [{"type": "text", "text": text}]
    return _turn(
        msg_type="assistant",
        role="assistant",
        content=content,
        **kwargs,
    )


def generate_session(output: Path) -> Path:
    """Generate and write a realistic demo session archive."""
    session_id = _uuid("demo-session")
    cwd = r"I:\project\payments-api"
    branch = "main"
    base = datetime(2026, 7, 28, 9, 0, tzinfo=timezone.utc)

    lines: list[dict] = []
    message_ids: list[str] = []

    # Snapshot (no content; adapter must skip it).
    lines.append(
        {
            "type": "file-history-snapshot",
            "messageId": _uuid("snapshot-message"),
            "snapshot": {
                "messageId": _uuid("snapshot-inner"),
                "trackedFileBackups": {},
                "timestamp": _ts(base, 0),
            },
            "isSnapshotUpdate": False,
        }
    )

    # Turn 1: user asks to build a payment service.
    m1 = _uuid("turn-1-user")
    message_ids.append(m1)
    lines.append(
        _user_text(
            "Build a FastAPI payment service with Stripe integration. "
            "I prefer SQLAlchemy over raw SQL, and we need PostgreSQL for production.",
            timestamp=_ts(base, 1),
            session_id=session_id,
            cwd=cwd,
            branch=branch,
            message_id=m1,
        )
    )

    # Turn 1 assistant: confirms plan.
    m2 = _uuid("turn-1-assistant")
    message_ids.append(m2)
    lines.append(
        _assistant_text(
            "Great, I will scaffold the FastAPI app with SQLAlchemy models, "
            "Stripe webhook handling, and a PostgreSQL schema. Let's start with the project layout.",
            timestamp=_ts(base, 3),
            session_id=session_id,
            cwd=cwd,
            branch=branch,
            message_id=m2,
            parent=m1,
        )
    )

    # Turn 2: user preference + instruction.
    m3 = _uuid("turn-2-user")
    message_ids.append(m3)
    lines.append(
        _user_text(
            "Remember to always use pydantic v2 for request validation, "
            "and please never log raw API keys. Also, my team prefers black formatting.",
            timestamp=_ts(base, 5),
            session_id=session_id,
            cwd=cwd,
            branch=branch,
            message_id=m3,
            parent=m2,
        )
    )

    # Turn 2 assistant: acknowledges + decision.
    m4 = _uuid("turn-2-assistant")
    message_ids.append(m4)
    lines.append(
        _assistant_text(
            "Understood. We will use pydantic v2, keep secrets out of logs, "
            "and format with black. I decided to put the Stripe client behind an interface "
            "so tests can mock it easily.",
            timestamp=_ts(base, 7),
            session_id=session_id,
            cwd=cwd,
            branch=branch,
            message_id=m4,
            parent=m3,
        )
    )

    # Turn 3: user states a fact/goal and commitment.
    m5 = _uuid("turn-3-user")
    message_ids.append(m5)
    lines.append(
        _user_text(
            "The payments API must be PCI compliant. We have a compliance review "
            "meeting on Aug 10, and I need to finish the webhook handler tomorrow.",
            timestamp=_ts(base, 9),
            session_id=session_id,
            cwd=cwd,
            branch=branch,
            message_id=m5,
            parent=m4,
        )
    )

    # Turn 3 assistant: plan summary.
    m6 = _uuid("turn-3-assistant")
    message_ids.append(m6)
    lines.append(
        _assistant_text(
            "I will keep the webhook handler idempotent, add PCI-relevant logging, "
            "and prepare a compliance checklist. The Aug 10 review is noted as a deadline.",
            timestamp=_ts(base, 11),
            session_id=session_id,
            cwd=cwd,
            branch=branch,
            message_id=m6,
            parent=m5,
        )
    )

    # Turn 4: user context about team/relationship.
    m7 = _uuid("turn-4-user")
    message_ids.append(m7)
    lines.append(
        _user_text(
            "My colleague Sarah works on the mobile app and needs our API docs. "
            "Our goal is to ship the beta by September.",
            timestamp=_ts(base, 13),
            session_id=session_id,
            cwd=cwd,
            branch=branch,
            message_id=m7,
            parent=m6,
        )
    )

    # Turn 4 assistant: closing summary.
    m8 = _uuid("turn-4-assistant")
    message_ids.append(m8)
    lines.append(
        _assistant_text(
            "Sounds good. I will generate OpenAPI docs for Sarah, and keep the "
            "September beta as the target milestone.",
            timestamp=_ts(base, 15),
            session_id=session_id,
            cwd=cwd,
            branch=branch,
            message_id=m8,
            parent=m7,
        )
    )

    # Tool traffic (excluded from memory text by the adapter).
    m9 = _uuid("turn-5-tool")
    message_ids.append(m9)
    lines.append(
        _turn(
            msg_type="assistant",
            role="assistant",
            content=[
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "Bash",
                    "input": {"command": "uvicorn app.main:app --reload"},
                }
            ],
            timestamp=_ts(base, 17),
            session_id=session_id,
            cwd=cwd,
            branch=branch,
            message_id=m9,
            parent=m8,
        )
    )

    # Last prompt sentinel.
    lines.append(
        {
            "type": "last-prompt",
            "lastPrompt": "Build a FastAPI payment service with Stripe integration.",
            "sessionId": session_id,
        }
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as fh:
        for item in lines:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    return output


def main() -> int:
    """Generate the demo session archive from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="demo_source/demo_session.jsonl",
        help="Output JSONL path",
    )
    args = parser.parse_args()
    path = generate_session(Path(args.output))
    print(f"Demo session written to {path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
