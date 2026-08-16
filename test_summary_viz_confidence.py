"""Test confidence pairing in summary visualization."""
import re
from datetime import datetime
from pathlib import Path

import pytest

from memanto.app.services.summary_visualization_service import (
    SummaryVisualizationService,
)


def _make_summary_file(tmp_path: Path, content: str, filename: str) -> Path:
    f = tmp_path / filename
    f.write_text(content, encoding="utf-8")
    return f


class TestConfidencePairing:
    def test_normal_pairing(self, tmp_path):
        content = (
            "# Session
"
            "### [2026-01-01 10:00:00] [FACT] Memory A
"
            "- **Confidence**: `0.9`
"
            "---
"
            "### [2026-01-01 11:00:00] [FACT] Memory B
"
            "- **Confidence**: `0.7`
"
        )
        _make_summary_file(tmp_path, content, "agent1_2026-01-01_sess_123_summary.md")
        svc = SummaryVisualizationService()
        memories = svc._parse_session_files("agent1", "2026-01-01", tmp_path)
        assert len(memories) == 2
        assert memories[0]["confidence"] == 0.9
        assert memories[1]["confidence"] == 0.7

    def test_empty_title_does_not_misalign(self, tmp_path):
        content = (
            "# Session
"
            "### [2026-01-01 10:00:00] [FACT] 
"
            "- **Confidence**: `0.5`
"
            "---
"
            "### [2026-01-01 11:00:00] [FACT] Memory B
"
            "- **Confidence**: `0.9`
"
        )
        _make_summary_file(tmp_path, content, "agent1_2026-01-01_sess_123_summary.md")
        svc = SummaryVisualizationService()
        memories = svc._parse_session_files("agent1", "2026-01-01", tmp_path)
        assert len(memories) == 1
        assert memories[0]["title"] == "Memory B"
        assert memories[0]["confidence"] == 0.9

    def test_deleted_entry_confidence(self, tmp_path):
        content = (
            "# Session
"
            "### [2026-01-01 10:00:00] [FACT] Memory A
"
            "- **Confidence**: `0.9`
"
            "---
"
            "### [2026-01-01 11:00:00] [DELETED] Memory Deleted
"
            "- **Confidence**: `1.0`
"
            "---
"
            "### [2026-01-01 12:00:00] [FACT] Memory C
"
            "- **Confidence**: `0.7`
"
        )
        _make_summary_file(tmp_path, content, "agent1_2026-01-01_sess_123_summary.md")
        svc = SummaryVisualizationService()
        memories = svc._parse_session_files("agent1", "2026-01-01", tmp_path)
        assert len(memories) == 3
        assert memories[0]["confidence"] == 0.9
        assert memories[1]["confidence"] == 1.0
        assert memories[2]["confidence"] == 0.7

    def test_missing_confidence_uses_default(self, tmp_path):
        content = (
            "# Session
"
            "### [2026-01-01 10:00:00] [FACT] Memory A
"
            "- **Memory ID**: `mem_a`
"
        )
        _make_summary_file(tmp_path, content, "agent1_2026-01-01_sess_123_summary.md")
        svc = SummaryVisualizationService()
        memories = svc._parse_session_files("agent1", "2026-01-01", tmp_path)
        assert len(memories) == 1
        assert memories[0]["confidence"] == 0.8
