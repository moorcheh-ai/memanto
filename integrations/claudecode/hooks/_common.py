"""Shared plumbing for the three Claude Code lifecycle hooks.

Design rules (these hooks run on the developer's hot path):

* **Never break Claude Code.** Any internal failure exits 0 silently. A memory
  companion that crashes the editor is worse than one that misses a memory.
* **Stay fast.** ``SessionStart`` and ``UserPromptExpansion`` gate the user, so we
  keep them lean. Heavy LLM distillation lives in ``Stop`` (registered async).
* **Be schema-tolerant.** The transcript line format is not officially pinned,
  so we extract text from whatever shape we find.

Input fields follow the official Claude Code hooks reference: common fields are
``session_id``, ``transcript_path``, ``cwd``, ``permission_mode``,
``hook_event_name``; ``UserPromptExpansion`` additionally carries ``prompt``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Make the sibling ``claudecode_memanto`` package importable whether or not the
# example has been pip-installed.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger(__name__)


def run(main: Callable[[], int]) -> None:
    """Execute a hook entry point under the never-break-Claude contract.

    This is the single place that guarantees a hook process exits 0: a nonzero
    exit would surface an error notice in the editor (or, for Stop hooks with
    exit code 2, block the session from stopping). Every hook's ``__main__``
    block goes through here so no individual hook can forget the contract.
    """
    try:
        code = main()
    except Exception:
        code = 0
    raise SystemExit(code)


def read_hook_input() -> dict[str, Any]:
    """Parse the hook's stdin JSON. Returns {} if absent/malformed."""
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def emit_additional_context(event_name: str, context: str) -> None:
    """Print the JSON that injects ``context`` for Claude to read.

    Matches the documented output shape:
        {"hookSpecificOutput": {"hookEventName": ..., "additionalContext": ...}}
    """
    if not context:
        return
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": event_name,
                "additionalContext": context,
            }
        },
        sys.stdout,
    )
    sys.stdout.write("\n")


# Matches a skill invocation like "/tdd" or "/grill-with-docs". The trailing
# negative lookahead rejects path-like tokens ("/usr/local/bin" is not a skill).
_SKILL_RE = re.compile(r"(?:^|\s)/([a-z][a-z0-9-]+)\b(?!/)", re.IGNORECASE)


def detect_skill(text: str | None) -> str | None:
    """Extract the first ``/skill`` token from text, else None."""
    if not text:
        return None
    m = _SKILL_RE.search(text)
    return m.group(1).lower() if m else None


def memory_enabled() -> bool:
    """Cheap hot-path gate: is an API key present at all?

    This deliberately duplicates one line of ``SkillsConfig.from_env`` so that
    hooks can no-op without importing the Memanto SDK (a substantial import on
    a path that runs every prompt). ``get_memory`` remains the authoritative
    check — it returns None for any configuration problem.
    """
    return bool((os.environ.get("MOORCHEH_API_KEY") or "").strip())


def get_memory():
    """Construct a SkillMemory, or None if config/import fails."""
    try:
        from claudecode_memanto import SkillMemory

        return SkillMemory()
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Transcript reading (schema-tolerant)
# --------------------------------------------------------------------------- #


def read_transcript_text(
    transcript_path: str | None,
    max_messages: int = 40,
    max_chars: int = 8000,
) -> str:
    """Return a plain-text rendering of the most recent transcript messages.

    The transcript is JSONL (one JSON object per line). We do not assume a
    fixed schema: we walk each entry and pull any human-readable text we can
    find (string content, or content blocks carrying a ``text`` field),
    labelling it by role when available. Returns the trailing ``max_chars``.
    """
    messages = _read_transcript_messages(transcript_path)
    return _render_messages(messages, max_messages=max_messages, max_chars=max_chars)


