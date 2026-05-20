#!/usr/bin/env python3
"""
Verify the Claude Code × Memanto integration is correctly installed.

Checks:
  1. Hooks are present in ~/.claude/hooks/memanto/
  2. settings.json references the hooks
  3. .env has a MOORCHEH_API_KEY
  4. The Memanto client can connect and create/recall a test memory

Exits 0 on success, non-zero on any check failure (so it's CI-friendly).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HOOKS_DIR = Path.home() / ".claude" / "hooks" / "memanto"
SETTINGS = Path.home() / ".claude" / "settings.json"
ENV_FILE = HOOKS_DIR / ".env"

EXPECTED_HOOK_FILES = [
    "_memanto_common.py",
    "inject_context.py",
    "distill_session.py",
    "skill_decisions.py",
]


def fail(msg: str) -> None:
    print(f"  ✗ {msg}")


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def info(msg: str) -> None:
    print(f"  ℹ {msg}")


def check_hook_files() -> bool:
    print("Checking hook files...")
    if not HOOKS_DIR.exists():
        fail(f"{HOOKS_DIR} does not exist. Did you run install.sh / install.ps1?")
        return False
    all_ok = True
    for fname in EXPECTED_HOOK_FILES:
        path = HOOKS_DIR / fname
        if path.exists():
            ok(f"{fname}")
        else:
            fail(f"missing: {fname}")
            all_ok = False
    return all_ok


def check_settings() -> bool:
    print("Checking settings.json wiring...")
    if not SETTINGS.exists():
        fail(f"{SETTINGS} not found.")
        return False
    try:
        data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"could not parse settings.json: {exc}")
        return False

    hooks = data.get("hooks", {}) or {}
    expected_events = {"UserPromptSubmit", "Stop", "PostToolUse"}
    all_ok = True
    for event in expected_events:
        entries = hooks.get(event) or []
        flat_commands: list[str] = []
        for e in entries:
            for h in e.get("hooks", []) or []:
                if isinstance(h, dict) and h.get("command"):
                    flat_commands.append(h["command"])
        if any("memanto" in c for c in flat_commands):
            ok(f"{event} hook is wired")
        else:
            fail(f"{event} hook NOT found in settings.json")
            all_ok = False
    return all_ok


def check_env() -> str | None:
    print("Checking .env...")
    if not ENV_FILE.exists():
        fail(f"{ENV_FILE} not found — installer should have created it.")
        return None
    api_key: str | None = None
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == "MOORCHEH_API_KEY":
            api_key = v.strip().strip('"').strip("'")
            break
    if not api_key or api_key == "your_moorcheh_api_key_here":
        fail("MOORCHEH_API_KEY is missing or is the placeholder value.")
        return None
    ok(f"MOORCHEH_API_KEY present (length={len(api_key)})")
    return api_key


def check_memanto(api_key: str) -> bool:
    print("Checking Memanto connectivity...")
    try:
        from memanto.cli.client.sdk_client import SdkClient
    except ImportError:
        fail("memanto package not installed. Run: pip install --user memanto")
        return False

    test_agent_id = "claude-code-memanto-verify"
    try:
        client = SdkClient(api_key=api_key)
    except Exception as exc:  # noqa: BLE001
        fail(f"could not instantiate SdkClient: {exc}")
        return False

    try:
        client.create_agent(
            agent_id=test_agent_id,
            pattern="tool",
            description="Verification agent for Claude Code × Memanto integration",
        )
    except Exception:
        info("verify-agent already exists or transient error (non-fatal)")

    try:
        result = client.remember(
            agent_id=test_agent_id,
            memory_type="fact",
            title="Verification memory",
            content="This memory was written by demo/verify_setup.py",
            confidence=0.9,
            tags=["verify", "claude-code"],
        )
        mem_id = result.get("memory_id", "?")
        ok(f"remember() worked — memory_id={mem_id}")
    except Exception as exc:  # noqa: BLE001
        fail(f"remember() failed: {exc}")
        return False

    try:
        result = client.recall(
            agent_id=test_agent_id,
            query="verification",
            limit=3,
        )
        count = len(result.get("memories") or [])
        ok(f"recall() worked — returned {count} memories")
    except Exception as exc:  # noqa: BLE001
        fail(f"recall() failed: {exc}")
        return False

    return True


def main() -> int:
    print()
    print("Claude Code × Memanto — setup verification")
    print("=" * 50)

    failed = 0

    if not check_hook_files():
        failed += 1
    print()

    if not check_settings():
        failed += 1
    print()

    api_key = check_env()
    print()

    if api_key:
        if not check_memanto(api_key):
            failed += 1
    else:
        failed += 1

    print()
    if failed == 0:
        print("All checks passed. Integration is ready to use.")
        return 0
    print(f"{failed} check(s) failed. See messages above for fixes.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
