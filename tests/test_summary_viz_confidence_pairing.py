"""Test confidence-heading pairing in summary visualization (bounty #770)."""

from datetime import datetime
from pathlib import Path
import tempfile

from memanto.app.services.summary_visualization_service import SummaryVisualizationService


def _write_session_md(tmp_dir: Path, agent_id: str, date: str, sess_id: str, content: str) -> Path:
    p = tmp_dir / f"{agent_id}_{date}_{sess_id}_summary.md"
    p.write_text(content, encoding="utf-8")
    return p


def test_deleted_entry_does_not_shift_confidence():
    """A DELETED entry has a heading but no confidence line.

    Before the fix, the i-th heading was paired with the i-th confidence
    value, so the DELETED heading consumed one confidence slot and shifted
    every later confidence to the wrong heading.
    """
    svc = SummaryVisualizationService()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        md = (
            "# Session Summary for test-agent
"
            "**Session ID:** `sess_1`

"
            "---

"
            "### [2026-01-15 10:00:00] [DELETED] Memory Deleted
"
            "- **Memory ID**: `mem-del`
"
            "- **Confidence**: `1.0`
"
            "---

"
            "### [2026-01-15 10:05:00] [FACT] Real fact
"
            "- **Memory ID**: `mem-fact`
"
            "- **Confidence**: `0.9`
"
            "---

"
            "### [2026-01-15 10:10:00] [PREFERENCE] User preference
"
            "- **Memory ID**: `mem-pref`
"
            "- **Confidence**: `0.7`
"
            "---

"
        )
        _write_session_md(tmp_dir, "test-agent", "2026-01-15", "sess_1", md)

        memories = svc._parse_session_files("test-agent", "2026-01-15", tmp_dir)

        # There should be 3 parsed entries (DELETED + FACT + PREFERENCE)
        assert len(memories) == 3, f"Expected 3, got {len(memories)}"

        # The DELETED entry should have the default confidence (0.8)
        deleted = memories[0]
        assert deleted["type"] == "DELETED"
        assert deleted["confidence"] == 0.8, f"DELETED confidence should be default 0.8, got {deleted['confidence']}"

        # The FACT entry should have 0.9, NOT 1.0 (which was the bug)
        fact = memories[1]
        assert fact["type"] == "FACT"
        assert fact["confidence"] == 0.9, f"FACT confidence should be 0.9, got {fact['confidence']}"

        # The PREFERENCE entry should have 0.7, NOT 0.9 (which was the bug)
        pref = memories[2]
        assert pref["type"] == "PREFERENCE"
        assert pref["confidence"] == 0.7, f"PREFERENCE confidence should be 0.7, got {pref['confidence']}"


def test_multiple_deleted_entries_confidence_alignment():
    """Multiple DELETED entries must not cascade confidence misalignment."""
    svc = SummaryVisualizationService()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        md = (
            "# Session Summary for test-agent2
"
            "**Session ID:** `sess_2`

"
            "---

"
            "### [2026-02-01 08:00:00] [DELETED] Deleted A
"
            "- **Memory ID**: `del-a`
"
            "- **Confidence**: `1.0`
"
            "---

"
            "### [2026-02-01 08:01:00] [DELETED] Deleted B
"
            "- **Memory ID**: `del-b`
"
            "- **Confidence**: `1.0`
"
            "---

"
            "### [2026-02-01 08:05:00] [INSTRUCTION] Important rule
"
            "- **Memory ID**: `mem-inst`
"
            "- **Confidence**: `0.95`
"
            "---

"
            "### [2026-02-01 08:10:00] [GOAL] Project goal
"
            "- **Memory ID**: `mem-goal`
"
            "- **Confidence**: `0.6`
"
            "---

"
        )
        _write_session_md(tmp_dir, "test-agent2", "2026-02-01", "sess_2", md)

        memories = svc._parse_session_files("test-agent2", "2026-02-01", tmp_dir)

        assert len(memories) == 4

        # Both DELETED entries get default confidence
        assert memories[0]["type"] == "DELETED"
        assert memories[0]["confidence"] == 0.8
        assert memories[1]["type"] == "DELETED"
        assert memories[1]["confidence"] == 0.8

        # INSTRUCTION gets 0.95 (not shifted by DELETED entries)
        assert memories[2]["type"] == "INSTRUCTION"
        assert memories[2]["confidence"] == 0.95, f"Expected 0.95, got {memories[2]['confidence']}"

        # GOAL gets 0.6 (not shifted by DELETED entries)
        assert memories[3]["type"] == "GOAL"
        assert memories[3]["confidence"] == 0.6, f"Expected 0.6, got {memories[3]['confidence']}"
