from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from generate_source import SESSIONS, generate_database
from langgraph_to_okf import convert_checkpoint_database
from validate_bundle import load_documents, validate_recall

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

    report = validate_recall(bundle, ROOT / "golden_qa.json")
    assert report["recall_parity"] == 1.0


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
