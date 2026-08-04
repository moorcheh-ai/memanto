"""Tests for the OKF portability audit example."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

EXAMPLE_DIR = Path(__file__).parents[1]


def _load_module(name: str, filename: str):
    """Load a script from the hyphenated example directory for unit tests."""
    spec = importlib.util.spec_from_file_location(name, EXAMPLE_DIR / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


okf_audit = _load_module("okf_audit", "okf_audit.py")
github_issue_to_okf = _load_module("github_issue_to_okf", "github_issue_to_okf.py")
roundtrip_demo = _load_module("roundtrip_demo", "roundtrip_demo.py")
run_demo = _load_module("run_demo", "run_demo.py")


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
    """Write a minimal loader-compatible OKF memory fixture."""
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
    """File moves and destination runtime IDs do not imply memory loss."""
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
    """Changed content and missing source records fail the audit."""
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
    """Provenance gaps remain visible in the report."""
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
    """Colliding semantic identities fail closed instead of hiding a record."""
    before = tmp_path / "before"
    after = tmp_path / "after"
    _write_entry(before, "a.md", mem_id="m1", title="Choice", body="Redis")
    _write_entry(before, "b.md", mem_id="m2", title="Choice", body="Valkey")
    _write_entry(after, "a.md", mem_id="m3", title="Choice", body="Redis")

    report = okf_audit.compare_bundles(before, after)

    assert len(report.source_duplicates) == 1
    assert not report.is_lossless


def test_provenance_gap_on_later_duplicate_is_not_discarded(tmp_path):
    """A duplicate without provenance is reported even when the first has it."""
    before = tmp_path / "before"
    after = tmp_path / "after"
    _write_entry(before, "a.md", mem_id="m1", title="Choice", body="Redis")
    _write_entry(
        before,
        "b.md",
        mem_id="m2",
        title="Choice",
        body="Valkey",
        source="",
        provenance="",
    )
    _write_entry(after, "a.md", mem_id="m3", title="Choice", body="Redis")

    report = okf_audit.compare_bundles(before, after)

    assert len(report.source_duplicates) == 1
    assert len(report.source_provenance_gaps) == 1


def test_reversible_memanto_wrapper_is_not_a_content_change(tmp_path):
    """The complete mapper-owned wrapper is normalized as reversible metadata."""
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


def test_native_description_prefix_is_preserved(tmp_path):
    """A native body beginning with its description is never discarded."""
    before = tmp_path / "before"
    after = tmp_path / "after"
    _write_entry(
        before,
        "a.md",
        mem_id="m1",
        title="Choice",
        body="A cache decision\n\nUse Redis",
    )
    _write_entry(after, "a.md", mem_id="m2", title="Choice", body="Use Redis")
    for root in (before, after):
        path = root / "memories" / "fact" / "a.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "tags: [portable]\n", "description: A cache decision\n"
            ),
            encoding="utf-8",
        )

    report = okf_audit.compare_bundles(before, after)

    assert not report.is_lossless
    assert report.changed[0].fields == ("body",)


def test_native_description_prefix_survives_mapper_footer(tmp_path):
    """A source-native description prefix is not mistaken for mapper content."""
    before = tmp_path / "before"
    after = tmp_path / "after"
    body = "A cache decision\n\nUse Redis"
    _write_entry(before, "a.md", mem_id="m1", title="Choice", body=body)
    _write_entry(
        after,
        "a.md",
        mem_id="m2",
        title="Choice",
        body=(
            body + "\n\n---\n[Supporting data]\n" + "- OKF source: memories/fact/a.md"
        ),
    )
    for root in (before, after):
        path = root / "memories" / "fact" / "a.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "tags: [portable]\n", "description: A cache decision\n"
            ),
            encoding="utf-8",
        )

    report = okf_audit.compare_bundles(before, after)

    assert report.is_lossless
    assert report.unchanged == 1


def test_cli_writes_json_and_fails_on_change(tmp_path):
    """JSON output and the CI failure exit code work together."""
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


def test_report_output_cannot_modify_an_input(tmp_path):
    """Report output is rejected inside a bundle or over a single-file input."""
    source = tmp_path / "source"
    target = tmp_path / "target"
    _write_entry(source, "a.md", mem_id="m1", title="Choice", body="Redis")
    _write_entry(target, "a.md", mem_id="m2", title="Choice", body="Redis")
    source_file = source / "memories" / "fact" / "a.md"

    cases = ((source, source / "audit.json"), (source_file, source_file))
    for source_input, unsafe in cases:
        try:
            okf_audit.validate_report_output(source_input, target, unsafe)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Unsafe output was accepted: {unsafe}")


def test_report_output_resolves_symlinked_bundle_paths(tmp_path):
    """Symlink aliases cannot bypass the report-output overlap check."""
    source = tmp_path / "source"
    target = tmp_path / "target"
    alias = tmp_path / "source-alias"
    _write_entry(source, "a.md", mem_id="m1", title="Choice", body="Redis")
    _write_entry(target, "a.md", mem_id="m2", title="Choice", body="Redis")
    try:
        alias.symlink_to(source, target_is_directory=True)
    except OSError:
        return

    try:
        okf_audit.validate_report_output(alias, target, source / "audit.json")
    except ValueError:
        pass
    else:
        raise AssertionError("Symlinked input accepted an overlapping output")


def test_roundtrip_rejects_overlapping_or_existing_targets(tmp_path):
    """The demo cannot overwrite, nest within, or contain its source bundle."""
    source = tmp_path / "source"
    _write_entry(source, "a.md", mem_id="m1", title="Choice", body="Redis")
    existing = tmp_path / "existing"
    existing.mkdir()

    for unsafe in (source, source / "target", tmp_path, existing):
        try:
            roundtrip_demo.round_trip(source, unsafe)
        except (ValueError, FileExistsError):
            pass
        else:
            raise AssertionError(f"Unsafe target was accepted: {unsafe}")


def test_real_archive_records_split_long_issue_without_losing_text():
    """Long real issue bodies split into bounded chunks without truncation."""
    issue_body = "First paragraph.\n\n" + ("memory " * 1200)
    issue = {
        "id": 99,
        "number": 7,
        "title": "Lived-in memory archive",
        "repository_url": "https://api.github.com/repos/example/project",
        "html_url": "https://github.com/example/project/issues/7",
        "labels": [{"name": "memory"}],
        "state": "open",
        "created_at": "2026-08-04T00:00:00Z",
        "body": issue_body,
    }
    comments = [
        {
            "id": 101,
            "user": {"login": "reviewer"},
            "html_url": "https://github.com/example/project/issues/7#comment-101",
            "created_at": "2026-08-04T01:00:00Z",
            "body": "A real correction.",
        }
    ]

    records = github_issue_to_okf.records_from_archive(issue, comments)

    issue_records = [record for record in records if record["type"] == "artifact"]
    assert len(issue_records) >= 2
    assert all(len(record["body"]) <= 7000 for record in issue_records)
    assert "".join(record["body"] for record in issue_records) == issue_body
    assert records[-1]["resource"].endswith("#comment-101")


def test_long_comments_are_split_losslessly_with_unique_ids():
    """Long comments retain every character, URL, and unique chunk identity."""
    comment_body = "Opening.\n\n" + ("comment payload " * 700)
    issue = {
        "id": 99,
        "number": 7,
        "title": "Migration",
        "body": "Short issue",
        "html_url": "https://github.com/acme/repo/issues/7",
        "repository_url": "https://api.github.com/repos/acme/repo",
        "labels": [],
        "state": "open",
        "created_at": "2025-01-01T00:00:00Z",
    }
    comment = {
        "id": 101,
        "body": comment_body,
        "html_url": "https://github.com/acme/repo/issues/7#issuecomment-101",
        "created_at": "2025-01-02T00:00:00Z",
        "user": {"login": "reviewer"},
    }

    records = github_issue_to_okf.records_from_archive(issue, [comment])
    comment_records = [r for r in records if r["type"] == "observation"]

    assert len(comment_records) >= 2
    assert "".join(r["body"] for r in comment_records) == comment_body
    assert len({r["id"] for r in comment_records}) == len(comment_records)
    assert {r["resource"] for r in comment_records} == {comment["html_url"]}


def test_bundle_indexes_escape_labels_and_keep_repeated_authors(tmp_path):
    """Index links stay valid and same-author comments cannot overwrite files."""
    records = [
        {
            "id": f"github-comment-{record_id}-part-1",
            "type": "observation",
            "title": "Comment by user [ops] on issue #7",
            "description": "Public comment.",
            "resource": f"https://example.test/comments/{record_id}",
            "tags": ["github"],
            "timestamp": "2025-01-01T00:00:00Z",
            "body": "Body",
        }
        for record_id in (101, 102)
    ]

    github_issue_to_okf.write_bundle(records, tmp_path / "bundle")
    observation_dir = tmp_path / "bundle" / "memories" / "observation"
    documents = [p for p in observation_dir.glob("*.md") if p.name != "index.md"]
    index = (observation_dir / "index.md").read_text(encoding="utf-8")

    assert len(documents) == 2
    assert "Comment by user \\[ops\\] on issue #7" in index


def test_one_command_demo_rejects_existing_workdir(tmp_path):
    """The orchestrator cannot mix evidence with a stale prior run."""
    try:
        run_demo.run_showcase("acme/repo", 7, tmp_path)
    except FileExistsError:
        pass
    else:
        raise AssertionError("Existing showcase directory was accepted")


def test_one_command_demo_preserves_failed_audit_report(tmp_path, monkeypatch):
    """A fidelity failure leaves its JSON receipt before propagating the error."""
    workdir = tmp_path / "new-showcase"
    report = {
        "source_count": 1,
        "target_count": 0,
        "unchanged": 0,
        "removed": ["lost"],
        "changed": [],
        "is_lossless": False,
    }

    def fake_run(command, *, capture=False):
        assert workdir.is_dir()
        if capture:
            raise run_demo.subprocess.CalledProcessError(
                1,
                command,
                output=run_demo.json.dumps(report),
            )
        return run_demo.subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(run_demo, "_run", fake_run)

    try:
        run_demo.run_showcase("acme/repo", 7, workdir)
    except run_demo.subprocess.CalledProcessError as error:
        assert error.returncode == 1
    else:
        raise AssertionError("Failed audit did not propagate its exit status")

    saved = run_demo.json.loads((workdir / "audit.json").read_text(encoding="utf-8"))
    assert saved == report


def test_generated_archive_is_a_loader_compatible_bundle(tmp_path):
    """Generated archive records load through Memanto's production loader."""
    issue = {
        "id": 99,
        "number": 7,
        "title": "Memory archive",
        "repository_url": "https://api.github.com/repos/example/project",
        "html_url": "https://github.com/example/project/issues/7",
        "labels": [],
        "state": "open",
        "created_at": "2026-08-04T00:00:00Z",
        "body": "A genuine issue body.",
    }
    records = github_issue_to_okf.records_from_archive(issue, [])

    github_issue_to_okf.write_bundle(records, tmp_path)
    loaded = okf_audit.load_okf_bundle(tmp_path)["memories"]

    assert len(loaded) == 1
    assert loaded[0]["resource"] == issue["html_url"]