def read_transcript_for_distillation(
    transcript_path: str | None,
    last_assistant_message: str | None = None,
    max_messages: int = 40,
    max_chars: int = 8000,
) -> tuple[str | None, str]:
    """Return ``(skill, current_turn_text)`` for one Stop-hook invocation.

    Claude Code fires ``Stop`` once per turn, not once per session. Re-sending
    the cumulative transcript on every invocation makes earlier decisions get
    extracted and stored repeatedly. Scope distillation to the latest user
    turn instead, while retaining the most recent skill invocation for tags.

    Async hooks can read the transcript after a newer turn has already been
    appended. ``last_assistant_message`` anchors the snapshot to the turn that
    triggered this hook so two overlapping hook processes cannot both ingest
    the newest turn.
    """
    messages = _read_transcript_messages(transcript_path)
    if not messages:
        return None, ""

    end = _anchored_end(messages, last_assistant_message)
    if end is None:
        return None, ""
    scoped = messages[:end]

    skill: str | None = None
    for role, text in scoped:
        if _is_user_role(role):
            found = detect_skill(text)
            if found:
                skill = found

    turn_start = 0
    for index in range(len(scoped) - 1, -1, -1):
        if _is_user_role(scoped[index][0]):
            turn_start = index
            break

    rendered = _render_messages(
        scoped[turn_start:], max_messages=max_messages, max_chars=max_chars
    )
    return skill, rendered


def _read_transcript_messages(
    transcript_path: str | None,
) -> list[tuple[str | None, str]]:
    """Read parseable prose messages from a Claude Code transcript."""
    if not transcript_path:
        return []
    path = Path(transcript_path)
    if not path.exists():
        return []

    messages: list[tuple[str | None, str]] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                role, text = _extract_role_text(entry)
                if not text:
                    continue
                messages.append((str(role) if role is not None else None, text))
    except Exception:
        logger.debug("Failed to read Claude Code transcript", exc_info=True)
        return []

    return messages


def _render_messages(
    messages: list[tuple[str | None, str]],
    *,
    max_messages: int,
    max_chars: int,
) -> str:
    """Render a bounded transcript slice for LLM distillation."""
    pieces = [f"{role}: {text}" if role else text for role, text in messages]
    rendered = "\n".join(pieces[-max_messages:])
    return rendered[-max_chars:]


def _is_user_role(role: str | None) -> bool:
    """Recognise user roles across the common transcript variants."""
    return bool(role and role.strip().lower() in {"user", "human"})


def _is_assistant_role(role: str | None) -> bool:
    """Recognise assistant roles across the common transcript variants."""
    return bool(role and role.strip().lower() in {"assistant", "ai"})


def _anchored_end(
    messages: list[tuple[str | None, str]],
    last_assistant_message: str | None,
) -> int | None:
    """Return the unique exclusive end index for the Stop event's own turn.

    Missing, stale, or ambiguous anchors fail closed so an asynchronous hook
    cannot silently distill a newer or duplicated turn.
    """
    if not last_assistant_message or not last_assistant_message.strip():
        return None

    needle = " ".join(last_assistant_message.split())
    matches: list[int] = []
    for index, (role, text) in enumerate(messages):
        if _is_assistant_role(role) and " ".join(text.split()) == needle:
            matches.append(index + 1)

    return matches[0] if len(matches) == 1 else None


def _extract_role_text(entry: Any) -> tuple[str | None, str]:
    """Best-effort (role, text) extraction from one transcript entry."""
    if not isinstance(entry, dict):
        return None, ""

    message = entry.get("message", entry)
    role = None
    if isinstance(message, dict):
        role = message.get("role") or entry.get("role") or entry.get("type")
        content = message.get("content")
    else:
        content = entry.get("content")

    return role, _flatten_content(content)


def _flatten_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        out: list[str] = []
        for block in content:
            if isinstance(block, str):
                out.append(block)
            elif isinstance(block, dict):
                # Common block shapes: {"type":"text","text":"..."}; tool blocks
                # are skipped to keep the summary focused on prose.
                if block.get("type") in (None, "text") and block.get("text"):
                    out.append(str(block["text"]))
        return " ".join(s.strip() for s in out if s.strip())
    return ""
