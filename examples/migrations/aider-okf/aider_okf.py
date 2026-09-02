"""Convert Aider's native Markdown chat history into an OKF 0.2 bundle."""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml  # type: ignore[import-untyped]

SESSION_PREFIX = "# aider chat started at "
ROLE_PREFIX = "#### "
SENSITIVE_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:sk-(?:proj-)?|gh[opusr]_|github_pat_)[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\b(?:api[_-]?key|token|password)\s*[:=]\s*[^\s]{8,}"),
)


@dataclass(frozen=True)
class AiderMessage:
    """One role-delimited record from Aider's append-only chat history."""

    session: int
    ordinal: int
    role: str
    content: str
    session_started_at: str | None


def _append(
    messages: list[AiderMessage],
    session: int,
    role: str,
    lines: list[str],
    started: str | None,
) -> None:
    content = "".join(lines).strip()
    if content:
        messages.append(
            AiderMessage(session, len(messages) + 1, role, content, started)
        )


def parse_aider_history(text: str, *, include_tools: bool = True) -> list[AiderMessage]:
    """Parse the same role markers used by Aider's ``split_chat_history_markdown``.

    Aider prefixes user input with ``#### `` and tool output with ``> ``;
    unprefixed text is assistant output. Session headings are metadata, not
    conversation content. Keeping the parser aligned with Aider's own format
    avoids inventing a provider schema.
    """

    messages: list[AiderMessage] = []
    user: list[str] = []
    assistant: list[str] = []
    tool: list[str] = []
    session = 0
    started: str | None = None

    def flush() -> None:
        nonlocal user, assistant, tool
        _append(messages, session, "assistant", assistant, started)
        _append(messages, session, "user", user, started)
        if include_tools:
            _append(messages, session, "tool", tool, started)
        user, assistant, tool = [], [], []

    for line in text.splitlines(keepends=True):
        if line.startswith(SESSION_PREFIX):
            flush()
            session += 1
            started = line[len(SESSION_PREFIX) :].strip() or None
            continue
        if line.startswith("# "):
            continue
        if line.startswith("> "):
            _append(messages, session, "assistant", assistant, started)
            assistant = []
            _append(messages, session, "user", user, started)
            user = []
            tool.append(line[2:])
            continue
        if line.startswith(ROLE_PREFIX):
            _append(messages, session, "assistant", assistant, started)
            assistant = []
            if include_tools:
                _append(messages, session, "tool", tool, started)
            tool = []
            user.append(line[len(ROLE_PREFIX) :])
            continue

        _append(messages, session, "user", user, started)
        user = []
        if include_tools:
            _append(messages, session, "tool", tool, started)
        tool = []
        assistant.append(line)

    flush()
    return [message for message in messages if include_tools or message.role != "tool"]


def find_sensitive_data(text: str) -> list[str]:
    """Return pattern labels only; never echo a matched secret."""

    return [
        f"pattern-{index}"
        for index, pattern in enumerate(SENSITIVE_PATTERNS, 1)
        if pattern.search(text)
    ]


def _timestamp(value: str | None) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _title(message: AiderMessage) -> str:
    first = next(
        (line.strip() for line in message.content.splitlines() if line.strip()),
        message.role,
    )
    # Strip Markdown decoration without damaging code identifiers such as
    # ``assistant_profile.md``.
    first = re.sub(r"[`*#]", "", first)
    return f"Aider {message.role} {message.ordinal}: {first[:72]}".strip()


def render_okf(message: AiderMessage, source_digest: str, message_digest: str) -> str:
    """Render one source message as human-readable OKF Markdown."""

    timestamp = _timestamp(message.session_started_at)
    frontmatter = {
        "type": "context" if message.role != "user" else "instruction",
        "title": _title(message),
        "description": f"A {message.role} record imported from a genuine Aider chat history.",
        "resource": f"aider://history/{source_digest}#message-{message.ordinal}",
        "tags": ["aider", "coding-agent", f"role-{message.role}"],
        "timestamp": timestamp,
        "x_memanto": {
            "source": "aider",
            "source_ref": f"aider://history/{source_digest}#message-{message.ordinal}",
            "provenance": "imported",
            "status": "active",
            "created_at": timestamp,
        },
        "x_aider": {
            "session": message.session,
            "ordinal": message.ordinal,
            "role": message.role,
            "content_sha256": message_digest,
            "source_sha256": source_digest,
        },
    }
    header = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{header}\n---\n\n# {message.role.title()}\n\n{message.content}\n"


def convert(
    source: Path, output: Path, *, include_tools: bool = True
) -> dict[str, object]:
    """Convert one Aider history file, refusing secrets and stale output."""

    raw = source.read_text(encoding="utf-8")
    findings = find_sensitive_data(raw)
    if findings:
        raise ValueError(f"source failed privacy preflight ({', '.join(findings)})")
    messages = parse_aider_history(raw, include_tools=include_tools)
    if not messages:
        raise ValueError("source contains no Aider messages")
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")

    source_digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))
    try:
        memories = staging / "memories"
        memories.mkdir()
        index_links: list[str] = []
        counts: dict[str, int] = {}
        for message in messages:
            digest = hashlib.sha256(message.content.encode("utf-8")).hexdigest()
            filename = f"{message.ordinal:03d}-{message.role}.md"
            (memories / filename).write_text(
                render_okf(message, source_digest, digest), encoding="utf-8"
            )
            index_links.append(f"- [{_title(message)}](memories/{filename})")
            counts[message.role] = counts.get(message.role, 0) + 1

        (staging / "index.md").write_text(
            "---\ntype: index\ntitle: Aider memory export\n---\n\n"
            f"# Aider memory export\n\nSource SHA-256: `{source_digest}`\n\n"
            + "\n".join(index_links)
            + "\n",
            encoding="utf-8",
        )
        staging.rename(output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return {
        "source_records": len(messages),
        "mapped_memories": len(messages),
        "skipped": 0,
        "per_role": counts,
        "source_sha256": source_digest,
        "output": str(output),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Aider .aider.chat.history.md file")
    parser.add_argument("output", type=Path, help="New OKF output directory")
    parser.add_argument(
        "--exclude-tools", action="store_true", help="omit Aider tool records"
    )
    args = parser.parse_args(argv)
    result = convert(args.source, args.output, include_tools=not args.exclude_tools)
    print(yaml.safe_dump(result, sort_keys=False).strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
