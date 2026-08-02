Looking at the code context, I need to complete the `test_okf.py` file. The context is cut off mid-function, and I need to implement a complete test file that covers OKF export/import functionality based on the description and existing code patterns.

```python
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
        {"fact": [_mem("f1", "Alpha fact", "Alpha content.")]},
        context_files=[summary, session],
    )
    base = svc.exports_dir / "agent1_okf"

    assert result["sections"] == ["memories", "context", "metrics"]
    assert (base / "context" / "agent1_2026-07-01.md").exists()
    assert (base / "context" / "agent1_2026-07-01_s1_summary.md").exists()

    # load_okf_bundle must ignore context/ and metrics/ sections.
    entries = load_okf_bundle(base)
    assert len(entries) == 1
    assert entries[0]["title"] == "Alpha fact"


def test_round_trip_via_x_memanto(tmp_path):
    """Memories exported with ``x_memanto`` frontmatter survive a load ->
    map_okf round-trip with original id, tags, and confidence intact."""
    memories_by_type = {
        "decision": [
            _mem(
                "d1",
                "Use gRPC for internal comms",
                "All internal services communicate via gRPC for performance.",
                tags=["architecture", "grpc"],
                confidence=0.95,
            ),
        ],
    }

    svc = OkfExportService(exports_dir=tmp_path / "exports")
    svc.write_okf_bundle("agentX", memories_by_type)
    base = svc.exports_dir / "agentX_okf"

    entries = load_okf_bundle(base)
    assert len(entries) == 1

    rows = map_okf(entries)
    assert len(rows) == 1
    row = rows[0]
    assert row["title"] == "Use gRPC for internal comms"
    assert row["content"] == "All internal services communicate via gRPC for performance."
    assert "architecture" in row["tags"]
    assert "grpc" in row["tags"]
    assert row["confidence"] == 0.95
    assert row["source_id"] == "d1"


def test_foreign_okf_bundle_unknown_keys_in_footer(tmp_path):
    """A foreign OKF bundle with free-form ``type`` and unknown frontmatter
    keys must be loaded without error; unknown keys land in ``[Supporting
    data]`` in the mapped content so no information is silently dropped."""
    bundle = tmp_path / "foreign_okf"
    memories_dir = bundle / "memories" / "insight"
    memories_dir.mkdir(parents=True)

    md = """\
---
title: Caching strategy chosen
type: insight
custom_field: important-value
priority: high
source: architecture-review-2026
---

Adopted Redis for session caching after benchmarking Memcached and Redis.
"""
    (memories_dir / "caching-strategy-chosen.md").mkdir(parents=False)
    (memories_dir / "caching-strategy-chosen.md").unlink(missing_ok=True)
    insight_file = memories_dir / "caching-strategy-chosen.md"
    insight_file.write_text(md, encoding="utf-8")

    entries = load_okf_bundle(bundle)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["title"] == "Caching strategy chosen"
    assert entry["type"] == "insight"

    rows = map_okf(entries)
    assert len(rows) == 1
    row = rows[0]
    assert "Caching strategy chosen" in row["title"]
    # Unknown keys must appear somewhere in the mapped content.
    combined = row["content"]
    assert "custom_field" in combined or "important-value" in combined
    assert "priority" in combined or "high" in combined


def test_load_okf_bundle_stacked_file(tmp_path):
    """A stacked OKF file (multiple ``---``-delimited documents in one file)
    is parsed into one entry per document."""
    bundle = tmp_path / "stacked_okf"
    memories_dir = bundle / "memories" / "fact"
    memories_dir.mkdir(parents=True)

    stacked = """\
---
title: Fact one
type: fact
---

Content of fact one.

---
title: Fact two
type: fact
---

Content of fact two.
"""
    (memories_dir / "fact.md").write_text(stacked, encoding="utf-8")

    entries = load_okf_bundle(bundle)
    assert len(entries) == 2
    titles = {e["title"] for e in entries}
    assert titles == {"Fact one", "Fact two"}


def test_load_okf_bundle_empty_bundle(tmp_path):
    """An empty or memories-less bundle yields an empty list without raising."""
    bundle = tmp_path / "empty_okf"
    (bundle / "memories").mkdir(parents=True)

    entries = load_okf_bundle(bundle)
    assert entries == []


def test_map_okf_preserves_all_entries(tmp_path):
    """``map_okf`` maps every loaded entry to a row; nothing is silently
    dropped for well-formed inputs."""
    entries = [
        {
            "title": f"Memory {i}",
            "type": "fact",
            "content": f"Content {i}.",
        }
        for i in range(10)
    ]
    rows = map_okf(entries)
    assert len(rows) == 10
    for i, row in enumerate(rows):
        assert row["title"] == f"Memory {i}"
        assert f"Content {i}." in row["content"]


def test_write_okf_bundle_one_split(tmp_path):
    """``split='one'`` writes all memories of every type into a single
    stacked file regardless of count."""
    memories_by_type