#!/usr/bin/env python3
"""
Standalone Memanto client for cross-session memory operations.

Can be used as a CLI tool or imported as a library.
"""
import requests
import json
import sys
import os

MEMANTO_URL = os.getenv("MEMANTO_URL", "http://localhost:3030")

class MemantoClient:
    """Client for the Memanto persistent memory API."""

    def __init__(self, base_url: str = MEMANTO_URL):
        self.base_url = base_url.rstrip("/")

    def store(self, user_id: str, key: str, value: str) -> bool:
        """Store a memory fact."""
        resp = requests.post(
            f"{self.base_url}/api/memory",
            json={"userId": user_id, "key": key, "value": value},
            timeout=5
        )
        return resp.status_code == 200

    def recall(self, user_id: str) -> list:
        """Recall all facts for a user."""
        resp = requests.get(
            f"{self.base_url}/api/memory/{user_id}",
            timeout=5
        )
        return resp.json() if resp.status_code == 200 else []

    def delete(self, user_id: str, key: str = None) -> bool:
        """Delete a fact (or all facts for a user)."""
        url = f"{self.base_url}/api/memory/{user_id}"
        if key:
            url += f"?key={key}"
        resp = requests.delete(url, timeout=5)
        return resp.status_code == 200


if __name__ == "__main__":
    client = MemantoClient()
    if len(sys.argv) < 2:
        print("Usage: memanto_client.py <store|recall|delete> <user_id> [key] [value]")
        sys.exit(1)

    cmd = sys.argv[1]
    user = sys.argv[2] if len(sys.argv) > 2 else "default"

    if cmd == "store":
        key = sys.argv[3] if len(sys.argv) > 3 else "fact"
        value = sys.argv[4] if len(sys.argv) > 4 else "stored"
        print(f"Stored: {client.store(user, key, value)}")
    elif cmd == "recall":
        mems = client.recall(user)
        print(f"Memories for {user}: {json.dumps(mems, indent=2)}")
    elif cmd == "delete":
        key = sys.argv[3] if len(sys.argv) > 3 else None
        print(f"Deleted: {client.delete(user, key)}")
