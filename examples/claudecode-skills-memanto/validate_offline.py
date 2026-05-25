#!/usr/bin/env python3
"""
validate_offline.py
===================
Offline smoke test — no API key, no server, no LLM required.

Run:
    python validate_offline.py
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

HERE = Path(__file__).parent
FILES = [
    "memanto_bridge.py",
    "skills_memory.py",
    "setup.py",
    "validate_offline.py",
]


def main() -> None:
    print("=" * 60)
    print("  Memanto Skills Companion — Offline Validation")
    print("=" * 60)

    # Step 1: Syntax check
    print("\n[1/3] Syntax check...")
    for fname in FILES:
        path = HERE / fname
        try:
            with open(path, encoding="utf-8") as fh:
                ast.parse(fh.read())
            print(f"  ✅ {fname} — valid syntax")
        except SyntaxError as exc:
            print(f"  ❌ {fname} — {exc}")
            sys.exit(1)
        except FileNotFoundError:
            print(f"  ⚠️  {fname} — not found (skipping)")

    # Step 2: Skill files present
    print("\n[2/3] Skill files check...")
    skills = [
        ".claude/commands/memanto-tdd.md",
        ".claude/commands/memanto-grill-with-docs.md",
        ".claude/commands/memanto-handoff.md",
    ]
    for skill in skills:
        path = HERE / skill
        if path.exists():
            print(f"  ✅ {skill}")
        else:
            print(f"  ❌ {skill} — missing")
            sys.exit(1)

    # Step 3: Offline demo
    print("\n[3/3] Running offline demo...")
    try:
        import io
        from contextlib import redirect_stdout
        from skills_memory import _run_offline_demo

        buf = io.StringIO()
        with redirect_stdout(buf):
            _run_offline_demo()

        output = buf.getvalue()
        checks = [
            ("SKILL EXECUTION 1", "grill-with-docs skill execution"),
            ("SESSION BOUNDARY",  "session boundary marker"),
            ("SKILL EXECUTION 2", "tdd skill execution with recalled profile"),
            ("ENGINEERING PROFILE", "engineering profile injection"),
            ("Zero repeated instructions", "zero re-prompting claim"),
        ]
        for marker, label in checks:
            if marker in output:
                print(f"  ✅ {label}")
            else:
                print(f"  ❌ {label} — marker '{marker}' not found in output")
                sys.exit(1)

    except Exception as exc:
        print(f"  ❌ Demo failed: {exc}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  offline validation passed ✅")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
