#!/usr/bin/env python3
"""
Install Memanto hooks into Claude Code's settings.json.

Adds two hooks:
  - UserPromptSubmit: injects relevant memories before each user message
  - Stop: captures engineering preferences at the end of each session

Run once after cloning the example:
    python3 install.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

EXAMPLE_DIR = Path(__file__).resolve().parent
HOOKS_DIR = EXAMPLE_DIR / "hooks"
CAPTURE_HOOK = str(HOOKS_DIR / "capture_preferences.py")
INJECT_HOOK = str(HOOKS_DIR / "inject_context.py")

CLAUDE_DIR = Path.home() / ".claude"
SETTINGS_FILE = CLAUDE_DIR / "settings.json"


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_settings(settings: dict) -> None:
    CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2))
    print(f"✅ Saved {SETTINGS_FILE}")


def add_hook(settings: dict, event: str, command: str) -> bool:
    """Add a hook for an event; return True if added, False if already present."""
    hooks = settings.setdefault("hooks", {})
    event_hooks: list = hooks.setdefault(event, [])

    # Check if this command is already registered
    for group in event_hooks:
        for hook in group.get("hooks", []):
            if hook.get("command") == command:
                return False  # Already installed

    event_hooks.append({
        "matcher": "",
        "hooks": [{"type": "command", "command": f"python3 {command}"}],
    })
    return True


def check_api_key() -> bool:
    key = os.environ.get("MOORCHEH_API_KEY", "")
    if not key:
        print(
            "\n⚠️  MOORCHEH_API_KEY is not set.\n"
            "   Get a free key at https://console.moorcheh.ai/api-keys\n"
            "   Then run:  export MOORCHEH_API_KEY=your_key\n"
            "   Or add it to your shell profile (~/.bashrc, ~/.zshrc, etc.)\n"
        )
        return False
    print(f"✅ MOORCHEH_API_KEY found ({key[:8]}...)")
    return True


def main() -> None:
    print("🧠 Installing Memanto ↔ Claude Code Skills hooks...\n")

    check_api_key()

    settings = load_settings()
    added: list[str] = []

    if add_hook(settings, "UserPromptSubmit", INJECT_HOOK):
        added.append("UserPromptSubmit (memory injection)")
    else:
        print("ℹ️  UserPromptSubmit hook already installed")

    if add_hook(settings, "Stop", CAPTURE_HOOK):
        added.append("Stop (preference capture)")
    else:
        print("ℹ️  Stop hook already installed")

    if added:
        save_settings(settings)
        print(f"\n✅ Installed hooks: {', '.join(added)}")
    else:
        print("\nℹ️  All hooks already installed — no changes made.")

    print(
        "\n🚀 Next steps:\n"
        "  1. Ensure MOORCHEH_API_KEY is exported in your shell\n"
        "  2. Start Claude Code in any project directory\n"
        "  3. Your engineering preferences are captured automatically\n"
        "  4. In future sessions, relevant preferences are injected as context\n"
        "\n📖 Run the demo:\n"
        "  python3 demo/run_demo.py\n"
    )


if __name__ == "__main__":
    main()
