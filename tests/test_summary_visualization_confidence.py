"""
Tests for SummaryVisualizationService confidence pairing.

Verifies that headings and confidence values are correctly paired by
position rather than by index, so a missing confidence line on one entry
does not misalign the confidence values of all subsequent entries.
"""

import re
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from memanto.app.services.summary_visualization_service import (
    SummaryVisualizationService,
)


def _write_session_file(tmp_path: Path, agent_id: str, date: str, content: str) -> Path:
    """Write a session summary MD file and return its path."""
    fname = f"{agent_id}_{date}_sess_test_summary.md"
    p = tmp_path / fname
    p.write_text(content, encoding="utf-8")
    return p


def test_confidence_pairing_aligned(tmp_path: Path):
    """Normal case: each heading has a matching confidence line."""
    agent_id = "agent1"
    date = "2026-01-01"
    md = (
        "# Session Summary
"
        "**Session ID:** `sess_1`
"
        "---

"
        "### [2026-01-01 10:00:00] [FACT] First memory
"
        "- **Memory ID**: `mem1`
"
        "- **Confidence**: `0.9`
"
        "---

"
        "### [2026-01-01 11:00:00] [FACT] Second memory
"
        "- **Memory ID**: `mem2`
"
        "- **Confidence**: `0.5`
"
        "---

"
    )
    _write_session_file(tmp_path, agent_id, date, md)

    svc = SummaryVisualizationService()
    memories = svc._parse_session_files(agent_id, date, tmp_path)

    assert len(memories) == 2
    assert memories[0]["confidence"] == 0.9
    assert memories[1]["confidence"] == 0.5


def test_confidence_pairing_with_missing_confidence(tmp_path: Path):
    """A heading without a confidence line must not shift subsequent pairings."""
    agent_id = "agent2"
    date = "2026-01-02"
    md = (
        "# Session Summary
"
        "**Session ID:** `sess_2`
"
        "---

"
        "### [2026-01-02 10:00:00] [FACT] Has confidence
"
        "- **Memory ID**: `mem1`
"
        "- **Confidence**: `0.9`
"
        "---

"
        "### [2026-01-02 11:00:00] [FACT] No confidence line
"
        "- **Memory ID**: `mem2`
"
        "- **Content**:
"
        "> Something
"
        "---

"
        "### [2026-01-02 12:00:00] [FACT] Has confidence again
"
        "- **Memory ID**: `mem3`
"
        "- **Confidence**: `0.3`
"
        "---

"
    )
    _write_session_file(tmp_path, agent_id, date, md)

    svc = SummaryVisualizationService()
    memories = svc._parse_session_files(agent_id, date, tmp_path)

    assert len(memories) == 3
    # First entry: confidence 0.9
    assert memories[0]["confidence"] == 0.9
    # Second entry: no confidence line, should get default 0.8
    assert memories[1]["confidence"] == 0.8
    # Third entry: confidence 0.3 (NOT 0.9 from the first entry)
    assert memories[2]["confidence"] == 0.3


def test_confidence_pairing_with_deletion_entry(tmp_path: Path):
    """Deletion entries have confidence=1.0; must not misalign neighbours."""
    agent_id = "agent3"
    date = "2026-01-03"
    md = (
        "# Session Summary
"
        "**Session ID:** `sess_3`
"
        "---

"
        "### [2026-01-03 10:00:00] [FACT] Normal memory
"
        "- **Memory ID**: `mem1`
"
        "- **Confidence**: `0.7`
"
        "---

"
        "### [2026-01-03 11:00:00] [DELETED] Memory Deleted
"
        "- **Memory ID**: `mem2`
"
        "- **Confidence**: `1.0`
"
        "---

"
        "### [2026-01-03 12:00:00] [FACT] Another normal memory
"
        "- **Memory ID**: `mem3`
"
        "- **Confidence**: `0.4`
"
        "---

"
    )
    _write_session_file(tmp_path, agent_id, date, md)

    svc = SummaryVisualizationService()
    memories = svc._parse_session_files(agent_id, date, tmp_path)

    assert len(memories) == 3
    assert memories[0]["confidence"] == 0.7
    assert memories[1]["confidence"] == 1.0
    assert memories[2]["confidence"] == 0.4


def test_confidence_pairing_all_missing(tmp_path: Path):
    """All headings lack confidence lines; all should get default 0.8."""
    agent_id = "agent4"
    date = "2026-01-04"
    md = (
        "# Session Summary
"
        "**Session ID:** `sess_4`
"
        "---

"
        "### [2026-01-04 10:00:00] [FACT] First
"
        "- **Content**: something
"
        "---

"
        "### [2026-01-04 11:00:00] [FACT] Second
"
        "- **Content**: something else
"
        "---

"
    )
    _write_session_file(tmp_path, agent_id, date, md)

    svc = SummaryVisualizationService()
    memories = svc._parse_session_files(agent_id, date, tmp_path)

    assert len(memories) == 2
    assert memories[0]["confidence"] == 0.8
    assert memories[1]["confidence"] == 0.8
