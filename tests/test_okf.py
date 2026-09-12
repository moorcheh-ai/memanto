"""OKF (Open Knowledge Format) export/import coverage.

Exercises the three pure building blocks — ``OkfExportService`` (Memanto ->
OKF bundle), ``load_okf_bundle`` (bundle -> entries), and ``map_okf`` (entries
-> Memanto batch-remember rows) — including the auto-split layout, the
Memanto <-> OKF round-trip via the ``x_memanto`` frontmatter block, and a
foreign OKF bundle whose free-form ``type`` and unknown keys must land in the
``[Supporting data]`` footer without loss.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path
from threading import Event
from time import perf_counter

import pytest
import yaml  # type: ignore[import-untyped]

import memanto.cli.migrate.okf_loader as okf_loader
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
    """Memanto -> OKF -> Memanto keeps schema fields and metadata via ``x_memanto``."""
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
                updated_at="2026-06-01T09:15:00Z",
                expires_at="2026-08-01T09:15:00Z",
                ttl_seconds=5_529_600,
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
    assert pg["provenance"] == "explicit_statement"
    assert set(pg["tags"]) == {"infra", "db"}
    assert pg["created_at"] is not None
    assert pg["updated_at"].isoformat() == "2026-06-01T09:15:00+00:00"
    assert pg["expires_at"].isoformat() == "2026-08-01T09:15:00+00:00"
    assert pg["ttl_seconds"] == 5_529_600
    assert "PostgreSQL 16" in pg["content"]
    assert by_title["Chose Redis"]["type"] == "decision"


def test_okf_import_ignores_invalid_temporal_extensions(tmp_path):
    """Malformed foreign extensions must not break an otherwise valid import."""
    (tmp_path / "memory.md").write_text(
        "---\n"
        "type: fact\n"
        "title: Durable fact\n"
        "x_memanto:\n"
        "  updated_at: true\n"
        "  expires_at: true\n"
        "  ttl_seconds: true\n"
        "---\n\n"
        "This memory remains importable.\n",
        encoding="utf-8",
    )

    row = map_okf(load_okf_bundle(tmp_path))[0]

    assert row["updated_at"] is not None
    assert row["expires_at"] is None
    assert row["ttl_seconds"] is None


def test_okf_invalid_provenance_falls_back_to_imported():
    """Foreign or malformed provenance must not reach batch validation."""
    export = {
        "memories": [
            {
                "title": "Foreign memory",
                "body": "Imported from another OKF producer.",
                "x_memanto": {"provenance": "untrusted-value"},
            }
        ]
    }

    assert map_okf(export)[0]["provenance"] == "imported"


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


def test_reexport_replaces_stale_bundle_entries(tmp_path):
    """A refreshed export must be an exact snapshot, not an overlay that can
    resurrect deleted or renamed memories during a later import."""
    svc = OkfExportService(exports_dir=tmp_path / "exports")
    first = {
        "fact": [_mem("f1", "Old fact", "This fact was later deleted.")],
        "event": [_mem("e1", "Old event", "This event was later deleted.")],
    }
    svc.write_okf_bundle("agent1", first, split="file")

    second = {"fact": [_mem("f2", "Current fact", "This is still current.")]}
    result = svc.write_okf_bundle("agent1", second, split="file")

    bundle = tmp_path / "exports" / "agent1_okf"
    assert not (bundle / "memories" / "fact" / "old-fact.md").exists()
    assert not (bundle / "memories" / "event").exists()

    imported = load_okf_bundle(result["output_path"])["memories"]
    assert [memory["title"] for memory in imported] == ["Current fact"]


def test_failed_reexport_preserves_last_good_bundle(tmp_path, monkeypatch):
    """A failed final rename restores the last good bundle and cleans up."""
    svc = OkfExportService(exports_dir=tmp_path / "exports")
    first = {"fact": [_mem("f1", "Last good fact", "Keep this snapshot.")]}
    result = svc.write_okf_bundle("agent1", first, split="file")

    original_rename = Path.rename

    def fail_staging_publish(path, target):
        target = Path(target)
        if path.name.startswith(".agent1_okf.tmp-") and target.name == "agent1_okf":
            raise OSError("simulated publish failure")
        return original_rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_staging_publish)
    with pytest.raises(OSError, match="simulated publish failure"):
        svc.write_okf_bundle(
            "agent1",
            {"fact": [_mem("f2", "Partial fact", "Do not publish this.")]},
            split="file",
        )

    imported = load_okf_bundle(result["output_path"])["memories"]
    assert [memory["title"] for memory in imported] == ["Last good fact"]
    assert not list((tmp_path / "exports").glob(".agent1_okf.tmp-*"))
    assert not list((tmp_path / "exports").glob(".agent1_okf.backup-*"))


def test_loader_waits_for_bundle_replacement(tmp_path, monkeypatch):
    """A reader cannot observe the target-to-backup replacement window."""
    svc = OkfExportService(exports_dir=tmp_path / "exports")
    svc.write_okf_bundle(
        "agent1", {"fact": [_mem("f1", "Old fact", "Old snapshot.")]}, split="file"
    )
    bundle = tmp_path / "exports" / "agent1_okf"
    replacement_window = Event()
    allow_publish = Event()
    original_rename = Path.rename

    def pause_after_backup(path, target):
        target = Path(target)
        result = original_rename(path, target)
        if path == bundle and target.name.startswith(".agent1_okf.backup-"):
            replacement_window.set()
            if not allow_publish.wait(timeout=5):
                raise TimeoutError("test did not release the bundle publisher")
        return result

    monkeypatch.setattr(Path, "rename", pause_after_backup)
    with ThreadPoolExecutor(max_workers=2) as executor:
        publish = executor.submit(
            svc.write_okf_bundle,
            "agent1",
            {"fact": [_mem("f2", "New fact", "New snapshot.")]},
            None,
            "file",
        )
        try:
            assert replacement_window.wait(timeout=5)
            read = executor.submit(load_okf_bundle, bundle)
            with pytest.raises(FutureTimeout):
                read.result(timeout=0.1)
        finally:
            allow_publish.set()

        publish.result(timeout=5)
        imported = read.result(timeout=5)["memories"]

    assert [memory["title"] for memory in imported] == ["New fact"]
    assert not list((tmp_path / "exports").glob(".agent1_okf.backup-*"))


def test_single_file_loader_uses_bundle_lock(tmp_path, monkeypatch):
    """An in-bundle file import waits on the bundle lock during replacement."""
    svc = OkfExportService(exports_dir=tmp_path / "exports")
    svc.write_okf_bundle(
        "agent1", {"fact": [_mem("f1", "Stable slug", "Old snapshot.")]}, split="file"
    )
    bundle = tmp_path / "exports" / "agent1_okf"
    entry = bundle / "memories" / "fact" / "stable-slug.md"
    replacement_window = Event()
    allow_publish = Event()
    original_rename = Path.rename

    def pause_after_backup(path, target):
        target = Path(target)
        result = original_rename(path, target)
        if path == bundle and target.name.startswith(".agent1_okf.backup-"):
            replacement_window.set()
            if not allow_publish.wait(timeout=5):
                raise TimeoutError("test did not release the bundle publisher")
        return result

    monkeypatch.setattr(Path, "rename", pause_after_backup)
    with ThreadPoolExecutor(max_workers=2) as executor:
        publish = executor.submit(
            svc.write_okf_bundle,
            "agent1",
            {"fact": [_mem("f1", "Stable slug", "New snapshot.")]},
            None,
            "file",
        )
        try:
            assert replacement_window.wait(timeout=5)
            read = executor.submit(load_okf_bundle, entry)
            with pytest.raises(FutureTimeout):
                read.result(timeout=0.1)
        finally:
            allow_publish.set()

        publish.result(timeout=5)
        imported = read.result(timeout=5)["memories"]

    assert [memory["body"] for memory in imported] == ["New snapshot."]


def test_loader_rejects_symlinked_document_outside_bundle(tmp_path):
    """An untrusted bundle must not import a local file through a .md symlink."""
    outside = tmp_path / "synthetic-private.txt"
    outside.write_text("SYNTHETIC_PRIVATE_VALUE", encoding="utf-8")
    memories = tmp_path / "attacker-bundle" / "memories"
    memories.mkdir(parents=True)
    link = memories / "innocent-memory.md"
    try:
        link.symlink_to(outside)
    except (NotImplementedError, OSError):
        pytest.skip("symbolic links are unavailable on this platform")

    with pytest.raises(ValueError, match="symbolic-link document"):
        load_okf_bundle(memories.parent)


def test_loader_rejects_symlinked_bundle_root(tmp_path):
    """Selecting a symlink as the bundle root must fail before traversal."""
    real_bundle = tmp_path / "real-bundle"
    real_bundle.mkdir()
    (real_bundle / "memory.md").write_text("Synthetic memory", encoding="utf-8")
    bundle_link = tmp_path / "selected-bundle"
    try:
        bundle_link.symlink_to(real_bundle, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("symbolic links are unavailable on this platform")

    with pytest.raises(ValueError, match="bundle path must not be a symbolic link"):
        load_okf_bundle(bundle_link)


def test_loader_rejects_symlinked_single_document(tmp_path):
    """The single-file import form must not follow a selected symlink."""
    outside = tmp_path / "synthetic-private.md"
    outside.write_text("Synthetic private value", encoding="utf-8")
    link = tmp_path / "selected-memory.md"
    try:
        link.symlink_to(outside)
    except (NotImplementedError, OSError):
        pytest.skip("symbolic links are unavailable on this platform")

    with pytest.raises(ValueError, match="bundle path must not be a symbolic link"):
        load_okf_bundle(link)


def test_loader_rejects_symlinked_memories_directory(tmp_path):
    """A Memanto bundle must not redirect its import subtree elsewhere."""
    outside = tmp_path / "outside-memories"
    outside.mkdir()
    (outside / "synthetic-private.md").write_text(
        "Synthetic private value", encoding="utf-8"
    )
    bundle = tmp_path / "attacker-bundle"
    bundle.mkdir()
    try:
        (bundle / "memories").symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("symbolic links are unavailable on this platform")

    with pytest.raises(
        ValueError, match="bundle directory must not be a symbolic link"
    ):
        load_okf_bundle(bundle)


def test_loader_rejects_document_swapped_to_symlink_before_open(tmp_path, monkeypatch):
    """A pathname swap after listing must not redirect the opened document."""
    if not okf_loader._SECURE_DIR_FD:
        pytest.skip("descriptor-relative no-follow opens are unavailable")

    outside = tmp_path / "outside.txt"
    outside.write_text("SYNTHETIC_RACE_VALUE", encoding="utf-8")
    memories = tmp_path / "bundle" / "memories"
    memories.mkdir(parents=True)
    victim = memories / "memory.md"
    victim.write_text("Ordinary content", encoding="utf-8")

    real_open = os.open
    swapped = False

    def swap_then_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if path == "memory.md" and kwargs.get("dir_fd") is not None and not swapped:
            victim.unlink()
            victim.symlink_to(outside)
            swapped = True
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", swap_then_open)

    with pytest.raises(ValueError, match="symbolic-link path"):
        load_okf_bundle(memories.parent)
    assert swapped


def test_loader_reads_pinned_root_when_selected_path_is_replaced(tmp_path, monkeypatch):
    """Replacing the selected pathname must not redirect an opened root."""
    if not okf_loader._SECURE_DIR_FD:
        pytest.skip("descriptor-relative no-follow opens are unavailable")

    bundle = tmp_path / "bundle"
    memories = bundle / "memories"
    memories.mkdir(parents=True)
    (memories / "memory.md").write_text("Ordinary content", encoding="utf-8")

    outside = tmp_path / "outside"
    outside_memories = outside / "memories"
    outside_memories.mkdir(parents=True)
    (outside_memories / "memory.md").write_text(
        "SYNTHETIC_OUTSIDE_VALUE", encoding="utf-8"
    )
    moved_bundle = tmp_path / "opened-bundle"

    real_fstat = os.fstat
    swapped = False

    def replace_path_after_root_open(fd):
        nonlocal swapped
        result = real_fstat(fd)
        if not swapped:
            bundle.rename(moved_bundle)
            bundle.symlink_to(outside, target_is_directory=True)
            swapped = True
        return result

    monkeypatch.setattr(os, "fstat", replace_path_after_root_open)

    export = load_okf_bundle(bundle)

    assert swapped
    assert export["memories"][0]["body"] == "Ordinary content"


def test_loader_reports_unsupported_without_secure_directory_descriptors(
    tmp_path, monkeypatch
):
    """Unsupported platforms fail explicitly instead of using path checks."""
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "memory.md").write_text("Ordinary content", encoding="utf-8")
    monkeypatch.setattr(
        "memanto.cli.migrate.okf_loader._SECURE_DIR_FD",
        False,
    )

    with pytest.raises(RuntimeError, match="OKF import is unsupported"):
        load_okf_bundle(bundle)


def test_loader_preserves_nested_document_read_errors(tmp_path, monkeypatch):
    """A nested file error must not be mislabeled as an unsafe parent directory."""
    if not okf_loader._SECURE_DIR_FD:
        pytest.skip("descriptor-relative no-follow opens are unavailable")

    nested = tmp_path / "bundle" / "memories" / "nested"
    nested.mkdir(parents=True)
    (nested / "memory.md").write_text("Ordinary content", encoding="utf-8")

    def fail_document_read(directory_fd, name, display_path):
        raise PermissionError("synthetic nested read failure")

    monkeypatch.setattr(okf_loader, "_read_document_at", fail_document_read)

    with pytest.raises(PermissionError, match="synthetic nested read failure"):
        load_okf_bundle(tmp_path / "bundle")


def test_loader_extracts_multiple_links_around_malformed_markup(tmp_path):
    """Malformed candidates do not hide valid links that follow them."""
    okf_file = tmp_path / "links.md"
    okf_file.write_text(
        "---\ntype: fact\ntitle: Links\n---\n"
        "Broken [label] text, then [first](/one) and [](ignored), "
        "then [second](https://example.com/two).\n",
        encoding="utf-8",
    )

    memory = load_okf_bundle(okf_file)["memories"][0]

    assert memory["links"] == [
        "first -> /one",
        "second -> https://example.com/two",
    ]


def test_loader_handles_many_unclosed_link_markers_quickly(tmp_path):
    """A malformed large note must not make link extraction scale quadratically."""
    okf_file = tmp_path / "malformed-links.md"
    okf_file.write_text(
        "---\ntype: fact\ntitle: Malformed links\n---\n" + "[" * 25_000,
        encoding="utf-8",
    )

    started = perf_counter()
    memory = load_okf_bundle(okf_file)["memories"][0]
    elapsed = perf_counter() - started

    assert memory["links"] == []
    assert elapsed < 1.0


def test_okf_export_splits_comma_separated_tags(tmp_path):
    """Tags serialized by Moorcheh arrive as a comma-separated string. The
    export must emit one frontmatter list entry per tag, not split the string
    character-by-character.

    Regression for BountyHub #770: with tags='project,db' the old
    ``list(tags)`` wrote ["p", "r", "o", "j", "e", "c", "t", ",", "d", "b"].
    """
    svc = OkfExportService(exports_dir=tmp_path / "exports")
    # Moorcheh wire format: flat ``tags`` field is a comma-joined string.
    memories_by_type = {
        "fact": [
            _mem("f1", "Postgres", "Use PG 16.", tags="project, db, prod"),
        ],
    }
    svc.write_okf_bundle("agent1", memories_by_type, split="file")
    fact_md = svc.exports_dir / "agent1_okf" / "memories" / "fact" / "postgres.md"
    front = fact_md.read_text(encoding="utf-8").split("---", 2)[1]
    fm = yaml.safe_load(front)
    assert set(fm["tags"]) == {"project", "db", "prod"}


def test_okf_export_preserves_list_tags(tmp_path):
    """Tags from the in-memory recall path arrive as a list; the export must
    still emit a proper frontmatter list of those tags (unchanged behaviour)."""
    svc = OkfExportService(exports_dir=tmp_path / "exports")
    memories_by_type = {
        "fact": [
            _mem("f1", "A fact", "Body.", tags=["infra", "db"]),
        ],
    }
    svc.write_okf_bundle("agent1", memories_by_type, split="file")
    fact_md = svc.exports_dir / "agent1_okf" / "memories" / "fact" / "a-fact.md"
    fm = yaml.safe_load(fact_md.read_text(encoding="utf-8").split("---", 2)[1])
    assert set(fm["tags"]) == {"infra", "db"}
