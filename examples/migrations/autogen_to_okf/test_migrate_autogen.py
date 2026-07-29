"""
Unit tests for AutoGen to OKF Migration Adapter
"""

import os
import json
import pytest
from migrate_autogen import sanitize_text, parse_autogen_json, export_to_okf

def test_sanitize_text_redacts_credentials():
    raw = "OpenAI key sk-1234567890abcdef12345678 and email dev@autogen.io"
    sanitized = sanitize_text(raw)
    assert "[REDACTED_API_KEY]" in sanitized
    assert "[REDACTED_EMAIL]" in sanitized

def test_parse_autogen_json(tmp_path):
    sample = [
        {"name": "user_proxy", "content": "Always prefer Markdown tables for financial reports.", "timestamp": "2026-07-28T10:00:00Z"},
        {"name": "assistant", "content": "Acknowledged. I will format all tables as GFM Markdown.", "timestamp": "2026-07-28T10:01:00Z"}
    ]
    path = tmp_path / "autogen_sample.json"
    path.write_text(json.dumps(sample), encoding='utf-8')

    memories = parse_autogen_json(str(path))
    assert len(memories) == 2
    assert memories[0]["memory_type"] == "preference"
    assert memories[1]["agent_id"] == "assistant"

def test_export_to_okf(tmp_path):
    memories = [
        {"id": "autogen-mem-0001", "agent_id": "user_proxy", "content": "Fact: GCP Cloud Run scale limit is 1000 instances.", "memory_type": "fact", "created_at": "2026-07-28T12:00:00Z", "tags": ["autogen"]}
    ]
    out_dir = tmp_path / "okf"
    count, manifest = export_to_okf(memories, str(out_dir))
    assert count == 1
    assert os.path.exists(manifest)
