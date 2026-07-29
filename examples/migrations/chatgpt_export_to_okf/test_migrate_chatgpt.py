"""
Unit tests for ChatGPT Export to OKF Migration Adapter
"""

import os
import json
import pytest
from migrate_chatgpt import sanitize_text, parse_chatgpt_export, export_to_okf

def test_sanitize_text_credentials():
    raw = "My API token is sk-999999999999999999999999 and email user@openai.com"
    sanitized = sanitize_text(raw)
    assert "[REDACTED_API_KEY]" in sanitized
    assert "[REDACTED_EMAIL]" in sanitized

def test_parse_chatgpt_export(tmp_path):
    sample = [
        {
            "title": "User Preferences & Setup",
            "mapping": {
                "node_1": {
                    "message": {
                        "author": {"role": "user"},
                        "content": {"parts": ["User prefers dark mode and concise JSON responses."]},
                        "create_time": 1785290000
                    }
                }
            }
        }
    ]
    p = tmp_path / "conversations.json"
    p.write_text(json.dumps(sample), encoding='utf-8')

    memories = parse_chatgpt_export(str(p))
    assert len(memories) == 1
    assert memories[0]["memory_type"] == "preference"

def test_export_to_okf(tmp_path):
    memories = [
        {"id": "chatgpt-mem-0001", "agent_id": "user", "content": "I work as a senior cloud architect.", "memory_type": "fact", "title": "Profile", "created_at": "2026-07-28T12:00:00Z", "tags": ["chatgpt"]}
    ]
    out_dir = tmp_path / "okf"
    count, manifest = export_to_okf(memories, str(out_dir))
    assert count == 1
    assert os.path.exists(manifest)
