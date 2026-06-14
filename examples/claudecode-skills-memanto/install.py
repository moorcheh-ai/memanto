"""
install.py
==========
One-command installer for the Memanto skills memory companion.

Registers SessionStart, UserPromptSubmit, and Stop hooks in
.claude/settings.json. Idempotent — safe to run multiple times.
Backs up existing settings before modifying.

Usage:
    python install.py                          # install into current project
    python install.py --target /path/to/repo  # install into specific repo
    python install.py --uninstall             # remove hooks
    python install.py --check                 # verify installation
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent

HOOKS_TO_REGISTER = {
    "SessionStart": [
        {"command": f"python {HERE}/hooks/on_session_start.py"}
    ],
    "UserPromptSubmit": [
        {"command": f"python {HERE}/hooks/on_prompt.py"}
    ],
    "Stop": [
        {"command": f"python {HERE}/hooks/on_stop.py"}
    ],
}

PYTHON_FILES = [
    "memanto_client.py",
    "skills_memory.py",
    "run_demo.py",
    "validate_offline.py",
    "requirements.txt",
    ".env.example",
]


def backup_settings(settings_path: Path) -> None:
    """Backup existing settings before modifying."""
    if settings_path.exists():
        backup = settings_path.with_suffix(
            f".backup-{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
        )
        shutil.copy2(settings_path, backup)
        print(f"  📋 Backed up settings → {backup.name}")


def load_settings(settings_path: Path) -> dict:
    """Load existing settings or return empty dict."""
    if settings_path.exists():
        try:
            return json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def install(target: Path) -> None:
    """Install hooks into target project's .claude/settings.json."""
    claude_dir = target / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    settings_path = claude_dir / "settings.json"

    backup_settings(settings_path)
    settings = load_settings(settings_path)

    hooks = settings.setdefault("hooks", {})

    # Register hooks — idempotent (don't duplicate)
    for event, new_hooks in HOOKS_TO_REGISTER.items():
        existing = hooks.setdefault(event, [])
        for hook in new_hooks:
            if hook not in existing:
                existing.append(hook)
                print(f"  ✅ Registered {event} hook")
            else:
                print(f"  ℹ️  {event} hook already registered")

    settings_path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n  ✅ Settings written → {settings_path}")

    # Copy skill command files
    commands_dir = claude_dir / "commands"
    commands_dir.mkdir(exist_ok=True)
    src_commands = HERE / ".claude" / "commands"
    if src_commands.exists():
        for md_file in src_commands.glob("*.md"):
            shutil.copy2(md_file, commands_dir / md_file.name)
            print(f"  ✅ Skill command → .claude/commands/{md_file.name}")

    print(f"\n✅ Memanto skills companion installed into {target}")
    print("\nNext steps:")
    print("  1. Set MOORCHEH_API_KEY=mk-... (get free key at moorcheh.ai)")
    print("  2. Open Claude Code — hooks activate automatically")
    print("  3. Run: python run_demo.py  (credential-free offline demo)")


def uninstall(target: Path) -> None:
    """Remove Memanto hooks from .claude/settings.json."""
    settings_path = target / ".claude" / "settings.json"
    if not settings_path.exists():
        print("No settings file found.")
        return

    backup_settings(settings_path)
    settings = load_settings(settings_path)
    hooks = settings.get("hooks", {})

    for event in HOOKS_TO_REGISTER:
        if event in hooks:
            hooks[event] = [
                h for h in hooks[event]
                if "on_session_start" not in str(h)
                and "on_prompt" not in str(h)
                and "on_stop" not in str(h)
            ]
            if not hooks[event]:
                del hooks[event]

    settings_path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print("✅ Memanto hooks removed.")


def check(target: Path) -> None:
    """Check installation status."""
    settings_path = target / ".claude" / "settings.json"
    settings = load_settings(settings_path)
    hooks = settings.get("hooks", {})

    print(f"\n📋 Installation status for: {target}\n")
    for event in HOOKS_TO_REGISTER:
        registered = any(
            "on_session_start" in str(h) or "on_prompt" in str(h) or "on_stop" in str(h)
            for h in hooks.get(event, [])
        )
        print(f"  {'✅' if registered else '❌'} {event} hook")

    api_key = os.getenv("MOORCHEH_API_KEY", "")
    print(f"\n  {'✅' if api_key else '⚠️ '} MOORCHEH_API_KEY {'set' if api_key else 'not set'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Install Memanto skills hooks")
    parser.add_argument("--target", default=os.getcwd())
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    target = Path(args.target).resolve()

    print("\n🧠 Memanto Skills Memory Companion")
    print("   Cross-session engineering memory for mattpocock/skills\n")

    if args.check:
        check(target)
    elif args.uninstall:
        uninstall(target)
    else:
        install(target)


if __name__ == "__main__":
    main()
