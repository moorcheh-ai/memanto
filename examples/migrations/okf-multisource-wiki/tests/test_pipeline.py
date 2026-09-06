"""Tests for the multi-source OKF consolidation showcase."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters import load_chroma_memories, load_sqlite_memories  # noqa: E402
from consolidate import consolidate  # noqa: E402
from okf_writer import write_okf_bundle  # noqa: E402
from seed_chroma import seed_chroma  # noqa: E402
from seed_sqlite_store import seed_sqlite  # noqa: E402
from validate import evaluate_parity  # noqa: E402


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory: pytest.TempPathFactory) -> dict:
    base = tmp_path_factory.mktemp("multisource")
    chroma_dir = base / "chroma"
    sqlite_path = base / "sqlite" / "agent_memory.db"
    seed_chroma(chroma_dir, force=True)
    seed_sqlite(sqlite_path, force=True)
    chroma = load_chroma_memories(chroma_dir)
    sqlite = load_sqlite_memories(sqlite_path)
    active, archived, summary = consolidate(chroma, sqlite)
    bundle = base / "okf"
    write_okf_bundle(active, bundle, session_notes=[("note", "archived")])
    return {
        "chroma": chroma,
        "sqlite": sqlite,
        "active": active,
        "archived": archived,
        "summary": summary,
        "bundle": bundle,
    }


def test_real_sources_not_empty(pipeline: dict) -> None:
    assert len(pipeline["chroma"]) >= 10
    assert len(pipeline["sqlite"]) >= 6


def test_consolidation_archives_stale_language_preference(pipeline: dict) -> None:
    archived_ids = {m["id"] for m in pipeline["archived"]}
    # Original Chroma TypeScript preference must be archived after correction.
    assert "chroma:chroma-lang" in archived_ids
    # SQLite stale TypeScript-for-all-backend preference must be archived.
    assert any("sql-lang-stale" in i for i in archived_ids)
    # Correction remains active.
    active_text = "\n".join(m["content"] for m in pipeline["active"]).lower()
    assert "fastapi" in active_text or "python" in active_text


def test_okf_bundle_layout(pipeline: dict) -> None:
    bundle = pipeline["bundle"]
    assert (bundle / "index.md").exists()
    assert (bundle / "memories").is_dir()
    md_files = [
        p for p in (bundle / "memories").rglob("*.md") if p.name.lower() != "index.md"
    ]
    assert len(md_files) == len(pipeline["active"])
    sample = md_files[0].read_text(encoding="utf-8")
    assert sample.startswith("---\n")
    assert "type:" in sample
    assert "x_memanto:" in sample


def test_memanto_loader_maps_all_records(pipeline: dict) -> None:
    repo_root = ROOT.parents[2]
    sys.path.insert(0, str(repo_root))
    from memanto.cli.migrate.mappers import map_okf
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    export = load_okf_bundle(pipeline["bundle"])
    mapped = map_okf(export)
    assert len(export["memories"]) == len(pipeline["active"])
    assert len(mapped) == len(pipeline["active"])
    assert all(row.get("content") for row in mapped)


def test_recall_parity(pipeline: dict) -> None:
    report = evaluate_parity(
        source_memories=pipeline["active"],
        okf_bundle=pipeline["bundle"],
        questions_path=ROOT / "golden_questions.json",
    )
    assert report["is_recall_preserved"] is True
    assert report["okf_recall"].startswith(str(report["total"]))


def test_summary_counts(pipeline: dict) -> None:
    s = pipeline["summary"]
    assert s["active_count"] == len(pipeline["active"])
    assert s["archived_count"] == len(pipeline["archived"])
    assert s["chroma_source_count"] + s["sqlite_source_count"] > s["active_count"]
