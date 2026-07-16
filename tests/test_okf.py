"""OKF (Open Knowledge Format) export/import coverage.

Exercises the three pure building blocks — ``OkfExportService`` (Memanto ->
OKF bundle), ``load_okf_bundle`` (bundle -> entries), and ``map_okf`` (entries
-> Memanto batch-remember rows) — including the auto-split layout, the
Memanto <-> OKF round-trip via the ``x_memanto`` frontmatter block, and a
foreign OKF bundle whose free-form ``type`` and unknown keys must land in the
``[Supporting data]`` footer without loss.
"""

from memanto.app.services.okf_export_service import OkfExportService
from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle


def _mem(mem_id, title, content, **extra):
    base = {
        "id": mem_id,
        "title": title,
        "content": content,
        "tags": [],
        "confidence": 0.8,
    }
    base.update(extra)
    return base


def test_auto_split_layout(tmp_path):
    """`auto` writes one file per memory for small types and a single stacked
    file once a type exceeds the threshold; memories live under ``memories/``
    and index files are always written."""
    memories_by_type = {
        "fact": [
            _mem("f1", "Postgres is the DB", "Uses PostgreSQL 16."),
            _mem("f2", "API base URL", "Served at https://api.example.com."),
        ],
        "event": [_mem(f"e{i}", f"Standup {i}", f"Standup {i}.") for i in range(60)],
    }

    svc = OkfExportService(exports_dir=tmp_path / "exports")
    result = svc.write_okf_bundle(
        "agent1", memories_by_type, split="auto", threshold=50
    )
    base = svc.exports_dir / "agent1_okf"
    memories = base / "memories"

    assert result["total_memories"] == 62
    assert result["per_type_counts"] == {"fact": 2, "event": 60}
    assert result["sections"] == ["memories", "metrics"]

    # Small type -> file per memory (+ index); large type -> stacked file.
    assert (base / "index.md").exists()
    assert (memories / "index.md").exists()
    assert (memories / "fact" / "postgres-is-the-db.md").exists()
    assert (memories / "fact" / "index.md").exists()
    assert (memories / "event" / "event.md").exists()
    assert not (memories / "event" / "standup-0.md").exists()
    # Aggregate metrics generated from the gathered memories.
    assert (base / "metrics" / "overview.md").exists()


def test_context_sections_and_import_scope(tmp_path):
    """Daily-summary and session files are copied into their sections, and
    import stays scoped to ``memories/`` so those context logs are never
    re-ingested as memories."""
    summary = tmp_path / "agent1_2026-07-01.md"
    summary.write_text("# Daily summary\nStuff happened.\n", encoding="utf-8")
    session = tmp_path / "agent1_2026-07-01_s1_summary.md"
    session.write_text(
        "# Session Summary for agent1\n### [2026-07-01 10:00:00] [FACT] X\n- **Source**: `user`\n",
        encoding="utf-8",
    )

    svc = OkfExportService(exports_dir=tmp_path / "exports")
    result = svc.write_okf_bundle(
        "agent1",
        {"fact": [_mem("f1", "A fact", "Water is wet.")]},
        summaries=[summary],
        sessions=[session],
    )
    base = svc.exports_dir / "agent1_okf"

    assert set(result["sections"]) == {
        "memories",
        "daily-summaries",
        "sessions",
        "metrics",
    }
    assert (base / "daily-summaries" / "agent1_2026-07-01.md").exists()
    assert (base / "sessions" / "agent1_2026-07-01_s1_summary.md").exists()

    # Import must see only the one memory, not the summary/session docs.
    export = load_okf_bundle(base)
    assert len(export["memories"]) == 1
    assert export["memories"][0]["title"] == "A fact"


def test_memanto_round_trip_preserves_extras(tmp_path):
    """Memanto -> OKF -> Memanto keeps type/confidence/source_ref/tags/body via
    the ``x_memanto`` block, and always marks provenance as imported."""
    memories_by_type = {
        "fact": [
            _mem(
                "m1",
                "Postgres is the DB",
                "The project uses PostgreSQL 16.",
                tags=["infra", "db"],
                confidence=0.9,
                provenance="explicit_statement",
                source="user",
                status="active",
                created_at="2026-05-28T14:30:00Z",
                source_ref="https://example.com/db",
            )
        ],
        "decision": [_mem("d1", "Chose Redis", "We decided on Redis for cache.")],
    }

    svc = OkfExportService(exports_dir=tmp_path / "exports")
    result = svc.write_okf_bundle("agent1", memories_by_type, split="file")

    rows = map_okf(load_okf_bundle(result["output_path"]))
    by_title = {r["title"]: r for r in rows}

    pg = by_title["Postgres is the DB"]
    assert pg["type"] == "fact"  # x_memanto.type round-trips
    assert pg["confidence"] == 0.9  # x_memanto.confidence round-trips
    assert pg["source_ref"] == "https://example.com/db"  # resource -> source_ref
    assert pg["provenance"] == "imported"
    assert set(pg["tags"]) == {"infra", "db"}
    assert pg["created_at"] is not None
    assert "PostgreSQL 16" in pg["content"]
    assert by_title["Chose Redis"]["type"] == "decision"


def test_foreign_okf_bundle_is_lossless(tmp_path):
    """A foreign OKF doc: free-form ``type`` -> auto-classify (None), and the
    type, unknown keys, and links are preserved in the footer. ``index.md`` is
    skipped."""
    tables = tmp_path / "tables"
    tables.mkdir()
    (tables / "orders.md").write_text(
        "---\n"
        "type: BigQuery Table\n"
        "title: Orders\n"
        "description: One row per completed customer order.\n"
        "resource: https://console.cloud.google.com/bigquery?t=orders\n"
        "tags: [sales, revenue]\n"
        "timestamp: 2026-05-28T14:30:00Z\n"
        "owner: data-team\n"
        "---\n\n"
        "# Schema\nJoined with [customers](/tables/customers.md).\n",
        encoding="utf-8",
    )
    (tables / "index.md").write_text(
        "---\ntype: index\ntitle: tables\n---\n- [Orders](orders.md)\n",
        encoding="utf-8",
    )

    export = load_okf_bundle(tmp_path)
    assert len(export["memories"]) == 1  # index.md skipped

    row = map_okf(export)[0]
    assert row["type"] is None  # free-form type -> auto-classify
    assert row["source"] == "okf"
    assert row["source_ref"] == "https://console.cloud.google.com/bigquery?t=orders"
    assert row["provenance"] == "imported"
    assert "One row per completed customer order." in row["content"]  # description
    assert "OKF type: BigQuery Table" in row["content"]  # unmapped type -> footer
    assert "OKF owner: data-team" in row["content"]  # unknown key -> footer
    assert "customers -> /tables/customers.md" in row["content"]  # link -> footer


def test_loader_splits_stacked_file(tmp_path):
    """A stacked per-type file is split back into one entry per memory."""
    memories_by_type = {
        "event": [
            _mem(f"e{i}", f"Standup {i}", f"Standup {i} happened.") for i in range(5)
        ]
    }
    svc = OkfExportService(exports_dir=tmp_path / "exports")
    result = svc.write_okf_bundle("agent1", memories_by_type, split="type")

    export = load_okf_bundle(result["output_path"])
    assert len(export["memories"]) == 5
    assert {m["title"] for m in export["memories"]} == {
        f"Standup {i}" for i in range(5)
    }
