from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "okf_diff.py"
SPEC = importlib.util.spec_from_file_location("okf_diff", MODULE_PATH)
assert SPEC and SPEC.loader
okf_diff = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = okf_diff
SPEC.loader.exec_module(okf_diff)


def _write_entry(
    root: Path,
    relative_path: str,
    *,
    mem_id: str | None,
    title: str,
    body: str,
    memory_type: str = "fact",
    tags: list[str] | None = None,
) -> None:
    path = root / "memories" / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    extension = f"x_memanto:\n  id: {mem_id}\n  type: {memory_type}\n" if mem_id else ""
    tag_text = json.dumps(tags or [])
    path.write_text(
        "---\n"
        f"type: {memory_type}\n"
        f"title: {title}\n"
        f"tags: {tag_text}\n"
        f"{extension}"
        "---\n\n"
        f"{body}\n",
        encoding="utf-8",
    )


def _status_map(diff):
    return {change.title: change.status for change in diff.changes}


def test_classifies_semantic_changes_and_ignores_layout_moves(tmp_path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    _write_entry(before, "fact/database.md", mem_id="db", title="Database", body="v15")
    _write_entry(before, "fact/same.md", mem_id="same", title="Same", body="Stable")
    _write_entry(before, "fact/gone.md", mem_id="gone", title="Gone", body="Remove me")

    _write_entry(
        after, "decision/database.md", mem_id="db", title="Database", body="v16"
    )
    _write_entry(after, "moved/same.md", mem_id="same", title="Same", body="Stable")
    _write_entry(after, "fact/new.md", mem_id="new", title="New", body="Add me")

    diff = okf_diff.compare_bundles(before, after)

    assert diff.counts == {
        "added": 1,
        "removed": 1,
        "changed": 1,
        "unchanged": 1,
    }
    assert _status_map(diff) == {
        "Gone": "removed",
        "Database": "changed",
        "New": "added",
        "Same": "unchanged",
    }
    database = next(change for change in diff.changes if change.title == "Database")
    assert database.changed_fields == ("body",)


def test_duplicate_identities_are_never_collapsed(tmp_path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    _write_entry(before, "fact/a.md", mem_id=None, title="Preference", body="A")
    _write_entry(before, "fact/b.md", mem_id=None, title="Preference", body="B")
    _write_entry(after, "fact/a.md", mem_id=None, title="Preference", body="A")
    _write_entry(after, "fact/b.md", mem_id=None, title="Preference", body="C")

    diff = okf_diff.compare_bundles(before, after)

    assert len(diff.changes) == 2
    assert diff.counts["unchanged"] == 1
    assert diff.counts["changed"] == 1
    assert {change.key.rsplit("#", 1)[-1] for change in diff.changes} == {"1", "2"}


def test_identical_duplicate_count_is_preserved(tmp_path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    _write_entry(before, "fact/a.md", mem_id=None, title="Preference", body="Same")
    _write_entry(before, "fact/b.md", mem_id=None, title="Preference", body="Same")
    _write_entry(after, "fact/a.md", mem_id=None, title="Preference", body="Same")

    diff = okf_diff.compare_bundles(before, after)

    assert len(diff.changes) == 2
    assert diff.counts["unchanged"] == 1
    assert diff.counts["removed"] == 1


def test_stacked_okf_entries_are_compared(tmp_path):
    before = tmp_path / "before.md"
    after = tmp_path / "after.md"
    delimiter = "\n<!-- okf-entry -->\n"
    before.write_text(
        "---\ntype: fact\ntitle: One\n---\n\nFirst"
        + delimiter
        + "---\ntype: fact\ntitle: Two\n---\n\nSecond\n",
        encoding="utf-8",
    )
    after.write_text(
        "---\ntype: fact\ntitle: One\n---\n\nFirst"
        + delimiter
        + "---\ntype: fact\ntitle: Two\n---\n\nUpdated\n",
        encoding="utf-8",
    )

    diff = okf_diff.compare_bundles(before, after)

    assert diff.before_count == 2
    assert diff.after_count == 2
    assert diff.counts["changed"] == 1
    assert diff.counts["unchanged"] == 1


def test_reports_are_self_contained_and_machine_readable(tmp_path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    _write_entry(before, "fact/a.md", mem_id="a", title="A", body="Old")
    _write_entry(after, "fact/a.md", mem_id="a", title="A", body="New")
    diff = okf_diff.compare_bundles(before, after)

    payload = json.loads(okf_diff.render_json(diff))
    markdown = okf_diff.render_markdown(diff)
    report = okf_diff.render_html(diff)

    assert payload["counts"]["changed"] == 1
    assert payload["changes"][0]["changed_fields"] == ["body"]
    assert "```diff" in markdown
    assert "-Old" in markdown
    assert "+New" in markdown
    assert "<!doctype html>" in report
    assert "<script src=" not in report
    assert '<link rel="stylesheet"' not in report
    assert "data-status='changed'" in report
    assert "Generated locally" in report


@pytest.mark.parametrize(
    ("flag", "expected"),
    [
        (None, 0),
        ("--fail-on-change", 1),
        ("--fail-on-removal", 0),
    ],
)
def test_cli_change_gates(tmp_path, flag, expected):
    before = tmp_path / "before"
    after = tmp_path / "after"
    _write_entry(before, "fact/a.md", mem_id="a", title="A", body="Old")
    _write_entry(after, "fact/a.md", mem_id="a", title="A", body="New")
    argv = [str(before), str(after)]
    if flag:
        argv.append(flag)

    assert okf_diff.main(argv) == expected


def test_cli_writes_reports_and_removal_gate_fails(tmp_path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    _write_entry(before, "fact/a.md", mem_id="a", title="A", body="Old")
    after.mkdir()
    reports = tmp_path / "reports"

    result = okf_diff.main(
        [
            str(before),
            str(after),
            "--json",
            str(reports / "diff.json"),
            "--markdown",
            str(reports / "diff.md"),
            "--html",
            str(reports / "diff.html"),
            "--fail-on-removal",
        ]
    )

    assert result == 1
    assert json.loads((reports / "diff.json").read_text())["counts"]["removed"] == 1
    assert (reports / "diff.md").read_text().startswith("# OKF bundle diff")
    assert (reports / "diff.html").read_text().startswith("<!doctype html>")
