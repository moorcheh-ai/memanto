import sqlite3
from pathlib import Path

from export_holo import export_holo_to_okf
from validate import validate


def build_db(path: Path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE facts (
            fact_id INTEGER PRIMARY KEY, content TEXT NOT NULL UNIQUE,
            category TEXT, tags TEXT, trust_score REAL,
            retrieval_count INTEGER, helpful_count INTEGER,
            created_at TIMESTAMP, updated_at TIMESTAMP, hrr_vector BLOB
        );
        CREATE TABLE entities (
            entity_id INTEGER PRIMARY KEY, name TEXT NOT NULL,
            entity_type TEXT, aliases TEXT, created_at TIMESTAMP
        );
        CREATE TABLE fact_entities (fact_id INTEGER, entity_id INTEGER, PRIMARY KEY(fact_id, entity_id));
        CREATE TABLE memory_banks (bank_id INTEGER PRIMARY KEY, bank_name TEXT, vector BLOB, dim INTEGER, fact_count INTEGER, updated_at TIMESTAMP);
        INSERT INTO facts VALUES (7, 'Operator prefers amber light.', 'user_pref', 'light,night', 0.9, 3, 2, '2026-09-01 01:02:03', '2026-09-02 04:05:06', X'01');
        INSERT INTO entities VALUES (4, 'Amber Light', 'concept', 'warm light', '2026-09-01 01:02:03');
        INSERT INTO fact_entities VALUES (7, 4);
        """
    )
    conn.commit()
    conn.close()


def test_validator_proves_every_portable_field(tmp_path: Path):
    db = tmp_path / "holo.db"
    bundle = tmp_path / "okf"
    build_db(db)
    export_holo_to_okf(db, bundle)
    report = validate(db, bundle)
    assert report["status"] == "PASS"
    assert report["source_facts"] == report["okf_memories"] == 1
    assert report["checked_fields"] == 14
    assert report["mismatches"] == []


def test_validator_detects_silent_content_loss(tmp_path: Path):
    db = tmp_path / "holo.db"
    bundle = tmp_path / "okf"
    build_db(db)
    export_holo_to_okf(db, bundle)
    fact = next((bundle / "memories").rglob("fact-*.md"))
    fact.write_text(
        fact.read_text().replace("amber light", "blue light"), encoding="utf-8"
    )
    report = validate(db, bundle)
    assert report["status"] == "FAIL"
    assert any("content" in item for item in report["mismatches"])


def test_validator_accepts_memanto_style_reslugged_filename(tmp_path: Path):
    db = tmp_path / "holo.db"
    bundle = tmp_path / "okf"
    build_db(db)
    export_holo_to_okf(db, bundle)
    fact = next((bundle / "memories").rglob("fact-*.md"))
    renamed = fact.with_name("operator-prefers-amber-light.md")
    fact.rename(renamed)
    report = validate(db, bundle)
    assert report["status"] == "PASS"
    assert report["okf_memories"] == 1


def test_validator_rejects_non_holo_memory_in_fresh_destination(tmp_path: Path):
    db = tmp_path / "holo.db"
    bundle = tmp_path / "okf"
    build_db(db)
    export_holo_to_okf(db, bundle)
    extra = bundle / "memories" / "fact" / "unrelated.md"
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text("---\ntype: fact\ntitle: unrelated\n---\n\nnot from Holo\n")
    report = validate(db, bundle)
    assert report["status"] == "FAIL"
    assert any("non-Holo" in item for item in report["mismatches"])
