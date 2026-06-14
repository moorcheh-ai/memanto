#!/usr/bin/env python3
"""
validate_offline.py
===================
Offline smoke test — no API key, no server required.

Run: python validate_offline.py
"""
from __future__ import annotations

import ast
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).parent
FILES = ["memanto_client.py", "skills_memory.py", "install.py",
         "run_demo.py", "validate_offline.py",
         "hooks/_common.py", "hooks/on_session_start.py",
         "hooks/on_prompt.py", "hooks/on_stop.py"]


def main():
    print("=" * 60)
    print("  Memanto Skills Companion — Offline Validation")
    print("=" * 60)

    # Step 1: Syntax check
    print("\n[1/4] Syntax check...")
    for fname in FILES:
        path = HERE / fname
        try:
            with open(path, encoding="utf-8") as f:
                ast.parse(f.read())
            print(f"  ✅ {fname}")
        except SyntaxError as e:
            print(f"  ❌ {fname} — {e}")
            sys.exit(1)
        except FileNotFoundError:
            print(f"  ⚠️  {fname} — not found (skipping)")

    # Step 2: Skill files
    print("\n[2/4] Skill command files...")
    skills = [
        ".claude/commands/memanto-tdd.md",
        ".claude/commands/memanto-grill-with-docs.md",
        ".claude/commands/memanto-handoff.md",
    ]
    for s in skills:
        p = HERE / s
        print(f"  {'✅' if p.exists() else '❌'} {s}")
        if not p.exists():
            sys.exit(1)

    # Step 3: Unit tests
    print("\n[3/4] Running unit tests...")
    import unittest
    loader = unittest.TestLoader()
    suite = loader.discover(str(HERE / "tests"), pattern="test_*.py")
    buf = io.StringIO()
    runner = unittest.TextTestRunner(stream=buf, verbosity=0)
    result = runner.run(suite)
    total = result.testsRun
    failures = len(result.failures) + len(result.errors)
    if failures:
        print(f"  ❌ {failures}/{total} tests failed")
        print(buf.getvalue())
        sys.exit(1)
    print(f"  ✅ {total} unit tests passed")

    # Step 4: Offline demo
    print("\n[4/4] Running offline demo...")
    try:
        from skills_memory import _offline_demo
        out = io.StringIO()
        with redirect_stdout(out):
            _offline_demo()
        output = out.getvalue()
        checks = [
            ("SESSION BOUNDARY", "session boundary"),
            ("engineering-profile", "engineering profile injection"),
            ("No repeated instructions", "zero re-prompting"),
            ("Demo complete", "demo completion"),
        ]
        for marker, label in checks:
            if marker in output:
                print(f"  ✅ {label}")
            else:
                print(f"  ❌ {label} — marker not found")
                sys.exit(1)
    except Exception as e:
        print(f"  ❌ Demo failed: {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  offline validation passed ✅")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
