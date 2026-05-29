#!/usr/bin/env python3
"""
Memanto-powered memory layer for mattpocock Skills ecosystem.

Provides persistent context sharing across skill invocations.
"""
import requests
import json
import os

MEMANTO_URL = os.getenv("MEMANTO_URL", "http://localhost:3030")

class MemantoMemory:
    """Bridge that lets any Skill tool share context via Memanto."""

    def __init__(self, base_url=None):
        self.base_url = (base_url or MEMANTO_URL).rstrip("/")

    def store(self, project: str, key: str, value: str) -> bool:
        """Store a context fact for a project."""
        try:
            r = requests.post(
                f"{self.base_url}/api/memory",
                json={"userId": project, "key": key, "value": value},
                timeout=5
            )
            return r.status_code == 200
        except Exception as e:
            print(f"Store error: {e}")
            return False

    def recall(self, project: str) -> dict:
        """Recall all context facts for a project."""
        try:
            r = requests.get(
                f"{self.base_url}/api/memory/{project}",
                timeout=5
            )
            if r.status_code == 200:
                data = r.json()
                return {item["key"]: item["value"] for item in data.get("memories", [])}
            return {}
        except Exception as e:
            print(f"Recall error: {e}")
            return {}

    def clear(self, project: str) -> bool:
        """Clear all context for a project."""
        try:
            r = requests.delete(f"{self.base_url}/api/memory/{project}", timeout=5)
            return r.status_code == 200
        except:
            return False
