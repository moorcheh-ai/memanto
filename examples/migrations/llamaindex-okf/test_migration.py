import json
import sqlite3
from pathlib import Path

from generate_source import build_store
from migrate_to_okf import _memory_type, convert, load_rows, redact_data
from show_portability import portability_story
from validate_round_trip import retrieve_answer, validate

HERE = Path(__file__).parent


def test_real_llamaindex_store_round_trips_to_okf(tmp_path):
    database = tmp_path / "source.sqlite"
    bundle = tmp_path / "bundle"
    assert build_store(database) == 13
    manifest = convert(database, bundle)
    report = validate(database, bundle, HERE / "golden_qa.json")

    rows = load_rows(database)
    assert len(rows) == 13
    assert {row["status"] for row in rows} == {"active", "archived"}
    assert sum(row["status"] == "active" for row in rows) == 10
    assert sum(row["status"] == "archived" for row in rows) == 3
    assert manifest["source_records"] == 13
    assert manifest["mapped_memories"] == 13
    assert manifest["skipped"] == 0
    assert report["record_recall"] == 1.0
    assert report["golden_recall"] == 1.0
    assert report["passed"] is True


def test_converter_refuses_to_overwrite_bundle(tmp_path):
    database = tmp_path / "source.sqlite"
    bundle = tmp_path / "bundle"
    build_store(database)
    convert(database, bundle)

    try:
        convert(database, bundle)
    except FileExistsError:
        pass
    else:
        raise AssertionError("converter should not overwrite an existing bundle")


def test_nested_metadata_redaction_preserves_structure():
    source = {
        "api_key": "sk-do-not-copy",
        "owner": "person@example.com",
        "nested": {"access_token": "abc", "count": 2},
    }
    assert redact_data(source) == {
        "api_key": "[REDACTED_SECRET]",
        "owner": "[REDACTED_EMAIL]",
        "nested": {"access_token": "[REDACTED_SECRET]", "count": 2},
    }


def test_sensitive_message_text_is_redacted_end_to_end(tmp_path):
    database = tmp_path / "source.sqlite"
    bundle = tmp_path / "bundle"
    build_store(database)
    with sqlite3.connect(database) as connection:
        row_id, raw = connection.execute(
            "SELECT id, data FROM llama_index_memory ORDER BY id LIMIT 1"
        ).fetchone()
        data = json.loads(raw)
        data["blocks"][0]["text"] = "Email person@example.com; secret: hunter2"
        connection.execute(
            "UPDATE llama_index_memory SET data = ? WHERE id = ?",
            (json.dumps(data), row_id),
        )

    convert(database, bundle)
    rendered = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (bundle / "memories").glob("*/*.md")
    )
    assert "person@example.com" not in rendered
    assert "hunter2" not in rendered
    assert "[REDACTED_EMAIL]" in rendered
    assert "[REDACTED_SECRET]" in rendered


def test_unsupported_explicit_type_uses_fallback_confidence(tmp_path):
    database = tmp_path / "source.sqlite"
    bundle = tmp_path / "bundle"
    build_store(database)
    with sqlite3.connect(database) as connection:
        row_id, raw = connection.execute(
            "SELECT id, data FROM llama_index_memory ORDER BY id LIMIT 1"
        ).fetchone()
        data = json.loads(raw)
        data["additional_kwargs"]["memory_type"] = "note"
        connection.execute(
            "UPDATE llama_index_memory SET data = ? WHERE id = ?",
            (json.dumps(data), row_id),
        )

    convert(database, bundle)
    record = next((bundle / "memories" / "fact").glob("*.md")).read_text(
        encoding="utf-8"
    )
    assert "confidence: 0.75" in record


def test_human_reviewed_assistant_fallback_is_observation():
    """Lock the submitter-reviewed fallback: assistant replies are observations."""
    assert _memory_type("assistant", {}, "A neutral assistant reply") == "observation"
    assert _memory_type("model", {}, "A neutral model reply") == "observation"
    assert _memory_type("chatbot", {}, "A neutral chatbot reply") == "observation"
    assert _memory_type(
        "assistant", {"memory_type": "learning"}, "An explicitly typed reply"
    ) == "learning"


def test_portability_story_exposes_lock_in_and_recovery(tmp_path):
    database = tmp_path / "source.sqlite"
    bundle = tmp_path / "bundle"
    build_store(database)
    convert(database, bundle)

    story = portability_story(database, bundle, HERE / "golden_qa.json")

    assert story["before_switch_llamaindex"]["answered"] == 6
    assert story["after_switch_without_export"]["answered"] == 0
    assert story["after_open_okf"]["answered"] == 6
    assert story["passed"] is True


def test_recall_requires_the_question_specific_record():
    result = retrieve_answer(
        "What is the preferred color?",
        ["The capital is Paris.", "The preferred color is blue."],
        "Paris",
    )
    assert result["retrieved"] == "The preferred color is blue."
    assert result["passed"] is False
