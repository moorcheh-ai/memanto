from pathlib import Path

from normalize_export import normalize_export


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_normalize_export_repairs_links_and_duplicate_opening(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    source = bundle / "memories" / "context" / "source.md"
    target = bundle / "memories" / "fact" / "target.md"
    write(
        source,
        "---\nresource: obsidian://open?path=Notes/Source.md\n---\n\n"
        "Opening prose.\n\nOpening prose.\n\n"
        "See [Target](../People/Target.md) and [Folder](../People/).\n",
    )
    write(
        target,
        "---\nresource: obsidian://open?path=People/Target.md\n---\n\nTarget.\n",
    )

    assert normalize_export(bundle) == 1

    rendered = source.read_text(encoding="utf-8")
    assert rendered.count("Opening prose.") == 1
    assert "[Target](../fact/target.md)" in rendered
    assert "[Folder](obsidian://open?path=People)" in rendered
    assert normalize_export(bundle) == 0
