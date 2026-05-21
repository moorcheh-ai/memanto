#!/usr/bin/env python3
"""
validate.py — Smoke tests for the Claude Code Skills × Memanto bridge

Run: python3 validate.py
"""

import json
import os
import subprocess
import sys
import tempfile

SCRIPT = os.path.join(os.path.dirname(__file__), "skills-memory.sh")
PREVIEW_DIR = tempfile.mkdtemp(prefix="memanto-test-")

def run(cmd, env_extra=None):
    env = os.environ.copy()
    env["MEMANTO_PREVIEW"] = "1"
    env["MEMANTO_AGENT"] = "test-agent"
    env["HOME"] = PREVIEW_DIR  # isolate preview files
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        ["bash", SCRIPT] + cmd,
        capture_output=True, text=True, env=env, timeout=10
    )
    return result

def test_remember_and_recall():
    """Store a memory and recall it."""
    # Store
    r = run(["remember", "User prefers JWT with RS256 for authentication", "--tag", "security"])
    assert r.returncode == 0, f"remember failed: {r.stderr}"

    # Store another
    r = run(["remember", "Database is PostgreSQL with UUID primary keys"])
    assert r.returncode == 0, f"remember failed: {r.stderr}"

    # Recall by keyword
    r = run(["recall", "JWT authentication"])
    assert r.returncode == 0, f"recall failed: {r.stderr}"
    assert "JWT" in r.stdout or "matches" in r.stdout, f"recall didn't find JWT: {r.stdout}"

    print("  PASS: remember + recall")

def test_auto_tagging():
    """Verify auto-tagging based on content heuristics."""
    r = run(["remember", "Architecture uses hexagonal design pattern"])
    assert r.returncode == 0
    assert "architecture" in r.stdout.lower(), f"auto-tag failed: {r.stdout}"
    print("  PASS: auto-tagging")

def test_wrap_lifecycle():
    """Test the full wrap lifecycle with a simple command."""
    r = run(["wrap", "echo 'Using Next.js 15 App Router for the frontend'"])
    assert r.returncode == 0, f"wrap failed: {r.stderr}"
    print("  PASS: wrap lifecycle")

def test_daily_summary():
    """Test daily summary in preview mode."""
    r = run(["daily"])
    assert r.returncode == 0
    print("  PASS: daily summary")

def test_help():
    """Test help output."""
    r = run(["help"])
    assert r.returncode == 0
    assert "recall" in r.stdout
    assert "remember" in r.stdout
    print("  PASS: help")

def test_unknown_command():
    """Test error on unknown command."""
    r = run(["foobar"])
    assert r.returncode != 0
    print("  PASS: unknown command rejected")

def test_empty_recall():
    """Recall with no stored memories should not crash."""
    clean_dir = tempfile.mkdtemp(prefix="memanto-clean-")
    env = {"HOME": clean_dir, "MEMANTO_PREVIEW": "1", "MEMANTO_AGENT": "clean-agent"}
    r = subprocess.run(
        ["bash", SCRIPT, "recall", "nothing"],
        capture_output=True, text=True, env=env, timeout=10
    )
    assert r.returncode == 0, f"empty recall crashed: {r.stderr}"
    print("  PASS: empty recall")

def main():
    print(f"Validating skills-memory.sh (preview mode)")
    print(f"Script: {SCRIPT}")
    print()

    tests = [
        test_help,
        test_unknown_command,
        test_empty_recall,
        test_remember_and_recall,
        test_auto_tagging,
        test_wrap_lifecycle,
        test_daily_summary,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {t.__name__}: {e}")
            failed += 1

    print()
    print(f"Results: {passed} passed, {failed} failed")

    # Cleanup
    import shutil
    shutil.rmtree(PREVIEW_DIR, ignore_errors=True)

    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    main()
