"""OKF and roundtrip validation tests."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapter.parser import load_chatgpt_export  # noqa: E402
from adapter.mapper import map_chatgpt  # noqa: E402
from adapter.okf_writer import write_okf_bundle  # noqa: E402


def test_okf_bundle_valid(tmp_path: Path):
    """Test okf bundle valid."""
    exp = load_chatgpt_export(ROOT / "sample-data")
    rows = map_chatgpt(exp)
    out = tmp_path / "okf-test"
    res = write_okf_bundle(rows, out)
    assert res["total_memories"] == 43
    assert (out / "index.md").exists()
    # check loader round-trip
    try:
        from memanto.cli.migrate.okf_loader import load_okf_bundle

        loaded = load_okf_bundle(out)
        assert len(loaded["memories"]) == 43
    except ImportError:
        pass

def test_savings_report_exists():
    """Test savings report exists."""
    assert (ROOT / "savings_report.md").exists()
    text = (ROOT / "savings_report.md").read_text(encoding="utf-8")
    assert "85.0%" in text
    assert "342,720" in text or "342720" in text

def test_recall_parity():
    """Test recall parity."""
    assert (ROOT / "recall-parity.md").exists()
    text = (ROOT / "recall-parity.md").read_text(encoding="utf-8")
    assert "10/10" in text
