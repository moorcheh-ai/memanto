"""Check archived sample provenance and resolve the original input pointers."""

import hashlib
import json
import re
from pathlib import Path

import pytest
from adapter import load_catalog, restore_bundle, unpack

from memanto.cli.migrate.okf_loader import load_okf_bundle

ROOT = Path(__file__).parent


@pytest.mark.parametrize(
    ("bundle", "manifest"),
    [
        ("sample-cloud-okf", "cloud_sample_provenance.json"),
        ("source-okf", "source_sample_provenance.json"),
    ],
)
def test_archived_sample_hashes_and_complete_public_snapshot(bundle, manifest):
    provenance = json.loads((ROOT / "evidence" / manifest).read_text())
    for row in provenance["files"]:
        content = (ROOT / bundle / row["path"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == row["sha256"]
    assert restore_bundle(ROOT / bundle) == load_catalog(ROOT / "source_public.json")


def test_cloud_source_pointers_resolve_to_matching_original_capsules():
    source = ROOT / "source-okf"
    memories = load_okf_bundle(ROOT / "sample-cloud-okf")["memories"]
    assert len(memories) == 67
    referenced = set()
    for row in memories:
        pointers = re.findall(r"^- OKF source: (.+)$", row["body"], re.MULTILINE)
        assert len(pointers) == 1
        relative = Path(pointers[0])
        assert not relative.is_absolute() and ".." not in relative.parts
        original = source / relative
        assert original.is_file()
        assert unpack(original.read_text()) == unpack(row["body"])
        referenced.add(relative)
    assert referenced == {p.relative_to(source) for p in source.glob("memories/*/*.md")}
