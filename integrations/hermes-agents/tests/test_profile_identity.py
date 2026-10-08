"""Read and create Hermes metadata within the documented byte limit."""

import json
import tracemalloc
from pathlib import Path

import pytest

from hermes_memanto._profile_identity import _read_metadata, _write_once
from hermes_memanto.provider import _resolve_compatible_profile_mapping


@pytest.mark.parametrize("chunk", [b"a" * 1024, "é".encode() * 512])
def test_oversized_metadata_has_bounded_memory(tmp_path: Path, chunk: bytes):
    """Reject a 2 MiB file without allocating memory proportional to its size."""
    metadata = tmp_path / ".memanto_identity.json"
    with metadata.open("wb") as handle:
        handle.write(b'{"identity":"')
        for _ in range(2048):
            handle.write(chunk)
        handle.write(b'"}')

    tracemalloc.start()
    try:
        with pytest.raises(RuntimeError, match="the metadata file is invalid"):
            _read_metadata(tmp_path)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert peak < 256 * 1024


def test_metadata_limit_counts_utf8_bytes(tmp_path: Path):
    """Accept an exact 4 KiB record, then refuse one extra multibyte character."""
    value = {
        "schema": 1,
        "identity": "équipe",
        "raw_agent_id": "hermes-équipe",
        "profile": tmp_path.name,
        "agent_namespace": "hermes-equipe",
    }
    payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
    metadata = tmp_path / ".memanto_identity.json"
    metadata.write_bytes(payload + b" " * (4096 - len(payload)))
    assert _read_metadata(tmp_path) == value

    with metadata.open("ab") as handle:
        handle.write("é".encode())
    with pytest.raises(RuntimeError, match="the metadata file is invalid") as error:
        _read_metadata(tmp_path)
    assert str(error.value.__cause__) == "metadata is too large"


@pytest.mark.parametrize("payload", [b'{"identity":"\xff"}', b"not json", b"[]"])
def test_invalid_metadata_stays_rejected(tmp_path: Path, payload: bytes):
    """Keep the existing UTF-8, JSON, and object validation boundaries."""
    (tmp_path / ".memanto_identity.json").write_bytes(payload)
    with pytest.raises(RuntimeError):
        _read_metadata(tmp_path)


@pytest.mark.parametrize("identity", ["a" * 2048, "é" * 512])
def test_profile_creation_refuses_unreadable_metadata(tmp_path: Path, identity: str):
    """Reject oversized records before accepting a new profile or writing metadata."""
    with pytest.raises(RuntimeError, match="metadata record exceeds the 4 KiB limit"):
        _resolve_compatible_profile_mapping(str(tmp_path), identity, "hermes-" + identity)
    assert not list(tmp_path.rglob(".memanto_identity.json"))


def test_metadata_writer_accepts_exact_reader_limit(tmp_path: Path):
    """A record at the writer's boundary can be read and is never overwritten."""
    value: dict[str, object] = {"identity": ""}
    overhead = len(json.dumps(value, sort_keys=True, separators=(",", ":"))) + 1
    value["identity"] = "a" * (4096 - overhead)

    assert _write_once(tmp_path, value)
    metadata = tmp_path / ".memanto_identity.json"
    original = metadata.read_bytes()
    assert len(original) == 4096
    assert _read_metadata(tmp_path) == value
    assert not _write_once(tmp_path, {"identity": "other"})
    assert metadata.read_bytes() == original
