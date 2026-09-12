"""Boundary and integrity tests: no network, credentials, or LLM required."""

import asyncio
import hashlib
import json
import threading
from collections import Counter
from contextlib import closing
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
import showcase_server
from migrate_demo import (
    canonical,
    recover_records,
    seed_source,
    to_okf,
    validate_checks,
)

from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle


def component(records):
    """Build the documented source envelope without normalizing its records."""
    return {
        "provider": "autogen_core.memory.ListMemory",
        "config": {"memory_contents": records},
    }


def test_actual_source_and_shipped_mapper_roundtrip(tmp_path):
    """Actual AutoGen calls retain every original record through the shipped mapper."""
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
    """Two equal source events must remain two independently importable records."""
    row = {"content": "Same event", "mime_type": "text/plain", "metadata": None}
    to_okf(component([row, row]), tmp_path / "okf")
    assert len(list((tmp_path / "okf").glob("*.md"))) == 2


@pytest.mark.parametrize(
    "record",
    [
        {"content": "data", "mime_type": "image/png", "metadata": {}},
        {"content": "x" * 6100, "mime_type": "text/plain", "metadata": {}},
        {"content": "data", "mime_type": "text/plain", "metadata": "wrong"},
        {"content": "data", "mime_type": "text/plain", "metadata": []},
        {"content": "data", "mime_type": "text/plain", "metadata": ""},
        {"content": "data", "mime_type": "text/plain", "metadata": 0},
        {"content": "data", "mime_type": "text/plain", "metadata": False},
    ],
)
def test_rejected_batch_leaves_no_partial_bundle(tmp_path, record):
    """A bad later record rejects the whole batch, including falsy metadata."""
    valid = {"content": "first", "mime_type": "text/plain", "metadata": {}}
    with pytest.raises(ValueError):
        to_okf(component([valid, record]), tmp_path / "okf")
    assert not (tmp_path / "okf").exists()


def test_no_overwrite_and_deterministic_output(tmp_path):
    """Rebuilds are byte-identical and never mix with an existing bundle."""
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
    """An unrelated provider cannot be mistaken for a ListMemory component."""
    with pytest.raises(ValueError, match="Expected autogen"):
        to_okf({"provider": "other.Memory"}, tmp_path / "okf")


def test_real_snapshot_is_not_mislabelled_synthetic(tmp_path):
    """The universal converter preserves real records without adding demo labels."""
    row = {
        "content": "Actual app preference",
        "mime_type": "text/plain",
        "metadata": {"kind": "decision"},
    }
    to_okf(component([row]), tmp_path / "okf")
    node = next((tmp_path / "okf").glob("*.md")).read_text()
    assert "synthetic" not in node
    assert recover_records(node) == [row]


@pytest.mark.parametrize("failure", ["source", "target", "integrity"])
def test_failure_gate_rejects_failed_proofs(failure):
    """Each independent source, target, or integrity failure stops the command."""
    report = {
        "mode": "live-cloud",
        "recall_passed": 6,
        "recall_total": 6,
        "lossless_payload_roundtrip": True,
    }
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
    """Complete equal-scope evidence permits a successful exit."""
    validate_checks(
        {
            "mode": "live-cloud",
            "recall_passed": 6,
            "recall_total": 6,
            "lossless_payload_roundtrip": True,
        },
        [{"passed": True}],
    )


def test_ranked_top3_is_informational_not_equal_scope_parity():
    """A recorded ranking limitation is distinct from equal-volume data loss."""
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


@pytest.mark.parametrize("inner", ['{"content":"not the source record"}', "bad JSON"])
def test_user_fences_do_not_become_adapter_records(tmp_path, inner):
    """Valid or malformed fences inside user text survive as text, not records."""
    row = {
        "content": f"User documentation\n```autogen-record\n{inner}\n```\nEnd.",
        "mime_type": "text/plain",
        "metadata": {},
    }
    to_okf(component([row]), tmp_path / "okf")
    source_node = next((tmp_path / "okf").glob("*.md")).read_text()
    mapped = map_okf(load_okf_bundle(tmp_path / "okf"))
    assert len(mapped) == 1
    assert recover_records(source_node) == [row]
    assert recover_records(mapped[0]["content"].rstrip("\n")) == [row]


