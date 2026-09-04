#!/usr/bin/env python3
"""MEMANTO PostToolUse hook — turn raw CLI calls into a readable line.

Without this, every memory operation shows up in chat as the bare shell command:

    Bash(memanto remember "Chose PostgreSQL over SQLite..." --type decision ...)

With it, the user sees what actually happened:

    👾 Memanto · stored a decision (confidence 0.95)
    👾 Memanto · recalled 7 memories
    👾 Memanto · MEMORY.md synced — 42 memories

Emits `systemMessage`, which is a universal hook output field shown to the user.
PostToolUse plain stdout only reaches the debug log, so the JSON field is the
only way to surface anything here.

Registered with `if: "Bash(memanto *)"` so the process is not spawned for
unrelated shell commands. Silent on anything it cannot confidently describe:
a wrong summary is worse than none.
"""

from __future__ import annotations

import json
import re
import shlex
import sys

MARK = "👾 Memanto"


def _claim(key: str, ttl: float = 10.0) -> bool:
    """First invocation for `key` wins; a duplicate stays silent.

    hooks.json registers each Python hook twice — once as `python`, once as
    `python3` — because neither spelling exists on every platform. On a machine
    where both resolve, both processes run, so the work must be claimed exactly
    once or the user sees every notice twice.
    """
    import hashlib
    import os
    import tempfile
    import time

    path = os.path.join(
        tempfile.gettempdir(),
        f"memanto-hook-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:24]}.lock",
    )
    try:
        os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        return True
    except FileExistsError:
        try:
            if time.time() - os.stat(path).st_mtime > ttl:
                os.unlink(path)
                os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                return True
        except Exception:
            # Ignore errors checking or unlinking lock file
            pass
        return False
    except Exception:
        return True  # never suppress the hook over an unexpected filesystem error


def _emit(message: str | None) -> None:
    if not message:
        return
    payload = {"systemMessage": f"{MARK} · {message}"}
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        # Ignore if stdout reconfigure fails or is unsupported
        pass
    try:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    except Exception:
        # Ignore stdout writing errors in hook
        pass


def _plain(value) -> str:
    """Flatten tool_response into searchable text; it may be str or blocks."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("stdout", "output", "content", "text"):
            val = value.get(key)
            if isinstance(val, str):
                return val
        return json.dumps(value)
    if isinstance(value, list):
        return " ".join(_plain(item) for item in value)
    return ""


def _flag(tokens: list[str], name: str) -> str | None:
    for i, token in enumerate(tokens):
        if token == name and i + 1 < len(tokens):
            return tokens[i + 1]
        if token.startswith(name + "="):
            return token.split("=", 1)[1]
    return None


def _int_after(pattern: str, text: str) -> int | None:
    match = re.search(pattern, text, re.I)
    return int(match.group(1)) if match else None


def describe(command: str, output: str) -> str | None:
    try:
        tokens = shlex.split(command)
    except Exception:
        tokens = command.split()
    if not tokens:
        return None

    # Strip anything before the memanto invocation (env prefixes, cd && ...).
    while tokens and not tokens[0].endswith("memanto"):
        tokens.pop(0)
    if len(tokens) < 2:
        return None

    verb = tokens[1]
    sub = tokens[2] if len(tokens) > 2 else ""

    if verb == "remember":
        stored = _int_after(r"Stored\s+(\d+)\s*/", output)
        if stored is not None:
            total = _int_after(r"Stored\s+\d+\s*/\s*(\d+)", output)
            noun = "memory" if stored == 1 else "memories"
            return f"stored {stored} {noun}" + (
                f" of {total}" if total and total != stored else ""
            )
        if "stored successfully" not in output.lower():
            return None
        kind = _flag(tokens, "--type") or _flag(tokens, "-t") or "memory"
        confidence = _flag(tokens, "--confidence") or _flag(tokens, "-c")
        article = "an" if kind[:1].lower() in "aeiou" else "a"
        tail = f" (confidence {confidence})" if confidence else ""
        return f"stored {article} {kind}{tail}"

    if verb == "recall":
        found = _int_after(r"Found\s+(\d+)\s+memor", output)
        if found is not None:
            return f"recalled {found} " + ("memory" if found == 1 else "memories")
        if "no memories found" in output.lower():
            return "searched memory — no matches"
        return None

    if verb == "answer":
        return "answered from memory" if output.strip() else None

    if verb == "upload":
        if "successful" in output.lower() or "uploaded" in output.lower():
            name = (
                tokens[2].replace("\\", "/").rsplit("/", 1)[-1]
                if len(tokens) > 2
                else "file"
            )
            return f"ingested {name}"
        return None

    if verb == "forget":
        return "permanently deleted a memory" if "deleted" in output.lower() else None

    if verb == "edit":
        return (
            "updated a memory"
            if "updated" in output.lower() or "OK" in output
            else None
        )

    if verb == "memory":
        if sub == "sync":
            count = _int_after(r"Synced\s+(\d+)\s+memor", output)
            return (
                f"MEMORY.md synced — {count} "
                + ("memory" if count == 1 else "memories")
                if count is not None
                else None
            )
        if sub == "export":
            return (
                "exported memory snapshot"
                if "OK" in output or "export" in output.lower()
                else None
            )
        if sub == "expire":
            return (
                "expired a memory (reversible)" if "expired" in output.lower() else None
            )
        if sub == "restore":
            return "restored an expired memory" if "restor" in output.lower() else None
        return None

    if verb == "detect-conflicts":
        count = _int_after(r"(\d+)\s+conflict", output)
        if count is not None:
            return f"found {count} " + ("conflict" if count == 1 else "conflicts")
        return "checked for conflicts"

    if verb == "daily-summary":
        return "generated a daily summary" if output.strip() else None

    if verb == "agent" and sub == "create":
        return f"created agent {tokens[3]}" if len(tokens) > 3 else "created an agent"

    if verb == "agent" and sub == "activate":
        return (
            f"activated agent {tokens[3]}" if len(tokens) > 3 else "activated an agent"
        )

    return None


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read().strip() or "{}")
        if not isinstance(payload, dict):
            return
        command = (payload.get("tool_input") or {}).get("command") or ""
        if "memanto" not in command:
            return
        response = _plain(payload.get("tool_response"))
        if not _claim("posttooluse:" + command + ":" + response[:200]):
            return
        _emit(describe(command, response))
    except Exception:
        # Never disrupt the session over a cosmetic notice.
        pass


if __name__ == "__main__":
    main()
