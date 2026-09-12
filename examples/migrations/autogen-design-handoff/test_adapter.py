"""Boundary and integrity tests: no network, credentials, or LLM required."""

import asyncio
from collections import Counter

import pytest
from migrate_demo import canonical, recover_records, seed_source, to_okf, validate_checks

from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle


def component(records):
    return {
        "provider": "autogen_core.memory.ListMemory",
        "config": {"memory_contents": records},
    }


def test_actual_source_and_shipped_mapper_roundtrip(tmp_path):
    source = asyncio.run(seed_source(tmp_path))
    report = to_okf(source, tmp_path / "okf")
    mapped = map_okf(load_okf_bundle(tmp_path / "okf"))
    restored = [r for item in mapped for r in recover_records(item["content"])]
    assert Counter(map(canonical, restored)) == Counter(
        map(canonical, source["config"]["memory_contents"])
    )
    assert report["type_counts"] == {"decision": 5, "fact": 2, "instruction": 1}
    assert all(item["provenance"] == "imported" for item in mapped)
    assert all(item["source"] == "autogen-listmemory" for item in mapped)


def test_duplicate_records_do_not_collapse(tmp_path):
    row = {"content": "Same event", "mime_type": "text/plain", "metadata": None}
    to_okf(component([row, row]), tmp_path / "okf")
    assert len(list((tmp_path / "okf").glob("*.md"))) == 2


@pytest.mark.parametrize(
    "record",
    [
        {"content": "data", "mime_type": "image/png", "metadata": {}},
        {"content": "x" * 6100, "mime_type": "text/plain", "metadata": {}},
        {"content": "data", "mime_type": "text/plain", "metadata": "wrong"},
    ],
)
def test_rejected_batch_leaves_no_partial_bundle(tmp_path, record):
    valid = {"content": "first", "mime_type": "text/plain", "metadata": {}}
    with pytest.raises(ValueError):
        to_okf(component([valid, record]), tmp_path / "okf")
    assert not (tmp_path / "okf").exists()


def test_no_overwrite_and_deterministic_output(tmp_path):
    source = component(
        [
            {
                "content": "---\nUnicode ✓",
                "mime_type": "text/plain",
                "metadata": {"odd": {"nested": [1, True, None]}},
            }
        ]
    )
    to_okf(source, tmp_path / "a")
    to_okf(source, tmp_path / "b")
    a = next((tmp_path / "a").glob("*.md"))
    b = next((tmp_path / "b").glob("*.md"))
    assert a.name == b.name and a.read_bytes() == b.read_bytes()
    with pytest.raises(ValueError, match="existing bundle"):
        to_okf(source, tmp_path / "a")


def test_other_component_is_not_silently_interpreted(tmp_path):
    with pytest.raises(ValueError, match="Expected autogen"):
        to_okf({"provider": "other.Memory"}, tmp_path / "okf")


def test_real_snapshot_is_not_mislabelled_synthetic(tmp_path):
    row = {"content": "Actual app preference", "mime_type": "text/plain", "metadata": {"kind": "decision"}}
    to_okf(component([row]), tmp_path / "okf")
    node = next((tmp_path / "okf").glob("*.md")).read_text()
    assert "synthetic" not in node
    assert recover_records(node) == [row]


@pytest.mark.parametrize("failure", ["source", "target", "integrity"])
def test_failure_gate_rejects_failed_proofs(failure):
    report = {"mode": "live-cloud", "recall_passed": 6, "recall_total": 6, "lossless_payload_roundtrip": True}
    checks = [{"passed": True}]
    if failure == "source":
        checks[0]["passed"] = False
    elif failure == "target":
        report["recall_passed"] = 5
    else:
        report["lossless_payload_roundtrip"] = False
    with pytest.raises(SystemExit, match="Validation failed"):
        validate_checks(report, checks)


def test_failure_gate_accepts_complete_proofs():
    validate_checks({"mode": "live-cloud", "recall_passed": 6, "recall_total": 6, "lossless_payload_roundtrip": True}, [{"passed": True}])


def test_ranked_top3_is_informational_not_equal_scope_parity():
    validate_checks(
        {
            "mode": "live-cloud",
            "recall_passed": 6,
            "recall_total": 6,
            "lossless_payload_roundtrip": True,
            "ranked_top3_passed": 5,
            "ranked_top3_total": 6,
        },
        [{"passed": True}],
    )
