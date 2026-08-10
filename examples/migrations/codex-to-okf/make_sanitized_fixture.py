#!/usr/bin/env python3
"""Create a deterministic, publishable fixture from a genuine Codex rollout.

The output preserves visible message text after the same privacy pass used by
the adapter. Session IDs and message IDs are replaced, while a SHA-256 digest
keeps the fixture's lineage independently verifiable without publishing the
raw rollout.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from codex_to_okf import read_rollout, sha256_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    session_meta, messages, _audit = read_rollout(args.source)
    source_digest = sha256_file(args.source)
    fixture_id = f"sanitized-{source_digest[:16]}"
    meta_timestamp = str(
        session_meta.get("timestamp")
        or (messages[0].timestamp if messages else "1970-01-01T00:00:00Z")
    )
    records: list[dict[str, object]] = [
        {
            "timestamp": meta_timestamp,
            "type": "session_meta",
            "payload": {
                "session_id": fixture_id,
                "id": fixture_id,
                "timestamp": meta_timestamp,
                "source": "privacy-sanitized genuine rollout fixture",
                "source_sha256": source_digest,
            },
        }
    ]
    for index, message in enumerate(messages, start=1):
        content_type = "input_text" if message.role == "user" else "output_text"
        payload: dict[str, object] = {
            "type": "message",
            "id": f"message-{index:03d}",
            "role": message.role,
            "content": [{"type": content_type, "text": message.text}],
        }
        records.append(
            {
                "timestamp": message.timestamp,
                "type": "response_item",
                "payload": payload,
            }
        )

    redacted_records = 0
    with args.source.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            record_type = str(raw.get("type") or "unknown")
            payload = raw.get("payload")
            if record_type == "session_meta":
                continue
            if isinstance(payload, dict):
                payload_type = str(payload.get("type") or "redacted")
                role = str(payload.get("role") or "")
                if (
                    record_type == "response_item"
                    and payload_type == "message"
                    and role in {"user", "assistant"}
                ):
                    continue
            else:
                payload_type, role = "redacted", ""

            safe_payload: dict[str, object] = {"redacted": True}
            if record_type == "response_item":
                safe_payload["type"] = payload_type
                if payload_type == "message":
                    safe_payload["role"] = role
                    safe_payload["content"] = []
            records.append(
                {
                    "timestamp": raw.get("timestamp", meta_timestamp),
                    "type": record_type,
                    "payload": safe_payload,
                }
            )
            redacted_records += 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "messages": len(messages),
                "redacted_records": redacted_records,
                "source_sha256": source_digest,
                "fixture_session_id": fixture_id,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
