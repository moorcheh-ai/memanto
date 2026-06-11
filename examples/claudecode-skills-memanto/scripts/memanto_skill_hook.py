#!/usr/bin/env python3
"""Claude Code skill lifecycle hook backed by Memanto.

The hook has two modes:

* ``pre`` reads the incoming Claude Code hook payload, builds a task-aware
  query, recalls relevant Memanto memories, and prints them as prompt context.
* ``post`` reads the completed transcript, extracts durable engineering signals,
  and stores a compact interaction summary in Memanto.

It intentionally depends only on the ``memanto`` CLI. Any Memanto failure is
reported to stderr and exits 0 so hooks never block the developer workflow.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_LIMIT = 8
DEFAULT_TIMEOUT_SECONDS = 30
MAX_QUERY_CHARS = 1200
MAX_MEMORY_CHARS = 6000
MAX_TRANSCRIPT_LINES = 80
SIGNAL_PATTERN = re.compile(
    r"\b(architect(?:ure|ural)?|avoid|bug|chose|constraint|decision|decided|"
    r"error|fixed|lesson|learned|must|never|prefer|preference|root cause|"
    r"should|standard|use|using|went with)\b",
    re.IGNORECASE,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("pre", "post", "sync"))
    parser.add_argument(
        "--limit", type=int, default=_int_env("MEMANTO_SKILL_LIMIT", DEFAULT_LIMIT)
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=_int_env("MEMANTO_SKILL_TIMEOUT", DEFAULT_TIMEOUT_SECONDS),
    )
    args = parser.parse_args()

    if os.environ.get("MEMANTO_SKILL_HOOK_DISABLED"):
        return 0

    event = _read_stdin_json()

    try:
        if args.mode == "sync":
            _run_memanto(["memory", "sync", "--project-dir", "."], args.timeout)
        elif args.mode == "pre":
            _pre_skill(event, args.limit, args.timeout)
        else:
            _post_skill(event, args.timeout)
    except Exception as exc:  # pragma: no cover - defensive hook behavior
        _log(f"Memanto skill hook skipped: {exc}")

    return 0


def _pre_skill(event: dict[str, Any], limit: int, timeout: int) -> None:
    skill_name = _skill_name(event)
    prompt = _event_text(event)
    query = _truncate(
        " ".join(
            part
            for part in [
                f"Claude Code skill {skill_name}"
                if skill_name
                else "Claude Code skill",
                f"cwd {_cwd(event)}",
                prompt,
            ]
            if part
        ),
        MAX_QUERY_CHARS,
    )

    if not query.strip():
        return

    recall = _run_memanto(["recall", query, "--limit", str(limit)], timeout)
    if not recall.strip():
        return

    print(_format_recall_context(skill_name, recall))


def _post_skill(event: dict[str, Any], timeout: int) -> None:
    transcript_text = _read_transcript_excerpt(event)
    prompt = _event_text(event)
    skill_name = _skill_name(event)
    signals = _extract_signals("\n".join([prompt, transcript_text]))

    if not signals and len(transcript_text.strip()) < 80:
        return

    memory = _build_memory(skill_name, prompt, signals, transcript_text)
    if len(memory) < 80:
        return

    tags = ["claude-code", "skills-memanto"]
    if skill_name:
        tags.append(_tagify(skill_name))

    _run_memanto(
        [
            "remember",
            _truncate(memory, MAX_MEMORY_CHARS),
            "--type",
            "context",
            "--confidence",
            "0.85",
            "--provenance",
            "observed",
            "--source",
            "claude_code_skills",
            "--tags",
            ",".join(tags),
        ],
        timeout,
    )


def _read_stdin_json() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        _log("Ignoring non-JSON Claude Code hook payload")
        return {}
    return value if isinstance(value, dict) else {}


def _run_memanto(args: list[str], timeout: int) -> str:
    command = ["memanto", *args]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        _log("memanto CLI is not installed or not on PATH")
        return ""
    except subprocess.TimeoutExpired:
        _log(f"Timed out running: {shlex.join(command)}")
        return ""

    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        _log(f"Memanto command failed ({result.returncode}): {stderr[:500]}")
        return ""
    return result.stdout


def _format_recall_context(skill_name: str, recall: str) -> str:
    header = "Memanto memories relevant to this skill run"
    if skill_name:
        header += f" ({skill_name})"
    return (
        f"\n<{header}>\n"
        "Apply these durable decisions, preferences, and codebase constraints "
        "while executing the requested skill. Do not repeat them to the user "
        "unless they affect the answer.\n\n"
        f"{recall.strip()}\n"
        f"</{header}>\n"
    )


def _build_memory(
    skill_name: str,
    prompt: str,
    signals: list[str],
    transcript_text: str,
) -> str:
    lines = ["Claude Code skill interaction completed."]
    if skill_name:
        lines.append(f"Skill: {skill_name}")
    if prompt:
        lines.append(f"User task: {_truncate(_one_line(prompt), 700)}")
    if signals:
        lines.append("Durable engineering signals:")
        lines.extend(f"- {signal}" for signal in signals[:12])
    else:
        lines.append("Interaction summary:")
        lines.append(_truncate(_one_line(transcript_text), 1400))
    return "\n".join(lines)


def _read_transcript_excerpt(event: dict[str, Any]) -> str:
    path_value = event.get("transcript_path") or event.get("transcriptPath")
    if not path_value:
        return ""

    path = Path(str(path_value)).expanduser()
    if not path.is_file():
        return ""

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    texts: list[str] = []
    for line in lines[-MAX_TRANSCRIPT_LINES:]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        text = _message_text(item)
        if text:
            texts.append(text)
    return "\n".join(texts)


def _message_text(item: dict[str, Any]) -> str:
    message = item.get("message", item)
    if not isinstance(message, dict):
        return ""
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                chunks.append(part["text"])
        return "\n".join(chunks)
    return ""


def _extract_signals(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    candidates = re.split(r"(?<=[.!?])\s+|\s+-\s+", cleaned)
    signals: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        candidate = candidate.strip(" -*\t\n")
        if len(candidate) < 35 or not SIGNAL_PATTERN.search(candidate):
            continue
        normalized = candidate.casefold()[:160]
        if normalized in seen:
            continue
        seen.add(normalized)
        signals.append(_truncate(candidate, 350))
    return signals


def _event_text(event: dict[str, Any]) -> str:
    keys = ["prompt", "user_prompt", "input", "command", "tool_input"]
    parts: list[str] = []
    for key in keys:
        value = event.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            parts.append(value)
        else:
            parts.append(json.dumps(value, sort_keys=True))
    return "\n".join(parts)


def _skill_name(event: dict[str, Any]) -> str:
    env_name = os.environ.get("CLAUDE_SKILL_NAME") or os.environ.get(
        "MEMANTO_SKILL_NAME"
    )
    if env_name:
        return env_name.strip().lstrip("/")

    text = _event_text(event)
    match = re.search(
        r"(?:^|\s)/(grill-with-docs|handoff|tdd|[a-z0-9][a-z0-9_-]+)\b", text
    )
    if match:
        return match.group(1)
    return ""


def _cwd(event: dict[str, Any]) -> str:
    value = event.get("cwd") or os.environ.get("PWD") or ""
    return str(value)


def _truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3].rstrip() + "..."


def _one_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _tagify(value: str) -> str:
    tag = re.sub(r"[^a-z0-9-]+", "-", value.lower().strip().lstrip("/"))
    return tag.strip("-") or "skill"


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, ""))
    except ValueError:
        return default


def _log(message: str) -> None:
    print(f"[memanto-skill-hook] {message}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
