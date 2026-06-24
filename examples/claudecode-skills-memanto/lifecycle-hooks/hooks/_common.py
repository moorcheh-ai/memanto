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
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Make the sibling ``memanto_skills`` package importable whether or not the
# example has been pip-installed.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


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
        from memanto_skills import SkillMemory

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
    _, rendered = _read_transcript_full(
        transcript_path, max_messages=max_messages, max_chars=max_chars
    )
    return rendered


def read_transcript_for_distillation(
    transcript_path: str | None,
    max_messages: int = 40,
    max_chars: int = 8000,
) -> tuple[str | None, str]:
    """Return ``(skill, tail_text)`` from a single pass over the transcript.

    Long sessions truncate to the tail for the LLM (the latest discussion is
    where decisions usually crystallise), but the user's original ``/tdd`` or
    ``/grill-with-docs`` invocation typically sits at the very start of the
    conversation and would fall outside that tail. We scan the entire
    transcript for the first skill token, then return it alongside the
    truncated text so ``distill_and_store`` can tag memories correctly even
    on long sessions.
    """
    return _read_transcript_full(
        transcript_path, max_messages=max_messages, max_chars=max_chars
    )


def _read_transcript_full(
    transcript_path: str | None,
    max_messages: int,
    max_chars: int,
) -> tuple[str | None, str]:
    """Read the transcript once and return (first-skill-seen, tail-text)."""
    if not transcript_path:
        return None, ""
    path = Path(transcript_path)
    if not path.exists():
        return None, ""

    try:
        with path.open(encoding="utf-8") as fh:
            lines = fh.readlines()
    except Exception:
        return None, ""

    pieces: list[str] = []
    skill: str | None = None
    for line in lines:
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
        # First skill mention wins — typically the opening user prompt.
        if skill is None:
            found = detect_skill(text)
            if found:
                skill = found
        pieces.append(f"{role}: {text}" if role else text)

    rendered = "" if max_messages <= 0 else "\n".join(pieces[-max_messages:])
    if max_chars <= 0:
        return skill, ""
    return skill, rendered[-max_chars:]


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
