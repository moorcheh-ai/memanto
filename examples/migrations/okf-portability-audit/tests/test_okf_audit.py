"""Tests for the OKF portability audit example."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

EXAMPLE_DIR = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("okf_audit", EXAMPLE_DIR / "okf_audit.py")
assert SPEC and SPEC.loader
okf_audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = okf_audit
SPEC.loader.exec_module(okf_audit)


def _write_entry(
    root: Path,
    filename: str,
    *,
    mem_id: str,
    title: str,
    body: str,
    source: str = "chatgpt",
    provenance: str = "imported",
) -> None:
    memories = root / "memories" / "fact"
    memories.mkdir(parents=True, exist_ok=True)
    (memories / filename).write_text(
        "---\n"
        "type: fact\n"
        f"title: {title}\n"
        "tags: [portable]\n"
        "x_memanto:\n"
        f"  id: {mem_id}\n"
        f"  source: {source}\n"
        f"  provenance: {provenance}\n"
        "---\n\n"
        f"{body}\n",
        encoding="utf-8",
    )


def test_lossless_bundle_can_move_files(tmp_path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    _write_entry(before, "old-name.md", mem_id="m1", title="Choice", body="Redis")
    _write_entry(after, "new-name.md", mem_id="m1", title="Choice", body="Redis")

    report = okf_audit.compare_bundles(before, after)

    assert report.is_lossless
    assert report.unchanged == 1
    assert len(report.moved) == 1
    assert report.removed == []


def test_changed_and_removed_nodes_fail_fidelity(tmp_path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    _write_entry(before, "a.md", mem_id="m1", title="Choice", body="Redis")
    _write_entry(before, "b.md", mem_id="m2", title="Region", body="Madrid")
    _write_entry(after, "a.md", mem_id="m1", title="Choice", body="Valkey")

    report = okf_audit.compare_bundles(before, after)

    assert not report.is_lossless
    assert report.changed[0].fields == ("body",)
    assert any(item.startswith("Region (semantic:") for item in report.removed)


def test_duplicates_and_provenance_gaps_are_visible(tmp_path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    _write_entry(before, "a.md", mem_id="m1", title="Choice", body="Redis")
    _write_entry(before, "b.md", mem_id="m1", title="Choice copy", body="Redis")
    _write_entry(
        after,
        "a.md",
        mem_id="m1",
        title="Choice",
        body="Redis",
        source="",
        provenance="",
    )

    report = okf_audit.compare_bundles(before, after)

    assert report.source_duplicates == []
    assert len(report.target_provenance_gaps) == 1
    assert report.target_provenance_gaps[0].startswith("Choice (semantic:")
    assert not report.is_lossless


def test_duplicate_semantic_identity_is_ambiguous(tmp_path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    _write_entry(before, "a.md", mem_id="m1", title="Choice", body="Redis")
    _write_entry(before, "b.md", mem_id="m2", title="Choice", body="Valkey")
    _write_entry(after, "a.md", mem_id="m3", title="Choice", body="Redis")

    report = okf_audit.compare_bundles(before, after)

    assert len(report.source_duplicates) == 1
    assert not report.is_lossless


def test_reversible_memanto_wrapper_is_not_a_content_change(tmp_path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    _write_entry(before, "a.md", mem_id="m1", title="Choice", body="Use Redis")
    _write_entry(
        after,
        "a.md",
        mem_id="m2",
        title="Choice",
        body=(
            "A cache decision\n\nUse Redis\n\n---\n[Supporting data]\n"
            "- OKF source: memories/fact/a.md\n- OKF resource: urn:choice"
        ),
    )
    for root in (before, after):
        path = root / "memories" / "fact" / "a.md"
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace(
                "tags: [portable]\n", "description: A cache decision\n"
            ).replace("x_memanto:\n", "resource: urn:choice\nx_memanto:\n"),
            encoding="utf-8",
        )

    report = okf_audit.compare_bundles(before, after)

    assert report.is_lossless
    assert report.unchanged == 1


def test_cli_writes_json_and_fails_on_change(tmp_path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    output = tmp_path / "audit.json"
    _write_entry(before, "a.md", mem_id="m1", title="Choice", body="Redis")
    _write_entry(after, "a.md", mem_id="m1", title="Choice", body="Valkey")

    exit_code = okf_audit.main(
        [
            str(before),
            str(after),
            "--format",
            "json",
            "--output",
            str(output),
            "--fail-on-change",
        ]
    )

    assert exit_code == 1
    assert '"is_lossless": false' in output.read_text(encoding="utf-8")
