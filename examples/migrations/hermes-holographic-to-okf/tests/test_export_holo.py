import sqlite3
from pathlib import Path

import pytest
import yaml
from export_holo import export_holo_to_okf, load_holo_snapshot


def make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE facts (
            fact_id INTEGER PRIMARY KEY,
            content TEXT NOT NULL UNIQUE,
            category TEXT DEFAULT 'general',
            tags TEXT DEFAULT '',
            trust_score REAL DEFAULT 0.5,
            retrieval_count INTEGER DEFAULT 0,
            helpful_count INTEGER DEFAULT 0,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            hrr_vector BLOB
        );
        CREATE TABLE entities (
            entity_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            entity_type TEXT DEFAULT 'unknown',
            aliases TEXT DEFAULT '',
            created_at TIMESTAMP
        );
        CREATE TABLE fact_entities (
            fact_id INTEGER,
            entity_id INTEGER,
            PRIMARY KEY (fact_id, entity_id)
        );
        CREATE TABLE memory_banks (
            bank_id INTEGER PRIMARY KEY,
            bank_name TEXT NOT NULL UNIQUE,
            vector BLOB NOT NULL,
            dim INTEGER NOT NULL,
            fact_count INTEGER DEFAULT 0,
            updated_at TIMESTAMP
        );
        """
    )
    conn.execute(
        """INSERT INTO facts VALUES
        (1, ?, 'user_pref', 'lighting, playa', 0.85, 4, 2,
         '2026-09-01 12:00:00', '2026-09-03 14:00:00', X'0102')""",
        ("The operator prefers warm work lights after sunset.",),
    )
    conn.execute(
        """INSERT INTO entities VALUES
        (1, 'Rift Cathedral', 'project', 'Rift', '2026-09-01 12:00:00')"""
    )
    conn.execute("INSERT INTO fact_entities VALUES (1, 1)")
    conn.execute(
        """INSERT INTO memory_banks VALUES
        (1, 'cat:user_pref', X'010203', 1024, 1, '2026-09-03 14:00:00')"""
    )
    conn.commit()
    conn.close()


def test_snapshot_preserves_canonical_fields_and_marks_derived(tmp_path: Path):
    db = tmp_path / "memory_store.db"
    make_db(db)

    snap = load_holo_snapshot(db)

    assert snap["facts"][0]["fact_id"] == 1
    assert snap["facts"][0]["trust_score"] == 0.85
    assert snap["facts"][0]["entities"][0]["name"] == "Rift Cathedral"
    assert snap["facts"][0]["has_hrr_vector"] is True
    assert snap["derived"]["memory_bank_count"] == 1


def test_export_emits_valid_okf_with_holo_provenance(tmp_path: Path):
    db = tmp_path / "memory_store.db"
    out = tmp_path / "okf"
    make_db(db)

    report = export_holo_to_okf(db, out)

    assert report["source_facts"] == 1
    assert report["exported_memories"] == 1
    assert len(report["source_sha256"]) == 64
    assert len(report["bundle_manifest_sha256"]) == 64
    files = sorted((out / "memories" / "preference").glob("fact-*.md"))
    assert len(files) == 1
    text = files[0].read_text()
    front = yaml.safe_load(text.split("---", 2)[1])
    assert front["type"] == "preference"
    assert front["tags"] == ["lighting", "playa"]
    assert front["x_memanto"]["confidence"] == 0.85
    assert front["x_memanto"]["source"] == "hermes-holographic"
    assert front["x_memanto"]["provenance"] == "imported"
    assert "fact_id: 1" in text
    assert "name: Rift Cathedral" in text
    assert "hrr_vector: rebuild" in text
    assert "prefers warm work lights" in text


def test_export_is_deterministic_and_replaces_stale_files(tmp_path: Path):
    db = tmp_path / "memory_store.db"
    out = tmp_path / "okf"
    make_db(db)

    export_holo_to_okf(db, out)
    first = {p.relative_to(out): p.read_bytes() for p in out.rglob("*") if p.is_file()}
    (out / "memories" / "preference" / "stale.md").write_text("stale")
    export_holo_to_okf(db, out)
    second = {p.relative_to(out): p.read_bytes() for p in out.rglob("*") if p.is_file()}

    assert first == second
    assert not (out / "memories" / "preference" / "stale.md").exists()


def test_export_refuses_records_that_would_risk_memanto_truncation(tmp_path: Path):
    db = tmp_path / "memory_store.db"
    out = tmp_path / "okf"
    make_db(db)
    conn = sqlite3.connect(db)
    try:
        conn.execute("UPDATE facts SET content = ? WHERE fact_id = 1", ("x" * 9500,))
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError, match="Memanto content limit"):
        export_holo_to_okf(db, out)
