"""Export actual Haystack chat-store snapshots to a scoped, inspectable OKF bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path
from typing import Any

import yaml
from haystack.dataclasses import ChatMessage

from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle

FORMAT = "haystack-chat-store-v1"
MAX_EXPORT_BYTES = 8 * 1024 * 1024
MAX_MESSAGES = 1000
MAX_BODY_CHARS = 8000


def reconstruct(content: str) -> dict[str, Any]:
    """Read only the unquoted canonical wrapper, never a transcript substring."""
    matches = re.findall(
        r"^<!-- haystack-source-json -->\n```json\n(.*?)\n```\n<!-- /haystack-source-json -->$",
        content,
        re.MULTILINE | re.DOTALL,
    )
    if len(matches) != 1:
        raise ValueError("Expected exactly one intact Haystack source envelope")
    envelope = json.loads(matches[0])
    if not isinstance(envelope, dict) or not isinstance(
        envelope.get("session_id"), str
    ):
        raise ValueError("Invalid source envelope")
    if type(envelope.get("position")) is not int or envelope["position"] < 0:
        raise ValueError("Invalid source position")
    ChatMessage.from_dict(envelope["message"])
    return envelope


def load_snapshot(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_EXPORT_BYTES:
        raise ValueError("Snapshot exceeds 8 MiB; export one session at a time")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("format") != FORMAT:
        raise ValueError(f"Expected an actual source snapshot with format {FORMAT}")
    sessions = value.get("sessions")
    if not isinstance(sessions, dict) or not sessions:
        raise ValueError("Snapshot needs at least one named session")
    return value


def render_session(snapshot: dict[str, Any], session_id: str) -> dict[str, str]:
    """Require explicit scope; do not mix different users' histories by default."""
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("Session ID must be a nonempty string")
    sessions = snapshot.get("sessions", {})
    if session_id not in sessions:
        raise ValueError("Requested session is absent from the snapshot")
    messages = sessions[session_id]
    if not isinstance(messages, list) or not messages:
        raise ValueError("Selected session is empty or malformed")
    if len(messages) > MAX_MESSAGES:
        raise ValueError("Session exceeds the 1000-message example limit")
    files: dict[str, str] = {}
    links = []
    for position, message in enumerate(messages):
        if not isinstance(message, dict):
            raise ValueError(f"Message {position} is not a serialized ChatMessage")
        role = message.get("role")
        parts = message.get("content")
        if role not in {"user", "assistant", "system", "tool"}:
            raise ValueError(f"Message {position} has an unsupported role")
        if not isinstance(parts, list) or not parts:
            raise ValueError(f"Message {position} has no content parts")
        if any(not isinstance(part, dict) for part in parts):
            raise ValueError(f"Message {position} has malformed content parts")
        if any(
            set(part) not in ({"text"}, {"tool_call"}, {"tool_call_result"})
            for part in parts
        ):
            raise ValueError(
                f"Message {position}: only text and tool content are supported"
            )
        ChatMessage.from_dict(message)
        # Preserve the complete source object, including tool calls, original
        # metadata and unknown fields. No inferred preferences or fabricated dates.
        envelope = {"session_id": session_id, "position": position, "message": message}
        canonical = json.dumps(envelope, ensure_ascii=False, sort_keys=True, indent=2)
        source_key = hashlib.sha256(
            f"{session_id}\0{position}\0{canonical}".encode()
        ).hexdigest()[:24]
        # JSON escapes protect the OKF entry sentinel/frontmatter from source text.
        canonical = canonical.replace("<", "\\u003c").replace(">", "\\u003e")
        text_parts = [
            part["text"] for part in parts if isinstance(part.get("text"), str)
        ]
        readable = "\n\n".join(text_parts)
        # Keep arbitrary source Markdown inert in the readable transcript; the
        # canonical JSON below remains the exact reconstruction source.
        readable = "\n".join("> " + line for line in readable.splitlines())
        readable = readable.replace("<!-- okf-entry -->", "&lt;!-- okf-entry --&gt;")
        body = (
            f"Haystack session message {position}, role: {role}.\n\n"
            f"{readable}\n\n"
            f"Source session: {json.dumps(session_id, ensure_ascii=False)}\n"
            f"Source position: {position}\n\n"
            "<!-- haystack-source-json -->\n```json\n"
            f"{canonical}\n```\n<!-- /haystack-source-json -->"
        )
        if len(body) > MAX_BODY_CHARS:
            raise ValueError(
                f"Message {position} exceeds the lossless 8000-character budget; "
                "nothing was written"
            )
        if "<!-- okf-entry -->" in body:
            raise ValueError("Session identifier contains an OKF delimiter")
        frontmatter = {
            "type": "observation",
            "title": f"Haystack {source_key}: {role} message {position}",
            "resource": f"haystack-chat:{source_key}",
            "tags": ["haystack", "chat-history", f"role-{role}"],
            "x_memanto": {
                "type": "observation",
                "source": "haystack",
                "provenance": "imported",
            },
        }
        path = f"memories/{position:06d}-{source_key}.md"
        files[path] = (
            "---\n"
            + yaml.safe_dump(frontmatter, sort_keys=False)
            + "---\n"
            + body
            + "\n"
        )
        links.append(f"- [{position}: {role}]({path})")
    files["index.md"] = (
        "---\ntype: index\ntitle: Haystack conversation memory\n---\n"
        "# Haystack conversation memory\n\n"
        "A single explicitly selected session; message order and roles are preserved.\n"
        "These are recorded observations, not automatically inferred user facts.\n\n"
        + "\n".join(links)
        + "\n"
    )
    return files


def write_bundle(
    snapshot: dict[str, Any], session_id: str, output: Path
) -> dict[str, int]:
    files = render_session(snapshot, session_id)
    # The CLI mapper has bounded fields. Check its actual output before writing
    # or uploading so changes to that contract cannot silently truncate a source.
    if output.exists():
        raise FileExistsError(
            "Output exists; choose a new directory to preserve prior evidence"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        staging = Path(temp) / "bundle"
        for name, text in files.items():
            path = staging / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        rows = map_okf(load_okf_bundle(staging))
        recovered = [reconstruct(row["content"]) for row in rows]
        expected = [
            {"session_id": session_id, "position": p, "message": m}
            for p, m in enumerate(snapshot["sessions"][session_id])
        ]
        if recovered != expected:
            raise ValueError(
                "The installed Memanto mapper does not preserve this session"
            )
        staging.rename(output)
    return {"source_messages": len(files) - 1, "okf_memories": len(files) - 1}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--session", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            write_bundle(load_snapshot(args.snapshot), args.session, args.output)
        )
    )


if __name__ == "__main__":
    main()
