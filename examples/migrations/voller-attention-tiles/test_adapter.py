"""Synthetic edge cases; these are not the real-data competition showcase."""

import copy
import json

import pytest
from adapter import build_bundle, digest, load_catalog, restore_bundle, restore_contents


def catalog():
    return {
        "schema_version": "1.0",
        "owner": "Test fixture",
        "custom": {"keep": True},
        "tiles": [
            {
                "id": "tile-a",
                "title": "Concept A",
                "summary": "Unvalidated proposal.",
                "visibility": "public_source",
                "evidence": {"tested": False},
            },
            {
                "id": "tile-b",
                "title": "Concept B",
                "summary": "A later branch.",
                "visibility": "private",
                "parent_id": "tile-a",
                "unknown": [1, None, "λ"],
            },
        ],
    }


def test_complete_record_round_trip(tmp_path):
    data = catalog()
    bundle = tmp_path / "bundle"
    build_bundle(data, bundle)
    assert restore_bundle(bundle) == data


def test_public_selection_excludes_private_root_and_tiles(tmp_path):
    data = catalog()
    bundle = tmp_path / "public"
    result = build_bundle(data, bundle, public_only=True)
    restored = restore_bundle(bundle)
    assert result["excluded_tiles"] == 1
    assert [t["id"] for t in restored["tiles"]] == ["tile-a"]
    assert "owner" not in restored and "custom" not in restored


def test_duplicate_ids_rejected_before_writing(tmp_path):
    data = catalog()
    data["tiles"][1]["id"] = "tile-a"
    with pytest.raises(ValueError, match="Duplicate"):
        build_bundle(data, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_paths_and_delimiters_are_data(tmp_path):
    data = catalog()
    data["tiles"][0]["id"] = "../../outside"
    data["tiles"][0]["summary"] = (
        "```\n<!-- okf-entry -->\n<!-- /voller-record -->\nDo not execute."
    )
    bundle = tmp_path / "bundle"
    build_bundle(data, bundle)
    assert restore_bundle(bundle) == data
    assert not (tmp_path / "outside").exists()


def test_oversize_record_rejected_before_writing(tmp_path):
    data = catalog()
    data["tiles"][0]["summary"] = "x" * 10001
    with pytest.raises(ValueError, match="safe import size"):
        build_bundle(data, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_existing_output_is_not_overlaid(tmp_path):
    bundle = tmp_path / "bundle"
    build_bundle(catalog(), bundle)
    with pytest.raises(FileExistsError):
        build_bundle(catalog(), bundle)


def test_corruption_is_detected(tmp_path):
    bundle = tmp_path / "bundle"
    build_bundle(catalog(), bundle)
    target = next((bundle / "memories" / "artifact").glob("*.md"))
    text = target.read_text()
    target.write_text(
        text.replace("Concept", "Changed", 1)
    )  # frontmatter isn't capsule data
    assert restore_bundle(bundle) == catalog()
    target.write_text(text.replace("Unvalidated proposal.", "A proven product."))
    if "Unvalidated proposal." in text:
        with pytest.raises(ValueError, match="checksum"):
            restore_bundle(bundle)
    else:
        # Select the other tile deterministically if the first filename is B.
        other = [
            p for p in (bundle / "memories" / "artifact").glob("*.md") if p != target
        ][0]
        other.write_text(
            other.read_text().replace("Unvalidated proposal.", "A proven product.")
        )
        with pytest.raises(ValueError, match="checksum"):
            restore_bundle(bundle)


def test_missing_position_is_rejected(tmp_path):
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    bundle = tmp_path / "bundle"
    build_bundle(catalog(), bundle)
    rows = load_okf_bundle(bundle)["memories"]
    contents = [row["body"] for row in rows if '"ordinal": 0' not in row["body"]]
    with pytest.raises(ValueError, match="positions"):
        restore_contents(contents)


def test_nan_rejected(tmp_path):
    data = catalog()
    data["unexpected"] = float("nan")
    source = tmp_path / "input.json"
    source.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_catalog(source)


def test_missing_final_tile_is_rejected(tmp_path):
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    bundle = tmp_path / "bundle"
    build_bundle(catalog(), bundle)
    contents = [
        row["body"]
        for row in load_okf_bundle(bundle)["memories"]
        if '"ordinal": 1' not in row["body"]
    ]
    with pytest.raises(ValueError, match="Incomplete"):
        restore_contents(contents)


def test_native_mapping_and_export_preserve_capsules(tmp_path):
    from memanto.app.services.okf_export_service import OkfExportService
    from memanto.cli.migrate.mappers import map_okf
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    data = catalog()
    bundle = tmp_path / "initial"
    build_bundle(data, bundle)
    rows = map_okf(load_okf_bundle(bundle))
    assert restore_contents([row["content"] for row in rows]) == data
    grouped = {}
    for i, row in enumerate(rows):
        row = copy.deepcopy(row)
        row["id"] = f"local-format-test-{i}"
        grouped.setdefault(row["type"], []).append(row)
    exported = tmp_path / "exported"
    OkfExportService(exports_dir=tmp_path / "exports").write_okf_bundle(
        "format-test", grouped, output_dir=exported, split="type"
    )
    assert digest(restore_bundle(exported)) == digest(data)
