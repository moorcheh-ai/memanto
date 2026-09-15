import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from adapter import export, read_memories, render
from demo_source import populate

from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle


def test_real_agno_database_preserves_correction_and_user_scope(tmp_path: Path):
    database = tmp_path / "source.db"
    populate(database)
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    output = tmp_path / "bundle"
    summary = export(database, "demo-user", output)
    mapped = map_okf(load_okf_bundle(output))
    assert summary["mapped_memories"] == 4
    bodies = "\n".join(row["content"] for row in mapped)
    assert "Friday at 16:00 UTC" in bodies
    assert "Monday at 09:00 UTC" not in bodies
    assert "separate user's memory" not in bodies
    assert "PostgreSQL 16" in bodies
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before


def test_does_not_overwrite_existing_bundle(tmp_path: Path):
    database = tmp_path / "source.db"
    populate(database)
    output = tmp_path / "bundle"
    export(database, "demo-user", output)
    with pytest.raises(FileExistsError):
        export(database, "demo-user", output)


def test_missing_source_does_not_create_database(tmp_path: Path):
    database = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        read_memories(database, "demo-user")
    assert not database.exists()


def test_empty_scope_is_explicit_failure(tmp_path: Path):
    database = tmp_path / "source.db"
    populate(database)
    with pytest.raises(ValueError, match="No memories"):
        export(database, "unknown", tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_untrusted_ids_cannot_control_filenames():
    name, text = render(
        {
            "user_id": "../person",
            "memory_id": "../../outside",
            "memory": "नमस्ते 🌍",
            "created_at": 0,
            "updated_at": 0,
            "topics": ["hello: world"],
        }
    )
    assert "/" not in name and "\\" not in name
    assert "1970-01-01T00:00:00+00:00" in text
    assert "नमस्ते 🌍" in text


def test_oversize_memory_fails_before_publishing(tmp_path: Path):
    from agno.db.schemas.memory import UserMemory
    from agno.db.sqlite import SqliteDb

    database = tmp_path / "source.db"
    db = SqliteDb(db_file=str(database))
    db.upsert_user_memory(UserMemory(memory="x" * 12000, memory_id="long", user_id="u"))
    with pytest.raises(ValueError, match="truncate"):
        export(database, "u", tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_reserved_delimiter_rejected():
    with pytest.raises(ValueError, match="reserved"):
        render({"memory_id": "m", "user_id": "u", "memory": "<!-- okf-entry -->"})


def test_long_source_metadata_remains_in_imported_body(tmp_path: Path):
    from agno.db.schemas.memory import UserMemory
    from agno.db.sqlite import SqliteDb

    database = tmp_path / "source.db"
    db = SqliteDb(db_file=str(database))
    source_input = "Full original instruction " * 40
    db.upsert_user_memory(
        UserMemory(
            memory="Use Markdown.",
            memory_id="metadata",
            user_id="u",
            input=source_input,
        )
    )
    export(database, "u", tmp_path / "out")
    mapped = map_okf(load_okf_bundle(tmp_path / "out"))
    assert source_input in mapped[0]["content"]


def test_null_topics_and_epoch_zero_survive_real_sqlite(tmp_path: Path):
    database = tmp_path / "source.db"
    populate(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE agno_memories SET created_at=0, updated_at=0, topics=NULL"
        )
    export(database, "demo-user", tmp_path / "out")
    mapped = map_okf(load_okf_bundle(tmp_path / "out"))
    assert all(row["created_at"].timestamp() == 0 for row in mapped)
    assert all(row["updated_at"].timestamp() == 0 for row in mapped)
    assert all(row["tags"] == [] for row in mapped)


def test_source_record_archive_has_every_selected_column(tmp_path: Path):
    database = tmp_path / "source.db"
    populate(database)
    with sqlite3.connect(database) as connection:
        connection.execute("ALTER TABLE agno_memories ADD COLUMN future_field TEXT")
        connection.execute("UPDATE agno_memories SET future_field='retained'")
    export(database, "demo-user", tmp_path / "out")
    archived = json.loads((tmp_path / "out" / "source-records.json").read_text())
    assert len(archived) == 4
    assert all(row["future_field"] == "retained" for row in archived)
    mapped = map_okf(load_okf_bundle(tmp_path / "out"))
    assert all('"future_field": "retained"' in row["content"] for row in mapped)


def test_invalid_table_identifier_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="identifier"):
        read_memories(tmp_path / "source.db", "u", 'agno_memories"; DROP TABLE x;--')


def test_memory_boundary_whitespace_survives_loader(tmp_path: Path):
    from agno.db.schemas.memory import UserMemory
    from agno.db.sqlite import SqliteDb

    database = tmp_path / "source.db"
    original = "  Preserve leading whitespace.\n\nTrailing whitespace too.  "
    db = SqliteDb(db_file=str(database))
    db.upsert_user_memory(UserMemory(memory=original, memory_id="spaces", user_id="u"))
    export(database, "u", tmp_path / "out")
    mapped = map_okf(load_okf_bundle(tmp_path / "out"))
    assert original in mapped[0]["content"]
