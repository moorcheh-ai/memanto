from pathlib import Path

import yaml
from obsidian_to_okf import convert_vault

from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_conversion_is_importable_and_preserves_links(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    output = tmp_path / "okf"
    write(
        vault / "Projects" / "Launch.md",
        "---\ntags: [projects, decision]\nstatus: active\n---\n"
        "# Launch plan\n\nWe chose Friday. See [[People/Ada|Ada]] and [[Missing]].\n",
    )
    write(vault / "People" / "Ada.md", "# Ada\n\nAda owns the release.\n")
    write(vault / ".obsidian" / "ignored.md", "internal")

    report = convert_vault(vault, output)

    assert report.source_files == 2
    assert report.converted_files == 2
    assert report.wikilinks_converted == 1
    assert report.unresolved_links == [
        {"source": "Projects/Launch.md", "target": "Missing"}
    ]
    rendered = (output / "memories" / "Projects" / "Launch.md").read_text()
    assert "[Ada](../People/Ada.md)" in rendered
    assert "[[Missing]]" in rendered
    frontmatter = yaml.safe_load(rendered.split("---", 2)[1])
    assert frontmatter["type"] == "decision"
    assert frontmatter["x_obsidian"]["frontmatter"] == {
        "tags": ["projects", "decision"],
        "status": "active",
    }

    loaded = load_okf_bundle(output)
    mapped = map_okf(loaded)
    assert len(mapped) == 2
    assert {row["type"] for row in mapped} == {"decision", "context"}
    assert all(row["source"] == "obsidian" for row in mapped)


def test_dry_run_does_not_write_output(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    output = tmp_path / "okf"
    write(vault / "Note.md", "A real note body.")

    report = convert_vault(vault, output, dry_run=True)

    assert report.converted_files == 1
    assert not output.exists()


def test_refuses_output_inside_vault(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    write(vault / "Note.md", "body")

    try:
        convert_vault(vault, vault / "okf")
    except ValueError as exc:
        assert "outside" in str(exc)
    else:
        raise AssertionError("expected unsafe output path to be rejected")
