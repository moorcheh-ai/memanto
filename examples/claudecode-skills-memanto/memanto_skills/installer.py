"""Idempotent installer for the Claude Code lifecycle hooks.

Registers three hooks in a Claude Code ``settings.json`` (project-local by
default, or ``~/.claude`` with ``--global``):

* ``SessionStart``     -> hooks/session_start.py   (inject profile once)
* ``UserPromptSubmit`` -> hooks/on_prompt.py       (recall + inject per skill)
* ``Stop``             -> hooks/on_stop.py          (async distill + store)

The hook command uses the *current* Python interpreter (``sys.executable``) so
the hooks run with the same environment that has ``memanto`` installed. The
settings file is backed up before modification, and re-running cleanly replaces
our previously-installed entries (matched by the hooks directory path) without
touching anyone else's hooks.

Hook JSON structure follows the official Claude Code hooks reference.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

# Absolute path to the hooks directory shipped beside this package.
_HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"

# Marker used to recognise (and replace) the entries we manage.
_MARKER = str(_HOOKS_DIR)


def _hook_command(script: str) -> str:
    return f'"{sys.executable}" "{_HOOKS_DIR / script}"'


def _managed_hooks() -> dict[str, list[dict[str, Any]]]:
    """The hook entries this installer owns, in settings.json shape."""
    return {
        "SessionStart": [
            {
                "matcher": "startup|resume|clear",
                "hooks": [
                    {
                        "type": "command",
                        "command": _hook_command("session_start.py"),
                        "timeout": 15,
                    }
                ],
            }
        ],
        "UserPromptSubmit": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": _hook_command("on_prompt.py"),
                        "timeout": 15,
                    }
                ]
            }
        ],
        "Stop": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": _hook_command("on_stop.py"),
                        "async": True,
                        "timeout": 60,
                    }
                ]
            }
        ],
    }


def _settings_path(global_scope: bool) -> Path:
    base = Path.home() / ".claude" if global_scope else Path.cwd() / ".claude"
    return base / "settings.json"


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = path.with_suffix(f".json.bak-{stamp}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return backup


def _is_managed(hook: Any) -> bool:
    return isinstance(hook, dict) and _MARKER in str(hook.get("command", ""))


def _strip_managed(entries: list[Any]) -> tuple[list[Any], int]:
    """Remove our hook commands from ``entries``; returns (kept, removed_count).

    Stripping happens at the individual-hook level: if a user merged their own
    hook into one of our entries, their hook survives and only ours is removed.
    """
    kept: list[Any] = []
    removed = 0
    for entry in entries:
        hooks = entry.get("hooks") if isinstance(entry, dict) else None
        if not isinstance(hooks, list):
            kept.append(entry)
            continue
        foreign = [h for h in hooks if not _is_managed(h)]
        removed += len(hooks) - len(foreign)
        if len(foreign) == len(hooks):
            kept.append(entry)
        elif foreign:
            kept.append({**entry, "hooks": foreign})
        # An entry whose hooks were all ours is dropped entirely.
    return kept, removed


def install_hooks(global_scope: bool = False) -> int:
    """Register the three lifecycle hooks in Claude Code's ``settings.json``.

    Writes to the project-local settings by default, or the user-global file
    when ``global_scope=True``. Idempotent: re-running replaces only our
    previously-installed entries, preserves foreign hooks, and backs up the
    settings file before any write. Returns 0 on success for CLI use.
    """
    path = _settings_path(global_scope)
    path.parent.mkdir(parents=True, exist_ok=True)

    settings = _load(path)
    backup = _backup(path)

    # If "hooks" is missing or malformed (list/string from a hand-edited file),
    # reset it to a dict rather than crashing with AttributeError on .get().
    existing_hooks = settings.get("hooks")
    if not isinstance(existing_hooks, dict):
        existing_hooks = {}
    settings["hooks"] = existing_hooks
    hooks_section: dict[str, Any] = existing_hooks

    for event, managed in _managed_hooks().items():
        existing = hooks_section.get(event, [])
        if not isinstance(existing, list):
            existing = []
        kept, _ = _strip_managed(existing)
        hooks_section[event] = kept + managed

    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")

    print(f"✓ Installed Memanto skill-memory hooks into {path}")
    if backup:
        print(f"  (backed up previous settings to {backup.name})")
    print("  Hooks: SessionStart, UserPromptSubmit, Stop")
    print("  Ensure MOORCHEH_API_KEY is set in this shell's environment.")
    return 0


def uninstall_hooks(global_scope: bool = False) -> int:
    """Remove only the hooks this installer manages from ``settings.json``.

    Foreign hooks — including any the user merged into one of our entries —
    are preserved. No-ops cleanly when nothing matches (no rewrite, no backup
    churn). Returns 0 in all non-error paths so the CLI exits successfully.
    """
    path = _settings_path(global_scope)
    if not path.exists():
        print(f"Nothing to uninstall ({path} does not exist).")
        return 0

    settings = _load(path)
    hooks_section = settings.get("hooks")
    if not isinstance(hooks_section, dict):
        # Nothing of ours could possibly be here if the shape is wrong.
        print(f"No Memanto hooks found in {path}; nothing to remove.")
        return 0
    removed = 0
    for event in _managed_hooks():
        entries = hooks_section.get(event)
        if not isinstance(entries, list):
            continue
        kept, n = _strip_managed(entries)
        removed += n
        if kept:
            hooks_section[event] = kept
        else:
            hooks_section.pop(event, None)

    if not removed:
        print(f"No Memanto hooks found in {path}; nothing to remove.")
        return 0

    backup = _backup(path)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    print(f"✓ Removed {removed} Memanto hook(s) from {path}")
    if backup:
        print(f"  (backed up previous settings to {backup.name})")
    return 0
