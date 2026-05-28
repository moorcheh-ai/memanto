#!/usr/bin/env python3
"""
setup.py
========
Installs the Memanto skills memory companion into your project.

What this does:
  1. Copies Memanto-enhanced skill files to your .claude/commands/ directory
  2. Copies memanto_bridge.py and skills_memory.py to your project root
  3. Validates MOORCHEH_API_KEY is set
  4. Prints next steps

Usage:
    python setup.py                          # install into current directory
    python setup.py --target /path/to/repo  # install into a specific repo
    python setup.py --check                 # check installation status only
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).parent
SKILLS = [
    "memanto-tdd.md",
    "memanto-grill-with-docs.md",
    "memanto-handoff.md",
]
PYTHON_FILES = [
    "memanto_bridge.py",
    "skills_memory.py",
]


def check_env() -> bool:
    key = os.getenv("MOORCHEH_API_KEY", "")
    if not key:
        print("⚠️  MOORCHEH_API_KEY not set.")
        print("   Get a free key at https://moorcheh.ai")
        print("   Then: export MOORCHEH_API_KEY=mk-...")
        return False
    print(f"✅  MOORCHEH_API_KEY set ({key[:8]}...)")
    return True


def install(target: Path) -> None:
    # Create .claude/commands directory
    commands_dir = target / ".claude" / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n📁 Installing into: {target}\n")

    # Copy skill files
    src_commands = HERE / ".claude" / "commands"
    for skill_file in SKILLS:
        src = src_commands / skill_file
        dst = commands_dir / skill_file
        if src.exists():
            shutil.copy2(src, dst)
            print(f"  ✅ {skill_file} → .claude/commands/")
        else:
            print(f"  ⚠️  {skill_file} not found in source — skipping")

    # Copy Python files
    for py_file in PYTHON_FILES:
        src = HERE / py_file
        dst = target / py_file
        if src.exists():
            shutil.copy2(src, dst)
            print(f"  ✅ {py_file} → project root")
        else:
            print(f"  ⚠️  {py_file} not found — skipping")

    print("\n✅  Installation complete!\n")
    print("Next steps:")
    print("  1. pip install -r requirements.txt")
    print("  2. export MOORCHEH_API_KEY=mk-...")
    print("  3. memanto serve   # start local Memanto server")
    print()
    print("In Claude Code, your new skills are available as:")
    print("  /memanto-tdd")
    print("  /memanto-grill-with-docs")
    print("  /memanto-handoff")
    print()
    print("Demo (offline, no server needed):")
    print("  python skills_memory.py demo --offline")
    print()
    print("Demo (live Memanto):")
    print("  python skills_memory.py demo")


def check_status(target: Path) -> None:
    print(f"\n📋 Installation status for: {target}\n")
    commands_dir = target / ".claude" / "commands"

    for skill_file in SKILLS:
        dst = commands_dir / skill_file
        status = "✅" if dst.exists() else "❌"
        print(f"  {status} {skill_file}")

    for py_file in PYTHON_FILES:
        dst = target / py_file
        status = "✅" if dst.exists() else "❌"
        print(f"  {status} {py_file}")

    check_env()


def main() -> None:
    parser = argparse.ArgumentParser(description="Install Memanto skills companion")
    parser.add_argument(
        "--target",
        default=os.getcwd(),
        help="Target project directory (default: current directory)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check installation status without installing",
    )
    args = parser.parse_args()

    target = Path(args.target).resolve()

    if args.check:
        check_status(target)
        return

    print("\n🧠  Memanto Skills Memory Companion — Setup")
    print("    Eliminating context fragmentation across skill executions\n")

    check_env()
    install(target)


if __name__ == "__main__":
    main()
