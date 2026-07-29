"""
Unit tests for CrewAI to OKF Migration Adapter
"""

import os
import json
import pytest
from migrate_crewai import sanitize_text, parse_crewai_json, export_to_okf

def test_sanitize_text_redacts_keys_and_emails():
    raw = "My OpenAI key is sk-abcdef1234567890abcdef1234 and email is test@domain.com"
    sanitized = sanitize_text(raw)
    assert "sk-abcdef" not in sanitized
    assert "[REDACTED_API_KEY]" in sanitized
    assert "test@domain.com" not in sanitized
    assert "[REDACTED_EMAIL]" in sanitized

def test_parse_crewai_json_normalization(tmp_path):
    sample = [
        {
            "agent_id": "researcher",
            "content": "User prefers concise bullet points with metrics.",
            "type": "long_term",
            "timestamp": "2026-07-28T12:00:00Z"
        },
        {
            "agent_id": "writer",
            "text": "Drafted blog post on AI agent memory portability.",
            "type": "short_term"
        }
    ]
    file_path = tmp_path / "crewai_sample.json"
    file_path.write_text(json.dumps(sample), encoding='utf-8')

    memories = parse_crewai_json(str(file_path))
    assert len(memories) == 2
    assert memories[0]["agent_id"] == "researcher"
    assert memories[0]["memory_type"] == "preference"
    assert memories[1]["memory_type"] == "context"

def test_export_to_okf_structure(tmp_path):
    memories = [
        {
            "id": "crewai-mem-0001",
            "agent_id": "analyst",
            "content": "BigQuery partitioned tables reduce query cost.",
            "memory_type": "fact",
            "task": "Analyze SQL costs",
            "created_at": "2026-07-28T14:00:00Z",
            "tags": ["crewai", "fact"]
        }
    ]
    out_dir = tmp_path / "okf_export"
    count, manifest_path = export_to_okf(memories, str(out_dir))

    assert count == 1
    assert os.path.exists(manifest_path)
    assert os.path.exists(out_dir / "crewai-mem-0001.md")
    assert os.path.exists(out_dir / "SAVINGS_REPORT.md")

    md_text = (out_dir / "crewai-mem-0001.md").read_text(encoding='utf-8')
    assert "okf_version" in md_text
    assert "BigQuery partitioned tables" in md_text
