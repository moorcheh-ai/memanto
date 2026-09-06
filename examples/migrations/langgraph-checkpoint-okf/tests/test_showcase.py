from __future__ import annotations

import sys
from pathlib import Path

import pytest


EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXAMPLE_ROOT))

from generate_langgraph_checkpoint import generate_checkpoint  # noqa: E402
from langgraph_checkpoint_to_okf import convert, extract_records, write_okf_bundle  # noqa: E402
from run_showcase import require_full_parity  # noqa: E402
from validate_recall_parity import validate  # noqa: E402


def test_langgraph_checkpoint_to_okf_showcase(tmp_path):
    source_db = tmp_path / "source" / "langgraph_memory.sqlite"
    transcript = tmp_path / "source" / "transcript.json"
    okf_dir = tmp_path / "okf_bundle"
    report = tmp_path / "validation" / "recall-parity-report.md"

    summary = generate_checkpoint(source_db, transcript)
    assert summary["memories"] == 5
    assert source_db.exists()

    records = convert(source_db, okf_dir)
    assert len(records) == 5
    assert (okf_dir / ".langgraph-checkpoint-okf.json").exists()
    write_okf_bundle(records, okf_dir, overwrite=True)
    assert (okf_dir / ".langgraph-checkpoint-okf.json").exists()
    assert {record.memory_type for record in records} == {
        "decision",
        "goal",
        "instruction",
        "preference",
    }

    loaded = extract_records(source_db)
    assert len(loaded) == 5

    validation = validate(
        source_db,
        okf_dir,
        EXAMPLE_ROOT / "data" / "golden_qa.json",
        report,
    )
    assert validation["source_score"] == 5
    assert validation["okf_score"] == 5
    assert validation["parity_percent"] == 100.0
    assert report.exists()


def test_showcase_rejects_partial_parity():
    with pytest.raises(RuntimeError, match="Recall parity validation failed"):
        require_full_parity({"questions": 2, "parity_score": 1})


def test_overwrite_refuses_non_generated_bundle(tmp_path):
    source_db = tmp_path / "source" / "langgraph_memory.sqlite"
    target = tmp_path / "manual_bundle"
    target.mkdir()
    index = target / "index.md"
    index.write_text("# Hand-authored bundle\n", encoding="utf-8")

    generate_checkpoint(source_db)
    records = extract_records(source_db)

    with pytest.raises(RuntimeError, match="non-generated OKF bundle"):
        write_okf_bundle(records, target, overwrite=True)

    assert index.read_text(encoding="utf-8") == "# Hand-authored bundle\n"
