"""Export one real Goose SQLite session as a privacy-safe JSON fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from goose_sessions_to_okf import read_sessions_db, redact_text, utc_timestamp


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_session(
    database: Path,
    *,
    session_id: str | None,
    session_name: str | None,
    goose_version: str,
) -> dict:
    session = next(
        (
            candidate
            for candidate in read_sessions_db(database)
            if (session_id is not None and candidate.session_id == session_id)
            or (session_name is not None and candidate.description == session_name)
        ),
        None,
    )
    if session is None:
        wanted = session_id or session_name
        raise ValueError(f"session {wanted!r} was not found in {database}")

    messages = [
        {
            "role": message.role,
            "created_at": message.timestamp,
            "content": redact_text(message.content),
        }
        for message in session.messages or []
    ]
    return {
        "id": session.session_id,
        "description": redact_text(session.description),
        "working_dir": redact_text(session.working_dir or ""),
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "provider": session.provider,
        "model": session.model,
        "total_tokens": session.total_tokens,
        "input_tokens": session.input_tokens,
        "output_tokens": session.output_tokens,
        "messages": messages,
        "capture": {
            "source": f"sessions.db#{session.session_id}",
            "source_sha256": file_sha256(database),
            "goose_version": goose_version,
            "exported_at": utc_timestamp(),
            "redacted": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--session-id")
    selector.add_argument("--session-name")
    parser.add_argument("--goose-version", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    payload = export_session(
        args.database,
        session_id=args.session_id,
        session_name=args.session_name,
        goose_version=args.goose_version,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["capture"], indent=2))


if __name__ == "__main__":
    main()
