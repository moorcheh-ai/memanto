from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from build_evidence_report import build_report
from generate_source import SESSIONS, generate_database
from langgraph_to_okf import convert_checkpoint_database
from query_source import query_source
from validate_bundle import load_documents, validate_content
from validate_parity import validate_parity

ROOT = Path(__file__).resolve().parents[1]


def test_real_langgraph_database_converts_losslessly(tmp_path):
    database = generate_database(tmp_path / "source.sqlite")
    bundle = tmp_path / "bundle"

    summary = convert_checkpoint_database(database, bundle)

    assert summary.threads == len(SESSIONS)
    assert summary.checkpoints > sum(len(turns) for turns in SESSIONS.values())
    assert summary.memories >= 8
    assert summary.memories_by_type["artifact"] == len(SESSIONS)
    assert summary.memories_by_type["preference"] == 2
    assert (bundle / "index.md").is_file()
    assert (bundle / "migration-summary.json").is_file()

    report = validate_content(bundle, ROOT / "golden_qa.json")
    assert report["content_coverage"] == 1.0


def test_source_database_is_not_modified(tmp_path):
    database = generate_database(tmp_path / "source.sqlite")
    before = database.read_bytes()

    convert_checkpoint_database(database, tmp_path / "bundle")

    assert database.read_bytes() == before


def test_correction_wins_in_latest_checkpoint(tmp_path):
    database = generate_database(tmp_path / "source.sqlite")
    bundle = tmp_path / "bundle"
    convert_checkpoint_database(database, bundle)

    documents = load_documents(bundle)
    preference_docs = [
        document
        for document in documents
        if document["frontmatter"].get("type") == "preference"
        and "Report Format" in document["frontmatter"].get("title", "")
    ]
    assert len(preference_docs) == 1
    assert "Markdown" in preference_docs[0]["body"]
    assert preference_docs[0]["frontmatter"]["x_memanto"]["source"] == "langgraph"


def test_invalid_sqlite_file_is_rejected(tmp_path):
    database = tmp_path / "not-langgraph.sqlite"
    with sqlite3.connect(database):
        pass

    with pytest.raises(ValueError, match="no LangGraph checkpoints table"):
        convert_checkpoint_database(database, tmp_path / "bundle")


def test_summary_matches_files(tmp_path):
    database = generate_database(tmp_path / "source.sqlite")
    bundle = tmp_path / "bundle"
    summary = convert_checkpoint_database(database, bundle)

    stored = json.loads((bundle / "migration-summary.json").read_text())
    assert stored["memories"] == summary.memories
    assert len(load_documents(bundle)) == summary.memories


def test_existing_output_requires_explicit_overwrite(tmp_path):
    database = generate_database(tmp_path / "source.sqlite")
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "keep.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        convert_checkpoint_database(database, bundle)

    assert (bundle / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_output_cannot_contain_source_database(tmp_path):
    source_dir = tmp_path / "source"
    database = generate_database(source_dir / "checkpoints.sqlite")

    with pytest.raises(ValueError, match="cannot contain the source"):
        convert_checkpoint_database(database, source_dir, overwrite=True)

    assert database.is_file()


def test_evidence_report_uses_measured_files_and_recall(tmp_path):
    source = generate_database(tmp_path / "source.sqlite")
    source_bundle = tmp_path / "source-okf"
    roundtrip_bundle = tmp_path / "roundtrip-okf"
    source_summary = convert_checkpoint_database(source, source_bundle)
    convert_checkpoint_database(source, roundtrip_bundle)
    recall = {"questions": 5, "passed": 5, "recall_parity": 1.0}
    source_recall = tmp_path / "source-recall.json"
    roundtrip_recall = tmp_path / "roundtrip-recall.json"
    source_recall.write_text(json.dumps(recall), encoding="utf-8")
    roundtrip_recall.write_text(json.dumps(recall), encoding="utf-8")

    report = build_report(
        source,
        source_bundle,
        roundtrip_bundle,
        source_recall,
        roundtrip_recall,
    )

    assert report["source"]["threads"] == len(SESSIONS)
    assert report["source"]["checkpoints"] > 0
    assert report["first_okf_bundle"]["memories"] == source_summary.memories
    assert len(report["source"]["sha256"]) == 64
    assert len(report["first_okf_bundle"]["sha256"]) == 64
    assert report["recall"]["after_memanto_roundtrip"] == 1.0


def test_source_questions_read_latest_checkpoint_state(tmp_path):
    source = generate_database(tmp_path / "source.sqlite")

    report = query_source(source, ROOT / "golden_qa.json")

    assert report["questions"] == 5
    assert report["passed"] == 5
    assert report["score"] == 1.0
    assert [item["question"] for item in report["results"]] == [
        item["question"]
        for item in json.loads((ROOT / "golden_qa.json").read_text(encoding="utf-8"))
    ]


def test_parity_requires_identical_questions_and_both_sides_to_pass(tmp_path):
    source_path = tmp_path / "source.json"
    memanto_path = tmp_path / "memanto.json"
    source_path.write_text(
        json.dumps(
            {"results": [{"question": "Q?", "answer": "yes", "passed": True}]}
        ),
        encoding="utf-8",
    )
    memanto_path.write_text(
        json.dumps(
            {"results": [{"question": "Q?", "answer": "no", "passed": False}]}
        ),
        encoding="utf-8",
    )

    report = validate_parity(source_path, memanto_path)

    assert report["questions"] == 1
    assert report["passed"] == 0
    assert report["recall_parity"] == 0.0


def test_evidence_ignores_okf_index_pages_when_summary_is_absent(tmp_path):
    source = generate_database(tmp_path / "source.sqlite")
    source_bundle = tmp_path / "source-okf"
    convert_checkpoint_database(source, source_bundle)
    roundtrip_bundle = tmp_path / "roundtrip-okf"
    memory_dir = roundtrip_bundle / "memories" / "fact"
    memory_dir.mkdir(parents=True)
    (roundtrip_bundle / "memories" / "index.md").write_text("index")
    (memory_dir / "index.md").write_text("index")
    (memory_dir / "one.md").write_text("memory")
    recall = {"questions": 1, "passed": 1, "recall_parity": 1.0}
    source_recall = tmp_path / "source-recall.json"
    roundtrip_recall = tmp_path / "roundtrip-recall.json"
    source_recall.write_text(json.dumps(recall), encoding="utf-8")
    roundtrip_recall.write_text(json.dumps(recall), encoding="utf-8")

    report = build_report(
        source,
        source_bundle,
        roundtrip_bundle,
        source_recall,
        roundtrip_recall,
    )

    assert report["memanto_roundtrip_okf"]["memories"] == 1
    assert report["memanto_roundtrip_okf"]["memories_by_type"] == {"fact": 1}
