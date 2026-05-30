"""Idempotent installer for Memanto Claude Code hooks."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
BACKUP_PATH = Path.home() / ".claude" / "settings.json.memanto-backup"
HOOKS_DIR = Path(__file__).parent.resolve()

HOOK_DEFINITIONS = {
    "UserPromptSubmit": [
        {
            "type": "command",
            "command": f"python3 {HOOKS_DIR / 'claude_hooks.py'}",
            "env": {"CLAUDE_HOOK_NAME": "UserPromptSubmit"},
        }
    ],
    "Stop": [
        {
            "type": "command",
            "command": f"python3 {HOOKS_DIR / 'claude_hooks.py'}",
            "env": {"CLAUDE_HOOK_NAME": "Stop"},
        }
    ],
    "PostToolUse": [
        {
            "type": "command",
            "command": f"python3 {HOOKS_DIR / 'claude_hooks.py'}",
            "env": {"CLAUDE_HOOK_NAME": "PostToolUse"},
        }
    ],
}


def _load_settings() -> dict:
    if SETTINGS_PATH.exists():
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_settings(settings: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


def install() -> None:
    if SETTINGS_PATH.exists():
        shutil.copy2(str(SETTINGS_PATH), str(BACKUP_PATH))
        print(f"Backed up existing settings to {BACKUP_PATH}")
    settings = _load_settings()
    hooks = settings.setdefault("hooks", {})
    installed = 0
    for hook_name, definitions in HOOK_DEFINITIONS.items():
        existing = hooks.get(hook_name, [])
        memanto_present = any(
            "claude_hooks.py" in str(h.get("command", ""))
            for h in existing
        )
        if not memanto_present:
            hooks[hook_name] = existing + definitions
            installed += 1
        else:
            print(f"Hook {hook_name} already installed -- skipping")
    _save_settings(settings)
    print(f"Installed {installed} new Memanto hooks into {SETTINGS_PATH}")


def uninstall() -> None:
    settings = _load_settings()
    hooks = settings.get("hooks", {})
    removed = 0
    for hook_name in list(hooks.keys()):
        definitions = hooks[hook_name]
        filtered = [d for d in definitions if "claude_hooks.py" not in str(d.get("command", ""))]
        if len(filtered) < len(definitions):
            hooks[hook_name] = filtered
            removed += 1
            if not filtered:
                del hooks[hook_name]
    _save_settings(settings)
    print(f"Removed Memanto hooks from {SETTINGS_PATH}")


def status() -> None:
    settings = _load_settings()
    hooks = settings.get("hooks", {})
    print("Memanto Claude Code Hooks Status:")
    print("=" * 40)
    for hook_name in HOOK_DEFINITIONS:
        existing = hooks.get(hook_name, [])
        memanto_present = any(
            "claude_hooks.py" in str(h.get("command", ""))
            for h in existing
        )
        s = "INSTALLED" if memanto_present else "NOT INSTALLED"
        print(f"  {hook_name}: {s}")
    backend = os.environ.get("MOORCHEH_API_KEY")
    print(f"\nBackend: {'Memanto SDK (live)' if backend else 'Local JSONL (credential-free)'}")


if __name__ == "__main__":
    if "--uninstall" in sys.argv:
        uninstall()
    elif "--status" in sys.argv:
        status()
    else:
        install()
