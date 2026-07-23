from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from build_demo_video import import_type_lines, type_breakdown_lines
from build_evidence_report import _markdown, build_report, parse_import_counts
from generate_source import SESSIONS, generate_database
from langgraph_to_okf import convert_checkpoint_database
from langgraph_to_okf.adapter import _semantic_type, _state_to_memories, _ThreadRef
from query_source import query_source
from record_live_terminal import Event, _clean, _commands, resolve_venv_python
from show_okf_sample import select_memory_markdown
from supplement_live_video import append_inspection_events
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
    assert "memanto_import" not in report


def test_evidence_report_embeds_run_id_without_inventing_import(tmp_path):
    source = generate_database(tmp_path / "source.sqlite")
    source_bundle = tmp_path / "source-okf"
    roundtrip_bundle = tmp_path / "roundtrip-okf"
    convert_checkpoint_database(source, source_bundle)
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
        run_id="20260723T000000Z-deadbeef",
    )

    assert report["run_id"] == "20260723T000000Z-deadbeef"
    assert "memanto_import" not in report


def test_parse_import_counts_from_cli_output():
    lines = [
        "Import complete",
        "OKF nodes: 8",
        "Mapped memories: 8  (skipped 0)",
        "Imported: 8  Failed: 0  Batches: 1",
    ]
    assert parse_import_counts(lines) == {
        "imported": 8,
        "failed": 0,
        "mapped": 8,
        "skipped": 0,
        "okf_nodes": 8,
    }
    assert (
        parse_import_counts(["Dry run complete", "Mapped memories: 8  (skipped 0)"])
        is None
    )


def test_live_pipeline_feeds_measured_import_output_into_report(tmp_path):
    run_id = "20260723T000000Z-deadbeef"
    commands = _commands(f"langgraph-migration-{run_id.lower()}", run_id, tmp_path)
    cloud_import = next(
        command for command in commands if command.key == "cloud_import"
    )
    evidence_report = next(
        command for command in commands if command.key == "evidence_report"
    )

    expected = tmp_path / "cloud-import-output.txt"
    assert cloud_import.output_path == expected
    import_arg = evidence_report.argv.index("--import-output")
    assert evidence_report.argv[import_arg + 1] == str(expected)


def test_evidence_report_attaches_parsed_import_counts(tmp_path):
    source = generate_database(tmp_path / "source.sqlite")
    source_bundle = tmp_path / "source-okf"
    roundtrip_bundle = tmp_path / "roundtrip-okf"
    convert_checkpoint_database(source, source_bundle)
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
        run_id="run-with-import",
        import_output="Imported: 8  Failed: 0\nMapped memories: 8  (skipped 0)\n",
    )

    assert report["run_id"] == "run-with-import"
    assert report["memanto_import"]["imported"] == 8
    assert report["memanto_import"]["failed"] == 0
    rendered = _markdown(report)
    assert "Recall after Memanto import:" in rendered
    assert "Memanto import: 8 imported, 0 failed." in rendered
    assert "re-importing" not in rendered.lower()
    assert "Recall after round trip" not in rendered


def test_demo_video_helpers_use_summary_type_counts():
    summary = {
        "memories_by_type": {
            "artifact": 2,
            "decision": 1,
            "fact": 2,
            "goal": 1,
            "preference": 2,
        }
    }
    breakdown = type_breakdown_lines(summary)
    assert any("artifact/" in line and "2 transcripts" in line for line in breakdown)
    assert any("preference/" in line and "2 preferences" in line for line in breakdown)
    joined = " ".join(import_type_lines(summary))
    assert "artifact: 2" in joined
    assert "preference: 2" in joined


def test_resolve_venv_python_finds_scripts_or_bin(tmp_path):
    scripts = tmp_path / ".venv" / "Scripts"
    scripts.mkdir(parents=True)
    windows_python = scripts / "python.exe"
    windows_python.write_text("", encoding="utf-8")
    assert resolve_venv_python(tmp_path) == windows_python

    posix_root = tmp_path / "posix"
    bin_dir = posix_root / ".venv" / "bin"
    bin_dir.mkdir(parents=True)
    posix_python = bin_dir / "python"
    posix_python.write_text("", encoding="utf-8")
    assert resolve_venv_python(posix_root) == posix_python


def test_show_okf_sample_prefers_a_real_preference_memory(tmp_path):
    memories = tmp_path / "memories"
    (memories / "fact").mkdir(parents=True)
    (memories / "preference").mkdir(parents=True)
    (memories / "fact" / "fact.md").write_text("# Fact\n", encoding="utf-8")
    (memories / "preference" / "index.md").write_text(
        "# Index\n", encoding="utf-8"
    )
    preference = memories / "preference" / "markdown.md"
    preference.write_text("# Report format\n\nMarkdown\n", encoding="utf-8")

    assert select_memory_markdown(tmp_path) == preference


def test_supplemented_video_labels_post_run_markdown_inspection():
    original = [Event(1.0, "Round trip complete.")]
    supplemented = append_inspection_events(
        original,
        "Opening portable OKF Markdown: memories/preference/example.md\n# Example\n",
        command_label="python show_okf_sample.py ./memanto-roundtrip-okf",
    )

    assert supplemented[:1] == original
    assert any("POST-RUN ARTIFACT INSPECTION" in event.text for event in supplemented)
    assert any("# Example" in event.text for event in supplemented)
    assert supplemented[-1].text == "OKF Markdown is readable and portable."


def test_path_redaction_removes_absolute_windows_home_paths():
    home = Path.home()
    sample = (
        f"export wrote to {home / '.memanto' / 'agent-roundtrip-okf'} "
        f'json="{(home / ".memanto").as_posix()}" '
        f"escaped={str(home).replace(chr(92), chr(92) * 2)}"
    )
    cleaned = _clean(sample)
    assert str(home) not in cleaned
    assert home.as_posix() not in cleaned
    assert "~" in cleaned


def test_commitment_channel_maps_heuristically():
    assert _semantic_type("commitments") == "commitment"
    assert _semantic_type("tasks") == "commitment"
    memories = _state_to_memories(
        _ThreadRef("demo", ""),
        {"commitments": ["Ship the release notes"]},
        "2026-07-23T00:00:00+00:00",
        "ckpt-1",
    )
    assert len(memories) == 1
    assert memories[0]["type"] == "commitment"
    assert "Ship the release notes" in memories[0]["body"]


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
        json.dumps({"results": [{"question": "Q?", "answer": "yes", "passed": True}]}),
        encoding="utf-8",
    )
    memanto_path.write_text(
        json.dumps({"results": [{"question": "Q?", "answer": "no", "passed": False}]}),
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