@pytest.mark.parametrize(
    "payload",
    [
        "{broken JSON",
        "[]",
        "null",
        "{}",
        '{"mime_type":"text/plain","content":1}',
        '{"mime_type":"image/png","content":"data"}',
        '{"mime_type":"text/plain","content":"data","metadata":false}',
    ],
)
def test_malformed_adapter_payload_is_rejected(payload):
    """Malformed JSON and invalid record schemas fail explicitly at recovery."""
    digest = hashlib.sha256(payload.encode()).hexdigest()
    content = f"Source order: 0. SHA256: {digest}\n\n```autogen-record\n{payload}\n```"
    with pytest.raises(ValueError):
        recover_records(content)


@pytest.mark.parametrize("damage", ["missing_close", "extra_suffix", "changed_payload"])
def test_damaged_adapter_envelope_is_rejected(tmp_path, damage):
    """Truncation, appended content, and hash mismatches cannot pass integrity."""
    row = {"content": "original", "mime_type": "text/plain", "metadata": None}
    to_okf(component([row]), tmp_path / "okf")
    node = next((tmp_path / "okf").glob("*.md")).read_text()
    if damage == "missing_close":
        node = node.removesuffix("```\n")
    elif damage == "extra_suffix":
        node += "unrecognised trailing content"
    else:
        node = node.replace('"content":"original"', '"content":"changed"')
    with pytest.raises(ValueError):
        recover_records(node)


def test_unrelated_fence_without_adapter_envelope_is_ignored():
    """A matching language tag alone is not evidence of an adapter record."""
    assert recover_records('Notes\n```autogen-record\n{"content":"example"}\n```') == []


def test_saved_cloud_payloads_remain_compatible():
    """Existing exported and recalled data remain readable without another live run."""
    evidence = Path(__file__).parent / "evidence"
    source = json.loads((evidence / "source-component.json").read_text())
    expected = Counter(map(canonical, source["config"]["memory_contents"]))
    exported = load_okf_bundle(evidence / "exported-okf")["memories"]
    restored = [record for item in exported for record in recover_records(item["body"])]
    assert Counter(map(canonical, restored)) == expected
    for name in ("recall-after.json", "ranked-top3.json"):
        for query in json.loads((evidence / name).read_text()):
            for item in query["results"]:
                (record,) = recover_records(item["content"])
                assert canonical(record) in expected


@pytest.fixture
def local_showcase(monkeypatch):
    """Serve the real HTTP handler on loopback with the cloud pipeline replaced."""
    monkeypatch.setattr(showcase_server, "STATE", {"started": False, "log": ""})
    monkeypatch.setattr(showcase_server, "pipeline", lambda: None)
    server = ThreadingHTTPServer(("127.0.0.1", 0), showcase_server.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize(
    ("origin", "path", "status"),
    [
        ("http://127.0.0.1:8769", "/start", 202),
        ("http://localhost:8769", "/start", 202),
        ("https://example.com", "/start", 403),
        ("http://localhost:8769.evil.example", "/start", 403),
        ("http://localhost:8770", "/start", 403),
        (None, "/start", 403),
        ("http://localhost:8769", "/other", 403),
    ],
)
def test_start_origin_boundary_and_one_shot(local_showcase, origin, path, status):
    """Both documented origins work once; missing, foreign, and wrong-port origins fail."""
    headers = {} if origin is None else {"Origin": origin}
    with closing(HTTPConnection("127.0.0.1", local_showcase, timeout=5)) as connection:
        connection.request("POST", path, headers=headers)
        response = connection.getresponse()
        assert response.status == status
        response.read()
        assert showcase_server.STATE["started"] is (status == 202)
        if status == 202:
            connection.request("POST", path, headers=headers)
            response = connection.getresponse()
            assert response.status == 409
            response.read()
