"""
Unit tests for LangMem to OKF Migration Adapter
"""

import os
import json
import pytest
from migrate_langmem import sanitize_text, parse_langmem_json, export_to_okf

def test_sanitize_text_credentials():
    raw = "My OpenAI key is sk-1234567890abcdef12345678 and email is dev@langchain.dev"
    sanitized = sanitize_text(raw)
    assert "[REDACTED_API_KEY]" in sanitized
    assert "[REDACTED_EMAIL]" in sanitized

def test_parse_langmem_json(tmp_path):
    sample = [
        {"agent_id": "langmem_user", "text": "User prefers concise Python code snippets with docstrings.", "created_at": "2026-07-28T10:00:00Z"},
        {"agent_id": "langmem_user", "text": "GCP Cloud Run handles serverless container deployment.", "created_at": "2026-07-28T10:05:00Z"}
    ]
    p = tmp_path / "langmem.json"
    p.write_text(json.dumps(sample), encoding='utf-8')

    memories = parse_langmem_json(str(p))
    assert len(memories) == 2
    assert memories[0]["memory_type"] == "preference"
    assert memories[1]["memory_type"] == "context"

def test_export_to_okf(tmp_path):
    memories = [
        {"id": "langmem-mem-0001", "agent_id": "user", "content": "Fact: Base USDC gas fees are negligible.", "memory_type": "fact", "created_at": "2026-07-28T12:00:00Z", "tags": ["langmem"]}
    ]
    out_dir = tmp_path / "okf"
    count, manifest = export_to_okf(memories, str(out_dir))
    assert count == 1
    assert os.path.exists(manifest)
