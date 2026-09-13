#!/usr/bin/env python3
"""MEMANTO SessionStart hook.

Three jobs, in order of importance:

1. Refresh MEMORY.md so the agent has full context before the first message.
2. Print a short notice — SessionStart stdout is added to the session context.
3. Install the MEMANTO status line into ~/.claude/settings.json, once.

A plugin cannot ship a `statusLine`: plugin settings.json only honors `agent`
and `subagentStatusLine`, so the entry has to be written into the user's own
settings. This hook resolves the interpreter with sys.executable — the Python
actually running right now — which sidesteps `python` vs `python3` entirely.

Must never crash the session. Every step is independently guarded, and the
script is idempotent so running it twice is harmless (hooks.json intentionally
registers two interpreter spellings so at least one resolves on any platform).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

MARK = "👾"
SYNC_TIMEOUT = 25
STATUSLINE_REFRESH = 5


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


def _out(text: str) -> None:
    """Write UTF-8 regardless of the console code page (Windows cp1252)."""
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        # Ignore if stdout reconfigure fails or is unsupported
        pass
    try:
        sys.stdout.write(text + "\n")
    except Exception:
        try:
            sys.stdout.write(text.encode("ascii", "ignore").decode("ascii") + "\n")
        except Exception:
            # Ignore stdout writing errors in hook
            pass


def _read_stdin() -> dict:
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return {}
        payload = json.loads(sys.stdin.read().strip() or "{}")
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _project_dir(payload: dict) -> str:
    workspace = payload.get("workspace") or {}
    for value in (
        workspace.get("project_dir"),
        workspace.get("current_dir"),
        payload.get("cwd"),
    ):
        if value:
            return str(value)
    return os.getcwd()


def sync_memory(project_dir: str) -> str | None:
    """Refresh MEMORY.md. Returns a one-line summary, or None if unavailable."""
    try:
        result = subprocess.run(
            ["memanto", "memory", "sync", "--project-dir", project_dir],
            capture_output=True,
            text=True,
            timeout=SYNC_TIMEOUT,
        )
    except FileNotFoundError:
        return None  # memanto not installed; stay quiet rather than nag every session
    except Exception:
        return None

    if result.returncode != 0:
        return None

    memory_file = Path(project_dir) / "MEMORY.md"
    if not memory_file.exists():
        return None

    try:
        import re

        text = memory_file.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"Total memories:\s*\*{0,2}\s*(\d+)", text)
        count = int(match.group(1)) if match else None
    except Exception:
        count = None

    if count is None:
        return "MEMORY.md refreshed."
    if count == 0:
        return "MEMORY.md refreshed — no memories stored yet."
    return (
        f"MEMORY.md refreshed — {count} "
        + ("memory" if count == 1 else "memories")
        + " loaded."
    )


def _settings_path() -> Path:
    return Path(os.path.expanduser("~")) / ".claude" / "settings.json"


def _statusline_script() -> Path:
    return (Path(__file__).resolve().parent.parent / "statusline.py").resolve()


def install_statusline() -> str | None:
    """Add our statusLine to the user's settings once. Never overwrite theirs."""
    marker = (
        Path(os.path.expanduser("~")) / ".memanto" / ".claude-statusline" / "installed"
    )
    if marker.exists():
        return None

    script = _statusline_script()
    if not script.exists():
        return None

    settings_file = _settings_path()
    try:
        settings = (
            json.loads(settings_file.read_text(encoding="utf-8"))
            if settings_file.exists()
            else {}
        )
        if not isinstance(settings, dict):
            return None
    except Exception:
        return None  # unreadable or malformed: never risk clobbering it

    existing = settings.get("statusLine")
    if isinstance(existing, dict) and "statusline.py" in json.dumps(existing):
        _touch(marker)
        return None

    command = f'"{sys.executable}" "{script}"'

    if existing:
        _touch(marker)
        return (
            f"{MARK} MEMANTO status line available, but you already have a "
            f'"statusLine" in ~/.claude/settings.json — run /memanto:statusline to switch.'
        )

    settings["statusLine"] = {
        "type": "command",
        "command": command,
        "refreshInterval": STATUSLINE_REFRESH,
    }

    try:
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = settings_file.with_suffix(".json.memanto.tmp")
        tmp.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, settings_file)
    except Exception:
        return None

    _touch(marker)
    return (
        f"{MARK} MEMANTO status line installed — it appears next time Claude Code starts. "
        f"Turn it off with /memanto:statusline remove."
    )


def _touch(marker: Path) -> None:
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("1", encoding="utf-8")
    except Exception:
        # Ignore errors writing statusline installation marker
        pass


def main() -> None:
    payload = _read_stdin()
    project_dir = _project_dir(payload)

    if not _claim("sessionstart:" + str(payload.get("session_id") or project_dir)):
        return

    lines = []
    try:
        summary = sync_memory(project_dir)
        if summary:
            lines.append(
                f"{MARK} {summary} Read MEMORY.md before acting; it carries standing instructions, decisions, and open commitments from previous sessions."
            )
    except Exception:
        # Ignore errors syncing memory in session start hook
        pass

    try:
        notice = install_statusline()
        if notice:
            lines.append(notice)
    except Exception:
        # Ignore errors installing statusline in session start hook
        pass

    if lines:
        _out("\n".join(lines))


if __name__ == "__main__":
    main()
